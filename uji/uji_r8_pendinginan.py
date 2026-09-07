# SPDX-License-Identifier: Apache-2.0
"""R8 (spek 7.3b): episode tetap aktif setelah konsolidasi; didinginkan hanya bila induk disetujui atau usia > hari_dingin.
Dan: run konsolidasi berulang tidak menggelembungkan keyakinan atau menjadikan bukti lama sebagai kontra."""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest

from ingat import skema
from ingat.gate import Gate
from ingat.konsolidasi import Konsolidator
from ingat.obsidian import Vault
from ingat.simpan import Store
from ingat.vektor import PenyematLokal

FP = "proyek:fp-dashboard"


class R8(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ingat-r8-")
        self.store = Store(os.path.join(self.dir, "data"), PenyematLokal())
        self.vault = Vault(os.path.join(self.dir, "vault"))
        self.kons = Konsolidator(self.store, Gate({"P": [], "I": []}), {}, self.vault, {"hari_dingin": 30})

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def episode(self, ringkas, jenis="kegagalan", sesi="s1", langkah=()):
        return self.store.tambah_episode(f"[verbatim] {ringkas}", sumber="uji", tier="I", lingkup=FP,
                                         jenis_kejadian=jenis, ringkas=ringkas, instrumen=["x"], sesi=sesi, langkah=list(langkah))

    def test_tetap_aktif_dan_run_ulang_idempoten(self):
        for s in ("s1", "s2", "s3"):
            self.episode("tool kosong disimpulkan tidak ada objek", sesi=s)
        lap1 = self.kons.jalankan()
        self.assertEqual(lap1["didinginkan"], 0, "episode baru tidak boleh langsung didinginkan (R8)")
        self.assertTrue(all(e.status == "aktif" for e in self.store.episode_semua()))
        p = self.store.pelajaran_semua()[0]
        bukti1, keyakinan1 = list(p.bukti), p.keyakinan
        lap2 = self.kons.jalankan()
        p2 = self.store.pelajaran(p.id)
        self.assertEqual(p2.bukti, bukti1, "run ulang tanpa episode baru tidak menambah bukti")
        self.assertEqual(p2.keyakinan, keyakinan1, "run ulang tanpa episode baru tidak menggelembungkan keyakinan")
        self.assertEqual(p2.kontra, [], "bukti lama tidak boleh berubah jadi kontra")
        self.assertEqual(lap2["bukti_ditambah"], 0)
        self.assertEqual(lap2["kontra_ditambah"], 0)

    def test_episode_baru_masih_bisa_bergabung(self):
        for s in ("s1", "s2", "s3"):
            self.episode("tool kosong disimpulkan tidak ada objek", sesi=s)
        self.kons.jalankan()
        self.episode("tool kosong disimpulkan tidak ada objek", sesi="s4")
        lap = self.kons.jalankan()
        self.assertEqual(lap["bukti_ditambah"], 1)
        self.assertEqual(len(self.store.pelajaran_semua()[0].bukti), 4, "episode ke-4 bergabung ke pelajaran yang sama")

    def test_didinginkan_saat_induk_disetujui(self):
        for s in ("s1", "s2", "s3"):
            self.episode("tool kosong disimpulkan tidak ada objek", sesi=s)
        self.kons.jalankan()
        p = self.store.pelajaran_semua()[0]
        # simulasi persetujuan manusia: usulan -> aturan
        self.store.ubah_status("pelajaran", p.id, "aturan", "manusia", "uji")
        lap = self.kons.jalankan()
        self.assertEqual(lap["didinginkan"], 3)
        self.assertTrue(all(e.status == "didinginkan" for e in self.store.episode_semua()))

    def test_didinginkan_saat_usia_lewat(self):
        e = self.episode("kejadian lama")
        self.store.db.execute("UPDATE episode SET waktu=? WHERE id=?", (skema.tambah_hari(skema.hari_ini(), -45) + "T10:00:00+07:00", e.id))
        self.store.db.commit()
        self.episode("kejadian baru")
        lap = self.kons.jalankan()
        self.assertEqual(lap["didinginkan"], 1)
        self.assertEqual(self.store.episode(e.id).status, "didinginkan")

    def test_draf_prosedur_tidak_duplikat(self):
        for s in ("s1", "s2", "s3"):
            self.episode("pasang dependensi berhasil", jenis="sukses", sesi=s, langkah=["npm ci --ignore-scripts", "npx playwright install chromium"])
        self.assertEqual(self.kons.jalankan()["prosedur_draf"], 1)
        self.assertEqual(self.kons.jalankan()["prosedur_draf"], 0, "run ulang tidak boleh membuat draf prosedur kedua")
        self.assertEqual(len(self.store.prosedur_semua()), 1)


if __name__ == "__main__":
    unittest.main()
