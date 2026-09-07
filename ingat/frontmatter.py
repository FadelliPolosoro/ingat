# SPDX-License-Identifier: Apache-2.0
"""Frontmatter untuk catatan Obsidian.

Memakai PyYAML bila tersedia. Tanpa PyYAML, parser subset ini menangani
persis bentuk yang dipakai skema Bab 6: skalar, list inline `[a, b]`,
list blok `- item`, dict inline `{k: v}`, null/true/false/angka, string
berkutip. Nested blok dict TIDAK didukung — skema kita memang datar.
"""
from __future__ import annotations

import json
import re

try:  # opsional
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

import datetime as _dt

_PEMISAH = "---"


def _skalar(teks: str):
    t = teks.strip()
    if t == "" or t in ("null", "~"):
        return None
    if t in ("true", "True"):
        return True
    if t in ("false", "False"):
        return False
    if (t.startswith('"') and t.endswith('"')) or (t.startswith("'") and t.endswith("'")):
        try:
            return json.loads(t) if t.startswith('"') else t[1:-1]
        except Exception:
            return t[1:-1]
    if re.fullmatch(r"-?\d+", t):
        return int(t)
    if re.fullmatch(r"-?\d+\.\d+", t):
        return float(t)
    return t


def _pisah_koma(t: str) -> list[str]:
    hasil, buf, kutip = [], "", None
    for c in t:
        if kutip:
            buf += c
            if c == kutip:
                kutip = None
        elif c in "\"'":
            kutip = c
            buf += c
        elif c == ",":
            hasil.append(buf)
            buf = ""
        else:
            buf += c
    if buf.strip():
        hasil.append(buf)
    return hasil


def _nilai(t: str):
    t = t.strip()
    if t.startswith("[") and t.endswith("]"):
        dalam = t[1:-1].strip()
        return [_skalar(x) for x in _pisah_koma(dalam)] if dalam else []
    if t.startswith("{") and t.endswith("}"):
        dalam = t[1:-1].strip()
        d = {}
        for pasangan in _pisah_koma(dalam) if dalam else []:
            if ":" in pasangan:
                k, v = pasangan.split(":", 1)
                d[k.strip().strip('"').strip("'")] = _skalar(v)
        return d
    return _skalar(t)


def _parse_subset(teks: str) -> dict:
    meta: dict = {}
    kunci_terakhir = None
    for baris in teks.splitlines():
        if not baris.strip() or baris.lstrip().startswith("#"):
            continue
        if baris.lstrip().startswith("- ") and kunci_terakhir is not None:
            if not isinstance(meta.get(kunci_terakhir), list):
                meta[kunci_terakhir] = []
            meta[kunci_terakhir].append(_skalar(baris.lstrip()[2:]))
            continue
        if ":" not in baris:
            continue
        k, v = baris.split(":", 1)
        k = k.strip()
        kunci_terakhir = k
        meta[k] = _nilai(v) if v.strip() else None
    return meta


def _dump_skalar(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    if (s == "" or re.search(r"[:#\[\]{},\"'\n]|^\s|\s$", s) or s in ("null", "true", "false", "~", "True", "False")
            or re.fullmatch(r"-?\d+(\.\d+)?", s)):
        return json.dumps(s, ensure_ascii=False)
    return s


def _dump_subset(meta: dict) -> str:
    baris = []
    for k, v in meta.items():
        if isinstance(v, list):
            if not v:
                baris.append(f"{k}: []")
            elif all(isinstance(x, (str, int, float, bool)) or x is None for x in v) and len(v) <= 6 and all(len(str(x)) < 60 for x in v):
                baris.append(f"{k}: [{', '.join(_dump_skalar(x) for x in v)}]")
            else:
                baris.append(f"{k}:")
                baris.extend(f"  - {_dump_skalar(x)}" for x in v)
        elif isinstance(v, dict):
            if not v:
                baris.append(f"{k}: {{}}")
            else:
                baris.append(f"{k}: {{{', '.join(f'{a}: {_dump_skalar(b)}' for a, b in v.items())}}}")
        else:
            baris.append(f"{k}: {_dump_skalar(v)}")
    return "\n".join(baris) + "\n"


def _tanggal_ke_teks(nilai):
    """PyYAML (resolver bawaan YAML 1.1) mengubah skalar tanggal TELANJANG seperti `2026-01-01`
    menjadi objek Python `datetime.date`/`datetime.datetime` secara otomatis — bukan string.
    Kontrak kita (skema/ingat.sql, docs Bab 6) menyatakan semua waktu adalah TEXT ISO 8601, dan
    seluruh kode hilir (skema.py, obsidian.py, gateway.py) memperlakukan field bertanggal sebagai
    str (slicing, perbandingan leksikografis, json.dumps). Dibiarkan sebagai date object, ini bug
    laten yang meledak sunyi di mana pun PyYAML terpasang — termasuk Docker produksi (Dockerfile
    memasang pyyaml). Dinetralkan di SATU titik ini: setelah parse, semua date/datetime dipaksa
    balik ke string ISO, secara rekursif (dict, list). Bukan menghapus kenyamanan PyYAML yang lain
    (bool/int/float/null/nested) — hanya menutup satu kuirk resolver timestamp-nya.
    """
    if isinstance(nilai, _dt.datetime):
        return nilai.isoformat()
    if isinstance(nilai, _dt.date):
        return nilai.isoformat()
    if isinstance(nilai, dict):
        return {k: _tanggal_ke_teks(v) for k, v in nilai.items()}
    if isinstance(nilai, list):
        return [_tanggal_ke_teks(v) for v in nilai]
    return nilai


def muat(teks: str) -> tuple[dict, str]:
    """Kembalikan (meta, badan). Tanpa frontmatter -> ({}, teks)."""
    if not teks.startswith(_PEMISAH):
        return {}, teks
    potong = teks.split("\n", 1)
    if len(potong) < 2:
        return {}, teks
    sisa = potong[1]
    akhir = re.search(r"^---\s*$", sisa, flags=re.M)
    if not akhir:
        return {}, teks
    blok = sisa[: akhir.start()]
    badan = sisa[akhir.end():].lstrip("\n")
    if yaml is not None:
        try:
            meta = yaml.safe_load(blok) or {}
            if isinstance(meta, dict):
                return _tanggal_ke_teks(meta), badan
        except Exception:
            pass
    return _parse_subset(blok), badan


def dump(meta: dict, badan: str = "") -> str:
    if yaml is not None:
        blok = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False, default_flow_style=None)
        if blok.lstrip().startswith("{"):
            # PyYAML meringkas mapping yang semua nilainya skalar menjadi satu baris flow `{a: 1, b: 2}`.
            # Itu melanggar kontrak frontmatter (satu kunci per baris) dan tidak terbaca parser subset
            # pada instalasi tanpa PyYAML. Paksa satu kunci per baris.
            blok = _dump_subset(meta)
    else:
        blok = _dump_subset(meta)
    return f"{_PEMISAH}\n{blok}{_PEMISAH}\n\n{badan.rstrip()}\n" if badan else f"{_PEMISAH}\n{blok}{_PEMISAH}\n"
