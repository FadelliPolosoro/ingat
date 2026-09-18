"""Uji modul screenpipe — adapter Screenpipe ke ingat."""
from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
import unittest

from ingat import screenpipe as SP
from ingat.simpan import Store
from ingat.vektor import PenyematLokal


class UjiScreenpipe(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ingat-sp-")
        self.store = Store(os.path.join(self.dir, "s"), PenyematLokal())
        self.db_path = self._buat_db_tiruan()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _buat_db_tiruan(self):
        db_path = os.path.join(self.dir, "screenpipe.db")
        conn = sqlite3.connect(db_path)
        conn.execute("""CREATE TABLE frames (
            id INTEGER PRIMARY KEY, timestamp TEXT, app_name TEXT,
            window_name TEXT, ocr_text TEXT)""")
        conn.execute("""CREATE TABLE audio_transcriptions (
            id INTEGER PRIMARY KEY, timestamp TEXT, transcription TEXT,
            device_name TEXT)""")
        conn.execute("INSERT INTO frames VALUES (1, '2026-09-19T10:00:00', 'Chrome', 'GitHub', 'def hello_world(): pass')")
        conn.execute("INSERT INTO frames VALUES (2, '2026-09-19T10:05:00', 'VSCode', 'main.py', 'import os; print(os.getcwd())')")
        conn.execute("INSERT INTO frames VALUES (3, '2026-09-19T10:10:00', 'Chrome', 'Google', 'pendek')")
        conn.execute("INSERT INTO audio_transcriptions VALUES (1, '2026-09-19T10:02:00', 'Hari ini kita akan membahas arsitektur microservice', 'Mic')")
        conn.execute("INSERT INTO audio_transcriptions VALUES (2, '2026-09-19T10:07:00', 'singkat', 'Mic')")
        conn.commit()
        conn.close()
        return db_path

    # -- test cases --

    def test_cari_db_tidak_ada(self):
        hasil = SP._cari_db_screenpipe()
        # Mungkin None atau path valid kalau kebetulan ada Screenpipe terinstall
        # Tapi di CI/test env biasanya None
        self.assertIsInstance(hasil, (str, type(None)))

    def test_baca_tangkapan_layar(self):
        rows = SP._baca_tangkapan_layar(self.db_path)
        self.assertEqual(len(rows), 2)  # 'pendek' di-skip (< 10 char)
        self.assertIn("hello_world", rows[0]["text"] + rows[1]["text"])

    def test_baca_transkripsi(self):
        rows = SP._baca_transkripsi(self.db_path)
        self.assertEqual(len(rows), 1)  # 'singkat' di-skip
        self.assertIn("microservice", rows[0]["transcription"])

    def test_impor_idempoten(self):
        h1 = SP.impor(self.store, db_path=self.db_path)
        self.assertEqual(h1["layar"], 2)
        self.assertEqual(h1["audio"], 1)
        self.assertEqual(h1["skip"], 0)

        h2 = SP.impor(self.store, db_path=self.db_path)
        self.assertEqual(h2["layar"], 0)
        self.assertEqual(h2["audio"], 0)
        self.assertEqual(h2["skip"], 3)

        total = len(self.store.episode_semua())
        self.assertEqual(total, 3)

    def test_impor_skip_pendek(self):
        SP.impor(self.store, db_path=self.db_path)
        semua = self.store.episode_semua()
        for ep in semua:
            self.assertGreater(len(ep.ringkas), 0)
            # Pastikan 'pendek' dan 'singkat' tidak masuk
            self.assertNotIn("pendek", getattr(ep, "sesi", ""))
            self.assertNotIn("singkat", getattr(ep, "sesi", ""))

    def test_status_terhubung(self):
        st = SP.status(db_path=self.db_path)
        self.assertTrue(st["terhubung"])
        self.assertEqual(st["layar"], 3)  # termasuk yang pendek
        self.assertEqual(st["audio"], 2)
        self.assertIn("frames", st["tabel"])
        self.assertIn("audio_transcriptions", st["tabel"])

    def test_status_tidak_ada(self):
        st = SP.status(db_path="/path/yang/tidak/ada.db")
        self.assertFalse(st["terhubung"])

    def test_sesi_deterministik(self):
        self.assertEqual(SP._sesi_screenpipe("layar", 42), "ep-screenpipe-layar-42")
        self.assertEqual(SP._sesi_screenpipe("audio", 7), "ep-screenpipe-audio-7")


if __name__ == "__main__":
    unittest.main()
