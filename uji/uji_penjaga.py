# SPDX-License-Identifier: Apache-2.0
"""Layer 9+10: penjaga keamanan — eskalasi ban, delay adaptif, statistik."""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest

from ingat.penjaga import Penjaga


class PenjagaTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ingat-penjaga-")
        self.db = os.path.join(self.tmp, "penjaga.sqlite")
        self.p = Penjaga(db_path=self.db)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_ip_baru_tidak_diban(self):
        self.assertEqual(self.p.ip_diblokir("1.2.3.4"), 0.0)

    def test_delay_setelah_3_gagal(self):
        for _ in range(3):
            self.p.catat_gagal("10.0.0.1", "token_gagal")
        self.assertGreater(self.p.delay_untuk("10.0.0.1"), 0)

    def test_ban_setelah_5_gagal(self):
        for i in range(5):
            self.p.catat_gagal("10.0.0.2", f"gagal_{i}")
        sisa = self.p.ip_diblokir("10.0.0.2")
        self.assertGreater(sisa, 0)
        self.assertLessEqual(sisa, 300)

    def test_eskalasi_ban_10_gagal(self):
        for i in range(10):
            self.p.catat_gagal("10.0.0.3", f"gagal_{i}")
        sisa = self.p.ip_diblokir("10.0.0.3")
        self.assertGreater(sisa, 300)
        self.assertLessEqual(sisa, 3600)

    def test_eskalasi_ban_20_gagal(self):
        for i in range(20):
            self.p.catat_gagal("10.0.0.4", f"gagal_{i}")
        sisa = self.p.ip_diblokir("10.0.0.4")
        self.assertGreater(sisa, 3600)
        self.assertLessEqual(sisa, 86400)

    def test_statistik(self):
        self.p.catat_gagal("10.0.0.5", "uji")
        self.p.catat_gagal("10.0.0.6", "uji")
        st = self.p.statistik()
        self.assertEqual(st["total_percobaan_gagal"], 2)
        self.assertEqual(st["ip_unik_gagal"], 2)
        self.assertEqual(len(st["terbaru"]), 2)

    def test_reset_ip(self):
        for _ in range(5):
            self.p.catat_gagal("10.0.0.7", "uji")
        self.assertGreater(self.p.ip_diblokir("10.0.0.7"), 0)
        self.p.reset_ip("10.0.0.7")
        self.assertEqual(self.p.ip_diblokir("10.0.0.7"), 0.0)
        self.assertEqual(self.p.delay_untuk("10.0.0.7"), 0.0)

    def test_ip_lain_tidak_terpengaruh(self):
        for _ in range(10):
            self.p.catat_gagal("10.0.0.8", "uji")
        self.assertEqual(self.p.ip_diblokir("10.0.0.9"), 0.0)
        self.assertEqual(self.p.delay_untuk("10.0.0.9"), 0.0)


if __name__ == "__main__":
    unittest.main()
