# SPDX-License-Identifier: Apache-2.0
"""Uji K10: redaksi kredensial sebelum tulis, penanda tier, dan titik tulis tunggal Store.tambah_episode."""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest

from ingat.redaksi import redaksi, tandai_tier
from ingat.simpan import Store
from ingat.vektor import PenyematLokal


class Redaksi(unittest.TestCase):
    def test_kunci_api_dan_token_hilang(self):
        masuk = ("export ANTHROPIC_API_KEY=sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789 "
                 "dan gh token ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef0123456789")
        h = redaksi(masuk)
        self.assertNotIn("sk-ant-api03", h.teks)
        self.assertNotIn("ghp_ABCDEF", h.teks)
        self.assertIn("[REDAKSI:kunci-anthropic]", h.teks)
        self.assertIn("[REDAKSI:token-github]", h.teks)
        self.assertEqual(h.jenis, ["kunci-anthropic", "token-github"])
        self.assertEqual(h.jumlah, 2)

    def test_pasangan_kunci_nilai(self):
        h = redaksi('KUNCI_ENKRIPSI=abcd1234efgh5678\npassword: "R4has1aBanget!"\n')
        self.assertIn("KUNCI_ENKRIPSI=[REDAKSI:pasangan-rahasia]", h.teks)
        self.assertIn('password: "[REDAKSI:pasangan-rahasia]"', h.teks)
        self.assertNotIn("R4has1aBanget", h.teks)

    def test_bearer_dan_prosa(self):
        self.assertNotIn("eyJhbGci", redaksi("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abcdefghijklmnop").teks)
        self.assertEqual(redaksi("token dikembalikan ke pemanggil setelah validasi").jumlah, 0)

    def test_private_key_utuh(self):
        pem = "-----BEGIN RSA PRIVATE KEY-----\nMIIEow...\nabc\n-----END RSA PRIVATE KEY-----"
        self.assertEqual(redaksi(f"config:\n{pem}\nselesai").teks, "config:\n[REDAKSI:kunci-privat]\nselesai")

    def test_tanpa_rahasia_tidak_diubah(self):
        t = "Deploy manual via SSH tidak terlihat oleh VPS_getProjectListV1. Token bus habis."
        h = redaksi(t)
        self.assertEqual(h.teks, t)
        self.assertEqual(h.jumlah, 0)

    def test_nik_npwp_tidak_diredaksi_tapi_tier_s(self):
        t = "NIK 3175012345678901 atas nama X, NPWP 01.234.567.8-901.000"
        self.assertEqual(redaksi(t).teks, t)
        tier, alasan = tandai_tier(t)
        self.assertEqual(tier, "S")
        self.assertEqual(alasan, ["nik", "npwp"])

    def test_episode_coding_tetap_i(self):
        tier, alasan = tandai_tier("npm ci --ignore-scripts gagal karena postinstall playwright diblokir jaga.mjs")
        self.assertEqual((tier, alasan), ("I", []))


class TitikTulisTunggal(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ingat-redaksi-")
        self.store = Store(os.path.join(self.dir, "data"), PenyematLokal())

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_kredensial_tidak_pernah_menyentuh_disk(self):
        ep = self.store.tambah_episode(
            "deploy pakai token ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef0123456789 lalu OK",
            sumber="uji", tier="I", lingkup="proyek:fp-dashboard", jenis_kejadian="sukses",
            ringkas="deploy sukses dengan token ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef0123456789")
        self.assertEqual(ep.diredaksi, ["token-github"])
        self.assertNotIn("ghp_", ep.ringkas)
        isi = self.store.buka_dingin(ep.isi_ref)["isi"]
        self.assertNotIn("ghp_", isi)
        self.assertIn("[REDAKSI:token-github]", isi)
        # dan diredaksi ikut tersimpan di baris SQLite (bulat-balik lewat _dari_baris)
        self.assertEqual(self.store.episode(ep.id).diredaksi, ["token-github"])

    def test_migrasi_kolom_diredaksi_idempoten(self):
        store2 = Store(os.path.join(self.dir, "data"), PenyematLokal())  # buka ulang DB yang sama
        kolom = {r[1] for r in store2.db.execute("PRAGMA table_info(episode)")}
        self.assertIn("diredaksi", kolom)


if __name__ == "__main__":
    unittest.main()
