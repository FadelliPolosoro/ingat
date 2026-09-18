# SPDX-License-Identifier: Apache-2.0
"""Konsolidasi berpandu pertanyaan (v0.5) — mesin BERTANYA, manusia MENYIMPULKAN.

Empat jenis pertanyaan, semuanya dibangun dari kolom yang sudah ada (tanpa LLM):

  generalisasi  pelajaran hipotesis/usulan yang belum ditinjau manusia
                → "adakah satu pemicu yang mencakup semua bukti ini? tulis pelajarannya"
  perluasan     pelajaran dengan `usulan_perluasan_lingkup` terisi
                → "bukti dari lingkup lain; jadikan global?"
  konflik       pelajaran aktif dengan `kontra`
                → "episode ini bertentangan; persempit domain, tarik, atau tetap?"
  kedaluwarsa   `tinjau_setelah` lewat atau `tinjau_ulang`
                → "masih berlaku?"

Alur: `susun()` memilih pertanyaan paling bernilai (active learning: manusia = oracle),
`tulis()` menaruh berkas `pelajaran/_usulan/tanya-<tanggal>.md`, manusia mengisi blok ```jawab```,
`jawab()` menerapkan jawaban KE BERKAS VAULT (bukan langsung ke store — P5: vault sumber kebenaran),
lalu `Vault.sinkron()` yang menegakkan state machine. Jawaban `lewati` / `tidak-tahu` sah;
`premis-salah` = pengelompokan mesin keliru, dicatat sebagai sinyal.

Yang turun dari 100 ke 10 adalah yang disuntik ke konteks, bukan yang disimpan (P1).
"""
from __future__ import annotations

import glob
import json
import os
import re
import shutil
from dataclasses import dataclass, field

import datetime as _dt

from . import frontmatter, skema
from .vault import Vault
from .simpan import Store


def _hari_antara(a: str | None, b: str | None) -> int | None:
    try:
        return (_dt.date.fromisoformat(str(b)[:10]) - _dt.date.fromisoformat(str(a)[:10])).days
    except (TypeError, ValueError):
        return None


def interval_tinjau_berikut(meta: dict) -> int:
    """Jadwal tinjau yang melebar setiap konfirmasi berhasil (kurva lupa Ebbinghaus + distributed practice):
    interval berikut = 2 × interval sebelumnya, dibatasi [HARI_TINJAU_DEFAULT, HARI_TINJAU_MAKS]."""
    sebelumnya = _hari_antara(meta.get("terakhir_dikonfirmasi"), meta.get("tinjau_setelah"))
    if not sebelumnya or sebelumnya <= 0:
        return skema.HARI_TINJAU_DEFAULT
    return min(skema.HARI_TINJAU_MAKS, max(skema.HARI_TINJAU_DEFAULT, 2 * sebelumnya))

JENIS = ("generalisasi", "perluasan", "konflik", "kedaluwarsa")

KEPUTUSAN = {
    "generalisasi": ("buat", "setuju-draf", "tolak", "lewati", "tidak-tahu", "premis-salah"),
    "perluasan": ("global", "tetap", "lingkup", "lewati", "tidak-tahu"),
    "konflik": ("persempit", "tarik", "tetap", "lewati", "tidak-tahu"),
    "kedaluwarsa": ("konfirmasi", "persempit", "tarik", "lewati", "tidak-tahu"),
}
_DITUNDA = ("lewati", "tidak-tahu")
_PENANDA = re.compile(r"<!--\s*tanya\s+nomor=(\d+)\s+jenis=(\w+)\s+id=([^\s]+)\s+kunci=([^\s]+)\s*-->")
_BLOK_JAWAB = re.compile(r"```jawab\s*\n(.*?)```", re.S)


@dataclass
class Pertanyaan:
    nomor: int
    jenis: str
    id: str
    lingkup: str
    prioritas: int
    kunci: str
    judul: str
    bukti: list[str] = field(default_factory=list)
    konteks: list[str] = field(default_factory=list)   # FAKTA, ditampilkan sebelum pertanyaan
    tanya: str = ""
    rekomendasi: str = ""                              # SARAN, ditampilkan SETELAH blok jawab (anti-sugesti)
    saran: list[str] = field(default_factory=list)     # draf mesin dll., juga setelah blok jawab
    jawab: dict = field(default_factory=dict)  # template blok jawab — tidak pernah diisi draf mesin


class Penanya:
    def __init__(self, store: Store, vault: Vault, konfig: dict | None = None):
        self.store = store
        self.vault = vault
        self.k = {"maks_pertanyaan": 7, "hari_tunggu": 30, "maks_diulang": 2, **(konfig or {})}
        os.makedirs(os.path.join(vault.path, "pelajaran", "_usulan", "selesai"), exist_ok=True)

    # ---- riwayat (metrik) -----------------------------------------------------
    def _riwayat(self, nama: str) -> list[dict]:
        baris = self.store.db.execute("SELECT waktu, konteks FROM metrik WHERE nama=? ORDER BY waktu", (nama,)).fetchall()
        hasil = []
        for b in baris:
            try:
                d = json.loads(b["konteks"] or "{}")
            except Exception:
                d = {}
            d["_waktu"] = b["waktu"]
            hasil.append(d)
        return hasil

    def _kunci_terbuka(self) -> set[tuple[str, str, str]]:
        """(jenis, id, kunci) di berkas tanya yang masih `status: menunggu`."""
        terbuka = set()
        for path in glob.glob(os.path.join(self.vault.path, "pelajaran", "_usulan", "tanya-*.md")):
            with open(path, encoding="utf-8") as f:
                teks = f.read()
            meta, _ = frontmatter.muat(teks)
            if meta.get("status") != "menunggu":
                continue
            for m in _PENANDA.finditer(teks):
                terbuka.add((m.group(2), m.group(3), m.group(4)))
        return terbuka

    # ---- pembangun pertanyaan -------------------------------------------------
    def _ringkas_bukti(self, ids: list[str], maks: int = 8) -> list[str]:
        baris = []
        for i in ids[:maks]:
            e = self.store.episode(i)
            if e:
                baris.append(f"`{e.id}` {e.jenis_kejadian} {e.waktu[:10]} — {e.ringkas[:160]}")
            else:
                baris.append(f"`{i}` (episode tidak ditemukan)")
        if len(ids) > maks:
            baris.append(f"… dan {len(ids) - maks} episode lain")
        return baris

    def _bobot_bukti(self, ids: list[str]) -> int:
        return sum(self.store.episode(i).bobot for i in ids if self.store.episode(i))

    def _generalisasi(self, p: skema.Pelajaran) -> Pertanyaan:
        bobot = self._bobot_bukti(p.bukti)
        return Pertanyaan(
            nomor=0, jenis="generalisasi", id=p.id, lingkup=p.lingkup, prioritas=10 * bobot + len(p.bukti),
            kunci="gen:" + ",".join(sorted(p.bukti)),
            judul=f"Kelompok {len(p.bukti)} episode belum punya pelajaran yang disetujui",
            bukti=self._ringkas_bukti(p.bukti),
            konteks=[f"Status: {p.status} · keyakinan {p.keyakinan:.2f} · tier_maks {p.tier_maks}"],
            tanya="Apakah ada SATU pemicu yang mencakup semua bukti di atas? Kalau ya, tulis pelajaran, pemicu, dan "
                  "tindakannya DENGAN KATA-KATAMU SENDIRI, pada tingkat yang bisa dipakai di proyek lain "
                  "(P8: sebut kondisinya, bukan nama tool/proyek). Jawab dulu, baru baca draf mesin di bawah.",
            rekomendasi="Kalau bukti-buktinya sebenarnya bukan satu hal, jawab `premis-salah`. `setuju-draf` boleh, "
                        "tetapi pelajaran yang kamu tulis sendiri diberi keyakinan lebih tinggi (0.8 vs 0.7) — "
                        "pemrosesan yang lebih dalam diingat lebih baik.",
            saran=[f"Draf mesin ({p.sintesis}) — dibaca SETELAH menjawab sendiri, supaya tidak mengarahkan: "
                   f"**pelajaran**: {p.pelajaran} · **pemicu**: {p.pemicu} · **tindakan**: {p.tindakan}"],
            jawab={"keputusan": "", "pelajaran": "", "pemicu": "", "tindakan": "", "lingkup": p.lingkup, "alasan": ""},
        )

    def _perluasan(self, p: skema.Pelajaran) -> Pertanyaan:
        usulan = p.usulan_perluasan_lingkup
        usulan_teks = ", ".join(usulan) if isinstance(usulan, list) else str(usulan)
        lingkup_bukti = sorted({self.store.episode(b).lingkup for b in p.bukti if self.store.episode(b)})
        return Pertanyaan(
            nomor=0, jenis="perluasan", id=p.id, lingkup=p.lingkup, prioritas=5 * len(p.bukti),
            kunci=f"perluasan:{usulan_teks}:{len(p.bukti)}",
            judul=f"Bukti datang dari lingkup lain — perluas ke {usulan_teks}?",
            bukti=self._ringkas_bukti(p.bukti),
            konteks=[f"**pelajaran**: {p.pelajaran}", f"Lingkup sekarang: `{p.lingkup}` · lingkup bukti: {', '.join(f'`{l}`' for l in lingkup_bukti)}"],
            tanya=f"Pelajaran ini terbukti di lebih dari satu lingkup. Jadikan `{usulan_teks}`, tetap di `{p.lingkup}`, "
                  "atau lingkup lain?",
            rekomendasi="Perluas hanya bila buktinya independen (sesi dan instrumen berbeda) — 7.2. Kalau ragu, `tetap`.",
            jawab={"keputusan": "", "lingkup": "", "alasan": ""},
        )

    def _konflik(self, p: skema.Pelajaran) -> Pertanyaan:
        return Pertanyaan(
            nomor=0, jenis="konflik", id=p.id, lingkup=p.lingkup, prioritas=20 * len(p.kontra) + self._bobot_bukti(p.kontra),
            kunci="konflik:" + ",".join(sorted(p.kontra)),
            judul=f"{len(p.kontra)} episode bertentangan dengan aturan ini",
            bukti=[f"BUKTI  {b}" for b in self._ringkas_bukti(p.bukti, 4)] + [f"KONTRA {k}" for k in self._ringkas_bukti(p.kontra, 6)],
            konteks=[f"**pelajaran**: {p.pelajaran}", f"**pemicu**: {p.pemicu}", f"**tindakan**: {p.tindakan}",
                     f"Status: {p.status} · berlaku_untuk: {json.dumps(p.berlaku_untuk, ensure_ascii=False)}"],
            tanya="Mana yang benar — aturannya, atau episode kontranya? Atau aturan ini hanya berlaku pada kondisi tertentu?",
            rekomendasi="`persempit` bila kontranya punya kondisi yang bisa dinamai (isi `berlaku_untuk` atau tulis ulang `pemicu`); "
                        "`tarik` bila aturannya memang keliru; `tetap` bila kontranya salah label.",
            jawab={"keputusan": "", "pemicu": "", "berlaku_untuk": {}, "alasan": ""},
        )

    def _kedaluwarsa(self, p: skema.Pelajaran, hari: str) -> Pertanyaan:
        sebab = "tinjau_ulang (instrumen/lingkungan berubah)" if p.tinjau_ulang else f"tinjau_setelah {p.tinjau_setelah} lewat"
        return Pertanyaan(
            nomor=0, jenis="kedaluwarsa", id=p.id, lingkup=p.lingkup, prioritas=3 + (5 if p.tinjau_ulang else 0),
            kunci=f"kedaluwarsa:{p.tinjau_setelah}:{p.terakhir_dikonfirmasi}:{int(p.tinjau_ulang)}",
            judul=f"Belum dikonfirmasi sejak {p.terakhir_dikonfirmasi} — {sebab}",
            bukti=self._ringkas_bukti(p.bukti, 4),
            konteks=[f"**pelajaran**: {p.pelajaran}", f"**pemicu**: {p.pemicu}",
                     f"berlaku_untuk: {json.dumps(p.berlaku_untuk, ensure_ascii=False)} · dibuat {p.dibuat}"],
            tanya="Masih berlaku apa adanya?",
            rekomendasi="`konfirmasi` bila masih dipakai dan benar; `persempit` bila hanya untuk versi/lingkungan tertentu; "
                        "`tarik` bila sudah tidak relevan.",
            jawab={"keputusan": "", "berlaku_untuk": {}, "alasan": ""},
        )

    # ---- susun ------------------------------------------------------------------
    def susun(self, hari: str | None = None) -> list[Pertanyaan]:
        hari = hari or skema.hari_ini()
        kandidat: list[Pertanyaan] = []
        for p in self.store.pelajaran_semua(("hipotesis", "usulan")):
            if not p.ditinjau_manusia:
                kandidat.append(self._generalisasi(p))
        for p in self.store.pelajaran_semua(("aturan", "dipersempit")):
            if p.kontra:
                kandidat.append(self._konflik(p))
            elif p.usulan_perluasan_lingkup:
                kandidat.append(self._perluasan(p))
            elif p.tinjau_ulang or (p.tinjau_setelah and p.tinjau_setelah < hari):
                kandidat.append(self._kedaluwarsa(p, hari))

        terbuka = self._kunci_terbuka()
        dijawab = self._riwayat("tanya_dijawab")
        hasil: list[Pertanyaan] = []
        for q in kandidat:
            k3 = (q.jenis, q.id, q.kunci)
            if k3 in terbuka:
                continue  # sedang menunggu jawaban
            riwayat = [r for r in dijawab if (r.get("jenis"), r.get("id"), r.get("kunci")) == k3]
            if any(r.get("keputusan") not in _DITUNDA for r in riwayat):
                continue  # sudah diputuskan untuk keadaan yang sama; tanya lagi hanya bila keadaan berubah (kunci berubah)
            if riwayat:
                terakhir = max(r["_waktu"][:10] for r in riwayat)
                if skema.tambah_hari(terakhir, self.k["hari_tunggu"]) > hari:
                    continue  # ditunda; belum waktunya ditanya ulang
                if len(riwayat) >= self.k["maks_diulang"]:
                    q.prioritas -= 100  # sudah sering dilewati: turun ke ekor, tidak menumpuk
            hasil.append(q)
        hasil.sort(key=lambda q: (-q.prioritas, q.jenis, q.id))
        hasil = hasil[: self.k["maks_pertanyaan"]]
        for n, q in enumerate(hasil, 1):
            q.nomor = n
        return hasil

    # ---- tulis ------------------------------------------------------------------
    def tulis(self, daftar: list[Pertanyaan], hari: str | None = None) -> str | None:
        if not daftar:
            return None
        hari = hari or skema.hari_ini()
        path = os.path.join(self.vault.path, "pelajaran", "_usulan", f"tanya-{hari}.md")
        n = 1
        while os.path.exists(path):
            n += 1
            path = os.path.join(self.vault.path, "pelajaran", "_usulan", f"tanya-{hari}-{n}.md")
        meta = {"id": os.path.basename(path)[:-3], "jenis": "tanya", "dibuat": hari, "status": "menunggu", "jumlah": len(daftar)}
        badan = [f"# Pertanyaan konsolidasi — {hari}", "",
                 "Isi blok `jawab` di tiap pertanyaan. `lewati` dan `tidak-tahu` adalah jawaban sah. Baris yang diawali `#` diabaikan.",
                 "Setelah selesai: `python3 -m ingat jawab --berkas <path berkas ini>` — jawaban diterapkan ke vault, lalu disinkronkan.",
                 ""]
        for q in daftar:
            badan += [f"<!-- tanya nomor={q.nomor} jenis={q.jenis} id={q.id} kunci={q.kunci} -->",
                      f"## T{q.nomor} · {q.jenis} · `{q.id}` · `{q.lingkup}` · prioritas {q.prioritas}", "",
                      f"**{q.judul}**", ""]
            if q.bukti:
                badan += ["Bukti:"] + [f"- {b}" for b in q.bukti] + [""]
            badan += [f"- {c}" for c in q.konteks] + ["", f"❓ {q.tanya}", "",
                      "```jawab", f"# keputusan: {' | '.join(KEPUTUSAN[q.jenis])}"]
            badan += [f"{k}: {frontmatter._dump_skalar(v) if not isinstance(v, dict) else '{}'}" for k, v in q.jawab.items()]
            badan += ["```", ""]
            # Saran dan draf mesin SETELAH blok jawab: pertanyaan yang mengarahkan menghasilkan ingatan palsu
            # (efek misinformasi, Loftus & Palmer 1974). Tampilkan bukti dulu, pendapat mesin belakangan.
            badan += [f"➡️ {q.rekomendasi}", ""]
            badan += [f"- {c}" for c in q.saran] + ([""] if q.saran else [])
        with open(path, "w", encoding="utf-8") as f:
            f.write(frontmatter.dump(meta, "\n".join(badan)))
        for q in daftar:
            self.store.catat_metrik("tanya_diajukan", 1, jenis=q.jenis, id=q.id, kunci=q.kunci, berkas=os.path.basename(path))
        return path

    # ---- jawab ------------------------------------------------------------------
    def _berkas_pelajaran(self, id_: str) -> tuple[str, dict, str] | None:
        for folder in ("pelajaran", "pelajaran/_usulan"):
            path = os.path.join(self.vault.path, folder, f"{id_}.md")
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    meta, badan = frontmatter.muat(f.read())
                return path, meta, badan
        return None

    def _meta_pelajaran(self, id_: str) -> tuple[dict, str, str | None]:
        """(meta, badan, path_lama). Dari berkas vault bila ada, kalau tidak dari store."""
        b = self._berkas_pelajaran(id_)
        if b:
            return dict(b[1]), b[2], b[0]
        p = self.store.pelajaran(id_)
        if p is None:
            raise KeyError(f"pelajaran {id_} tidak ada di vault maupun store")
        meta = {"id": p.id, "jenis": "pelajaran", **{k: v for k, v in skema.ke_dict(p).items() if k != "id"}}
        return meta, "", None

    def _tulis_pelajaran(self, folder: str, meta: dict, badan: str, path_lama: str | None) -> str:
        path = os.path.join(self.vault.path, folder, f"{meta['id']}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(frontmatter.dump(meta, badan))
        if path_lama and os.path.abspath(path_lama) != os.path.abspath(path):
            os.remove(path_lama)
        return path

    def _terapkan(self, jenis: str, id_: str, d: dict, hari: str, laporan: dict) -> str:
        kep = str(d.get("keputusan") or "").strip().lower()
        if kep == "":
            return "kosong"
        if kep not in KEPUTUSAN[jenis]:
            laporan["galat"].append(f"{id_}: keputusan '{kep}' tidak dikenal untuk {jenis}")
            return "galat"
        if kep in _DITUNDA:
            return kep
        alasan = str(d.get("alasan") or "").strip()
        meta, badan, path_lama = self._meta_pelajaran(id_)
        catatan_tambah = f"[{hari} tanya/{jenis}/{kep}] {alasan}".strip()

        if jenis == "generalisasi":
            if kep == "buat":
                if not all(str(d.get(k) or "").strip() for k in ("pelajaran", "pemicu", "tindakan")):
                    laporan["galat"].append(f"{id_}: 'buat' butuh pelajaran, pemicu, tindakan — dianggap lewati")
                    return "lewati"
                meta.update(pelajaran=str(d["pelajaran"]).strip(), pemicu=str(d["pemicu"]).strip(), tindakan=str(d["tindakan"]).strip())
                lingkup = str(d.get("lingkup") or "").strip()
                if lingkup and skema.lingkup_valid(lingkup):
                    meta["lingkup"] = lingkup
                meta.update(status="aturan", ditinjau_manusia=True, sintesis="manusia", keyakinan=max(float(meta.get("keyakinan") or 0), 0.8),
                            terakhir_dikonfirmasi=hari, tinjau_setelah=skema.tambah_hari(hari, skema.HARI_TINJAU_DEFAULT), tinjau_ulang=False)
                meta["catatan"] = (str(meta.get("catatan") or "") + "\n" + catatan_tambah).strip()
                self._tulis_pelajaran("pelajaran", meta, badan or "Ditulis manusia lewat tanya (generalisasi).", path_lama)
            elif kep == "setuju-draf":
                meta.update(status="aturan", ditinjau_manusia=True, terakhir_dikonfirmasi=hari, tinjau_ulang=False)
                self._tulis_pelajaran("pelajaran", meta, badan, path_lama)
            elif kep in ("tolak", "premis-salah"):
                meta["veto_manusia"] = f"{hari} — {alasan or ('pengelompokan salah' if kep == 'premis-salah' else 'ditolak lewat tanya')}"
                self._tulis_pelajaran("pelajaran/_usulan", meta, badan, path_lama)
                if kep == "premis-salah":
                    self.store.catat_metrik("pengelompokan_salah", 1, pelajaran=id_, bukti=list(meta.get("bukti") or []))
            return kep

        if jenis == "perluasan":
            if kep == "global":
                meta["lingkup"] = "global"
            elif kep == "lingkup":
                lingkup = str(d.get("lingkup") or "").strip()
                if not skema.lingkup_valid(lingkup):
                    laporan["galat"].append(f"{id_}: lingkup '{lingkup}' tidak valid — dianggap tetap")
                else:
                    meta["lingkup"] = lingkup
            meta["usulan_perluasan_lingkup"] = None
            meta["catatan"] = (str(meta.get("catatan") or "") + "\n" + catatan_tambah).strip()
            self._tulis_pelajaran("pelajaran", meta, badan, path_lama)
            return kep

        # konflik & kedaluwarsa berbagi tiga keputusan: persempit / tarik / (tetap|konfirmasi)
        if kep == "persempit":
            bu = d.get("berlaku_untuk")
            if isinstance(bu, dict) and bu:
                meta["berlaku_untuk"] = {**(meta.get("berlaku_untuk") or {}), **{str(a): str(b) for a, b in bu.items()}}
            if str(d.get("pemicu") or "").strip():
                meta["pemicu"] = str(d["pemicu"]).strip()
            meta.update(status="dipersempit", tinjau_ulang=False, terakhir_dikonfirmasi=hari,
                        tinjau_setelah=skema.tambah_hari(hari, skema.HARI_TINJAU_DEFAULT), ditinjau_manusia=True)
        elif kep == "tarik":
            meta["veto_manusia"] = f"{hari} — {alasan or f'ditarik lewat tanya/{jenis}'}"
        else:  # tetap (konflik) / konfirmasi (kedaluwarsa): interval melebar tiap konfirmasi (spaced repetition)
            interval = interval_tinjau_berikut(meta)
            meta.update(tinjau_ulang=False, terakhir_dikonfirmasi=hari,
                        tinjau_setelah=skema.tambah_hari(hari, interval), ditinjau_manusia=True)
        meta["catatan"] = (str(meta.get("catatan") or "") + "\n" + catatan_tambah).strip()
        self._tulis_pelajaran("pelajaran", meta, badan, path_lama)
        return kep

    def jawab(self, path: str, hari: str | None = None) -> dict:
        hari = hari or skema.hari_ini()
        with open(path, encoding="utf-8") as f:
            teks = f.read()
        meta, badan = frontmatter.muat(teks)
        if meta.get("jenis") != "tanya":
            raise ValueError(f"{path} bukan berkas tanya")
        laporan = {"berkas": os.path.basename(path), "dijawab": 0, "kosong": 0, "ditunda": 0, "galat": [], "keputusan": {}}
        penanda = list(_PENANDA.finditer(badan))
        for i, m in enumerate(penanda):
            akhir = penanda[i + 1].start() if i + 1 < len(penanda) else len(badan)
            bagian = badan[m.end():akhir]
            nomor, jenis, id_, kunci = int(m.group(1)), m.group(2), m.group(3), m.group(4)
            blok = _BLOK_JAWAB.search(bagian)
            d = frontmatter.muat("---\n" + (blok.group(1) if blok else "") + "\n---\n")[0]
            try:
                hasil = self._terapkan(jenis, id_, d, hari, laporan)
            except Exception as e:  # satu jawaban rusak tidak menghentikan yang lain
                laporan["galat"].append(f"T{nomor} {id_}: {e}")
                hasil = "galat"
            laporan["keputusan"][f"T{nomor}"] = hasil
            if hasil == "kosong":
                laporan["kosong"] += 1
            elif hasil in _DITUNDA:
                laporan["ditunda"] += 1
                self.store.catat_metrik("tanya_dijawab", 1, jenis=jenis, id=id_, kunci=kunci, keputusan=hasil)
            elif hasil != "galat":
                laporan["dijawab"] += 1
                self.store.catat_metrik("tanya_dijawab", 1, jenis=jenis, id=id_, kunci=kunci, keputusan=hasil)
        laporan["sinkron"] = self.vault.sinkron(self.store)
        # arsipkan berkas: status selesai + laporan, pindah ke _usulan/selesai/
        meta["status"] = "selesai" if laporan["kosong"] == 0 else "sebagian"
        meta["dijawab_pada"] = hari
        ringkas = [f"- T{k}: {v}" for k, v in laporan["keputusan"].items()]
        badan_baru = badan.rstrip() + "\n\n## Laporan penerapan\n\n" + "\n".join(ringkas)
        if laporan["galat"]:
            badan_baru += "\n\nGalat:\n" + "\n".join(f"- {g}" for g in laporan["galat"])
        tujuan = os.path.join(self.vault.path, "pelajaran", "_usulan", "selesai", os.path.basename(path))
        with open(tujuan, "w", encoding="utf-8") as f:
            f.write(frontmatter.dump(meta, badan_baru))
        if os.path.abspath(tujuan) != os.path.abspath(path):
            os.remove(path)
        laporan["diarsipkan_ke"] = tujuan
        return laporan
