# SPDX-License-Identifier: Apache-2.0
"""K26: TOTP mandiri (RFC 6238). Diverifikasi terhadap vektor uji RESMI RFC 6238 Lampiran B —
bukan cuma mempercayai implementasi sendiri."""
from __future__ import annotations

import base64
import unittest

from ingat.auth_totp import _hotp, buat_rahasia, kode_sekarang, otpauth_url, verifikasi_kode

# RFC 6238 Lampiran B: seed ASCII "12345678901234567890", HMAC-SHA1, langkah 30 detik, 8 digit.
RAHASIA_RFC = base64.b32encode(b"12345678901234567890").decode().rstrip("=")
VEKTOR_RFC = [
    (59, "94287082"),
    (1111111109, "07081804"),
    (1111111111, "14050471"),
    (1234567890, "89005924"),
    (2000000000, "69279037"),
]


class VektorRFC6238(unittest.TestCase):
    def test_kode_8_digit_cocok_rfc_6238_lampiran_b(self):
        for waktu, kode_benar in VEKTOR_RFC:
            counter = waktu // 30
            self.assertEqual(_hotp(RAHASIA_RFC, counter, digit=8), kode_benar, f"waktu={waktu}")


class Kode(unittest.TestCase):
    def test_verifikasi_kode_benar_pada_waktu_yang_sama(self):
        rahasia = buat_rahasia()
        kode = kode_sekarang(rahasia, waktu=1_700_000_000)
        self.assertTrue(verifikasi_kode(rahasia, kode, waktu=1_700_000_000))

    def test_kode_salah_ditolak(self):
        rahasia = buat_rahasia()
        kode = kode_sekarang(rahasia, waktu=1_700_000_000)
        salah = f"{(int(kode) + 1) % 1_000_000:06d}"
        self.assertFalse(verifikasi_kode(rahasia, salah, waktu=1_700_000_000))

    def test_toleransi_jendela_30_detik(self):
        rahasia = buat_rahasia()
        kode = kode_sekarang(rahasia, waktu=1_700_000_000)
        self.assertTrue(verifikasi_kode(rahasia, kode, waktu=1_700_000_015))  # +15dtk, langkah sama
        self.assertTrue(verifikasi_kode(rahasia, kode, waktu=1_700_000_029))  # +29dtk, masih langkah sama
        # +30dtk pas masuk langkah berikutnya -> beda kode, tapi jendela ±1 tetap menerima
        self.assertTrue(verifikasi_kode(rahasia, kode, waktu=1_700_000_035))

    def test_di_luar_jendela_ditolak(self):
        rahasia = buat_rahasia()
        kode = kode_sekarang(rahasia, waktu=1_700_000_000)
        self.assertFalse(verifikasi_kode(rahasia, kode, waktu=1_700_000_000 + 120))  # +4 langkah, jauh di luar ±1

    def test_kode_bukan_angka_atau_panjang_salah_ditolak(self):
        rahasia = buat_rahasia()
        self.assertFalse(verifikasi_kode(rahasia, "abcdef", waktu=1_700_000_000))
        self.assertFalse(verifikasi_kode(rahasia, "12345", waktu=1_700_000_000))
        self.assertFalse(verifikasi_kode(rahasia, "1234567", waktu=1_700_000_000))

    def test_rahasia_selalu_berbeda_dan_valid_base32(self):
        a, b = buat_rahasia(), buat_rahasia()
        self.assertNotEqual(a, b)
        base64.b32decode(a + "=" * ((8 - len(a) % 8) % 8))  # tidak boleh melempar

    def test_otpauth_url_memuat_field_wajib(self):
        u = otpauth_url("ABCDEF", akun_label="fadelli", penerbit="ingat")
        self.assertTrue(u.startswith("otpauth://totp/"))
        self.assertIn("secret=ABCDEF", u)
        self.assertIn("issuer=ingat", u)
        self.assertIn("digits=6", u)
        self.assertIn("period=30", u)


if __name__ == "__main__":
    unittest.main()
