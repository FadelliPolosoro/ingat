# SPDX-License-Identifier: Apache-2.0
"""Redaksi kredensial SEBELUM tulis + penanda tier (K10, KEPUTUSAN.md).

Kredensial (kunci API, token, password, private key) diganti ``[REDAKSI:<jenis>]`` — nilainya
tidak pernah disimpan. Data pribadi (NIK, NPWP, rekening) TIDAK diredaksi, tetapi episode
dinaikkan ke tier S. Satu-satunya titik panggil: ``Store.tambah_episode``.
Tambah pola = tambah uji di uji/uji_redaksi.py. Padanan TS: port/typescript/src/tangkap/.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# (jenis, pola, fungsi_ganti|None). Urutan penting: yang spesifik dulu, pasangan kunci=nilai terakhir.
POLA_KREDENSIAL: list[tuple[str, re.Pattern, object]] = [
    ("kunci-privat", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"), None),
    ("kunci-anthropic", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}"), None),
    ("kunci-openai", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}"), None),
    ("token-github", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"), None),
    ("kunci-aws", re.compile(r"\bAKIA[0-9A-Z]{16}\b"), None),
    ("token-slack", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"), None),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"), None),
    ("bearer", re.compile(r"\bBearer\s+(?!\[REDAKSI:)[A-Za-z0-9._~+/=-]{16,}"), None),
    (
        "pasangan-rahasia",
        # api_key = "...", password: ..., KUNCI_ENKRIPSI=... — wajib pemisah : atau = ; nilai ≥ 8 karakter tanpa spasi.
        # Tanpa pemisah sengaja tidak ditangkap: "token dikembalikan" adalah prosa.
        re.compile(
            r"\b(api[_-]?key|secret[_-]?key|secret|passw(?:or)?d|token|bearer|kunci_enkripsi|kunci_csrf)\b"
            r"(\s*[:=]\s*)(['\"]?)(?!\[REDAKSI:)([^\s'\"]{8,})\3",
            re.IGNORECASE,
        ),
        lambda m: f"{m.group(1)}{m.group(2)}{m.group(3)}[REDAKSI:pasangan-rahasia]{m.group(3)}",
    ),
]

POLA_TIER_S: list[tuple[str, re.Pattern]] = [
    ("nik", re.compile(r"\b\d{16}\b")),
    ("npwp", re.compile(r"\b\d{2}\.\d{3}\.\d{3}\.\d-\d{3}\.\d{3}\b")),
    ("npwp-16", re.compile(r"\bNPWP\s*[:#]?\s*\d{15,16}\b", re.IGNORECASE)),
    ("rekening", re.compile(r"\b(?:no\.?\s*)?rek(?:ening)?\s*[:#]?\s*\d{10,16}\b", re.IGNORECASE)),
    ("kata-kunci-sensitif", re.compile(r"\b(payroll|slip gaji|bukti potong|SPT|faktur pajak|e-faktur)\b", re.IGNORECASE)),
]


@dataclass
class HasilRedaksi:
    teks: str
    jenis: list[str] = field(default_factory=list)
    jumlah: int = 0


def redaksi(teks: str) -> HasilRedaksi:
    hasil = HasilRedaksi(teks=teks)
    for jenis, pola, ganti in POLA_KREDENSIAL:
        n = 0

        def _g(m, _jenis=jenis, _ganti=ganti):
            nonlocal n
            n += 1
            return _ganti(m) if _ganti else f"[REDAKSI:{_jenis}]"

        hasil.teks = pola.sub(_g, hasil.teks)
        if n:
            hasil.jenis.append(jenis)
            hasil.jumlah += n
    return hasil


def tandai_tier(teks: str, dasar: str = "I") -> tuple[str, list[str]]:
    """Kembalikan (tier, alasan). Naik ke S bila pola terpicu; tidak pernah turun otomatis."""
    alasan = [nama for nama, pola in POLA_TIER_S if pola.search(teks)]
    if alasan:
        return "S", alasan
    return dasar, []
