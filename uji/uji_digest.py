# SPDX-License-Identifier: Apache-2.0
"""Uji modul digest harian."""
from __future__ import annotations

import shutil
import tempfile
import unittest

from ingat.aplikasi import Aplikasi, muat_konfig
from ingat import skema, digest


class UjiDigest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ingat-digest-")
        k = muat_konfig(None)
        k["dir_data"] = self.dir + "/data"
        k["vault"] = self.dir + "/vault"
        self.app = Aplikasi(k)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _simpan_ep(self, id, waktu, sumber="mcp", jenis="sukses", ringkas="test"):
        self.app.store.tambah_episode(
            "isi test", id=id, waktu=waktu, sumber=sumber,
            jenis_kejadian=jenis, ringkas=ringkas, tier="I", lingkup="global"
        )

    def test_digest_kosong(self):
        d = digest.digest_hari(self.app.store, "2026-01-01")
        self.assertEqual(d["total"], 0)
        self.assertEqual(d["butir"], [])
        self.assertIn("Tidak ada episode", d["ringkasan"])

    def test_digest_satu_episode(self):
        self._simpan_ep("ep-1", "2026-09-19T14:23:00", sumber="mcp", jenis="sukses")
        d = digest.digest_hari(self.app.store, "2026-09-19")
        self.assertEqual(d["total"], 1)
        self.assertIn("Claude Desktop", d["platform"])
        self.assertEqual(d["platform"]["Claude Desktop"], 1)
        self.assertEqual(len(d["butir"]), 1)
        self.assertEqual(d["butir"][0]["waktu"], "14:23")

    def test_digest_multi_platform(self):
        self._simpan_ep("ep-a", "2026-09-19T10:00:00", sumber="mcp")
        self._simpan_ep("ep-b", "2026-09-19T11:00:00", sumber="browser:chatgpt.com")
        self._simpan_ep("ep-c", "2026-09-19T12:00:00", sumber="browser:gemini.google.com")
        d = digest.digest_hari(self.app.store, "2026-09-19")
        self.assertEqual(d["total"], 3)
        self.assertEqual(len(d["platform"]), 3)
        self.assertIn("Claude Desktop", d["platform"])
        self.assertIn("ChatGPT", d["platform"])
        self.assertIn("Gemini", d["platform"])

    def test_format_tanggal(self):
        self.assertEqual(digest._format_tanggal_id("2026-09-19"), "19 September 2026")
        self.assertEqual(digest._format_tanggal_id("2026-01-05"), "5 Januari 2026")

    def test_ringkasan_terbentuk(self):
        self._simpan_ep("ep-x", "2026-09-19T09:00:00", sumber="claude-code", jenis="sukses")
        self._simpan_ep("ep-y", "2026-09-19T10:00:00", sumber="claude-code", jenis="kegagalan")
        d = digest.digest_hari(self.app.store, "2026-09-19")
        self.assertIn("2", d["ringkasan"])
        self.assertIn("Claude Code", d["ringkasan"])

    def test_digest_7_hari(self):
        import datetime as _dt
        hari_ini = _dt.date.today()
        kemarin = hari_ini - _dt.timedelta(days=1)
        self._simpan_ep("ep-h", hari_ini.isoformat() + "T08:00:00")
        self._simpan_ep("ep-k", kemarin.isoformat() + "T09:00:00")
        hasil = digest.digest_7_hari(self.app.store)
        self.assertGreaterEqual(len(hasil), 1)
        tanggal_set = {h["tanggal"] for h in hasil}
        self.assertIn(hari_ini.isoformat(), tanggal_set)
        for h in hasil:
            self.assertGreater(h["total"], 0)


if __name__ == "__main__":
    unittest.main()
