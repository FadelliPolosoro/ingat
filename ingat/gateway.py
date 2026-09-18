# SPDX-License-Identifier: Apache-2.0
"""Satu pintu retrieval (Bab 8). Tidak ada jalur baca memori lain.

ingat()        -> L-tarik: item berperingkat + pointer + asumsi + bendera + peringatan
muat_startup() -> L-peta + L-aturan dengan anggaran token
buka_bukti()   -> L-bukti: isi verbatim satu episode per panggilan
"""
from __future__ import annotations

import datetime as _dt
import math as _math

from . import skema
from .simpan import Store
from .vektor import skor_hibrida, mmr, kosinus

PERINGKAT = {
    "norma_otoritatif": 1, "norma_konsolidasi": 2, "kurasi_manusia": 3,
    "mesin_aktif": 4, "dipersempit": 5, "belum_ditinjau": 6, "episode": 7,
}
SKOR_MIN = 0.18
SKOR_PERINGATAN = 0.30


def _bobot_kebaruan(waktu_iso: str | None, separuh_hari: float = 90.0) -> float:
    """Faktor peluruhan eksponensial 0..1 berdasarkan umur item.

    separuh_hari=90 berarti item berumur 90 hari mendapat bobot 0.5.
    Item tanpa waktu mendapat 0.5 (netral). Status/peringkat tetap dominan —
    ini hanya tie-breaker halus supaya item lebih baru menang saat skor mirip.
    """
    if not waktu_iso:
        return 0.5
    try:
        t = _dt.datetime.fromisoformat(waktu_iso)
        if t.tzinfo is None:
            t = t.replace(tzinfo=_dt.timezone.utc)
        hari = max(0.0, (_dt.datetime.now(_dt.timezone.utc) - t).total_seconds() / 86400)
        return _math.pow(0.5, hari / separuh_hari)
    except Exception:
        return 0.5


def _cocok_lingkungan(berlaku_untuk: dict, lingkungan: dict | None) -> bool:
    """True bila tidak ada konflik versi. Kunci yang tidak disebut sesi dianggap cocok."""
    if not berlaku_untuk or not lingkungan:
        return True
    for k, v in berlaku_untuk.items():
        if k in lingkungan and str(lingkungan[k]).split(".")[0] != str(v).split(".")[0]:
            return False
    return True


class Gateway:
    def __init__(self, store: Store, konfig: dict | None = None):
        self.store = store
        self.k = {"anggaran_tarik": 600, "maks_item": 5, "anggaran_peta": 300, "anggaran_aturan": 1500,
                  "rasio_maks": 0.15, **(konfig or {})}

    # ---- render ------------------------------------------------------------
    @staticmethod
    def render(jenis: str, obj, bendera: list[str]) -> str:
        b = f" ⚑{','.join(bendera)}" if bendera else ""
        if jenis == "pelajaran":
            return (f"[pelajaran {obj.id} · {obj.status} · keyakinan {obj.keyakinan:.2f} · lingkup {obj.lingkup}{b}] "
                    f"{obj.pelajaran} | Pemicu: {obj.pemicu} | Tindakan: {obj.tindakan}")
        if jenis == "prosedur":
            langkah = " ".join(f"{i+1}) {l}" for i, l in enumerate(obj.langkah))
            return (f"[prosedur {obj.id} · {obj.status} · lingkup {obj.lingkup}{b}] {obj.prosedur} | "
                    f"Tugas: {obj.tugas_pemicu} | Langkah: {langkah}" + (f" | Uji: {obj.uji}" if obj.uji else ""))
        if jenis == "norma":
            jenis_n = "TAMPILAN KONSOLIDASI" if not obj.otoritatif else obj.status
            masa = f"{obj.berlaku_sejak or '?'}–{obj.berlaku_sampai or '…'}" if obj.otoritatif else f"untuk {obj.berlaku_untuk_tanggal}"
            teks = f"[norma {obj.id} · {jenis_n}{b}] {obj.norma} — {obj.judul} | berlaku {masa}"
            if obj.peralihan:
                teks += f" | Peralihan: {obj.peralihan[:400]}"
            if not obj.otoritatif:
                teks += f" | Disusun dari: {', '.join(obj.disusun_dari)}"
            return teks
        return str(obj)

    # ---- kandidat per jenis -----------------------------------------------
    def _kandidat_norma(self, qvec, query, tanggal) -> list[dict]:
        hasil = []
        for n in self.store.norma_semua():
            if not n.berlaku_pada(tanggal):
                continue
            skor = skor_hibrida(qvec, query, n._vektor, n.teks_embedding())
            if n.norma.lower() in query.lower() or n.id in query:
                skor = max(skor, 0.95)
            if skor < SKOR_MIN:
                continue
            bendera = []
            if not n.otoritatif:
                bendera.append("tampilan_konsolidasi")
                peringkat = PERINGKAT["norma_konsolidasi"]
            else:
                peringkat = PERINGKAT["norma_otoritatif"]
                if n.status == "dicabut":
                    bendera.append("versi_lama_masih_mengikat")
            hasil.append({"jenis": "norma", "obj": n, "skor": skor, "peringkat": peringkat,
                          "bendera": bendera, "vektor": n._vektor})
        return hasil

    def _kandidat_pelajaran(self, qvec, query, lingkup, lingkungan, peringatan: list) -> list[dict]:
        hasil = []
        for p in self.store.pelajaran_semua():
            if not skema.lingkup_memuat(p.lingkup, lingkup):
                continue
            # R12: isyarat `pemicu` dicocokkan terpisah dari isi — situasi sesi cocok dengan kondisi, bukan kalimat
            skor = max(skor_hibrida(qvec, query, p._vektor, p.teks_embedding()),
                       skor_hibrida(qvec, query, p._vektor_pemicu, p.pemicu) if p._vektor_pemicu else 0.0)
            if p.status == "ditarik":
                if skor >= SKOR_PERINGATAN:
                    peringatan.append({"jenis": "pelajaran", "id": p.id,
                                       "teks": f"pernah diyakini: {p.pelajaran} — DITARIK ({p.veto_manusia or 'terbukti salah'}); jangan dipakai."})
                continue
            if skor < SKOR_MIN:
                continue
            bendera = []
            keyakinan = p.keyakinan
            if p.tinjau_ulang:
                keyakinan = max(0.0, keyakinan - 0.2)
                bendera.append("tinjau_ulang")
            if not _cocok_lingkungan(p.berlaku_untuk, lingkungan):
                bendera.append("versi_berbeda")
            if p.status in ("usulan", "hipotesis"):
                bendera.append("belum_ditinjau")
                peringkat = PERINGKAT["belum_ditinjau"]
                keyakinan = min(keyakinan, 0.6)
            elif p.status == "dipersempit":
                peringkat = PERINGKAT["dipersempit"]
            elif p.ditinjau_manusia:
                peringkat = PERINGKAT["kurasi_manusia"]
            else:
                peringkat = PERINGKAT["mesin_aktif"]
            waktu_item = getattr(p, "terakhir_dikonfirmasi", None) or getattr(p, "dibuat", None)
            kebaruan = _bobot_kebaruan(waktu_item)
            hasil.append({"jenis": "pelajaran", "obj": p, "skor": skor * (0.5 + 0.5 * keyakinan) * (0.85 + 0.15 * kebaruan), "peringkat": peringkat,
                          "bendera": bendera, "vektor": p._vektor, "keyakinan": keyakinan})
        return hasil

    def _kandidat_prosedur(self, tvec, tugas, lingkup, lingkungan) -> list[dict]:
        hasil = []
        for p in self.store.prosedur_semua():
            if p.status in ("draf", "ditarik") or not skema.lingkup_memuat(p.lingkup, lingkup):
                continue
            skor = max(skor_hibrida(tvec, tugas, p._vektor, p.teks_embedding()),
                       skor_hibrida(tvec, tugas, p._vektor_pemicu, p.tugas_pemicu) if p._vektor_pemicu else 0.0)
            if skor < SKOR_MIN:
                continue
            bendera = []
            if p.tinjau_ulang:
                bendera.append("tinjau_ulang")
            if not _cocok_lingkungan(p.berlaku_untuk, lingkungan):
                bendera.append("versi_berbeda")
            if p.status == "teruji":
                bendera.append("belum_ditinjau")
                peringkat = PERINGKAT["belum_ditinjau"]
            elif p.status == "dipersempit":
                peringkat = PERINGKAT["dipersempit"]
            elif p.ditinjau_manusia:
                peringkat = PERINGKAT["kurasi_manusia"]
            else:
                peringkat = PERINGKAT["mesin_aktif"]
            waktu_item = getattr(p, "dibuat", None)
            kebaruan = _bobot_kebaruan(waktu_item)
            hasil.append({"jenis": "prosedur", "obj": p, "skor": skor * (0.5 + 0.5 * p.tingkat_berhasil) * (0.85 + 0.15 * kebaruan), "peringkat": peringkat,
                          "bendera": bendera, "vektor": p._vektor})
        return hasil

    def _pointer_episode(self, qvec, query, lingkup, maks=3, sertakan_S: bool = False) -> list[dict]:
        kandidat = []
        for e in self.store.episode_semua():
            if e.status == "diarsipkan" or not skema.lingkup_memuat(e.lingkup, lingkup):
                continue
            if e.tier == "S" and not sertakan_S:  # K10: tersimpan, tidak muncul tanpa permintaan eksplisit
                continue
            s = skor_hibrida(qvec, query, e._vektor, e.ringkas)
            waktu_ep = getattr(e, "waktu", None)
            kebaruan = _bobot_kebaruan(waktu_ep)
            s_final = s * (0.85 + 0.15 * kebaruan)
            if s_final >= SKOR_PERINGATAN:
                kandidat.append({"jenis": "episode", "id": e.id, "ringkas": e.ringkas[:120], "skor": round(s_final, 3)})
        kandidat.sort(key=lambda x: -x["skor"])
        return kandidat[:maks]

    def _semat_query(self, teks: str) -> list[float]:
        f = getattr(self.store.penyemat, "semat_query", None)
        return f(teks) if f else self.store.penyemat.semat(teks)

    # ---- L-tarik ------------------------------------------------------------
    def ingat(self, query: str, lingkup: str, jenis: str | None = None, tanggal_peristiwa: str | None = None,
              tugas: str | None = None, lingkungan: dict | None = None, anggaran_token: int | None = None,
              sesi: str = "", sertakan_S: bool = False) -> dict:
        if not skema.lingkup_valid(lingkup):
            raise ValueError("lingkup wajib dan harus valid (global | proyek:<nama> | peran:<nama>)")
        anggaran = anggaran_token or self.k["anggaran_tarik"]
        asumsi: list[str] = []
        peringatan: list[dict] = []
        tanggal = tanggal_peristiwa or skema.hari_ini()
        if not tanggal_peristiwa:
            asumsi.append(f"tanggal peristiwa diasumsikan hari ini ({tanggal})")
        qvec = self._semat_query(query)
        jenis_diminta = [jenis] if jenis else ["norma", "pelajaran", "prosedur"]

        kandidat: list[dict] = []
        if "norma" in jenis_diminta:
            kandidat += self._kandidat_norma(qvec, query, tanggal)
        if "pelajaran" in jenis_diminta:
            kandidat += self._kandidat_pelajaran(qvec, query, lingkup, lingkungan, peringatan)
        if "prosedur" in jenis_diminta and tugas:
            tvec = self._semat_query(tugas)
            kandidat += self._kandidat_prosedur(tvec, tugas, lingkup, lingkungan)
        if tugas:  # query bertipe cara: prosedur aktif di atas pelajaran deklaratif
            for c in kandidat:
                if c["jenis"] == "prosedur" and c["peringkat"] <= PERINGKAT["dipersempit"]:
                    c["peringkat"] -= 0.5

        # dedup MMR pada pool, lalu urutkan arbiter (peringkat, skor)
        pool = mmr(qvec, sorted(kandidat, key=lambda c: -c["skor"]), k=self.k["maks_item"] * 3)
        pool.sort(key=lambda c: (c["peringkat"], -c["skor"]))

        # boost item yang disematkan supaya naik ke atas
        id_sematan = {s["item_id"] for s in self.store.sematan_semua()}
        for c in pool:
            if c["obj"].id in id_sematan:
                c["peringkat"] = min(c["peringkat"], 1)  # naik ke peringkat norma
                c["bendera"].append("disematkan")

        item, pointer, token = [], [], 0
        for c in pool:
            teks = self.render(c["jenis"], c["obj"], c["bendera"])
            t = skema.hitung_token(teks)
            if len(item) < self.k["maks_item"] and token + t <= anggaran:
                item.append({"jenis": c["jenis"], "id": c["obj"].id, "peringkat": c["peringkat"], "skor": round(c["skor"], 3),
                             "status": c["obj"].status, "lingkup": getattr(c["obj"], "lingkup", "-"),
                             "bendera": c["bendera"], "teks": teks})
                token += t
            else:
                ringkas = getattr(c["obj"], "pelajaran", None) or getattr(c["obj"], "prosedur", None) or getattr(c["obj"], "judul", "")
                pointer.append({"jenis": c["jenis"], "id": c["obj"].id, "ringkas": (ringkas or "")[:100], "bendera": c["bendera"]})
        pointer += self._pointer_episode(qvec, query, lingkup, sertakan_S=sertakan_S)

        bendera_semua = sorted({b for i in item for b in i["bendera"]})
        if peringatan:
            bendera_semua.append("pernah_ditarik")
        self.store.catat_panggilan(sesi, lingkup, query, len(item), token, jenis or "semua")
        return {"item": item, "pointer": pointer, "asumsi": asumsi, "bendera": bendera_semua,
                "peringatan": peringatan, "token": token, "anggaran": anggaran, "tanggal_peristiwa": tanggal}

    # ---- L-peta + L-aturan -------------------------------------------------
    def muat_startup(self, lingkup: str, tugas: str | None = None, lingkungan: dict | None = None,
                     sesi: str = "") -> dict:
        if not skema.lingkup_valid(lingkup):
            raise ValueError("lingkup wajib")
        hari = skema.hari_ini()
        anggaran_peta, anggaran_aturan = self.k["anggaran_peta"], self.k["anggaran_aturan"]

        pelajaran_aktif = [p for p in self.store.pelajaran_semua(("aturan", "dipersempit"))
                           if skema.lingkup_memuat(p.lingkup, lingkup)]
        pelajaran_aktif.sort(key=lambda p: (-p.ditinjau_manusia, -p.keyakinan))
        prosedur_aktif = [p for p in self.store.prosedur_semua(("aktif", "dipersempit"))
                          if skema.lingkup_memuat(p.lingkup, lingkup)]
        norma_hari_ini = [n for n in self.store.norma_semua() if n.otoritatif and n.berlaku_pada(hari)]

        # L-peta: judul saja
        baris = [f"# peta memori · lingkup {lingkup} · {hari}"]
        baris += [f"norma: {n.id} {n.norma}" for n in norma_hari_ini]
        baris += [f"pelajaran: {p.id} {p.pelajaran[:70]}" for p in pelajaran_aktif]
        baris += [f"prosedur: {p.id} {p.prosedur[:70]}" for p in prosedur_aktif]
        baris += [f"instrumen: {i.id}" for i in self.store.instrumen_semua()]
        peta, tok_peta, terpotong = [], 0, 0
        for b in baris:
            t = skema.hitung_token(b)
            if tok_peta + t <= anggaran_peta:
                peta.append(b)
                tok_peta += t
            else:
                terpotong += 1
        if terpotong:
            peta.append(f"…(+{terpotong} entri lagi; panggil ingat() untuk menarik)")

        # L-aturan: isi pelajaran yang cocok lingkungan + prosedur yang cocok tugas
        aturan, pointer, tok_aturan = [], [], 0

        # Fakta tetap (pin): selalu masuk di awal, kebal peluruhan
        sematan = self.store.sematan_semua()
        for s in sematan:
            if s["jenis"] == "pelajaran":
                obj = self.store.pelajaran(s["item_id"])
                if obj and obj.status != "ditarik":
                    teks = self.render("pelajaran", obj, ["disematkan"])
                    t = skema.hitung_token(teks)
                    aturan.insert(0, teks)
                    tok_aturan += t
            elif s["jenis"] == "episode":
                obj = self.store.episode(s["item_id"])
                if obj:
                    teks = f"[fakta tetap {obj.id}] {obj.ringkas}"
                    t = skema.hitung_token(teks)
                    aturan.insert(0, teks)
                    tok_aturan += t

        urutan: list[tuple[str, object, list[str]]] = []
        for p in pelajaran_aktif:
            if _cocok_lingkungan(p.berlaku_untuk, lingkungan):
                urutan.append(("pelajaran", p, ["tinjau_ulang"] if p.tinjau_ulang else []))
            else:
                pointer.append({"jenis": "pelajaran", "id": p.id, "ringkas": p.pelajaran[:100], "bendera": ["versi_berbeda"]})
        if tugas:
            tvec = self._semat_query(tugas)
            for p in prosedur_aktif:
                s = max(skor_hibrida(tvec, tugas, p._vektor, p.teks_embedding()),
                        skor_hibrida(tvec, tugas, p._vektor_pemicu, p.tugas_pemicu) if p._vektor_pemicu else 0.0)
                if s >= 0.25 and _cocok_lingkungan(p.berlaku_untuk, lingkungan):
                    urutan.append(("prosedur", p, ["tinjau_ulang"] if p.tinjau_ulang else []))
        for jenis, obj, bendera in urutan:
            teks = self.render(jenis, obj, bendera)
            t = skema.hitung_token(teks)
            if tok_aturan + t <= anggaran_aturan:
                aturan.append(teks)
                tok_aturan += t
            else:
                ringkas = getattr(obj, "pelajaran", None) or getattr(obj, "prosedur", "")
                pointer.append({"jenis": jenis, "id": obj.id, "ringkas": ringkas[:100], "bendera": bendera})

        self.store.catat_panggilan(sesi, lingkup, "<startup>", len(aturan), tok_peta + tok_aturan, "startup")
        return {"peta": peta, "aturan": aturan, "pointer": pointer,
                "token": {"peta": tok_peta, "aturan": tok_aturan, "total": tok_peta + tok_aturan}}

    # ---- L-bukti ------------------------------------------------------------
    def buka_bukti(self, id_: str, sesi: str = "", sertakan_S: bool = False) -> dict:
        ep = self.store.episode(id_)
        if ep is None:
            raise KeyError(f"episode {id_} tidak ada")
        if ep.tier == "S" and not sertakan_S:
            raise PermissionError(f"episode {id_} tier S: butuh sertakan_S=True (K10)")
        isi = self.store.buka_dingin(ep.isi_ref)
        self.store.catat_panggilan(sesi, ep.lingkup, f"<bukti {id_}>", 1, skema.hitung_token(isi.get("isi", "")), "bukti")
        return {"id": ep.id, "waktu": ep.waktu, "status": ep.status, "tier": ep.tier, "lingkup": ep.lingkup,
                "jenis_kejadian": ep.jenis_kejadian, "ringkas": ep.ringkas, "isi": isi.get("isi", "")}

    def rasio_konteks(self, token_memori: int, ukuran_context: int) -> dict:
        rasio = token_memori / ukuran_context if ukuran_context else 0.0
        self.store.catat_metrik("rasio_token_memori", rasio, token_memori=token_memori, context=ukuran_context)
        return {"rasio": round(rasio, 4), "alarm": rasio > self.k["rasio_maks"]}
