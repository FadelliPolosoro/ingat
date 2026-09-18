# SPDX-License-Identifier: Apache-2.0
"""Modul kesehatan — pemantauan adaptif koneksi ke situs AI dan server ingat.

Fitur:
1. Adaptive rate limiting per situs AI (belajar dari respons 429)
2. Deteksi adapter rusak (selektor yang tidak cocok, API endpoint berubah)
3. Status kesehatan keseluruhan sistem ingat
4. Riwayat insiden untuk diagnostik

Data disimpan di ~/.ingat/kesehatan.json — ringan, tanpa database tambahan.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field, asdict
from typing import Any

DIR_INGAT = os.path.join(os.path.expanduser("~"), ".ingat")
BERKAS_KESEHATAN = os.path.join(DIR_INGAT, "kesehatan.json")

BATAS_BAKU_PER_MENIT = 10
JEDA_BAKU_DETIK = 2.0
MAKS_INSIDEN = 200
MAKS_UMUR_INSIDEN_JAM = 168  # 7 hari


@dataclass
class ProfilSitus:
    """Profil rate-limit adaptif per situs AI."""
    nama: str
    batas_per_menit: int = BATAS_BAKU_PER_MENIT
    jeda_antar_detik: float = JEDA_BAKU_DETIK
    terakhir_429: float = 0.0
    jumlah_429: int = 0
    jumlah_sukses: int = 0
    jumlah_gagal: int = 0
    terakhir_sukses: float = 0.0
    terakhir_gagal: float = 0.0
    adapter_rusak: bool = False
    pesan_adapter: str = ""

    def catat_sukses(self) -> None:
        self.jumlah_sukses += 1
        self.terakhir_sukses = time.time()
        self.adapter_rusak = False
        self.pesan_adapter = ""
        if self.jumlah_429 > 0 and self.jumlah_sukses > self.jumlah_429 * 3:
            self._naikkan_batas()

    def catat_429(self) -> None:
        self.jumlah_429 += 1
        self.terakhir_429 = time.time()
        self._turunkan_batas()

    def catat_gagal(self, pesan: str = "") -> None:
        self.jumlah_gagal += 1
        self.terakhir_gagal = time.time()
        if pesan:
            self.pesan_adapter = pesan

    def tandai_adapter_rusak(self, pesan: str) -> None:
        self.adapter_rusak = True
        self.pesan_adapter = pesan
        self.terakhir_gagal = time.time()

    def boleh_kirim(self) -> tuple[bool, float]:
        """Apakah boleh kirim permintaan sekarang? Kembalikan (boleh, tunggu_detik)."""
        sekarang = time.time()
        if self.terakhir_429 > 0:
            sejak_429 = sekarang - self.terakhir_429
            cooldown = self._cooldown_429()
            if sejak_429 < cooldown:
                return False, cooldown - sejak_429
        return True, 0.0

    def _turunkan_batas(self) -> None:
        self.batas_per_menit = max(1, self.batas_per_menit // 2)
        self.jeda_antar_detik = min(60.0, self.jeda_antar_detik * 2)

    def _naikkan_batas(self) -> None:
        self.batas_per_menit = min(BATAS_BAKU_PER_MENIT * 2, self.batas_per_menit + 2)
        self.jeda_antar_detik = max(0.5, self.jeda_antar_detik * 0.8)

    def _cooldown_429(self) -> float:
        if self.jumlah_429 <= 1:
            return 30.0
        if self.jumlah_429 <= 3:
            return 120.0
        if self.jumlah_429 <= 10:
            return 300.0
        return 600.0


@dataclass
class Insiden:
    """Satu insiden kesehatan."""
    waktu: float
    situs: str
    jenis: str  # "429", "adapter_rusak", "koneksi_gagal", "server_mati"
    pesan: str = ""


@dataclass
class StatusKesehatan:
    """Keadaan kesehatan keseluruhan sistem."""
    profil: dict[str, ProfilSitus] = field(default_factory=dict)
    insiden: list[dict] = field(default_factory=list)
    terakhir_periksa: float = 0.0


def _path() -> str:
    return BERKAS_KESEHATAN


def muat() -> StatusKesehatan:
    try:
        with open(_path(), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return StatusKesehatan()
    st = StatusKesehatan()
    for nama, p in (data.get("profil") or {}).items():
        if isinstance(p, dict):
            st.profil[nama] = ProfilSitus(
                nama=nama,
                batas_per_menit=p.get("batas_per_menit", BATAS_BAKU_PER_MENIT),
                jeda_antar_detik=p.get("jeda_antar_detik", JEDA_BAKU_DETIK),
                terakhir_429=p.get("terakhir_429", 0.0),
                jumlah_429=p.get("jumlah_429", 0),
                jumlah_sukses=p.get("jumlah_sukses", 0),
                jumlah_gagal=p.get("jumlah_gagal", 0),
                terakhir_sukses=p.get("terakhir_sukses", 0.0),
                terakhir_gagal=p.get("terakhir_gagal", 0.0),
                adapter_rusak=p.get("adapter_rusak", False),
                pesan_adapter=p.get("pesan_adapter", ""),
            )
    st.insiden = (data.get("insiden") or [])[-MAKS_INSIDEN:]
    st.terakhir_periksa = data.get("terakhir_periksa", 0.0)
    return st


def simpan(st: StatusKesehatan) -> None:
    os.makedirs(DIR_INGAT, exist_ok=True)
    batas = time.time() - MAKS_UMUR_INSIDEN_JAM * 3600
    st.insiden = [i for i in st.insiden if (i.get("waktu", 0) if isinstance(i, dict) else 0) > batas][-MAKS_INSIDEN:]
    data: dict[str, Any] = {
        "profil": {n: asdict(p) for n, p in st.profil.items()},
        "insiden": st.insiden,
        "terakhir_periksa": st.terakhir_periksa,
    }
    tmp = _path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _path())


def profil(nama_situs: str, st: StatusKesehatan | None = None) -> ProfilSitus:
    if st is None:
        st = muat()
    if nama_situs not in st.profil:
        st.profil[nama_situs] = ProfilSitus(nama=nama_situs)
    return st.profil[nama_situs]


def catat_insiden(st: StatusKesehatan, situs: str, jenis: str, pesan: str = "") -> None:
    st.insiden.append({"waktu": time.time(), "situs": situs, "jenis": jenis, "pesan": pesan})


# ── API publik untuk ekstensi browser / panel ──

def catat_respons(nama_situs: str, kode_http: int, pesan: str = "") -> dict:
    """Catat respons dari situs AI. Dipanggil oleh ekstensi browser setelah fetch."""
    st = muat()
    p = profil(nama_situs, st)
    if kode_http == 429:
        p.catat_429()
        catat_insiden(st, nama_situs, "429", pesan or "Rate limited")
    elif 200 <= kode_http < 400:
        p.catat_sukses()
    else:
        p.catat_gagal(pesan)
        if kode_http >= 500:
            catat_insiden(st, nama_situs, "koneksi_gagal", pesan or f"HTTP {kode_http}")
    simpan(st)
    return {"situs": nama_situs, "batas_per_menit": p.batas_per_menit, "jeda": p.jeda_antar_detik}


def catat_adapter_rusak(nama_situs: str, pesan: str) -> None:
    """Tandai bahwa selektor/adapter untuk situs ini tidak cocok lagi."""
    st = muat()
    p = profil(nama_situs, st)
    p.tandai_adapter_rusak(pesan)
    catat_insiden(st, nama_situs, "adapter_rusak", pesan)
    simpan(st)


def boleh_kirim(nama_situs: str) -> tuple[bool, float]:
    """Periksa apakah situs ini boleh dikirimi permintaan sekarang."""
    st = muat()
    p = profil(nama_situs, st)
    return p.boleh_kirim()


def ringkasan() -> dict:
    """Ringkasan kesehatan seluruh sistem untuk /metrik dan panel."""
    st = muat()
    sekarang = time.time()
    situs_list = []
    for nama, p in st.profil.items():
        lampu = "hijau"
        if p.adapter_rusak:
            lampu = "merah"
        elif p.jumlah_429 > 0 and sekarang - p.terakhir_429 < 3600:
            lampu = "kuning"
        elif p.jumlah_gagal > 0 and sekarang - p.terakhir_gagal < 3600:
            lampu = "kuning"
        situs_list.append({
            "nama": nama,
            "lampu": lampu,
            "batas_per_menit": p.batas_per_menit,
            "jeda_detik": p.jeda_antar_detik,
            "sukses": p.jumlah_sukses,
            "gagal_429": p.jumlah_429,
            "gagal_lain": p.jumlah_gagal,
            "adapter_rusak": p.adapter_rusak,
            "pesan": p.pesan_adapter if p.adapter_rusak else "",
        })
    insiden_terkini = [i for i in st.insiden if isinstance(i, dict) and sekarang - i.get("waktu", 0) < 86400]
    lampu_global = "hijau"
    if any(s["lampu"] == "merah" for s in situs_list):
        lampu_global = "merah"
    elif any(s["lampu"] == "kuning" for s in situs_list):
        lampu_global = "kuning"
    return {
        "lampu": lampu_global,
        "situs": situs_list,
        "insiden_24jam": len(insiden_terkini),
        "terakhir_periksa": st.terakhir_periksa,
    }


def periksa_server(host: str = "http://127.0.0.1:8765", token: str | None = None) -> dict:
    """Periksa apakah server ingat hidup dan responsif."""
    import urllib.request
    import urllib.error
    st = muat()
    st.terakhir_periksa = time.time()
    try:
        req = urllib.request.Request(host + "/sehat")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        hasil = {"hidup": True, "versi": data.get("versi", "?"), "pesan": "OK"}
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
        hasil = {"hidup": False, "versi": None, "pesan": str(e)}
        catat_insiden(st, "server-ingat", "server_mati", str(e))
    simpan(st)
    return hasil


def reset_situs(nama_situs: str) -> bool:
    """Reset profil situs ke bawaan (setelah masalah diperbaiki)."""
    st = muat()
    if nama_situs in st.profil:
        st.profil[nama_situs] = ProfilSitus(nama=nama_situs)
        simpan(st)
        return True
    return False
