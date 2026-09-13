# SPDX-License-Identifier: Apache-2.0
"""K30 — ekspor/impor episode antar mesin. Menjaga id/waktu (pointer bukti), lewat titik tulis
tunggal (redaksi K10 jalan ulang), embedder-agnostik, idempoten."""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest

from ingat import pindah
from ingat.simpan import Store
from ingat.vektor import PenyematLokal

FP = "proyek:fp-dashboard"


class _Dasar(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ingat-pindah-")
        self.a = Store(os.path.join(self.dir, "a"), PenyematLokal())

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _ep(self, store, isi, ringkas, tier="I", jenis="koreksi", sesi="s1"):
        return store.tambah_episode(isi, sumber="uji", tier=tier, lingkup=FP, jenis_kejadian=jenis,
                                    ringkas=ringkas, instrumen=["x"], sesi=sesi)

    def _store_b(self, dim=512):
        return Store(os.path.join(self.dir, f"b{dim}"), PenyematLokal(dim))


class RoundTrip(_Dasar):
    def test_ekspor_menangkap_semua_episode_dan_isi(self):
        self._ep(self.a, "isi verbatim satu", "ringkas satu")
        self._ep(self.a, "isi verbatim dua", "ringkas dua", jenis="kegagalan")
        d = pindah.ekspor(self.a)
        self.assertEqual(d["versi_ekspor"], pindah.VERSI_EKSPOR)
        self.assertEqual(d["jumlah"], 2)
        isi = {e["isi"] for e in d["episode"]}
        self.assertEqual(isi, {"isi verbatim satu", "isi verbatim dua"})

    def test_impor_mempertahankan_id_waktu_tier_status_isi(self):
        ep = self._ep(self.a, "kejadian penting", "ringkasnya", tier="I")
        d = pindah.ekspor(self.a)
        b = self._store_b()
        lap = pindah.impor(b, d)
        self.assertEqual(lap["diimpor"], 1)
        ep2 = b.episode(ep.id)
        self.assertIsNotNone(ep2, "id harus dipertahankan — bukti pelajaran menunjuknya")
        self.assertEqual(ep2.waktu, ep.waktu)
        self.assertEqual(ep2.tier, ep.tier)
        self.assertEqual(ep2.jenis_kejadian, ep.jenis_kejadian)
        self.assertEqual(ep2.bobot, ep.bobot)  # diturunkan dari jenis_kejadian
        self.assertEqual(b.buka_dingin(ep2.isi_ref)["isi"], "kejadian penting")

    def test_embedder_agnostik_dim_berbeda(self):
        self._ep(self.a, "isi", "ringkas")           # sumber dim=512
        d = pindah.ekspor(self.a)
        b = self._store_b(dim=256)                    # tujuan dim=256
        lap = pindah.impor(b, d)
        self.assertEqual(lap["diimpor"], 1)
        self.assertEqual(lap["embedder_tujuan"]["dim"], 256)
        # vektor dihitung ulang di tujuan → episode bisa ditemukan lagi, tanpa IdentitasEmbedderTidakCocok
        self.assertEqual(len(b.episode_semua()), 1)

    def test_idempoten_impor_dua_kali_melewati_yang_sudah_ada(self):
        self._ep(self.a, "isi", "ringkas")
        d = pindah.ekspor(self.a)
        b = self._store_b()
        pindah.impor(b, d)
        lap2 = pindah.impor(b, d)
        self.assertEqual(lap2["diimpor"], 0)
        self.assertEqual(lap2["dilewati_sudah_ada"], 1)
        self.assertEqual(len(b.episode_semua()), 1, "tidak boleh menggandakan")

    def test_tier_s_ikut_dan_tetap_s(self):
        ep = self._ep(self.a, "NIK 3174091208900007 bermasalah", "kasus sensitif", tier="I")
        self.assertEqual(ep.tier, "S", "NIK menaikkan ke S saat pertama ditulis (redaksi.tandai_tier)")
        d = pindah.ekspor(self.a)
        b = self._store_b()
        pindah.impor(b, d)
        self.assertEqual(b.episode(ep.id).tier, "S", "tier S harus bertahan lintas migrasi")

    def test_impor_menjalankan_ulang_redaksi_sebagai_pengaman(self):
        """Titik tulis tunggal: kalaupun ekspor memuat kredensial mentah, impor tetap meredaksinya."""
        d = {"versi_ekspor": pindah.VERSI_EKSPOR, "episode": [{
            "meta": {"id": "ep-2026-01-01-0001", "waktu": "2026-01-01T00:00:00+00:00", "sumber": "uji",
                     "tier": "I", "lingkup": FP, "jenis_kejadian": "sukses", "ringkas": "r"},
            "isi": "token bocor: api_key=RAHASIA_SANGAT_PANJANG_123"}]}
        b = self._store_b()
        pindah.impor(b, d)
        isi = b.buka_dingin(b.episode("ep-2026-01-01-0001").isi_ref)["isi"]
        self.assertNotIn("RAHASIA_SANGAT_PANJANG_123", isi, "kredensial harus diredaksi saat impor")
        self.assertIn("[REDAKSI:", isi)

    def test_versi_tak_dikenal_ditolak(self):
        with self.assertRaises(ValueError):
            pindah.impor(self._store_b(), {"versi_ekspor": 999, "episode": []})


if __name__ == "__main__":
    unittest.main()
