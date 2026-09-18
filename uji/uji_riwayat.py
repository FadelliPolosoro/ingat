# SPDX-License-Identifier: Apache-2.0
"""Audit trail: riwayat_perubahan tercatat saat hapus episode, ubah status, edit judul."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest

from ingat import skema
from ingat.simpan import Store
from ingat.vektor import PenyematLokal


class RiwayatPerubahan(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ingat-riwayat-")
        self.store = Store(os.path.join(self.dir, "s"), PenyematLokal())

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _tambah(self, ringkas="episode uji", sumber="mcp"):
        return self.store.tambah_episode("isi verbatim", sumber=sumber, tier="I",
                                         lingkup="peran:asisten-ai", jenis_kejadian="sukses",
                                         ringkas=ringkas, instrumen=["x"], sesi="s1")

    def test_catat_dan_baca_riwayat(self):
        self.store.catat_perubahan("episode", "ep-1", "edit_isi",
                                   sebelum='{"x":1}', sesudah='{"x":2}', oleh="manusia")
        self.store.catat_perubahan("episode", "ep-1", "hapus", oleh="panel")
        r = self.store.riwayat_perubahan("ep-1")
        self.assertEqual(len(r), 2)
        self.assertEqual(r[0]["aksi"], "edit_isi")
        self.assertEqual(r[0]["oleh"], "manusia")
        self.assertEqual(r[1]["aksi"], "hapus")
        # item_id lain tidak bocor
        self.assertEqual(self.store.riwayat_perubahan("ep-lain"), [])

    def test_hapus_episode_menulis_riwayat(self):
        ep = self._tambah("ringkasan penting", "mcp")
        self.assertTrue(self.store.hapus_episode(ep.id))
        r = self.store.riwayat_perubahan(ep.id)
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["aksi"], "hapus")
        self.assertEqual(r[0]["jenis"], "episode")
        self.assertEqual(r[0]["oleh"], "manusia")
        delta = json.loads(r[0]["sebelum"])
        self.assertEqual(delta["ringkas"], "ringkasan penting")
        self.assertEqual(delta["sumber"], "mcp")

    def test_ubah_status_menulis_riwayat(self):
        ep = self._tambah()
        self.store.ubah_status("episode", ep.id, "didinginkan", oleh="mesin", alasan="uji")
        r = self.store.riwayat_perubahan(ep.id)
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["aksi"], "ubah_status")
        self.assertEqual(json.loads(r[0]["sebelum"]), {"status": "aktif"})
        self.assertEqual(json.loads(r[0]["sesudah"]), {"status": "didinginkan"})
        self.assertEqual(r[0]["oleh"], "mesin")

    def test_riwayat_kosong_untuk_item_baru(self):
        ep = self._tambah()
        self.assertEqual(self.store.riwayat_perubahan(ep.id), [])


if __name__ == "__main__":
    unittest.main()
