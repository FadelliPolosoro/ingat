# SPDX-License-Identifier: Apache-2.0
"""Jalur A — impor dari file ekspor resmi Claude.ai dan ChatGPT.

Claude.ai: Settings → Export → ZIP berisi conversations.json
ChatGPT: Settings → Data controls → Export data → ZIP berisi conversations.json

Keduanya menghasilkan file JSON dengan struktur berbeda. Modul ini membaca keduanya,
mengkonversi ke episode ingat, dan menyimpan ke store. Idempoten: episode yang sudah
ada (berdasar ID sumber) dilewati.

ID episode: ep-ekspor-<platform>-<hash_pendek_id_asli>
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import zipfile
from typing import Any

from . import skema
from .aplikasi import Aplikasi

BATAS_ISI = 8000
PLATFORM_CLAUDE = "claude"
PLATFORM_CHATGPT = "chatgpt"


def _hash_pendek(teks: str) -> str:
    return hashlib.sha256(teks.encode()).hexdigest()[:12]


def _potong(teks: str, batas: int = BATAS_ISI) -> str:
    if len(teks) <= batas:
        return teks
    return teks[:batas // 2] + "\n\n[...dipotong...]\n\n" + teks[-batas // 2:]


# ── Claude.ai ──

def _baca_claude_conversations(data: list[dict]) -> list[dict]:
    """Parse conversations.json dari ekspor Claude.ai."""
    hasil = []
    for conv in data:
        if not isinstance(conv, dict):
            continue
        conv_id = conv.get("uuid") or conv.get("id") or ""
        nama = conv.get("name") or ""
        pesan_list = conv.get("chat_messages") or []
        if not pesan_list:
            continue
        turns: list[tuple[str, str]] = []
        for msg in pesan_list:
            if not isinstance(msg, dict):
                continue
            pengirim = msg.get("sender") or msg.get("role") or ""
            teks = ""
            content = msg.get("content") or msg.get("text") or ""
            if isinstance(content, str):
                teks = content.strip()
            elif isinstance(content, list):
                bagian = []
                for blok in content:
                    if isinstance(blok, dict):
                        if blok.get("type") == "text":
                            bagian.append(str(blok.get("text", "")))
                        elif blok.get("type") == "tool_result":
                            continue
                    elif isinstance(blok, str):
                        bagian.append(blok)
                teks = "\n".join(bagian).strip()
            if not teks:
                continue
            peran = "user" if pengirim in ("human", "user") else "AI"
            turns.append((peran, teks))
        if not turns:
            continue
        isi = "\n\n".join(f"{p}: {t}" for p, t in turns)
        isi = _potong(isi)
        prompt1 = next((t for p, t in turns if p == "user"), "")
        ringkas = f"Ekspor Claude.ai: {nama or prompt1[:100]}" if nama else f"Ekspor Claude.ai: {prompt1[:100]}"
        hasil.append({
            "id_sumber": conv_id,
            "platform": PLATFORM_CLAUDE,
            "isi": isi,
            "ringkas": ringkas[:200],
            "giliran": len(turns),
            "nama": nama,
        })
    return hasil


# ── ChatGPT ──

def _baca_chatgpt_conversations(data: list[dict]) -> list[dict]:
    """Parse conversations.json dari ekspor ChatGPT."""
    hasil = []
    for conv in data:
        if not isinstance(conv, dict):
            continue
        conv_id = conv.get("id") or conv.get("conversation_id") or ""
        judul = conv.get("title") or ""
        mapping = conv.get("mapping") or {}
        if not isinstance(mapping, dict):
            continue
        nodes: list[tuple[float, str, str]] = []
        for node_id, node in mapping.items():
            if not isinstance(node, dict):
                continue
            msg = node.get("message")
            if not isinstance(msg, dict):
                continue
            role = (msg.get("author") or {}).get("role") or msg.get("role") or ""
            if role not in ("user", "assistant"):
                continue
            create_time = msg.get("create_time") or 0
            content = msg.get("content") or {}
            parts = content.get("parts") or []
            teks_list = []
            for part in parts:
                if isinstance(part, str):
                    teks_list.append(part)
                elif isinstance(part, dict) and part.get("content_type") == "text":
                    teks_list.append(str(part.get("text", "")))
            teks = "\n".join(teks_list).strip()
            if teks:
                nodes.append((float(create_time or 0), "user" if role == "user" else "AI", teks))
        nodes.sort(key=lambda x: x[0])
        turns = [(peran, teks) for _, peran, teks in nodes]
        if not turns:
            continue
        isi = "\n\n".join(f"{p}: {t}" for p, t in turns)
        isi = _potong(isi)
        prompt1 = next((t for p, t in turns if p == "user"), "")
        ringkas = f"Ekspor ChatGPT: {judul or prompt1[:100]}"
        hasil.append({
            "id_sumber": conv_id,
            "platform": PLATFORM_CHATGPT,
            "isi": isi,
            "ringkas": ringkas[:200],
            "giliran": len(turns),
            "nama": judul,
        })
    return hasil


# ── Deteksi dan baca ──

def _deteksi_platform(data: list[dict]) -> str | None:
    """Tebak platform dari struktur data."""
    if not data:
        return None
    sampel = data[0] if isinstance(data, list) and data else {}
    if not isinstance(sampel, dict):
        return None
    if "chat_messages" in sampel or "uuid" in sampel:
        return PLATFORM_CLAUDE
    if "mapping" in sampel:
        return PLATFORM_CHATGPT
    return None


def baca_dari_zip(path_zip: str) -> tuple[str | None, list[dict]]:
    """Baca file ZIP ekspor, kembalikan (platform, conversations)."""
    if not zipfile.is_zipfile(path_zip):
        return None, []
    with zipfile.ZipFile(path_zip, "r") as zf:
        for nama in zf.namelist():
            if nama.endswith("conversations.json") or nama == "conversations.json":
                with zf.open(nama) as f:
                    data = json.loads(f.read().decode("utf-8"))
                if isinstance(data, list):
                    platform = _deteksi_platform(data)
                    if platform == PLATFORM_CLAUDE:
                        return PLATFORM_CLAUDE, _baca_claude_conversations(data)
                    elif platform == PLATFORM_CHATGPT:
                        return PLATFORM_CHATGPT, _baca_chatgpt_conversations(data)
    return None, []


def baca_dari_json(path_json: str) -> tuple[str | None, list[dict]]:
    """Baca file conversations.json langsung (tanpa ZIP)."""
    with open(path_json, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        return None, []
    platform = _deteksi_platform(data)
    if platform == PLATFORM_CLAUDE:
        return PLATFORM_CLAUDE, _baca_claude_conversations(data)
    elif platform == PLATFORM_CHATGPT:
        return PLATFORM_CHATGPT, _baca_chatgpt_conversations(data)
    return None, []


def baca(path: str) -> tuple[str | None, list[dict]]:
    """Baca file ekspor (ZIP atau JSON), kembalikan (platform, list_percakapan)."""
    if path.lower().endswith(".zip"):
        return baca_dari_zip(path)
    if path.lower().endswith(".json"):
        return baca_dari_json(path)
    if zipfile.is_zipfile(path):
        return baca_dari_zip(path)
    return baca_dari_json(path)


# ── Impor ke store ──

def impor_ekspor(app: Aplikasi, path: str, tulis: bool = False,
                 lingkup_paksa: str | None = None) -> dict:
    """Impor file ekspor resmi ke store ingat.

    tulis=False → dry-run (cetak rencana tanpa menulis).
    Idempoten: episode ep-ekspor-<platform>-<hash> yang sudah ada dilewati.
    """
    if tulis and app.relay:
        return {"galat": "instans ini relay (baca-saja, K30); impor hanya ke store otoritatif"}
    try:
        platform, percakapan = baca(path)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as e:
        return {"galat": f"gagal membaca berkas: {e}"}
    if platform is None:
        return {"galat": "format tidak dikenali — bukan ekspor Claude.ai atau ChatGPT"}
    rencana: list[dict] = []
    dilewati = 0
    for conv in percakapan:
        id_ep = f"ep-ekspor-{conv['platform']}-{_hash_pendek(conv['id_sumber'])}"
        if app.store.episode(id_ep):
            dilewati += 1
            continue
        lingkup = lingkup_paksa or f"peran:asisten-{conv['platform']}"
        if not skema.lingkup_valid(lingkup):
            lingkup = "peran:asisten-ai"
        rencana.append({
            "id": id_ep,
            "lingkup": lingkup,
            "giliran": conv["giliran"],
            "ringkas": conv["ringkas"],
        })
        if tulis:
            app.store.tambah_episode(
                conv["isi"], id=id_ep, sumber=f"ekspor-{conv['platform']}",
                tier="I", lingkup=lingkup, jenis_kejadian="sukses",
                ringkas=conv["ringkas"],
            )
    kunci = "diimpor" if tulis else "akan_diimpor"
    return {
        "platform": platform,
        "ditemukan": len(percakapan),
        kunci: len(rencana),
        "dilewati_sudah_ada": dilewati,
        "rencana": rencana,
    }
