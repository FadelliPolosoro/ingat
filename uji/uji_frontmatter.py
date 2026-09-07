# SPDX-License-Identifier: Apache-2.0
"""Frontmatter Python (ingat/frontmatter.py). Fokus pada bug nyata yang ditemukan 8 Sep 2026:
PyYAML mengubah tanggal telanjang jadi datetime.date/datetime, melanggar kontrak TEXT ISO 8601."""
from __future__ import annotations

import datetime as dt
import json
import unittest

from ingat import frontmatter as fm


class TanggalTetapString(unittest.TestCase):
    """Bug: yaml.safe_load('dibuat: 2026-01-01') -> datetime.date(2026,1,1), bukan str.
    Konsekuensi nyata sebelum diperbaiki: Vault.sinkron gagal dengan
    "'datetime.date' object is not subscriptable" pada SETIAP pelajaran/prosedur/norma
    yang menulis tanggal tanpa kutip di frontmatter — termasuk gaya penulisan yang dipakai
    di seluruh contoh KEPUTUSAN.md, vault-contoh/, dan dokumen spek sendiri."""

    def test_tanggal_polos_tetap_string(self):
        data, _ = fm.muat("---\ndibuat: 2026-01-01\n---\nbadan\n")
        self.assertEqual(data["dibuat"], "2026-01-01")
        self.assertIsInstance(data["dibuat"], str)

    def test_datetime_dengan_jam_tetap_string(self):
        data, _ = fm.muat("---\nwaktu: 2026-01-01T10:30:00\n---\n")
        self.assertEqual(data["waktu"], "2026-01-01T10:30:00")
        self.assertIsInstance(data["waktu"], str)

    def test_tanggal_di_dalam_list_dan_dict_bersarang(self):
        data, _ = fm.muat("---\nlist: [2026-01-01, teks]\nsub: {a: 2026-01-01}\n---\n")
        self.assertEqual(data["list"][0], "2026-01-01")
        self.assertIsInstance(data["list"][0], str)
        self.assertEqual(data["sub"]["a"], "2026-01-01")
        self.assertIsInstance(data["sub"]["a"], str)

    def test_hasil_selalu_json_serializable(self):
        """Kontrak API (api.py mengirim JSON): objek date tidak bisa di-json.dumps tanpa encoder khusus."""
        data, _ = fm.muat("---\nid: x\ndibuat: 2026-01-01\ntinjau_setelah: 2026-04-01\n---\n")
        json.dumps(data)  # tidak boleh melempar TypeError

    def test_bukan_string_lain_tidak_terganggu(self):
        """Perbaikan hanya menyasar date/datetime — bool, int, float, null, string biasa tetap sama."""
        data, _ = fm.muat("---\nn: 3\nf: 0.5\nb: true\nkosong: null\nteks: halo\n---\n")
        self.assertEqual(data, {"n": 3, "f": 0.5, "b": True, "kosong": None, "teks": "halo"})

    def test_tidak_ada_objek_date_lolos_sama_sekali(self):
        data, _ = fm.muat("---\na: 2026-01-01\nb: 2026-01-01T00:00:00\nc: [2026-01-01]\n---\n")

        def _cek(v):
            self.assertNotIsInstance(v, (dt.date, dt.datetime))
            if isinstance(v, dict):
                for x in v.values():
                    _cek(x)
            if isinstance(v, list):
                for x in v:
                    _cek(x)
        _cek(data)


if __name__ == "__main__":
    unittest.main()
