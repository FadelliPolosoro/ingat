# SPDX-License-Identifier: Apache-2.0
"""Lapis Kurasi: vault Obsidian (Bab 10.1).

Arah tulis mesin  : HANYA ke `pelajaran/_usulan/` dan `prosedur/_usulan/` (P5).
Arah baca         : `pelajaran/`, `prosedur/`, `norma/`, `norma/_konsolidasi/`.
Tinjauan manusia  : memindahkan berkas dari `_usulan/` ke folder induk = usulan->aturan
                    (atau teruji->aktif). Mengisi `veto_manusia` = ditarik.
Struktur vault:
  <vault>/pelajaran/*.md, <vault>/pelajaran/_usulan/*.md
  <vault>/prosedur/*.md,  <vault>/prosedur/_usulan/*.md
  <vault>/norma/*.md,     <vault>/norma/_konsolidasi/*.md
"""
from __future__ import annotations

import glob
import os

from . import frontmatter, skema
from .simpan import Store

_STATUS_PELAJARAN_VALID = set(skema.TRANSISI["pelajaran"])
_STATUS_PROSEDUR_VALID = set(skema.TRANSISI["prosedur"])


def _jalur_transisi(jenis: str, dari: str, ke: str) -> list[str] | None:
    """BFS jalur transisi terpendek (manusia boleh semua transisi yang terdefinisi)."""
    if dari == ke:
        return []
    antrean, dilihat = [(dari, [])], {dari}
    while antrean:
        s, jalur = antrean.pop(0)
        for nxt in skema.TRANSISI[jenis].get(s, ()):
            if nxt == ke:
                return jalur + [nxt]
            if nxt not in dilihat:
                dilihat.add(nxt)
                antrean.append((nxt, jalur + [nxt]))
    return None


def _terapkan_rantai(store: Store, jenis: str, id_: str, dari: str, ke: str, alasan: str, laporan: dict) -> bool:
    jalur = _jalur_transisi(jenis, dari, ke)
    if jalur is None:
        laporan["galat"].append(f"{jenis} {id_}: {dari} -> {ke} tidak punya jalur transisi")
        return False
    sekarang = dari
    for langkah in jalur:
        store.ubah_status(jenis, id_, langkah, "manusia", alasan)
        laporan["transisi"].append(f"{jenis} {id_}: {sekarang} -> {langkah}")
        sekarang = langkah
    return True


class Vault:
    def __init__(self, path: str):
        self.path = path
        for sub in ("pelajaran/_usulan", "prosedur/_usulan", "norma/_konsolidasi"):
            os.makedirs(os.path.join(path, sub), exist_ok=True)

    # ---- tulis (hanya _usulan) --------------------------------------------
    def tulis_usulan_pelajaran(self, p: skema.Pelajaran, ringkas_bukti: list[str]) -> str:
        meta = {k: v for k, v in skema.ke_dict(p).items() if k not in ("id",)}
        meta = {"id": p.id, "jenis": "pelajaran", **meta}
        badan = ["## Ringkas bukti", *[f"- {r}" for r in ringkas_bukti],
                 "", "## Cara meninjau",
                 "- Setuju: pindahkan berkas ini ke folder `pelajaran/` (status naik ke `aturan`).",
                 "- Tolak : isi `veto_manusia: \"<tanggal> — <alasan>\"` (status jadi `ditarik`).",
                 "- Ubah  : sunting `pelajaran`/`pemicu`/`tindakan`/`lingkup` lalu pindahkan."]
        path = os.path.join(self.path, "pelajaran", "_usulan", f"{p.id}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(frontmatter.dump(meta, "\n".join(badan)))
        return path

    def tulis_usulan_prosedur(self, p: skema.Prosedur, ringkas_bukti: list[str]) -> str:
        meta = {"id": p.id, "jenis": "prosedur", **{k: v for k, v in skema.ke_dict(p).items() if k != "id"}}
        badan = ["## Ringkas bukti", *[f"- {r}" for r in ringkas_bukti], "",
                 "## Cara meninjau",
                 "- Jalankan `uji` dulu. Lulus → pindahkan ke `prosedur/` (status `aktif`).",
                 "- Tolak: isi `veto_manusia`."]
        path = os.path.join(self.path, "prosedur", "_usulan", f"{p.id}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(frontmatter.dump(meta, "\n".join(badan)))
        return path

    # ---- baca ---------------------------------------------------------------
    def _baca_semua(self, sub: str) -> list[tuple[str, dict, str]]:
        hasil = []
        for path in sorted(glob.glob(os.path.join(self.path, sub, "*.md"))):
            with open(path, encoding="utf-8") as f:
                meta, badan = frontmatter.muat(f.read())
            if meta.get("id"):
                hasil.append((path, meta, badan))
        return hasil

    @staticmethod
    def _bangun(kelas, meta: dict):
        from dataclasses import fields
        nama = {f.name for f in fields(kelas)}
        d = {k: v for k, v in meta.items() if k in nama}
        for k in ("bukti", "kontra", "instrumen_saat_dibuat", "mengganti", "disusun_dari", "langkah", "titik_buta_diketahui"):
            if k in d and d[k] is None:
                d[k] = []
        if "berlaku_untuk" in d and not isinstance(d["berlaku_untuk"], dict):
            d["berlaku_untuk"] = {}
        for k in ("keyakinan",):
            if k in d and d[k] is not None:
                d[k] = float(d[k])
        return kelas(**d)

    def sinkron(self, store: Store) -> dict:
        """Vault -> store. Mengembalikan ringkasan perubahan."""
        laporan = {"pelajaran": 0, "prosedur": 0, "norma": 0, "transisi": [], "galat": []}

        # pelajaran disetujui (folder induk) dan usulan
        for folder, target in (("pelajaran", "aturan"), ("pelajaran/_usulan", "usulan")):
            for path, meta, _ in self._baca_semua(folder):
                try:
                    p = self._bangun(skema.Pelajaran, meta)
                    lama = store.pelajaran(p.id)
                    if p.veto_manusia:
                        p.status = "ditarik"
                    elif target == "aturan":
                        # manusia memindahkan berkas: status berkas boleh aturan/dipersempit/abadi-like
                        if p.status not in ("aturan", "dipersempit"):
                            p.status = "aturan"
                        p.ditinjau_manusia = True
                        p.keyakinan = max(p.keyakinan, 0.7)  # persetujuan manusia = bukti kuat
                    else:
                        if p.status not in ("usulan", "hipotesis"):
                            p.status = "usulan"
                    if lama and lama.status != p.status:
                        if not _terapkan_rantai(store, "pelajaran", p.id, lama.status, p.status, f"sinkron vault {folder}", laporan):
                            continue
                    if lama:
                        p.bukti = sorted(set(lama.bukti) | set(p.bukti))
                        p.kontra = sorted(set(lama.kontra) | set(p.kontra))
                    store.simpan_pelajaran(p)
                    laporan["pelajaran"] += 1
                except Exception as e:  # berkas rusak tidak boleh menghentikan sinkron
                    laporan["galat"].append(f"{path}: {e}")

        for folder, target in (("prosedur", "aktif"), ("prosedur/_usulan", "teruji")):
            for path, meta, _ in self._baca_semua(folder):
                try:
                    p = self._bangun(skema.Prosedur, meta)
                    lama = store.prosedur(p.id)
                    if p.veto_manusia:
                        p.status = "ditarik"
                    elif target == "aktif":
                        if p.status not in ("aktif", "dipersempit"):
                            p.status = "aktif"
                        p.ditinjau_manusia = True
                    else:
                        if p.status not in ("draf", "teruji"):
                            p.status = "teruji"
                    if lama and lama.status != p.status:
                        if not _terapkan_rantai(store, "prosedur", p.id, lama.status, p.status, f"sinkron vault {folder}", laporan):
                            continue
                    store.simpan_prosedur(p)
                    laporan["prosedur"] += 1
                except Exception as e:
                    laporan["galat"].append(f"{path}: {e}")

        # norma otoritatif + tampilan konsolidasi
        semua_norma: dict[str, skema.Norma] = {}
        for folder, otoritatif in (("norma", True), ("norma/_konsolidasi", False)):
            for path, meta, badan in self._baca_semua(folder):
                try:
                    n = self._bangun(skema.Norma, meta)
                    n.otoritatif = otoritatif
                    n.isi = badan
                    if not otoritatif and not n.disusun_dari:
                        raise ValueError("tampilan konsolidasi wajib punya disusun_dari")
                    semua_norma[n.id] = n
                except Exception as e:
                    laporan["galat"].append(f"{path}: {e}")
        # turunkan berlaku_sampai dari dicabut_oleh -> berlaku_sejak pengganti
        for n in semua_norma.values():
            if n.otoritatif and n.dicabut_oleh and n.dicabut_oleh in semua_norma:
                pengganti = semua_norma[n.dicabut_oleh]
                n.berlaku_sampai = pengganti.berlaku_sejak
                if n.status == "berlaku":
                    n.status = "dicabut"
            if n.dibatalkan_oleh and n.status != "dibatalkan":
                n.status = "dibatalkan"
        for n in semua_norma.values():
            store.simpan_norma(n)
            laporan["norma"] += 1
        return laporan

    def daftar_usulan(self) -> dict:
        return {"pelajaran": [os.path.basename(p) for p, _, _ in self._baca_semua("pelajaran/_usulan")],
                "prosedur": [os.path.basename(p) for p, _, _ in self._baca_semua("prosedur/_usulan")]}
