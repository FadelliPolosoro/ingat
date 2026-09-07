# SPDX-License-Identifier: Apache-2.0
"""`python3 -m ingat pasang [--tulis]` — pasang hook, perintah /koreksi, MCP, dan konfigurasi default.

Tanpa `--tulis`: hanya mencetak apa yang AKAN ditulis (tidak menyentuh berkas). Dengan `--tulis`:
- ~/.ingat/konfigurasi.json    (dibuat bila belum ada; yang sudah ada tidak ditimpa)
- ~/.ingat/{data,vault}/       (folder)
- ~/.claude/settings.json      (kunci `hooks` DIGABUNG: entri ingat ditambahkan bila belum ada; entri lain utuh)
- ~/.claude/commands/koreksi.md
- ~/.claude/.mcp.json          (server `ingat` ditambahkan bila belum ada)
Semua path dari `pasang/` di repo ini; `~` diperluas.
"""
from __future__ import annotations

import json
import os
import shutil

AKAR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLAT = os.path.join(AKAR, "pasang")


def _baca_json(p: str) -> dict:
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _tulis_json(p: str, d: dict):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)
        f.write("\n")


def gabung_hooks(lama: dict, tambahan: dict) -> tuple[dict, int]:
    """Gabungkan `hooks` tanpa menduplikasi entri yang perintahnya sama. Kembalikan (hasil, jumlah_ditambah)."""
    hasil = json.loads(json.dumps(lama))
    hooks = hasil.setdefault("hooks", {})
    n = 0
    for peristiwa, grup_baru in tambahan.get("hooks", {}).items():
        grup = hooks.setdefault(peristiwa, [])
        perintah_ada = {h.get("command") for g in grup for h in g.get("hooks", [])}
        for g in grup_baru:
            if all(h.get("command") in perintah_ada for h in g.get("hooks", [])):
                continue
            grup.append(g)
            n += 1
    return hasil, n


def rencana(rumah: str | None = None) -> list[tuple[str, str]]:
    rumah = rumah or os.path.expanduser("~")
    return [
        ("konfigurasi", os.path.join(rumah, ".ingat", "konfigurasi.json")),
        ("settings.hooks", os.path.join(rumah, ".claude", "settings.json")),
        ("koreksi", os.path.join(rumah, ".claude", "commands", "koreksi.md")),
        ("mcp", os.path.join(rumah, ".claude", ".mcp.json")),
    ]


def pasang(tulis: bool = False, rumah: str | None = None) -> dict:
    rumah = rumah or os.path.expanduser("~")
    laporan = {"tulis": tulis, "langkah": []}
    tujuan = dict(rencana(rumah))

    # 1. konfigurasi (tidak menimpa)
    p = tujuan["konfigurasi"]
    if os.path.exists(p):
        laporan["langkah"].append(f"lewati {p} (sudah ada)")
    else:
        laporan["langkah"].append(f"buat {p}")
        if tulis:
            d = _baca_json(os.path.join(TEMPLAT, "konfigurasi.json"))
            for k in ("dir_data", "vault"):
                d[k] = os.path.expanduser(d[k])
            _tulis_json(p, d)
    if tulis:
        for sub in ("data", "vault/pelajaran/_usulan", "vault/prosedur/_usulan", "vault/norma"):
            os.makedirs(os.path.join(rumah, ".ingat", sub), exist_ok=True)

    # 2. hooks (gabung)
    p = tujuan["settings.hooks"]
    lama = _baca_json(p)
    baru, n = gabung_hooks(lama, _baca_json(os.path.join(TEMPLAT, "settings.hooks.json")))
    laporan["langkah"].append(f"gabung {n} grup hook ke {p}" if n else f"hook sudah ada di {p}")
    if tulis and n:
        _tulis_json(p, baru)

    # 3. /koreksi
    p = tujuan["koreksi"]
    laporan["langkah"].append(f"salin {p}")
    if tulis:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        shutil.copyfile(os.path.join(TEMPLAT, "commands", "koreksi.md"), p)

    # 4. MCP
    p = tujuan["mcp"]
    lama = _baca_json(p)
    if "ingat" in lama.get("mcpServers", {}):
        laporan["langkah"].append(f"server MCP ingat sudah ada di {p}")
    else:
        laporan["langkah"].append(f"tambah server MCP ingat ke {p}")
        if tulis:
            templat = _baca_json(os.path.join(TEMPLAT, "mcp.json"))["mcpServers"]["ingat"]
            templat["args"] = [os.path.expanduser(a) if a.startswith("~") else a for a in templat["args"]]
            lama.setdefault("mcpServers", {})["ingat"] = templat
            _tulis_json(p, lama)

    laporan["catatan"] = [
        "Paket ingat harus bisa diimpor oleh python3 yang dipanggil hook: `pip install -e .` di repo ini.",
        "Model embedding: bash model/bangun-gguf.sh && ollama create ingat-e5-base -f model/Modelfile (atau embedding.jenis=lokal untuk uji).",
        "Uji: buka sesi Claude Code di repo mana pun, jalankan satu perintah, lalu `python3 -m ingat --konfig ~/.ingat/konfigurasi.json metrik` (episode_aktif harus > 0).",
    ]
    return laporan
