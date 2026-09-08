# SPDX-License-Identifier: Apache-2.0
"""Mode jauh: hook menulis ke server, bukan ke SQLite mesin ini (ingat/jauh.py).

Tanpa jaringan sungguhan — `pembuka` (pengganti urlopen) disuntik, sesuai aturan uji repo.
Yang dijaga di sini bukan "jalur bahagia"-nya, melainkan janji yang bikin mode ini layak dipakai:
server mati tidak boleh menghilangkan episode, dan tidak boleh menggagalkan hook.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
import unittest
import unittest.mock
import urllib.error

from ingat.jauh import (AplikasiJauh, JauhGagal, KlienJauh, StoreJauh, TIMEOUT_BAWAAN,
                        bangun_aplikasi_jauh, baca_token)


class PembukaPalsu:
    """Mencatat permintaan dan mengembalikan jawaban yang sudah disiapkan; bisa disuruh gagal."""

    def __init__(self, jawaban=None, galat=None):
        self.jawaban = jawaban if jawaban is not None else {"id": "ep-dari-server", "bobot": 1}
        self.galat = galat
        self.permintaan: list[tuple[str, dict, dict]] = []

    def __call__(self, req, timeout=None):
        badan = json.loads(req.data.decode("utf-8")) if req.data else {}
        self.permintaan.append((req.full_url, badan, dict(req.header_items())))
        if self.galat:
            raise self.galat
        isi = json.dumps(self.jawaban).encode("utf-8")

        class Jawab(io.BytesIO):
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *a):
                return False

        return Jawab(isi)


class Kirim(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ingat-jauh-")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_episode_dikirim_dengan_bearer_dan_id_dipertahankan(self):
        """`id` WAJIB ikut: itu yang membuat hook Stop meng-upsert satu episode per sesi, bukan membanjiri."""
        p = PembukaPalsu()
        store = StoreJauh(KlienJauh("https://contoh.id/", "rahasia123", pembuka=p), self.dir)
        ep = store.tambah_episode("isi", id="ep-sesi-abc", lingkup="proyek:x", tier="I", sesi="abc")
        url, badan, header = p.permintaan[0]
        self.assertEqual(url, "https://contoh.id/episode", "host bergaris miring di ujung harus dirapikan")
        self.assertEqual(badan["id"], "ep-sesi-abc", "id deterministik harus diteruskan apa adanya")
        self.assertEqual(header.get("Authorization"), "Bearer rahasia123")
        self.assertEqual(ep.id, "ep-dari-server", "id dari server yang dipakai, bukan tebakan klien")

    def test_metrik_dikirim_sebagai_konteks_bersarang(self):
        p = PembukaPalsu(jawaban={"ok": True})
        store = StoreJauh(KlienJauh("https://contoh.id", "t", pembuka=p), self.dir)
        store.catat_metrik("sesi_tanpa_episode", 1, sesi="abc", lingkup="proyek:x")
        _url, badan, _h = p.permintaan[0]
        self.assertEqual(badan["nama"], "sesi_tanpa_episode")
        self.assertEqual(badan["konteks"], {"sesi": "abc", "lingkup": "proyek:x"})


class ServerMati(unittest.TestCase):
    """Janji inti: jaringan putus tidak menghilangkan episode dan tidak melempar ke pemanggil."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ingat-jauh-mati-")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _store(self, pembuka):
        return StoreJauh(KlienJauh("https://contoh.id", "t", pembuka=pembuka), self.dir)

    def test_gagal_jaringan_tidak_melempar_dan_masuk_spool(self):
        p = PembukaPalsu(galat=OSError("jaringan mati"))
        store = self._store(p)
        ep = store.tambah_episode("isi penting", id="ep-1", lingkup="proyek:x")
        self.assertEqual(ep.id, "ep-1", "tanpa jawaban server, id lokal dipakai supaya pemanggil tetap dapat sesuatu")
        with open(os.path.join(self.dir, "spool.jsonl"), encoding="utf-8") as f:
            baris = [json.loads(b) for b in f if b.strip()]
        self.assertEqual(len(baris), 1, "episode yang gagal kirim harus tersimpan, bukan hilang")
        self.assertEqual(baris[0]["badan"]["isi"], "isi penting")

    def test_spool_dikuras_saat_server_hidup_lagi(self):
        mati = PembukaPalsu(galat=OSError("jaringan mati"))
        store = self._store(mati)
        store.tambah_episode("episode pertama", id="ep-1")
        store.tambah_episode("episode kedua", id="ep-2")

        hidup = PembukaPalsu()
        store.klien._pembuka = hidup
        store.tambah_episode("episode ketiga", id="ep-3")

        terkirim = [b["isi"] for _u, b, _h in hidup.permintaan]
        self.assertEqual(terkirim, ["episode pertama", "episode kedua", "episode ketiga"],
                         "spool harus dikuras lebih dulu dan urutannya dipertahankan")
        self.assertFalse(os.path.exists(os.path.join(self.dir, "spool.jsonl")),
                         "spool yang sudah terkirim habis harus dihapus")

    def test_galat_4xx_tidak_di_spool(self):
        """Token salah/permintaan cacat: mengulangnya selamanya hanya menumpuk sampah."""
        galat = urllib.error.HTTPError("https://contoh.id/episode", 401, "Unauthorized", {}, None)
        store = self._store(PembukaPalsu(galat=galat))
        store.tambah_episode("isi", id="ep-1")
        self.assertFalse(os.path.exists(os.path.join(self.dir, "spool.jsonl")),
                         "galat 4xx tidak layak diulang, jadi tidak boleh masuk spool")

    def test_galat_5xx_di_spool(self):
        galat = urllib.error.HTTPError("https://contoh.id/episode", 503, "Unavailable", {}, None)
        store = self._store(PembukaPalsu(galat=galat))
        store.tambah_episode("isi", id="ep-1")
        self.assertTrue(os.path.exists(os.path.join(self.dir, "spool.jsonl")),
                        "5xx bersifat sementara — harus dicoba lagi nanti")

    def test_startup_gagal_mengembalikan_konteks_kosong_bukan_galat(self):
        """SessionStart saat VPS mati: sesi tetap jalan, cuma tanpa konteks memori."""
        app = AplikasiJauh(KlienJauh("https://contoh.id", "t", pembuka=PembukaPalsu(galat=OSError("mati"))), self.dir)
        hasil = app.gateway.muat_startup("proyek:x", sesi="abc")
        self.assertEqual(hasil["peta"], [])
        self.assertEqual(hasil["aturan"], [])
        self.assertFalse(os.path.exists(os.path.join(self.dir, "spool.jsonl")),
                         "operasi BACA tidak boleh di-spool — jawabannya sudah basi saat dikirim ulang")


class BangunDariKonfigurasi(unittest.TestCase):
    def test_tanpa_blok_jauh_mengembalikan_none(self):
        self.assertIsNone(bangun_aplikasi_jauh({"dir_data": "/tmp/x"}),
                          "tanpa `jauh.host`, hook harus tetap memakai store lokal")

    def test_host_kosong_dianggap_tidak_diminta(self):
        self.assertIsNone(bangun_aplikasi_jauh({"dir_data": "/tmp/x", "jauh": {"host": "   "}}))

    def test_dengan_host_menghasilkan_aplikasi_jauh(self):
        app = bangun_aplikasi_jauh({"dir_data": "/tmp/x", "jauh": {"host": "https://contoh.id", "timeout_detik": 2}})
        self.assertIsInstance(app, AplikasiJauh)
        self.assertEqual(app.store.klien.timeout, 2.0)

    def test_timeout_bawaan_pendek(self):
        """Hook tidak boleh menggantung: bawaannya harus beberapa detik, bukan puluhan."""
        self.assertLessEqual(TIMEOUT_BAWAAN, 10, f"timeout bawaan {TIMEOUT_BAWAAN}s terlalu lama untuk hook")


class Token(unittest.TestCase):
    """`~` DIALIHKAN ke folder sementara di seluruh kelas ini.

    Tanpa itu uji membaca `~/.ingat/token` milik mesin yang menjalankannya: hijau di mesin yang
    belum memakai mode jauh, merah di mesin yang sudah — persis yang terjadi begitu laptop ini
    disambungkan ke VPS. Uji tidak boleh bergantung pada keadaan mesin penguji.
    """

    def setUp(self):
        self.simpan = os.environ.pop("INGAT_TOKEN", None)
        self.rumah = tempfile.mkdtemp(prefix="ingat-rumah-")
        asli = os.path.expanduser

        def expanduser_palsu(p: str) -> str:
            return os.path.join(self.rumah, p[2:]) if p.startswith("~/") else asli(p)

        self.tambal = unittest.mock.patch("ingat.jauh.os.path.expanduser", expanduser_palsu)
        self.tambal.start()

    def tearDown(self):
        self.tambal.stop()
        shutil.rmtree(self.rumah, ignore_errors=True)
        if self.simpan is not None:
            os.environ["INGAT_TOKEN"] = self.simpan
        else:
            os.environ.pop("INGAT_TOKEN", None)

    def _tulis_berkas_token(self, isi: str):
        os.makedirs(os.path.join(self.rumah, ".ingat"), exist_ok=True)
        with open(os.path.join(self.rumah, ".ingat", "token"), "w", encoding="utf-8") as f:
            f.write(isi)

    def test_env_diutamakan(self):
        os.environ["INGAT_TOKEN"] = "dari-env"
        self._tulis_berkas_token("dari-berkas")
        self.assertEqual(baca_token({"jauh": {"token": "dari-konfig"}}), "dari-env")

    def test_berkas_diutamakan_di_atas_konfigurasi(self):
        """Hook sering jalan tanpa mewarisi environment shell — berkas harus menang atas konfigurasi."""
        self._tulis_berkas_token("dari-berkas\n")
        self.assertEqual(baca_token({"jauh": {"token": "dari-konfig"}}), "dari-berkas",
                         "spasi/baris baru di berkas token harus dipangkas")

    def test_jatuh_ke_konfigurasi_bila_env_dan_berkas_kosong(self):
        self.assertEqual(baca_token({"jauh": {"token": "dari-konfig"}}), "dari-konfig")

    def test_berkas_kosong_dilewati_bukan_dianggap_token(self):
        self._tulis_berkas_token("   \n")
        self.assertEqual(baca_token({"jauh": {"token": "dari-konfig"}}), "dari-konfig",
                         "berkas token yang isinya spasi harus dianggap tidak ada")

    def test_tanpa_sumber_apa_pun_mengembalikan_kosong(self):
        self.assertEqual(baca_token({}), "")


if __name__ == "__main__":
    unittest.main()
