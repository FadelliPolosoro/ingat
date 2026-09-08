# SPDX-License-Identifier: Apache-2.0
"""Store harus bisa dipindah antar sistem operasi — `isi_ref` tidak boleh membawa separator OS penulis.

Ditemukan 8 Sep 2026 saat memindahkan store laptop (Windows) ke VPS (Linux): `os.path.relpath`
mengembalikan `dingin\\sesi\\-d\\ep-….json.gz`, dan di Linux itu jadi NAMA BERKAS literal — bukan
tiga folder. Akibatnya `buka_dingin` gagal untuk SETIAP episode hasil migrasi, dan gagalnya senyap
(kelihatan seperti bukti yang hilang, bukan seperti bug path). Kontraknya sekarang: tulis selalu
`/`; baca menerima keduanya supaya store lama tetap bisa dibuka.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest

from ingat.simpan import Store
from ingat.vektor import PenyematLokal


class RefDinginPortabel(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ingat-portabel-")
        self.store = Store(os.path.join(self.dir, "data"), PenyematLokal())

    def tearDown(self):
        self.store.db.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_isi_ref_selalu_garis_miring_depan(self):
        ref = self.store.simpan_dingin("ep-20260908-164319-7b67", {"isi": "halo"})
        self.assertNotIn("\\", ref, f"isi_ref tidak boleh memuat backslash, dapat: {ref!r}")
        self.assertIn("/", ref, f"isi_ref bersarang harus dipisah '/', dapat: {ref!r}")

    def test_yang_ditulis_bisa_dibaca_lagi(self):
        ref = self.store.simpan_dingin("ep-20260908-164319-7b67", {"isi": "bukti verbatim"})
        self.assertEqual(self.store.buka_dingin(ref)["isi"], "bukti verbatim")

    def test_ref_gaya_windows_lama_tetap_terbaca(self):
        """Store yang sudah telanjur ditulis Windows tidak boleh jadi tidak terbaca setelah pindah."""
        ref = self.store.simpan_dingin("ep-20260908-164319-7b67", {"isi": "store lama"})
        ref_lama = ref.replace("/", "\\")
        self.assertEqual(self.store.buka_dingin(ref_lama)["isi"], "store lama",
                         f"ref gaya lama {ref_lama!r} harus tetap bisa dibuka")

    def test_hapus_dingin_menerima_kedua_gaya(self):
        """Gulung balik (K10) memakai jalur path yang sama — kalau ia salah, blob yatim tertinggal."""
        for ubah in (lambda r: r, lambda r: r.replace("/", "\\")):
            with self.subTest(gaya=ubah("a/b")):
                ref = self.store.simpan_dingin("ep-20260908-164319-7b67", {"isi": "x"})
                penuh = os.path.join(self.store.dir_data, ref.replace("/", os.sep))
                self.assertTrue(os.path.exists(penuh))
                self.store._hapus_dingin(ubah(ref))
                self.assertFalse(os.path.exists(penuh), "blob harus terhapus apa pun gaya separator ref-nya")

    def test_episode_utuh_lewat_jalur_tulis_sungguhan(self):
        """Bukan hanya simpan_dingin: episode yang dibuat lewat tambah_episode juga harus portabel."""
        ep = self.store.tambah_episode("isi verbatim episode", sumber="uji", tier="I",
                                       lingkup="proyek:uji", jenis_kejadian="sukses", ringkas="ringkas")
        baris = self.store.db.execute("SELECT isi_ref FROM episode WHERE id=?", (ep.id,)).fetchone()[0]
        self.assertNotIn("\\", baris, f"isi_ref di basis data memuat backslash: {baris!r}")
        self.assertEqual(self.store.buka_dingin(baris)["isi"], "isi verbatim episode")


if __name__ == "__main__":
    unittest.main()
