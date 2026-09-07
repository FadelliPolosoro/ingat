# SPDX-License-Identifier: Apache-2.0
"""`<python> -m ingat pasang [--tulis]` — pasang hook, perintah /koreksi, MCP, dan konfigurasi default.

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
import sys

AKAR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLAT = os.path.join(AKAR, "pasang")

#: Penanda `-m …` yang menandai sebuah perintah hook sebagai milik ingat, apa pun penafsirnya.
PENANDA_HOOK = "-m ingat.tangkap"


def penafsir() -> str:
    """Penafsir Python yang ditulis ke settings.json / .mcp.json di mesin ini.

    Dipakai `sys.executable` — penafsir yang SEDANG menjalankan `pasang`. Itu satu-satunya
    yang dijamin bisa mengimpor paket `ingat` yang baru saja dipasang (termasuk bila
    pemasangan dilakukan di dalam venv).

    Nama telanjang tidak dipakai karena tidak ada satu pun yang benar di semua OS:
    `python3` tidak dipasang oleh installer python.org di Windows — nama itu jatuh ke stub
    Microsoft Store yang keluar dengan kode bukan-nol, dan karena handler tangkap memang
    dirancang selalu exit 0, kegagalannya tidak akan kelihatan sama sekali. Sebaliknya
    banyak distribusi Linux tidak memasang `python` sama sekali.
    """
    if sys.executable:
        return sys.executable
    for nama in ("python3", "python", "py"):  # penafsir tertanam/beku: cari di PATH
        ada = shutil.which(nama)
        if ada:
            return ada
    raise RuntimeError("tidak ada penafsir Python yang bisa ditulis ke perintah hook")


def _kutip(exe: str) -> str:
    """Perintah hook dijalankan lewat shell, jadi path berspasi wajib dikutip."""
    return f'"{exe}"' if " " in exe and not exe.startswith('"') else exe


def _sisa_hook(perintah: str) -> str | None:
    """Bagian `-m ingat.tangkap …` bila `perintah` adalah hook ingat; None bila bukan.

    Dipakai sebagai identitas hook supaya entri yang ditulis mesin lain (penafsir berbeda)
    dikenali sebagai entri yang SAMA — diperbarui, bukan diduplikasi.
    """
    i = perintah.find(PENANDA_HOOK)
    return perintah[i:] if i > 0 else None


def _kunci(perintah: str) -> str:
    return _sisa_hook(perintah) or perintah


def terapkan_penafsir(templat: dict, py: str | None = None) -> dict:
    """Salinan `templat` dengan tiap perintah hook ingat memakai penafsir mesin ini.

    Templat di `pasang/settings.hooks.json` menulis `python3` sebagai penampung; nilai itu
    tidak pernah dipakai apa adanya — selalu diganti di sini.
    """
    py = _kutip(py or penafsir())
    hasil = json.loads(json.dumps(templat))
    for grup in hasil.get("hooks", {}).values():
        for g in grup:
            for h in g.get("hooks", []):
                sisa = _sisa_hook(h.get("command", ""))
                if sisa:
                    h["command"] = f"{py} {sisa}"
    return hasil


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


def gabung_hooks(lama: dict, tambahan: dict) -> tuple[dict, int, int]:
    """Gabungkan `hooks` tanpa menduplikasi entri. Kembalikan (hasil, ditambah, penafsir_diperbarui).

    Entri ingat dikenali dari `-m ingat.tangkap …`, bukan dari perintah utuh. Tanpa itu,
    memasang ulang di mesin dengan penafsir berbeda akan menambah grup KEDUA yang ikut
    menembak di setiap peristiwa, bukan memperbarui yang lama.
    """
    hasil = json.loads(json.dumps(lama))
    hooks = hasil.setdefault("hooks", {})
    n = diperbarui = 0
    for peristiwa, grup_baru in tambahan.get("hooks", {}).items():
        grup = hooks.setdefault(peristiwa, [])
        ada = {_kunci(h.get("command", "")): h for g in grup for h in g.get("hooks", [])}
        for g in grup_baru:
            baru = g.get("hooks", [])
            if not all(_kunci(h.get("command", "")) in ada for h in baru):
                grup.append(g)
                n += 1
                continue
            for h in baru:  # entri sudah ada — samakan penafsirnya dengan mesin ini
                lama_h = ada[_kunci(h.get("command", ""))]
                if lama_h.get("command") != h.get("command"):
                    lama_h["command"] = h["command"]
                    diperbarui += 1
    return hasil, n, diperbarui


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
    py = penafsir()
    laporan = {"tulis": tulis, "penafsir": py, "langkah": []}
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
    templat = terapkan_penafsir(_baca_json(os.path.join(TEMPLAT, "settings.hooks.json")), py)
    baru, n, diperbarui = gabung_hooks(lama, templat)
    if n:
        laporan["langkah"].append(f"gabung {n} grup hook ke {p}")
    elif diperbarui:
        laporan["langkah"].append(f"perbarui penafsir {diperbarui} hook ingat di {p}")
    else:
        laporan["langkah"].append(f"hook sudah ada di {p}")
    if tulis and (n or diperbarui):
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
    ada = lama.get("mcpServers", {}).get("ingat")
    if ada and ada.get("command") == py:
        laporan["langkah"].append(f"server MCP ingat sudah ada di {p}")
    elif ada:
        # penafsir berubah (pindah mesin, venv baru) — perbarui, jangan biarkan menunjuk yang hilang
        laporan["langkah"].append(f"perbarui penafsir server MCP ingat di {p}")
        if tulis:
            ada["command"] = py
            _tulis_json(p, lama)
    else:
        laporan["langkah"].append(f"tambah server MCP ingat ke {p}")
        if tulis:
            templat = _baca_json(os.path.join(TEMPLAT, "mcp.json"))["mcpServers"]["ingat"]
            # `command` di MCP adalah argv[0], BUKAN baris shell — jangan dikutip.
            templat["command"] = py
            templat["args"] = [os.path.expanduser(a) if a.startswith("~") else a for a in templat["args"]]
            lama.setdefault("mcpServers", {})["ingat"] = templat
            _tulis_json(p, lama)

    laporan["catatan"] = [
        f"Hook dan MCP ditulis memakai penafsir ini: {py}",
        f"Paket ingat harus bisa diimpor olehnya: `{py} -m pip install -e .` di repo ini.",
        "Model embedding: bash model/bangun-gguf.sh && ollama create ingat-e5-base -f model/Modelfile (atau embedding.jenis=lokal untuk uji).",
        f"Uji: buka sesi Claude Code di repo mana pun, jalankan satu perintah, lalu `{py} -m ingat --konfig ~/.ingat/konfigurasi.json metrik` (episode_aktif harus > 0).",
    ]
    return laporan
