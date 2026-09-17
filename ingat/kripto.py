# SPDX-License-Identifier: Apache-2.0
"""Enkripsi/dekripsi tarball backup — 4 lapisan perlindungan (K28).

Layer 1: Fernet (AES-128-CBC + HMAC-SHA256), PBKDF2-SHA256 600k iterasi
Layer 2: ChaCha20-Poly1305 envelope — kunci terpisah, authenticated encryption
Layer 3: HMAC-SHA256 luar — integritas seluruh payload terverifikasi sebelum dekripsi
Layer 4: Header anti-tamper — nonce + timestamp + versi, di-sign HMAC

Format berkas v2 (INGAT2):
  Header (60 byte):
    magic         b"INGAT2"     6 byte
    versi         0x02          1 byte
    flags         0x00          1 byte (cadangan)
    timestamp     uint64 BE     8 byte (unix epoch detik)
    salt_dalam    random        16 byte (PBKDF2 → kunci Fernet)
    salt_luar     random        16 byte (PBKDF2 → kunci ChaCha20)
    nonce         random        12 byte (ChaCha20-Poly1305 IV)
  hmac_header     HMAC-SHA256   32 byte (L4 — header harus utuh)
  ciphertext      variabel      ChaCha20-Poly1305(Fernet(plaintext))
  hmac_total      HMAC-SHA256   32 byte (L3 — semua byte di atas harus utuh)

Salt, nonce, dan timestamp selalu berbeda → output berubah total walau isi dan
sandi sama. Backward compatible: masih bisa membaca format v1 (INGAT1).

Dependensi: `cryptography` (opsional — hanya untuk fitur enkripsi).
"""
from __future__ import annotations

import hashlib
import hmac as _hmac
import os
import struct
import time

_MAGIC_V1 = b"INGAT1"
_MAGIC_V2 = b"INGAT2"
_MAGIC = _MAGIC_V2

_SALT_LEN = 16
_NONCE_LEN = 12
_HMAC_LEN = 32
_ITERASI = 600_000
_HEADER_LEN = 6 + 1 + 1 + 8 + 16 + 16 + 12  # 60 byte


def _cek_dep():
    try:
        from cryptography.fernet import Fernet  # noqa: F401
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC  # noqa: F401
        from cryptography.hazmat.primitives import hashes  # noqa: F401
        from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305  # noqa: F401
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF  # noqa: F401
    except ImportError:
        raise ImportError(
            "Enkripsi membutuhkan library 'cryptography'. "
            "Pasang dengan: pip install cryptography"
        )


# ---------------------------------------------------------------------------
# Turunan kunci — setiap layer punya kunci sendiri
# ---------------------------------------------------------------------------

def _turunkan_kunci_fernet(sandi: str, salt: bytes) -> bytes:
    """L1: PBKDF2-SHA256 → 32 byte → base64 (format yang diminta Fernet)."""
    import base64
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32,
                     salt=salt, iterations=_ITERASI)
    return base64.urlsafe_b64encode(kdf.derive(sandi.encode("utf-8")))


def _turunkan_kunci_chacha(sandi: str, salt: bytes) -> bytes:
    """L2: PBKDF2-SHA256 → 32 byte raw (ChaCha20-Poly1305)."""
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32,
                     salt=salt, iterations=_ITERASI)
    return kdf.derive(sandi.encode("utf-8"))


def _turunkan_kunci_hmac(kunci_luar: bytes) -> bytes:
    """L3/L4: HKDF-SHA256 dari kunci luar → 32 byte terpisah untuk HMAC."""
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives import hashes
    return HKDF(
        algorithm=hashes.SHA256(), length=32,
        salt=None, info=b"ingat-hmac-integritas",
    ).derive(kunci_luar)


def _turunkan_kunci(sandi: str, salt: bytes) -> bytes:
    """Backward compat — alias ke _turunkan_kunci_fernet (dipakai dekripsi v1)."""
    return _turunkan_kunci_fernet(sandi, salt)


def _hmac256(key: bytes, data: bytes) -> bytes:
    return _hmac.new(key, data, hashlib.sha256).digest()


# ---------------------------------------------------------------------------
# Enkripsi — selalu v2 (4 layer)
# ---------------------------------------------------------------------------

def enkripsi(masuk: str, keluar: str, sandi: str) -> str:
    """Enkripsi berkas `masuk` → `keluar` dengan 4 lapisan. Kembalikan path keluar."""
    _cek_dep()
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

    if not sandi or len(sandi) < 8:
        raise ValueError("Sandi minimal 8 karakter")

    # Material acak — berubah setiap kali
    salt_dalam = os.urandom(_SALT_LEN)
    salt_luar = os.urandom(_SALT_LEN)
    nonce = os.urandom(_NONCE_LEN)
    timestamp = int(time.time())

    # Turunkan 3 kunci independen
    k_fernet = _turunkan_kunci_fernet(sandi, salt_dalam)
    k_chacha = _turunkan_kunci_chacha(sandi, salt_luar)
    k_hmac = _turunkan_kunci_hmac(k_chacha)

    with open(masuk, "rb") as f:
        data = f.read()

    # L1: Fernet (AES-128-CBC + HMAC-SHA256)
    token_fernet = Fernet(k_fernet).encrypt(data)

    # L2: ChaCha20-Poly1305 envelope
    ciphertext = ChaCha20Poly1305(k_chacha).encrypt(nonce, token_fernet, None)

    # L4: Header anti-tamper
    header = (
        _MAGIC_V2
        + struct.pack("BB", 0x02, 0x00)
        + struct.pack(">Q", timestamp)
        + salt_dalam + salt_luar + nonce
    )
    assert len(header) == _HEADER_LEN

    hmac_header = _hmac256(k_hmac, header)

    # L3: HMAC integritas luar — seluruh payload
    hmac_total = _hmac256(k_hmac, header + hmac_header + ciphertext)

    with open(keluar, "wb") as fo:
        fo.write(header)
        fo.write(hmac_header)
        fo.write(ciphertext)
        fo.write(hmac_total)

    return keluar


# ---------------------------------------------------------------------------
# Dekripsi — auto-deteksi v1 / v2
# ---------------------------------------------------------------------------

def dekripsi(masuk: str, keluar: str, sandi: str) -> str:
    """Dekripsi berkas terenkripsi. Mendukung format v1 (INGAT1) dan v2 (INGAT2)."""
    _cek_dep()
    with open(masuk, "rb") as f:
        magic = f.read(6)

    if magic == _MAGIC_V1:
        return _dekripsi_v1(masuk, keluar, sandi)
    if magic == _MAGIC_V2:
        return _dekripsi_v2(masuk, keluar, sandi)
    raise ValueError("Bukan berkas terenkripsi ingat (magic tidak cocok)")


def _dekripsi_v1(masuk: str, keluar: str, sandi: str) -> str:
    """Format lama INGAT1 — satu layer Fernet."""
    from cryptography.fernet import Fernet, InvalidToken
    with open(masuk, "rb") as fi:
        fi.read(len(_MAGIC_V1))  # skip magic
        salt = fi.read(_SALT_LEN)
        if len(salt) < _SALT_LEN:
            raise ValueError("Berkas terenkripsi terpotong (salt tidak lengkap)")
        token = fi.read()
    kunci = _turunkan_kunci_fernet(sandi, salt)
    try:
        data = Fernet(kunci).decrypt(token)
    except InvalidToken:
        raise ValueError("Sandi salah atau berkas rusak")
    with open(keluar, "wb") as fo:
        fo.write(data)
    return keluar


def _dekripsi_v2(masuk: str, keluar: str, sandi: str) -> str:
    """Format baru INGAT2 — 4 layer verifikasi."""
    from cryptography.fernet import Fernet, InvalidToken
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

    with open(masuk, "rb") as fi:
        header = fi.read(_HEADER_LEN)
        if len(header) < _HEADER_LEN:
            raise ValueError("Header terpotong")

        hmac_header_tersimpan = fi.read(_HMAC_LEN)
        if len(hmac_header_tersimpan) < _HMAC_LEN:
            raise ValueError("Berkas terpotong (HMAC header)")

        sisa = fi.read()

    if len(sisa) < _HMAC_LEN + 1:
        raise ValueError("Berkas terpotong (ciphertext/HMAC total)")

    ciphertext = sisa[:-_HMAC_LEN]
    hmac_total_tersimpan = sisa[-_HMAC_LEN:]

    # Parse header
    salt_dalam = header[16:32]
    salt_luar = header[32:48]
    nonce = header[48:60]

    # Turunkan kunci
    k_chacha = _turunkan_kunci_chacha(sandi, salt_luar)
    k_hmac = _turunkan_kunci_hmac(k_chacha)

    # L4: Verifikasi HMAC header — header belum diubah?
    hmac_header_hitung = _hmac256(k_hmac, header)
    if not _hmac.compare_digest(hmac_header_tersimpan, hmac_header_hitung):
        raise ValueError("Sandi salah atau header rusak (L4: HMAC header gagal)")

    # L3: Verifikasi HMAC total — payload utuh?
    hmac_total_hitung = _hmac256(k_hmac, header + hmac_header_tersimpan + ciphertext)
    if not _hmac.compare_digest(hmac_total_tersimpan, hmac_total_hitung):
        raise ValueError("Berkas dimodifikasi atau rusak (L3: HMAC total gagal)")

    # L2: ChaCha20-Poly1305 dekripsi envelope
    try:
        token_fernet = ChaCha20Poly1305(k_chacha).decrypt(nonce, ciphertext, None)
    except Exception:
        raise ValueError("Sandi salah atau berkas rusak (L2: ChaCha20 gagal)")

    # L1: Fernet dekripsi
    k_fernet = _turunkan_kunci_fernet(sandi, salt_dalam)
    try:
        data = Fernet(k_fernet).decrypt(token_fernet)
    except InvalidToken:
        raise ValueError("Sandi salah atau berkas rusak (L1: Fernet gagal)")

    with open(keluar, "wb") as fo:
        fo.write(data)
    return keluar


# ---------------------------------------------------------------------------
# Deteksi
# ---------------------------------------------------------------------------

def adalah_terenkripsi(path: str) -> bool:
    """Periksa apakah berkas memiliki magic header enkripsi ingat (v1 atau v2)."""
    try:
        with open(path, "rb") as f:
            magic = f.read(6)
            return magic in (_MAGIC_V1, _MAGIC_V2)
    except (OSError, IOError):
        return False


def versi_enkripsi(path: str) -> int | None:
    """Kembalikan versi format enkripsi (1 atau 2), atau None jika bukan terenkripsi."""
    try:
        with open(path, "rb") as f:
            magic = f.read(6)
            if magic == _MAGIC_V1:
                return 1
            if magic == _MAGIC_V2:
                return 2
    except (OSError, IOError):
        pass
    return None
