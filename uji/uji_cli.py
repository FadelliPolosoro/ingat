# SPDX-License-Identifier: Apache-2.0
"""CLI: stdout dipaksa UTF-8 supaya json.dumps(ensure_ascii=False) tidak jatuh di
konsol Windows (cp1252) saat keluaran memuat karakter non-cp1252 — mis. bendera
'⚑' pada hasil `ingat ingat`. Bug ditemukan 13 Sep 2026 di cli.py:176."""
from __future__ import annotations

import contextlib
import io
import sys
import unittest

from ingat.cli import _paksa_stdout_utf8, utama


class UjiPaksaStdoutUtf8(unittest.TestCase):
    def test_konsol_cp1252_bisa_cetak_karakter_non_cp1252(self):
        """Reproduksi bug: TextIOWrapper cp1252 jatuh saat menulis '⚑',
        tapi lolos setelah _paksa_stdout_utf8 mengubahnya ke UTF-8."""
        buf = io.BytesIO()
        konsol = io.TextIOWrapper(buf, encoding="cp1252")
        # Sebelum diperbaiki: menulis bendera ke konsol cp1252 harus gagal.
        with self.assertRaises(UnicodeEncodeError):
            konsol.write("⚑")
            konsol.flush()

        semula = sys.stdout
        try:
            sys.stdout = konsol
            _paksa_stdout_utf8()
            konsol.write("⚑")
            konsol.flush()
        finally:
            sys.stdout = semula

        self.assertEqual(buf.getvalue().decode("utf-8"), "⚑")

    def test_stringio_tanpa_reconfigure_dilewati_tanpa_galat(self):
        """Di uji, stdout adalah io.StringIO yang tidak punya .reconfigure —
        _paksa_stdout_utf8 harus melewatinya diam-diam, bukan meledak."""
        keluaran = io.StringIO()
        self.assertFalse(hasattr(keluaran, "reconfigure"))
        with contextlib.redirect_stdout(keluaran):
            _paksa_stdout_utf8()  # tidak boleh melempar AttributeError


class UjiUtamaAmanDiUji(unittest.TestCase):
    def test_utama_memanggil_paksa_utf8_tanpa_jatuh_di_stringio(self):
        """utama() memanggil _paksa_stdout_utf8 di awal; dijalankan di bawah
        redirect_stdout(StringIO) harus tetap aman (perintah `token` cukup)."""
        keluaran = io.StringIO()
        with contextlib.redirect_stdout(keluaran):
            kode = utama(["token"])
        self.assertEqual(kode, 0)
        self.assertTrue(keluaran.getvalue().strip(), "perintah token harus mencetak token")


if __name__ == "__main__":
    unittest.main()
