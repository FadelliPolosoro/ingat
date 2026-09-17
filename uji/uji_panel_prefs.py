# SPDX-License-Identifier: Apache-2.0
"""Fase 2 — preferensi otomasi panel (konsolidasi terjadwal). Helper bebas-Tkinter:
muat/simpan panel-prefs.json + hitung interval. Diuji tanpa layar."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from ingat import panel


class Prefs(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ingat-prefs-")
        self._p = mock.patch.object(panel, "DIR_INGAT", self.dir)
        self._p.start()

    def tearDown(self):
        self._p.stop()
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_default_saat_tak_ada_berkas(self):
        p = panel.muat_prefs()
        self.assertFalse(p["auto_konsolidasi"])
        self.assertEqual(p["interval_jam"], 6)
        self.assertIsNone(p["terakhir_konsolidasi"])

    def test_roundtrip_simpan_muat(self):
        panel.simpan_prefs({"auto_konsolidasi": True, "interval_jam": 12,
                            "terakhir_konsolidasi": "2026-09-18T00:00:00"})
        p = panel.muat_prefs()
        self.assertTrue(p["auto_konsolidasi"])
        self.assertEqual(p["interval_jam"], 12)
        self.assertEqual(p["terakhir_konsolidasi"], "2026-09-18T00:00:00")

    def test_berkas_rusak_jatuh_ke_default(self):
        with open(os.path.join(self.dir, "panel-prefs.json"), "w", encoding="utf-8") as f:
            f.write("{ini bukan json")
        p = panel.muat_prefs()
        self.assertEqual(p["interval_jam"], 6)
        self.assertFalse(p["auto_konsolidasi"])

    def test_interval_negatif_atau_salah_tipe_disanitasi(self):
        panel.simpan_prefs({"interval_jam": -5})
        self.assertEqual(panel.muat_prefs()["interval_jam"], 6)
        panel.simpan_prefs({"interval_jam": "banyak"})
        self.assertEqual(panel.muat_prefs()["interval_jam"], 6)
        # bool bukan interval sah walau int di Python
        panel.simpan_prefs({"interval_jam": True})
        self.assertEqual(panel.muat_prefs()["interval_jam"], 6)

    def test_interval_ms(self):
        self.assertEqual(panel.interval_ms(0), 0)
        self.assertEqual(panel.interval_ms(-3), 0)
        self.assertEqual(panel.interval_ms(6), 6 * 3_600_000)
        self.assertEqual(panel.interval_ms(1), 3_600_000)
        # penjaga minimal 60 dtk untuk interval sangat kecil
        self.assertEqual(panel.interval_ms(0.001), 60_000)


if __name__ == "__main__":
    unittest.main()
