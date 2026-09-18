# SPDX-License-Identifier: Apache-2.0
"""Digest harian: rangkum episode hari ini/kemarin menjadi rekap singkat.

Versi 1 = heuristik (tanpa LLM): kelompokkan episode per platform,
buat daftar bullet, hitung statistik. Upgrade ke LLM nanti.
"""
from __future__ import annotations

import datetime as _dt
from collections import Counter

from . import judul_memori as JM

_NAMA_SUMBER = dict(JM._NAMA_SUMBER)


def digest_hari(store, tanggal: str | None = None) -> dict:
    """Buat digest untuk satu hari.

    tanggal: "YYYY-MM-DD" (default: hari ini).
    """
    if tanggal is None:
        tanggal = _dt.date.today().isoformat()

    judul_map = JM.semua_judul(store)
    eps = [e for e in store.episode_semua()
           if (getattr(e, "waktu", "") or "")[:10] == tanggal]

    eps.sort(key=lambda e: getattr(e, "waktu", "") or "")

    platform_count: Counter[str] = Counter()
    jenis_count: Counter[str] = Counter()
    butir = []

    for ep in eps:
        sumber = getattr(ep, "sumber", "") or ""
        nama = _NAMA_SUMBER.get(sumber)
        if not nama:
            nama = sumber[8:] if sumber.startswith("browser:") else (sumber or "Lainnya")
        platform_count[nama] += 1
        jenis = getattr(ep, "jenis_kejadian", "") or ""
        jenis_count[jenis] += 1

        jam = (getattr(ep, "waktu", "") or "")[11:16]
        judul = judul_map.get(ep.id) or (getattr(ep, "ringkas", "") or "")[:80] or ep.id

        butir.append({
            "waktu": jam,
            "judul": judul,
            "platform": nama,
            "tier": getattr(ep, "tier", ""),
            "jenis": jenis,
        })

    ringkasan = _buat_ringkasan(len(eps), platform_count, jenis_count)
    judul_hari = _format_tanggal_id(tanggal)

    return {
        "tanggal": tanggal,
        "judul": f"Rekap {judul_hari}",
        "total": len(eps),
        "platform": dict(platform_count.most_common()),
        "jenis": dict(jenis_count.most_common()),
        "butir": butir,
        "ringkasan": ringkasan,
    }


def _buat_ringkasan(total: int, platform: Counter, jenis: Counter) -> str:
    if total == 0:
        return "Tidak ada episode hari ini."
    bagian = []
    bagian.append(f"{total} episode dari {len(platform)} platform.")
    if jenis:
        atas = jenis.most_common(1)[0]
        bagian.append(f"Mayoritas {atas[0]} ({atas[1]}).")
        gagal = jenis.get("gagal", 0)
        if gagal:
            bagian.append(f"{gagal} gagal.")
    if platform:
        utama = platform.most_common(1)[0]
        bagian.append(f"Platform utama: {utama[0]}.")
    return " ".join(bagian)


def _format_tanggal_id(tanggal: str) -> str:
    """Format "2026-09-19" -> "19 September 2026"."""
    BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni",
             "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
    try:
        d = _dt.date.fromisoformat(tanggal)
        return f"{d.day} {BULAN[d.month - 1]} {d.year}"
    except Exception:
        return tanggal


def digest_rentang(store, dari: str, sampai: str) -> list[dict]:
    """Digest untuk rentang tanggal. Return list digest per hari (non-kosong saja)."""
    hasil = []
    d = _dt.date.fromisoformat(dari)
    s = _dt.date.fromisoformat(sampai)
    while d <= s:
        dg = digest_hari(store, d.isoformat())
        if dg["total"] > 0:
            hasil.append(dg)
        d += _dt.timedelta(days=1)
    return hasil


def digest_7_hari(store) -> list[dict]:
    """Digest 7 hari terakhir."""
    hari_ini = _dt.date.today()
    return digest_rentang(store, (hari_ini - _dt.timedelta(days=6)).isoformat(), hari_ini.isoformat())
