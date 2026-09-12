# SPDX-License-Identifier: Apache-2.0
"""MCP server (stdio) — konektor masuk untuk Claude Code / Claude Desktop / klien MCP lain.

Protokol: JSON-RPC 2.0, satu pesan per baris di stdin/stdout.
Tools yang diekspos = tepat empat pintu di Bab 8; tidak ada tool "hapus".
"""
from __future__ import annotations

import json
import sys

from . import __version__, __penulis__
from .aplikasi import Aplikasi
from .relay import TOOL_TULIS, tolak as relay_tolak

TOOLS = [
    {"name": "ingat", "description": "L-tarik: ambil memori berperingkat (norma per tanggal, pelajaran, prosedur) dalam lingkup. Wajib: query, lingkup.",
     "inputSchema": {"type": "object", "required": ["query", "lingkup"], "properties": {
         "query": {"type": "string"}, "lingkup": {"type": "string", "description": "global | proyek:<nama> | peran:<nama>"},
         "jenis": {"type": "string", "enum": ["norma", "pelajaran", "prosedur"]},
         "tanggal_peristiwa": {"type": "string", "description": "YYYY-MM-DD; kosong = hari ini (asumsi dilaporkan)"},
         "tugas": {"type": "string", "description": "isi bila query bertipe 'cara' — mengaktifkan pencocokan prosedur"},
         "lingkungan": {"type": "object", "description": "mis. {\"node\": \"22\", \"tailwind\": \"4\"}"},
         "anggaran_token": {"type": "integer"}, "sesi": {"type": "string"}}}},
    {"name": "muat_startup", "description": "L-peta + L-aturan untuk awal sesi. Panggil sekali di awal.",
     "inputSchema": {"type": "object", "required": ["lingkup"], "properties": {
         "lingkup": {"type": "string"}, "tugas": {"type": "string"}, "lingkungan": {"type": "object"}, "sesi": {"type": "string"}}}},
    {"name": "buka_bukti", "description": "L-bukti: isi verbatim SATU episode. Hanya dipanggil bila benar-benar perlu.",
     "inputSchema": {"type": "object", "required": ["id"], "properties": {"id": {"type": "string"}, "sesi": {"type": "string"}}}},
    {"name": "catat_episode", "description": "Catat kejadian (koreksi/kegagalan/pola/sukses) sebagai episode L0. Kredensial diredaksi sebelum tulis; tier S tersimpan tetapi tidak pernah dikirim ke LLM (K10).",
     "inputSchema": {"type": "object", "required": ["isi", "lingkup", "jenis_kejadian", "ringkas"], "properties": {
         "isi": {"type": "string"}, "lingkup": {"type": "string"}, "jenis_kejadian": {"type": "string", "enum": ["koreksi", "kegagalan", "pola", "sukses"]},
         "ringkas": {"type": "string"}, "tier": {"type": "string", "enum": ["P", "I", "S"], "default": "I"},
         "sumber": {"type": "string", "default": "mcp"}, "instrumen": {"type": "array", "items": {"type": "string"}},
         "langkah": {"type": "array", "items": {"type": "string"}}, "sesi": {"type": "string"}}}},
]


def tools_untuk(app: Aplikasi) -> list[dict]:
    """Daftar tool yang diiklankan. Di relay (K30) tool tulis tidak ditawarkan sama sekali."""
    if getattr(app, "relay", False):
        return [t for t in TOOLS if t["name"] not in TOOL_TULIS]
    return TOOLS


def _panggil(app: Aplikasi, nama: str, arg: dict) -> dict:
    # Menyembunyikan dari tools/list saja tidak cukup: klien bisa memanggil namanya begitu saja.
    if getattr(app, "relay", False) and nama in TOOL_TULIS:
        raise relay_tolak(f"tool '{nama}'")
    if nama == "ingat":
        return app.gateway.ingat(**{k: arg[k] for k in ("query", "lingkup", "jenis", "tanggal_peristiwa", "tugas", "lingkungan", "anggaran_token", "sesi") if k in arg})
    if nama == "muat_startup":
        return app.gateway.muat_startup(**{k: arg[k] for k in ("lingkup", "tugas", "lingkungan", "sesi") if k in arg})
    if nama == "buka_bukti":
        return app.gateway.buka_bukti(arg["id"], arg.get("sesi", ""))
    if nama == "catat_episode":
        ep = app.store.tambah_episode(arg.pop("isi"), sumber=arg.pop("sumber", "mcp"), tier=arg.pop("tier", "I"),
                                      **{k: arg[k] for k in ("lingkup", "jenis_kejadian", "ringkas", "instrumen", "langkah", "sesi") if k in arg})
        return {"id": ep.id, "bobot": ep.bobot}
    raise KeyError(f"tool tidak dikenal: {nama}")


def tangani_pesan(app: Aplikasi, pesan: dict) -> dict | None:
    """Tangani SATU pesan JSON-RPC. Mengembalikan respons, atau None untuk notifikasi (tanpa id).
    Dipakai oleh transport stdio (fungsi `layani`) dan Streamable HTTP (`mcp_http.py`) — satu logika, dua pintu."""
    id_, metode, param = pesan.get("id"), pesan.get("method"), pesan.get("params") or {}
    if metode == "initialize":
        return {"jsonrpc": "2.0", "id": id_, "result": {
            "protocolVersion": param.get("protocolVersion", "2025-06-18"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "ingat", "version": __version__, "title": f"ingat — {__penulis__}"}}}
    if metode is None or str(metode).startswith("notifications/"):
        return None
    if metode == "ping":
        return {"jsonrpc": "2.0", "id": id_, "result": {}}
    if metode == "tools/list":
        return {"jsonrpc": "2.0", "id": id_, "result": {"tools": tools_untuk(app)}}
    if metode == "tools/call":
        try:
            hasil = _panggil(app, param.get("name", ""), dict(param.get("arguments") or {}))
            return {"jsonrpc": "2.0", "id": id_, "result": {"content": [{"type": "text", "text": json.dumps(hasil, ensure_ascii=False)}], "isError": False}}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": id_, "result": {"content": [{"type": "text", "text": f"{type(e).__name__}: {e}"}], "isError": True}}
    if id_ is not None:
        return {"jsonrpc": "2.0", "id": id_, "error": {"code": -32601, "message": f"metode tidak dikenal: {metode}"}}
    return None


def layani(app: Aplikasi, masuk=None, keluar=None):
    masuk = masuk or sys.stdin
    keluar = keluar or sys.stdout

    def kirim(obj):
        keluar.write(json.dumps(obj, ensure_ascii=False) + "\n")
        keluar.flush()

    for baris in masuk:
        baris = baris.strip()
        if not baris:
            continue
        try:
            pesan = json.loads(baris)
        except json.JSONDecodeError:
            kirim({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}})
            continue
        respons = tangani_pesan(app, pesan)
        if respons is not None:
            kirim(respons)
