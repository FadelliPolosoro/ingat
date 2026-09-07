# SPDX-License-Identifier: Apache-2.0
"""MCP Streamable HTTP — supaya `ingat` bisa dipasang sebagai *Custom Connector* di claude.ai (web/mobile/desktop),
sejajar dengan GitHits/Zernio di menu Connectors. Spek: MCP 2025-06-18, mode respons JSON (bukan SSE — diizinkan spek).

Dipasang di dalam server REST (`api.py`) pada path `/mcp`. Dua cara autentikasi:
  1. Header `Authorization: Bearer <INGAT_TOKEN>`  — Claude Code (`--header`), klien yang mendukung header.
  2. Rahasia di path: `/mcp/<INGAT_TOKEN>`         — untuk claude.ai remote tanpa OAuth: URL adalah kunci.
     Konsekuensi: URL harus diperlakukan seperti kata sandi (jangan dibagikan, matikan access log Caddy untuk path ini).

Yang SENGAJA belum ada: OAuth 2.1 + Dynamic Client Registration. Beberapa konteks claude.ai (terutama org-managed)
mengasumsikan OAuth dan menolak server tanpa metadata OAuth. Kalau URL rahasia ditolak oleh akunmu, itu tiket berikutnya —
bukan kegagalan server ini. Verifikasi dulu dengan `curl` (lihat pasang/README-connector.md).
"""
from __future__ import annotations

import hmac
import json
import secrets

from .aplikasi import Aplikasi
from .mcp_stdio import tangani_pesan

VERSI_PROTOKOL = "2025-06-18"


def token_cocok(token_diberi: str | None, token_benar: str) -> bool:
    return bool(token_diberi) and hmac.compare_digest(token_diberi, token_benar)


def ambil_token_dari_path(path: str, awalan: str = "/mcp") -> str | None:
    """`/mcp/<token>` → token; `/mcp` → None."""
    sisa = path[len(awalan):].strip("/")
    return sisa.split("/")[0] if sisa else None


def tangani_http(app: Aplikasi, metode: str, badan_mentah: bytes | None, sesi_masuk: str | None) -> tuple[int, dict, dict | list | None]:
    """Kembalikan (status, header_tambahan, badan_json). Transport-agnostik: dipanggil handler REST.

    Aturan spek Streamable HTTP yang ditegakkan:
    - POST notifikasi/respons-saja → 202 tanpa badan.
    - POST request → 200 application/json.
    - GET (buka stream SSE) → 405: server ini tidak menawarkan stream.
    - HEAD → 200 tanpa badan (beberapa klien memakai HEAD untuk deteksi).
    - DELETE → 200 (sesi ditutup; server stateless, tidak ada yang perlu dihapus).
    - Header `Mcp-Session-Id` diberikan saat initialize dan diterima apa adanya sesudahnya.
    """
    header = {"MCP-Protocol-Version": VERSI_PROTOKOL}
    if metode == "HEAD":
        return 200, header, None
    if metode == "GET":
        return 405, {**header, "Allow": "POST, HEAD, DELETE"}, {"galat": "server ini tidak menawarkan stream SSE; pakai POST"}
    if metode == "DELETE":
        return 200, header, None
    if metode != "POST":
        return 405, {**header, "Allow": "POST, HEAD, DELETE"}, None
    try:
        pesan = json.loads((badan_mentah or b"").decode("utf-8") or "null")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return 400, header, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
    if pesan is None:
        return 400, header, {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "badan kosong"}}

    daftar = pesan if isinstance(pesan, list) else [pesan]
    if not all(isinstance(p, dict) for p in daftar):
        return 400, header, {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "permintaan tidak valid"}}
    hasil = []
    sesi_keluar = sesi_masuk
    for p in daftar:
        r = tangani_pesan(app, p)
        if p.get("method") == "initialize" and not sesi_keluar:
            sesi_keluar = secrets.token_urlsafe(16)
        if r is not None:
            hasil.append(r)
    if sesi_keluar:
        header["Mcp-Session-Id"] = sesi_keluar
    if not hasil:
        return 202, header, None  # hanya notifikasi
    return 200, header, (hasil if isinstance(pesan, list) else hasil[0])
