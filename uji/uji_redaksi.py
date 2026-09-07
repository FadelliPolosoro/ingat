# SPDX-License-Identifier: Apache-2.0
"""Uji K10: redaksi kredensial sebelum tulis, penanda tier, dan titik tulis tunggal Store.tambah_episode."""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest

from ingat.redaksi import redaksi, tandai_tier
from ingat.simpan import IdentitasEmbedderTidakCocok, Store
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


class PenyematGagal:
    """Penyemat yang selalu gagal — meniru Ollama mati (WinError 10061)."""
    nama = "lokal-hash-v1"

    def __init__(self, dim: int = 512):
        self.dim = dim

    def semat(self, teks: str):
        raise RuntimeError("Ollama mati")


class PenyematE5Palsu:
    """Meniru pindah ke e5-base: nama DAN dimensi berbeda dari penyemat lokal."""
    nama = "e5-base-palsu"

    def __init__(self, dim: int = 768):
        self.dim = dim

    def semat(self, teks: str):
        v = [0.0] * self.dim
        for i, k in enumerate(teks.split()):
            v[(len(k) * 31 + i) % self.dim] += 1.0
        n = sum(x * x for x in v) ** 0.5 or 1.0
        return [x / n for x in v]


class GulungBalikEpisode(unittest.TestCase):
    """Penyematan gagal tidak boleh meninggalkan apa pun — bukan baris, bukan blob yatim.

    Ditemukan saat memasang ingat di laptop 8 Sep 2026: Ollama mati, `Stop` keluar 0, nol
    episode tercatat, tapi `dingin/sesi/-u/ep-sesi-*.json.gz` tetap tertulis dan tidak dirujuk
    baris mana pun. Urutan yang benar ditentukan kontrak: baris episode yang ter-commit WAJIB
    punya blob verbatim (K10), jadi blob harus lebih dulu — dan bila baris gagal, blob dicabut.
    """

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ingat-gulung-")
        self.data = os.path.join(self.dir, "data")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _berkas_dingin(self, store) -> list[str]:
        akar = store.dir_dingin
        return [os.path.join(d, f) for d, _, fs in os.walk(akar) for f in fs] if os.path.isdir(akar) else []

    def test_penyemat_gagal_tidak_meninggalkan_blob_yatim(self):
        store = Store(self.data, PenyematGagal())
        with self.assertRaises(RuntimeError):
            store.tambah_episode("deploy gagal", sumber="uji", tier="I", lingkup="proyek:x",
                                 jenis_kejadian="kegagalan", ringkas="ringkas")
        self.assertEqual(store.db.execute("SELECT COUNT(*) FROM episode").fetchone()[0], 0)
        self.assertEqual(store.db.execute("SELECT COUNT(*) FROM vektor").fetchone()[0], 0)
        self.assertEqual(self._berkas_dingin(store), [], "tidak ada blob yatim")

    def test_gagal_menulis_baris_juga_mencabut_blob(self):
        """Penyematan lolos tetapi penulisan baris gagal — blob tetap tidak boleh tertinggal."""
        store = Store(self.data, PenyematLokal())

        def meledak(*a, **k):
            raise RuntimeError("disk penuh")

        store._simpan_vektor = meledak
        with self.assertRaises(RuntimeError):
            store.tambah_episode("apa pun", sumber="uji", tier="I", lingkup="proyek:x",
                                 jenis_kejadian="sukses", ringkas="r")
        self.assertEqual(self._berkas_dingin(store), [], "blob dicabut walau kegagalannya bukan di penyemat")

    def test_kegagalan_tidak_ikut_ter_commit_oleh_penulis_berikutnya(self):
        """Tanpa rollback, INSERT yang gagal menggantung lalu ikut ter-commit oleh catat_metrik."""
        store = Store(self.data, PenyematLokal())

        def meledak(*a, **k):
            raise RuntimeError("disk penuh")

        store._simpan_vektor = meledak
        with self.assertRaises(RuntimeError):
            store.tambah_episode("hantu", sumber="uji", tier="I", lingkup="proyek:x",
                                 jenis_kejadian="sukses", ringkas="r")
        store.catat_metrik("apa_saja", 1)  # penulis berikutnya melakukan commit
        self.assertEqual(store.db.execute("SELECT COUNT(*) FROM episode").fetchone()[0], 0,
                         "baris hantu tidak boleh muncul setelah commit orang lain")

    def test_episode_yang_berhasil_tetap_punya_blob(self):
        """Arah kedua: jangan sampai 'tidak ada yatim' dicapai dengan tidak menulis apa pun."""
        store = Store(self.data, PenyematLokal())
        ep = store.tambah_episode("berhasil", sumber="uji", tier="I", lingkup="proyek:x",
                                  jenis_kejadian="sukses", ringkas="r")
        self.assertEqual(len(self._berkas_dingin(store)), 1)
        self.assertEqual(store.buka_dingin(ep.isi_ref)["isi"], "berhasil")


class PindahEmbedder(unittest.TestCase):
    """K8/K9: lokal (512-dim) → e5-base (768-dim). Jalur pindahnya harus benar-benar bekerja."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ingat-pindah-")
        self.data = os.path.join(self.dir, "data")
        store = Store(self.data, PenyematLokal())
        self.ep = store.tambah_episode("npm ci gagal karena postinstall diblokir", sumber="uji", tier="I",
                                       lingkup="proyek:fp-dashboard", jenis_kejadian="kegagalan",
                                       ringkas="npm ci gagal")
        store.db.close()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_ganti_penyemat_ditolak_tanpa_bangun_ulang(self):
        with self.assertRaises(IdentitasEmbedderTidakCocok) as c:
            Store(self.data, PenyematE5Palsu())
        self.assertIn("bangun_ulang_vektor=True", str(c.exception))

    def test_bangun_ulang_vektor_menyelesaikan_pindah(self):
        store = Store(self.data, PenyematE5Palsu(), bangun_ulang_vektor=True)
        dim = {r[0] for r in store.db.execute("SELECT DISTINCT dimensi FROM vektor")}
        self.assertEqual(dim, {768}, "semua vektor disemat ulang ke dimensi baru")
        self.assertEqual({r[0] for r in store.db.execute("SELECT DISTINCT model FROM identitas_embedder")},
                         {"e5-base-palsu"})
        ep = store.episode(self.ep.id)
        self.assertIsNotNone(ep, "episode tidak boleh hilang saat pindah")
        self.assertEqual(store.buka_dingin(ep.isi_ref)["isi"], "npm ci gagal karena postinstall diblokir",
                         "isi verbatim utuh (K10) — yang disemat ulang hanya vektor")

    def test_membuka_lagi_setelah_pindah_tidak_perlu_bendera(self):
        Store(self.data, PenyematE5Palsu(), bangun_ulang_vektor=True).db.close()
        store = Store(self.data, PenyematE5Palsu())  # tanpa bendera — identitas sudah tercatat
        self.assertEqual(store.episode(self.ep.id).id, self.ep.id)


if __name__ == "__main__":
    unittest.main()
