# SPDX-License-Identifier: Apache-2.0
"""Verifikasi dua langkah MANDIRI (TOTP, RFC 6238) — jalur masuk dashboard yang TIDAK bergantung Google
sama sekali. Cocok untuk aplikasi authenticator apa pun (Google Authenticator, Authy, Bitwarden,
1Password, dll. — semuanya mengimplementasikan standar terbuka yang sama, bukan produk Google
tertentu). Dibangun sebagai jalur cadangan (K26): kalau OAuth Google jadi kendala (status "belum
diverifikasi", batas test users, dsb.), ini tetap jalan karena tidak memanggil server pihak mana pun.

Murni stdlib: hmac + hashlib + struct + base64 + time. Diverifikasi terhadap vektor uji resmi
RFC 6238 Lampiran B (bukan cuma dipercaya sendiri) — lihat uji/uji_auth_totp.py.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets as _secrets
import struct
import time
import urllib.parse

LANGKAH_DETIK = 30
JUMLAH_DIGIT = 6
JENDELA_DEFAULT = 1  # ±1 langkah (±30 detik) toleransi jam tidak sinkron


def buat_rahasia(panjang_byte: int = 20) -> str:
    """Rahasia baru, base32 (format yang dipahami semua aplikasi authenticator)."""
    return base64.b32encode(_secrets.token_bytes(panjang_byte)).decode().rstrip("=")


def _hotp(rahasia_b32: str, counter: int, digit: int = JUMLAH_DIGIT) -> str:
    pad = rahasia_b32 + "=" * ((8 - len(rahasia_b32) % 8) % 8)
    kunci = base64.b32decode(pad.upper())
    pesan = struct.pack(">Q", counter)
    h = hmac.new(kunci, pesan, hashlib.sha1).digest()
    offset = h[-1] & 0x0F
    kode_bin = struct.unpack(">I", h[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(kode_bin % (10 ** digit)).zfill(digit)


def kode_sekarang(rahasia_b32: str, waktu: float | None = None, langkah: int = LANGKAH_DETIK,
                   digit: int = JUMLAH_DIGIT) -> str:
    t = int((waktu if waktu is not None else time.time()) // langkah)
    return _hotp(rahasia_b32, t, digit)


def verifikasi_kode(rahasia_b32: str, kode: str, waktu: float | None = None, langkah: int = LANGKAH_DETIK,
                     jendela: int = JENDELA_DEFAULT, digit: int = JUMLAH_DIGIT) -> bool:
    kode = str(kode).strip()
    if not kode.isdigit() or len(kode) != digit:
        return False
    t0 = int((waktu if waktu is not None else time.time()) // langkah)
    for delta in range(-jendela, jendela + 1):
        if hmac.compare_digest(_hotp(rahasia_b32, t0 + delta, digit), kode):
            return True
    return False


def otpauth_url(rahasia_b32: str, akun_label: str = "pemilik", penerbit: str = "ingat") -> str:
    """URI standar yang dipindai QR code oleh aplikasi authenticator mana pun."""
    q = urllib.parse.urlencode({"secret": rahasia_b32, "issuer": penerbit, "algorithm": "SHA1",
                                "digits": JUMLAH_DIGIT, "period": LANGKAH_DETIK})
    label = urllib.parse.quote(f"{penerbit}:{akun_label}")
    return f"otpauth://totp/{label}?{q}"
