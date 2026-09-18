# SPDX-License-Identifier: Apache-2.0
"""Uji fitur sematan (fakta tetap / pin)."""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest

from ingat.simpan import Store
from ingat.vektor import PenyematLokal


class Sematan(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ingat-pin-")
        self.store = Store(os.path.join(self.dir, "s"), PenyematLokal())

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_sematkan_dan_lepas(self):
        ep = self.store.tambah_episode(
            "saya Fadelli", sumber="panel", tier="I",
            lingkup="global", jenis_kejadian="sukses",
            ringkas="identitas", instrumen=["x"], sesi="s1")
        self.store.sematkan("episode", ep.id, "fakta identitas")
        self.assertTrue(self.store.disematkan(ep.id))
        self.assertEqual(len(self.store.sematan_semua()), 1)
        self.assertTrue(self.store.lepas_sematan(ep.id))
        self.assertFalse(self.store.disematkan(ep.id))

    def test_lepas_yang_tak_ada(self):
        self.assertFalse(self.store.lepas_sematan("ep-tak-ada"))

    def test_sematan_idempoten(self):
        ep = self.store.tambah_episode(
            "data", sumber="mcp", tier="I",
            lingkup="global", jenis_kejadian="sukses",
            ringkas="r", instrumen=["x"], sesi="s1")
        self.store.sematkan("episode", ep.id)
        self.store.sematkan("episode", ep.id, "update catatan")  # INSERT OR REPLACE
        self.assertEqual(len(self.store.sematan_semua()), 1)

    def test_hapus_episode_juga_hapus_sematan(self):
        ep = self.store.tambah_episode(
            "data penting", sumber="panel", tier="I",
            lingkup="global", jenis_kejadian="sukses",
            ringkas="penting", instrumen=["x"], sesi="s1")
        self.store.sematkan("episode", ep.id)
        self.assertTrue(self.store.disematkan(ep.id))
        self.store.hapus_episode(ep.id)
        self.assertFalse(self.store.disematkan(ep.id))
        self.assertEqual(len(self.store.sematan_semua()), 0)


if __name__ == "__main__":
    unittest.main()
