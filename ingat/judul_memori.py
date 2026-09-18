# SPDX-License-Identifier: Apache-2.0
"""Rapikan 'nama' memori yang tersimpan (18 Sep 2026).

Masalah: `ringkas` episode sering generik/berulang ("Percakapan gemini.google.com: 3 pesan")
atau `sumber` lama berupa free-text kacau — daftar memori jadi mengacak. Modul ini memberi tiap
episode JUDUL bersih & deskriptif dengan mempelajari isinya.

NON-DESTRUKTIF: judul ditulis ke tabel sidecar `judul_memori`, `sumber`/`ringkas`/isi asli TIDAK
disentuh (undo = kosongkan tabel). `sumber` sengaja tak diubah karena indikator kesehatan koneksi
& peta klien di panel bergantung padanya.

Otak bisa di-swap: `judul_heuristik` (baku, tanpa LLM, instan) atau nanti `judul_llm` (model instruct
lokal) — keduanya `(ep, isi) -> str`, jadi `rapikan(otak_fn=...)` cukup diganti fungsinya.
"""
from __future__ import annotations

import re

from . import skema

SKEMA_JUDUL = """
CREATE TABLE IF NOT EXISTS judul_memori (
  item_id TEXT PRIMARY KEY,
  judul   TEXT NOT NULL,
  otak    TEXT NOT NULL,
  waktu   TEXT NOT NULL
);
"""

# Prefiks boilerplate yang menempel di depan ringkas/isi tanpa memberi makna.
_PREFIKS = re.compile(
    r'^(chat claude code \(histori\)|percakapan\s+[^:]{1,40}|chat\s+[^:]{1,40}|sesi\s+[^:]{1,40}'
    r'|situasi serupa dengan|bash gagal|memori|catatan|ringkasan)\s*[:\-–]\s*',
    re.I,
)
# "Percakapan gemini.google.com: 3 pesan" — murni boilerplate, tak ada isi: pakai verbatim.
_GENERIK = re.compile(r'^percakapan\s+\S+\s*:\s*\d+\s*pesan\.?$', re.I)
# Penanda peran di awal baris verbatim (biar tak jadi judul).
_PERAN = re.compile(r'^\s*(user|assistant|human|ai|pengguna|asisten)\s*[:>\-]\s*', re.I)
# Baris metadata header ekstensi ("[percakapan host/path] N pesan (...)") atau "N pesan ...".
_META_BARIS = re.compile(r'^\s*\[[^\]]*\]|^\s*\d+\s*pesan\b', re.I)
# Stempel waktu di depan baris pesan ("17:23:17 user: ...").
_STEMPEL = re.compile(r'^\s*\d{1,2}:\d{2}(?::\d{2})?\s+')

_NAMA_SUMBER = {
    "browser:gemini.google.com": "Gemini",
    "browser:chatgpt.com": "ChatGPT",
    "browser:chat.openai.com": "ChatGPT",
    "browser:claude.ai": "Claude.ai",
    "browser:www.perplexity.ai": "Perplexity",
    "browser:perplexity.ai": "Perplexity",
    "mcp": "Claude Desktop",
    "claude-code": "Claude Code",
    "claude-code-histori": "Claude Code",
}


def _bersih(teks) -> str:
    return re.sub(r"\s+", " ", str(teks or "")).strip().strip("\"'“”‘’ ").strip()


def _potong(teks: str, maks_kata: int = 10, maks_char: int = 64) -> str:
    kata = teks.split()
    if len(kata) > maks_kata:
        teks = " ".join(kata[:maks_kata]) + "…"
    if len(teks) > maks_char:
        teks = teks[: maks_char - 1].rstrip(" ,.;:-") + "…"
    return teks


def _label_sumber(ep) -> str:
    """Cadangan terakhir bila tak ada isi bermakna: nama platform + tanggal."""
    s = str(getattr(ep, "sumber", "") or "")
    nama = _NAMA_SUMBER.get(s)
    if not nama:
        nama = s[8:] if s.startswith("browser:") else (s or "Memori")
    tgl = str(getattr(ep, "waktu", "") or "")[:10]
    return f"{nama} · {tgl}" if tgl else nama


def _kalimat_pertama_bermakna(teks: str) -> str:
    """Pesan pertama bermakna dari isi verbatim: lompati header metadata, strip stempel & peran."""
    for baris in str(teks or "").splitlines():
        if not baris.strip() or _META_BARIS.match(baris):
            continue
        b = _STEMPEL.sub("", baris)
        b = _PERAN.sub("", b).strip()
        b = _PREFIKS.sub("", b).strip()
        if len(b) >= 6:
            m = re.split(r"(?<=[.!?])\s", b, maxsplit=1)  # kalimat pertama saja
            return m[0]
    return ""


_LEWAT_TOKEN = {"sudo", "env", "nohup", "time"}


def _program_shell(cmd: str) -> str:
    """Nama program pertama dari sebuah perintah shell, lewati env-var & pembungkus."""
    toks = cmd.split()
    i = 0
    while i < len(toks):
        t = toks[i]
        if re.match(r"^\w+=", t):  # VAR=nilai di depan perintah
            i += 1
            continue
        if t in _LEWAT_TOKEN:
            i += 1
            continue
        if t == "timeout":
            i += 1
            if i < len(toks) and re.match(r"^[\d.]+$", toks[i]):
                i += 1
            continue
        return t.split("/")[-1].split("\\")[-1][:24]  # basename
    return ""


def _judul_teknis(ringkas: str) -> str:
    """Pola teknis dominan (claude-code) → judul ringkas bermakna, bukan buang perintah mentah."""
    r = ringkas.strip()
    m = re.match(r"^Bash gagal:\s*(.+)", r, re.I)
    if m:
        prog = _program_shell(m.group(1))
        return f"Perintah gagal: {prog}" if prog else "Perintah gagal"
    m = re.search(r"mcp__[\w-]+?__(\w+)", r)  # nama tool MCP → segmen terakhir
    if m:
        ekor = " gagal" if re.search(r"\bgagal\b", r, re.I) else ""
        return f"Alat {m.group(1)}{ekor}"
    m = re.match(r"^Sesi Claude Code:\s*(\d+)\s*langkah", r, re.I)
    if m:
        return f"Sesi Claude Code · {m.group(1)} langkah"
    return ""


def judul_heuristik(ep, isi: str | None = None) -> str:
    """Judul bersih dari sebuah episode. Tanpa LLM, deterministik."""
    ringkas = _bersih(getattr(ep, "ringkas", ""))
    teknis = _judul_teknis(ringkas)
    if teknis:
        return _potong(teknis)
    kandidat = ""
    if ringkas and not _GENERIK.match(ringkas):
        kandidat = _bersih(_PREFIKS.sub("", ringkas))
    if len(kandidat) < 6 and isi:
        kandidat = _bersih(_kalimat_pertama_bermakna(isi))
    if len(kandidat) < 6:
        return _label_sumber(ep)
    # kapitalkan huruf pertama saja; sisanya biarkan (istilah/URL tetap utuh)
    if kandidat and kandidat[0].islower():
        kandidat = kandidat[0].upper() + kandidat[1:]
    return _potong(kandidat)


def _pastikan_tabel(store):
    store.db.execute(SKEMA_JUDUL)
    store.db.commit()


def rapikan(store, otak_fn=judul_heuristik, otak: str = "heuristik", batas: int | None = None, tulis: bool = True) -> dict:
    """Beri judul rapi ke semua episode. Kembalikan {diproses, ditulis, contoh:[{sumber,ringkas,judul}]}."""
    _pastikan_tabel(store)
    eps = store.episode_semua()
    if batas:
        eps = eps[:batas]
    waktu = skema.sekarang()
    ditulis = 0
    contoh = []
    for ep in eps:
        isi = None
        ref = getattr(ep, "isi_ref", "") or ""
        if ref:
            try:
                isi = store.buka_dingin(ref).get("isi")
            except Exception:
                isi = None
        j = otak_fn(ep, isi)
        if tulis:
            store.db.execute(
                "INSERT OR REPLACE INTO judul_memori(item_id,judul,otak,waktu) VALUES(?,?,?,?)",
                (ep.id, j, otak, waktu),
            )
            ditulis += 1
        if len(contoh) < 15:
            contoh.append({
                "sumber": str(getattr(ep, "sumber", ""))[:32],
                "ringkas": _bersih(getattr(ep, "ringkas", ""))[:48],
                "judul": j,
            })
    if tulis:
        store.db.commit()
    return {"diproses": len(eps), "ditulis": ditulis, "contoh": contoh}


def judul_untuk(store, item_id: str) -> str | None:
    try:
        b = store.db.execute("SELECT judul FROM judul_memori WHERE item_id=?", (item_id,)).fetchone()
        return b["judul"] if b else None
    except Exception:
        return None


def berapa_berjudul(store) -> int:
    try:
        _pastikan_tabel(store)
        return store.db.execute("SELECT COUNT(*) FROM judul_memori").fetchone()[0]
    except Exception:
        return 0


def kosongkan(store) -> int:
    """Undo: hapus semua judul rapi (episode asli tak pernah tersentuh)."""
    _pastikan_tabel(store)
    n = store.db.execute("SELECT COUNT(*) FROM judul_memori").fetchone()[0]
    store.db.execute("DELETE FROM judul_memori")
    store.db.commit()
    return n
