# SPDX-License-Identifier: Apache-2.0
"""Impor 'chat terdahulu' Claude Code dari transkrip JSONL lokal (Jalur A — tanpa ekspor).

Transkrip ada di ~/.claude/projects/<slug>/<sesi>.jsonl. Hook `ingat.tangkap` hanya menangkap sesi
SETELAH dipasang (episode `ep-sesi-<sesi>` berisi ringkasan langkah tool). Importer ini mengisi sesi
LAMA sebagai episode `ep-histori-<sesi>` berisi TEKS percakapan (bukan langkah tool).

Idempoten & tidak menimpa hook: lewati bila store sudah punya `ep-histori-<sesi>` (sudah diimpor)
ATAU `ep-sesi-<sesi>` (hook sudah menangani sesi itu — berarti bukan sesi lama). Titik tulis tunggal
`tambah_episode` (redaksi K10 + penyematan jalan). Kering (cetak rencana) kecuali `tulis=True`.
"""
from __future__ import annotations

import glob
import json
import os
import re

from . import skema
from .aplikasi import Aplikasi
from .tangkap import tentukan_lingkup

BATAS_ISI = 8000  # cap panjang isi episode (char); bila lebih, ambil kepala + ekor


def _teks_dari_content(content) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        bagian = [b["text"] for b in content
                  if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str)]
        return "\n".join(bagian).strip()
    return ""


def _hasil_tool(content) -> bool:
    """True bila content list yang hanya berisi hasil/panggilan tool (bukan teks manusia)."""
    return (isinstance(content, list) and len(content) > 0 and
            all(isinstance(b, dict) and b.get("type") in ("tool_result", "tool_use", "image") for b in content))


def baca_sesi(path: str) -> dict | None:
    """Baca satu transkrip -> {sesi, cwd, turns:[(peran, teks)]}. None bila tak ada giliran nyata."""
    sesi = cwd = None
    turns: list[tuple[str, str]] = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            sesi = sesi or r.get("sessionId") or r.get("session_id")
            cwd = cwd or r.get("cwd")
            t = r.get("type")
            if t not in ("user", "assistant"):
                continue
            msg = r.get("message")
            if not isinstance(msg, dict):
                continue
            content = msg.get("content")
            if t == "user" and _hasil_tool(content):  # hasil tool, bukan pesan manusia
                continue
            teks = _teks_dari_content(content)
            if teks:
                turns.append(("user" if t == "user" else "assistant", teks))
    sesi = sesi or os.path.splitext(os.path.basename(path))[0]
    return {"sesi": sesi, "cwd": cwd, "turns": turns} if turns else None


def _rakit(turns: list[tuple[str, str]]) -> tuple[str, str]:
    isi = "\n\n".join(f"{'user' if p == 'user' else 'AI'}: {t}" for p, t in turns)
    if len(isi) > BATAS_ISI:
        isi = isi[: BATAS_ISI // 2] + "\n\n[...dipotong...]\n\n" + isi[-BATAS_ISI // 2:]
    prompt1 = next((t for p, t in turns if p == "user"), "")
    ringkas = (f"Chat Claude Code (histori): {prompt1[:120]}" if prompt1
               else f"Chat Claude Code (histori): {len(turns)} giliran")
    return isi, ringkas


def temukan_transkrip(root: str) -> list[str]:
    pola = os.path.join(root, "**", "*.jsonl")
    pisah = os.sep + "subagents" + os.sep
    return sorted(f for f in glob.glob(pola, recursive=True) if pisah not in f)


def _lingkup_untuk(cwd: str | None, paksa: str | None) -> str:
    if paksa:
        return paksa
    lingkup = tentukan_lingkup(cwd) if cwd else ""
    return lingkup if skema.lingkup_valid(lingkup) else "peran:asisten-ai"


def impor_histori(app: Aplikasi, root: str | None = None, tulis: bool = False,
                  lingkup_paksa: str | None = None) -> dict:
    if tulis and app.relay:
        return {"galat": "instans ini relay (baca-saja, K30); impor histori hanya ke store otoritatif laptop"}
    root = root or os.path.join(os.path.expanduser("~"), ".claude", "projects")
    if not os.path.isdir(root):
        return {"galat": f"folder transkrip tidak ditemukan: {root}"}
    files = temukan_transkrip(root)
    rencana: list[dict] = []
    dilewati = kosong = 0
    for path in files:
        s = baca_sesi(path)
        if not s:
            kosong += 1
            continue
        bersih = re.sub(r"[^A-Za-z0-9_-]", "_", s["sesi"])[:40]
        id_hist, id_hook = f"ep-histori-{bersih}", f"ep-sesi-{bersih}"
        if app.store.episode(id_hist) or app.store.episode(id_hook):
            dilewati += 1
            continue
        lingkup = _lingkup_untuk(s.get("cwd"), lingkup_paksa)
        isi, ringkas = _rakit(s["turns"])
        rencana.append({"id": id_hist, "lingkup": lingkup, "giliran": len(s["turns"]), "ringkas": ringkas[:100]})
        if tulis:
            app.store.tambah_episode(isi, id=id_hist, sumber="claude-code-histori", tier="I",
                                     lingkup=lingkup, jenis_kejadian="sukses", ringkas=ringkas)
    kunci = "diimpor" if tulis else "akan_diimpor"
    return {"ditemukan": len(files), kunci: len(rencana),
            "dilewati_sudah_ada": dilewati, "tanpa_giliran": kosong, "rencana": rencana}
