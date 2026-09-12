# SPDX-License-Identifier: Apache-2.0
"""Loop konsolidasi — "tidur" (Bab 7).

Tidak pernah berjalan saat tulis. Dipanggil oleh cron (02:00 WIB), oleh
akumulasi >= 50 episode, atau jalur cepat (bobot >= 3) di akhir sesi.

Sintesis pelajaran memakai LLM lewat gate P/I/S bila ada penyedia yang
diizinkan untuk tier tertinggi kelompok; bila tidak ada, jatuh ke sintesis
heuristik (tidak ada data keluar mesin) dan ditandai `sintesis: heuristik`.
"""
from __future__ import annotations

import json
import re

from . import skema
from .gate import JALUR_KONSOLIDASI, Gate
from .obsidian import Vault
from .rem import periksa_abstraksi
from .simpan import Store
from .vektor import kosinus, centroid, tumpang_tindih

AMBANG_KELOMPOK = 0.55
AMBANG_COCOK_PELAJARAN = 0.50
AMBANG_COCOK_PROSEDUR = 0.55

_PROMPT_SINTESIS = """Kamu menyusun satu PELAJARAN dari beberapa kejadian yang serupa untuk sistem memori agent.
Aturan (P8): tulis pada tingkat abstraksi yang bisa dipakai di proyek lain — jangan sebut nama tool, orang,
atau proyek spesifik kecuali itu memang domainnya. `pemicu` harus berupa KONDISI yang bisa dikenali di kasus
lain, bukan deskripsi kejadian asal. `tindakan` harus konkret dan bisa dieksekusi agent.
Jawab HANYA JSON dengan kunci: pelajaran, pemicu, tindakan. Bahasa Indonesia, masing-masing ≤ 40 kata."""


def _potong_json(teks: str) -> dict:
    t = re.sub(r"```(?:json)?", "", teks).strip().strip("`")
    awal, akhir = t.find("{"), t.rfind("}")
    if awal == -1 or akhir == -1:
        raise ValueError("tidak ada JSON")
    return json.loads(t[awal:akhir + 1])


class Konsolidator:
    def __init__(self, store: Store, gate: Gate, penyedia: dict, vault: Vault | None, konfig: dict | None = None):
        self.store = store
        self.gate = gate
        self.penyedia = penyedia or {}
        self.vault = vault
        self.k = {"ambang_batch": 50, "hari_dingin": 30, **(konfig or {})}

    # ---- pengelompokan ------------------------------------------------------
    @staticmethod
    def _kelompokkan(episodes: list[skema.Episode]) -> list[list[skema.Episode]]:
        kelompok: list[list[skema.Episode]] = []
        for e in episodes:
            tempat = None
            for g in kelompok:
                a = g[0]
                if a.lingkup != e.lingkup or a.jenis_kejadian != e.jenis_kejadian:
                    continue
                c = centroid([x._vektor for x in g])
                if kosinus(c, e._vektor) >= AMBANG_KELOMPOK or tumpang_tindih(a.ringkas, e.ringkas) >= 0.5:
                    tempat = g
                    break
            (tempat if tempat is not None else kelompok).append(e) if tempat is not None else kelompok.append([e])
        return kelompok

    def _pelajaran_cocok(self, vek: list[float], teks: str) -> skema.Pelajaran | None:
        terbaik, nilai = None, 0.0
        for p in self.store.pelajaran_semua(("hipotesis", "usulan", "aturan", "dipersempit")):
            s = 0.6 * kosinus(vek, p._vektor) + 0.4 * tumpang_tindih(teks, f"{p.pelajaran}\n{p.pemicu}")
            if s > nilai:
                terbaik, nilai = p, s
        return terbaik if nilai >= AMBANG_COCOK_PELAJARAN else None

    # ---- sintesis -------------------------------------------------------------
    def _sintesis(self, kelompok: list[skema.Episode], tier: str) -> dict:
        utama = max(kelompok, key=lambda e: e.bobot)
        bahan = "\n".join(f"- [{e.jenis_kejadian}] {e.ringkas}" for e in kelompok[:12])
        # Tier S hanya lolos lewat jalur konsolidasi DAN hanya bila keempat rem K28 terpasang.
        pid = self.gate.pilih(tier, self.penyedia, jalur=JALUR_KONSOLIDASI)
        if pid and tier == "S" and not self.gate.rem.ada_anggaran(self.store, skema.hitung_token(_PROMPT_SINTESIS + bahan)):
            self.store.catat_metrik("rem_tier_s_anggaran_habis", 1, penyedia=pid)  # rem 3
            pid = None
        if pid:
            try:
                jawaban = self.penyedia[pid].tanya(_PROMPT_SINTESIS, f"Kejadian:\n{bahan}", maks_token=400)
                d = _potong_json(jawaban)
                if all(d.get(k) for k in ("pelajaran", "pemicu", "tindakan")):
                    hasil = {"pelajaran": d["pelajaran"].strip(), "pemicu": d["pemicu"].strip(),
                             "tindakan": d["tindakan"].strip(), "sintesis": f"llm:{pid}"}
                    if tier != "S":
                        return hasil
                    # Rem 3: pemakaian dicatat begitu model dipanggil — gagal P11 pun tetap memakan anggaran.
                    self.gate.rem.catat_pemakaian(self.store, skema.hitung_token(_PROMPT_SINTESIS + bahan + jawaban), pid)
                    # Rem 2 (P11): yang dijaga adalah KELUARAN, bukan masukan.
                    lolos, alasan = periksa_abstraksi("\n".join((hasil["pelajaran"], hasil["pemicu"], hasil["tindakan"])), bahan)
                    if lolos:
                        return hasil
                    self.store.catat_metrik("rem_tier_s_abstraksi_ditolak", 1, penyedia=pid, alasan=alasan[:200])
            except Exception as e:  # jatuh ke heuristik, catat
                self.store.catat_metrik("sintesis_llm_gagal", 1, penyedia=pid, galat=str(e)[:200])
        if tier == "S":
            # Bab 9 + P11: isi episode tier S TIDAK BOLEH disalin ke pelajaran — vault adalah repo git (K7),
            # jadi heuristik "salin ringkas" yang dipakai P/I akan membocorkannya keluar mesin.
            # Tanpa sintesis abstrak yang lolos, pelajaran tier S ditulis manusia (Bab 9).
            return {"pelajaran": "Episode tier S belum bisa disintesis secara abstrak; pelajarannya perlu ditulis manusia.",
                    "pemicu": "Sekelompok episode tier S menunggu penilaian manusia.",
                    "tindakan": "Buka episodenya lewat buka_bukti() lalu tulis pelajarannya sendiri.",
                    "sintesis": "heuristik"}
        return {"pelajaran": utama.ringkas.strip(),
                "pemicu": f"Situasi serupa dengan: {utama.ringkas[:160].strip()}",
                "tindakan": "Periksa asumsi yang sama sebelum mengulang tindakan serupa; cari jalur verifikasi kedua.",
                "sintesis": "heuristik"}

    @staticmethod
    def _konsisten(pelajaran: skema.Pelajaran, kelompok: list[skema.Episode]) -> bool:
        """Kegagalan/koreksi yang terjadi padahal aturan sudah aktif = kontra. Selain itu = bukti."""
        if pelajaran.status in ("aturan", "dipersempit") and any(e.jenis_kejadian in ("koreksi", "kegagalan") for e in kelompok):
            return False
        return True

    # ---- job utama ------------------------------------------------------------
    def jalankan(self, jalur: str = "batch") -> dict:
        bobot_min = 3 if jalur == "cepat" else 0
        # Tier S ikut HANYA bila keempat rem K28 terpasang; kalau tidak, dilewati seperti sebelumnya (Bab 9).
        tier_diproses = ("P", "I", "S") if self.gate.rem.terbuka() else ("P", "I")
        episodes = self.store.episode_aktif(tier_diproses, bobot_min)
        laporan = {"jalur": jalur, "episode": len(episodes), "kelompok": 0, "hipotesis_baru": 0,
                   "usulan_baru": 0, "bukti_ditambah": 0, "kontra_ditambah": 0, "dipersempit": 0,
                   "prosedur_draf": 0, "perluasan_lingkup": 0, "didinginkan": 0, "tier_tanpa_penyedia": []}
        if not episodes:
            return laporan
        for kelompok in self._kelompokkan(episodes):
            laporan["kelompok"] += 1
            vek = centroid([e._vektor for e in kelompok])
            teks = " ".join(e.ringkas for e in kelompok)
            tier = skema.tier_tertinggi([e.tier for e in kelompok])
            if tier != "P" and not self.gate.pilih(tier, self.penyedia) and tier not in laporan["tier_tanpa_penyedia"]:
                laporan["tier_tanpa_penyedia"].append(tier)

            # prosedur dari pola sukses berulang (7.6)
            if kelompok[0].jenis_kejadian == "sukses" and len(kelompok) >= 3 and all(e.langkah for e in kelompok):
                sudah = {b for pr in self.store.prosedur_semua() for b in pr.bukti}
                if any(e.id not in sudah for e in kelompok):
                    self._draf_prosedur(kelompok, tier)
                    laporan["prosedur_draf"] += 1

            p = self._pelajaran_cocok(vek, teks)
            if p is None:
                s = self._sintesis(kelompok, tier)
                p = skema.Pelajaran(id=skema.id_baru("pl"), pelajaran=s["pelajaran"], pemicu=s["pemicu"],
                                    tindakan=s["tindakan"], lingkup=kelompok[0].lingkup, status="hipotesis",
                                    keyakinan=0.4, bukti=[e.id for e in kelompok],
                                    instrumen_saat_dibuat=sorted({i for e in kelompok for i in e.instrumen}),
                                    tier_maks=tier, sintesis=s["sintesis"])
                laporan["hipotesis_baru"] += 1
            else:
                # R8 (spek 7.3b): episode tetap aktif setelah konsolidasi, jadi kelompok bisa memuat episode yang
                # sudah jadi bukti/kontra. Hanya episode BARU yang boleh mengubah pelajaran — tanpa ini setiap run
                # "mengonfirmasi" bukti yang sama (keyakinan menggelembung) atau menjadikan bukti lama kontra.
                kelompok = [e for e in kelompok if e.id not in p.bukti and e.id not in p.kontra]
                if not kelompok:
                    continue
                if self._konsisten(p, kelompok):
                    bukti_lama = [self.store.episode(b) for b in p.bukti]
                    sesi_lama = {b.sesi for b in bukti_lama if b}
                    baru = [e.id for e in kelompok]
                    p.bukti += baru
                    laporan["bukti_ditambah"] += len(baru)
                    p.terakhir_dikonfirmasi = skema.hari_ini()
                    p.tinjau_setelah = skema.tambah_hari(p.terakhir_dikonfirmasi,
                                                         min(skema.HARI_TINJAU_MAKS, skema.HARI_TINJAU_DEFAULT * (1 + len(p.bukti) // 3)))
                    p.keyakinan = min(0.95, p.keyakinan + 0.1)
                    p.tinjau_ulang = False
                    # 7.2 — bukti dari lingkup lain hanya mengusulkan perluasan, tidak melebarkan sendiri
                    if p.lingkup != "global" and any(e.lingkup != p.lingkup for e in kelompok):
                        if any(e.sesi not in sesi_lama or set(e.instrumen) != set(p.instrumen_saat_dibuat) for e in kelompok):
                            p.usulan_perluasan_lingkup = "global"
                            laporan["perluasan_lingkup"] += 1
                else:
                    baru = [e.id for e in kelompok]
                    p.kontra += baru
                    laporan["kontra_ditambah"] += len(baru)
                    if len(p.kontra) >= max(2, len(p.bukti)):
                        if p.status == "aturan":
                            self.store.ubah_status("pelajaran", p.id, "dipersempit", "mesin", "kontra >= bukti (7.3)")
                            p.status = "dipersempit"
                            laporan["dipersempit"] += 1
                        p.tinjau_ulang = True
                        p.catatan = f"kontra mendominasi ({len(p.kontra)} vs {len(p.bukti)}); domain perlu dipersempit manusia"

            # Pelajaran yang menerima bukti tier S ikut diatur rem K28 selamanya, tidak bisa turun lagi.
            p.tier_maks = skema.tier_tertinggi([p.tier_maks or "P", tier])

            # ambang hipotesis -> usulan (7.2)
            if p.status == "hipotesis" and p.tier_maks == "S":
                # K28 rem 4 — manusia penjaga akhir. Berapa pun bobot buktinya, pelajaran turunan
                # tier S tidak pernah naik status sendiri; ia menunggu penilaian manusia.
                p.tinjau_ulang = True
                p.catatan = "tier S: menunggu penilaian manusia (K28 rem 4); tidak naik status otomatis"
            elif p.status == "hipotesis":
                bobot = sum(self.store.episode(b).bobot for b in p.bukti if self.store.episode(b))
                if bobot >= skema.AMBANG_USULAN:
                    self.store.simpan_pelajaran(p)
                    self.store.ubah_status("pelajaran", p.id, "usulan", "mesin", f"bobot bukti {bobot} >= {skema.AMBANG_USULAN}")
                    p.status = "usulan"
                    laporan["usulan_baru"] += 1
                    if self.vault:
                        self.vault.tulis_usulan_pelajaran(p, [self.store.episode(b).ringkas for b in p.bukti if self.store.episode(b)])
            self.store.simpan_pelajaran(p)

        # R8: pendinginan tertunda — episode didinginkan hanya bila pelajaran induknya disetujui manusia
        # atau usianya melewati hari_dingin (konsolidasi sistem bertahap: jejak baru tetap bergantung
        # pada "hipokampus" berbulan-bulan sebelum menetap; H.M., ONI 13.2).
        laporan["didinginkan"] = self.dinginkan_tertunda()

        for nama, nilai in laporan.items():
            if isinstance(nilai, (int, float)):
                self.store.catat_metrik(f"konsolidasi_{nama}", nilai, jalur=jalur)
        return laporan

    def dinginkan_tertunda(self) -> int:
        """Episode aktif → didinginkan bila (a) ada di bukti/kontra pelajaran `aturan`/`dipersempit`, atau
        (b) usia > hari_dingin. Selain itu tetap aktif supaya bisa dikelompokkan ulang saat bukti baru datang."""
        hari = skema.hari_ini()
        induk_disetujui: set[str] = set()
        for p in self.store.pelajaran_semua(("aturan", "dipersempit")):
            induk_disetujui |= set(p.bukti) | set(p.kontra)
        n = 0
        for e in self.store.episode_semua("aktif"):
            if e.id in induk_disetujui:
                self.store.ubah_status("episode", e.id, "didinginkan", "mesin", "pelajaran induk disetujui (R8)")
                n += 1
                continue
            usia = self._usia_hari(e.waktu, hari)
            if usia is not None and usia > self.k["hari_dingin"]:
                self.store.ubah_status("episode", e.id, "didinginkan", "mesin", f"usia {usia} hari > hari_dingin (R8)")
                n += 1
        return n

    @staticmethod
    def _usia_hari(waktu_iso: str, hari: str) -> int | None:
        import datetime as dt
        try:
            return (dt.date.fromisoformat(hari) - dt.date.fromisoformat(waktu_iso[:10])).days
        except ValueError:
            return None

    def _draf_prosedur(self, kelompok: list[skema.Episode], tier: str):
        terpanjang = max(kelompok, key=lambda e: len(e.langkah))
        p = skema.Prosedur(id=skema.id_baru("pr"), prosedur=terpanjang.ringkas[:120],
                           tugas_pemicu=kelompok[0].ringkas[:160], langkah=list(terpanjang.langkah),
                           lingkup=kelompok[0].lingkup, status="draf", uji=terpanjang.langkah[-1],
                           bukti=[e.id for e in kelompok], tier_maks=tier,
                           eksekusi_total=len(kelompok), eksekusi_berhasil=len(kelompok))
        self.store.simpan_prosedur(p)
        if self.vault:
            self.vault.tulis_usulan_prosedur(p, [e.ringkas for e in kelompok])

    # ---- 7.4 instrumen baru ---------------------------------------------------
    def instrumen_baru(self, ins: skema.Instrumen) -> dict:
        self.store.simpan_instrumen(ins)
        batas = ins.dipasang_sejak or skema.hari_ini()
        ditandai = []
        for p in self.store.pelajaran_semua(("aturan", "dipersempit", "usulan", "hipotesis")):
            if ins.id in p.instrumen_saat_dibuat:
                continue
            waktu = [self.store.episode(b).waktu[:10] for b in p.bukti if self.store.episode(b)]
            semua_sebelum = bool(waktu) and all(w < batas for w in waktu)
            singgung = tumpang_tindih(ins.cakupan + " " + ins.nama, p.teks_embedding()) >= 0.08
            if semua_sebelum and singgung:
                p.tinjau_ulang = True
                p.catatan = f"instrumen baru {ins.id} dipasang setelah semua bukti (7.4)"
                self.store.simpan_pelajaran(p)
                ditandai.append(p.id)
        self.store.catat_metrik("instrumen_baru_tinjau_ulang", len(ditandai), instrumen=ins.id)
        return {"instrumen": ins.id, "tinjau_ulang": ditandai}

    # ---- 7.5 kedaluwarsa --------------------------------------------------------
    def kedaluwarsa(self) -> dict:
        hari = skema.hari_ini()
        ditandai = []
        for p in self.store.pelajaran_semua(("aturan", "dipersempit", "usulan", "hipotesis")):
            if p.tinjau_setelah and hari > p.tinjau_setelah and p.terakhir_dikonfirmasi < p.tinjau_setelah and not p.tinjau_ulang:
                p.tinjau_ulang = True
                p.catatan = f"lewat tinjau_setelah {p.tinjau_setelah} tanpa konfirmasi (7.5)"
                self.store.simpan_pelajaran(p)
                ditandai.append(p.id)
        for p in self.store.prosedur_semua(("aktif", "dipersempit", "teruji")):
            if p.tinjau_setelah and hari > p.tinjau_setelah and not p.tinjau_ulang:
                p.tinjau_ulang = True
                p.catatan = f"lewat tinjau_setelah {p.tinjau_setelah} (7.5)"
                self.store.simpan_prosedur(p)
                ditandai.append(p.id)
        self.store.catat_metrik("kedaluwarsa_tinjau_ulang", len(ditandai))
        return {"tinjau_ulang": ditandai}

    # ---- 6.5 hasil eksekusi prosedur -------------------------------------------
    def catat_eksekusi_prosedur(self, id_: str, berhasil: bool) -> dict:
        p = self.store.prosedur(id_)
        if p is None:
            raise KeyError(id_)
        p.eksekusi_total += 1
        if berhasil:
            p.eksekusi_berhasil += 1
            p.gagal_beruntun = 0
        else:
            p.gagal_beruntun += 1
            if p.gagal_beruntun >= 3 and p.status != "ditarik":
                self.store.simpan_prosedur(p)
                self.store.ubah_status("prosedur", p.id, "ditarik", "mesin", "uji gagal 3x berturut (6.5)")
                p.status = "ditarik"
            elif p.gagal_beruntun >= 2:
                p.tinjau_ulang = True
        self.store.simpan_prosedur(p)
        return {"id": p.id, "status": p.status, "tingkat_berhasil": round(p.tingkat_berhasil, 3), "gagal_beruntun": p.gagal_beruntun}
