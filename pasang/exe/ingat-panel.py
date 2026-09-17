# SPDX-License-Identifier: Apache-2.0
"""Titik masuk .exe Panel Kendali ingat (Fase 0 portable, PyInstaller onefile).

Menjalankan `ingat.panel.jalankan()` dengan konfig default `~/.ingat/konfigurasi.json`
bila ada — supaya .exe langsung membuka store & vault sungguhan (embedder Ollama e5-base),
bukan `KONFIG_DEFAULT` (PenyematLokal 512-dim, dir_data lain). `muat_konfig(None)` sendiri
hanya mencari `konfigurasi.json` relatif folder kerja, yang untuk .exe rapuh.

Path `static/` dibundel ke root arsip lewat `--add-data static;static`. `api.py`/`pantau.py`
menghitung static dari struktur package (`dirname(dirname(__file__))/static`); di dalam bundle
onefile itu jatuh ke `_MEIPASS/static` — cocok, jadi tak perlu menambal kode sumber.
"""
from __future__ import annotations

import os
import sys


def _konfig_awal() -> str | None:
    lewat = os.environ.get("INGAT_KONFIG")
    if lewat:
        return lewat
    rumah = os.path.expanduser(os.path.join("~", ".ingat", "konfigurasi.json"))
    return rumah if os.path.exists(rumah) else None


def main() -> int:
    from ingat.panel import jalankan
    return jalankan(_konfig_awal())


if __name__ == "__main__":
    sys.exit(main())
