import unittest
import datetime as dt
from ingat.gateway import _bobot_kebaruan


class BobotKebaruan(unittest.TestCase):
    def test_baru_dekat_satu(self):
        iso = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)).isoformat()
        self.assertGreater(_bobot_kebaruan(iso), 0.99)

    def test_separuh_di_90_hari(self):
        iso = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=90)).isoformat()
        b = _bobot_kebaruan(iso)
        self.assertAlmostEqual(b, 0.5, delta=0.02)

    def test_sangat_lama_mendekati_nol(self):
        iso = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=365)).isoformat()
        self.assertLess(_bobot_kebaruan(iso), 0.1)

    def test_none_netral(self):
        self.assertEqual(_bobot_kebaruan(None), 0.5)

    def test_rusak_netral(self):
        self.assertEqual(_bobot_kebaruan("bukan-tanggal"), 0.5)

    def test_dampak_kecil(self):
        """Bobot kebaruan hanya pengali 0.85-1.0 -- dampaknya halus."""
        baru = _bobot_kebaruan((dt.datetime.now(dt.timezone.utc)).isoformat())
        lama = _bobot_kebaruan((dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=365)).isoformat())
        # paling jauh turun 15%
        self.assertGreaterEqual(0.85 + 0.15 * lama, 0.85)
        self.assertAlmostEqual(0.85 + 0.15 * baru, 1.0, delta=0.01)
