# SPDX-License-Identifier: Apache-2.0
"""K30 — mode relay: server ini BUKAN sumber kebenaran, hanya pintu masuk baca-saja.

Sejak K30 laptop yang memegang store otoritatif, Ollama, dan konsolidasi; tier S tidak pernah
keluar laptop. VPS turun pangkat jadi *relay*: replika **tier P/I saja** yang melayani klien
yang memanggil dari luar (connector claude.ai, dan dashboard bila dipakai).

**Kenapa menutup jalur tulis, bukan menyaring tier di relay.** Opsi yang dipilih (A, 13 Sep 2026)
menghilangkan masalahnya, bukan meredamnya: kalau tidak ada tulis yang mendarat, tidak ada tier S
yang bisa tiba. Alternatifnya — relay membaca episode masuk, mendeteksi tier S, lalu menghapusnya —
bergantung pada dua langkah yang dua-duanya bisa gagal diam-diam, dan sementara itu relay sudah
melihat plaintext-nya.

Penangkapan dari sisi klien tidak hilang karenanya: ekstensi browser (K18/K20/K22) berjalan di
browser laptop, jadi ia menulis langsung ke `127.0.0.1` — tidak pernah butuh relay.

Sisi baca sudah aman sejak sebelumnya (`Gateway.buka_bukti` menolak tier S tanpa `sertakan_S`,
dan jalur HTTP tidak pernah mengirim flag itu), jadi modul ini hanya mengurus sisi tulis.
"""
from __future__ import annotations

JALUR_TULIS = frozenset({"/episode", "/metrik", "/tanya", "/konsolidasi", "/sinkron", "/instrumen"})
TOOL_TULIS = frozenset({"catat_episode"})

PESAN = ("server ini berjalan sebagai relay baca-saja (K30): store otoritatif ada di laptop. "
         "Tulis ke instans laptop, bukan ke relay.")


class RelayBacaSaja(PermissionError):
    """Dipetakan ke HTTP 403 oleh api.py lewat cabang PermissionError yang sudah ada."""


def jalur_tulis(path: str) -> bool:
    """True untuk jalur POST yang mengubah keadaan. `/dashboard/data` sengaja TIDAK termasuk:
    ia POST tetapi murni membangun graf untuk dibaca."""
    if path in JALUR_TULIS:
        return True
    return path.startswith("/prosedur/") and path.endswith("/eksekusi")


def tolak(apa: str) -> RelayBacaSaja:
    return RelayBacaSaja(f"{apa} ditolak: {PESAN}")
