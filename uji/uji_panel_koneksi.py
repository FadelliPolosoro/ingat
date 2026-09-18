# SPDX-License-Identifier: Apache-2.0
"""Fase 4 — status koneksi klien AI di panel. Helper bebas-Tkinter: baca rekam
terakhir per sumber (browser:<host> / mcp) dari store, dan baca token server."""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from unittest import mock

from ingat import panel
from ingat.simpan import Store
from ingat.vektor import PenyematLokal

from .uji_panel_gui import KasusTk


class StatusKoneksi(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ingat-kon-")
        self.store = Store(os.path.join(self.dir, "s"), PenyematLokal())

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _ep(self, sumber):
        return self.store.tambah_episode("isi " + sumber, sumber=sumber, tier="I",
                                         lingkup="peran:asisten-ai", jenis_kejadian="sukses",
                                         ringkas="r", instrumen=["x"], sesi="s1")

    def test_klien_terekam_dan_yang_kosong(self):
        self._ep("mcp")
        self._ep("browser:claude.ai")
        self._ep("browser:chatgpt.com")
        peta = {d["nama"]: d for d in panel.status_koneksi(self.store)}
        self.assertIsNotNone(peta["Claude Desktop"]["terakhir"])
        self.assertIsNotNone(peta["Claude.ai"]["terakhir"])
        self.assertIsNotNone(peta["ChatGPT"]["terakhir"])
        self.assertIsNone(peta["Perplexity"]["terakhir"])
        self.assertIsNone(peta["Gemini"]["terakhir"])
        self.assertEqual(peta["Claude Desktop"]["jalur"], "MCP")
        self.assertEqual(peta["Claude.ai"]["jalur"], "web")

    def test_alias_chatgpt_openai_dikenali(self):
        self._ep("browser:chat.openai.com")
        peta = {d["nama"]: d for d in panel.status_koneksi(self.store)}
        self.assertIsNotNone(peta["ChatGPT"]["terakhir"], "chat.openai.com harus terpetakan ke ChatGPT")

    def test_semua_kosong_tanpa_episode(self):
        for d in panel.status_koneksi(self.store):
            self.assertIsNone(d["terakhir"])


class KesehatanKoneksi(unittest.TestCase):
    """Penanda basi: platform yang PERNAH aktif lalu terdiam ≥7 hari → ⚠ merah (capture rusak
    diam-diam, spt ChatGPT dulu). Belum-pernah = netral, bukan alarm."""

    def _iso(self, jam_lalu):
        import datetime as dt
        return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=jam_lalu)).isoformat(timespec="seconds")

    def test_segar_hijau(self):
        self.assertEqual(panel._kesehatan_koneksi(self._iso(2)), ("●", "hijau"))
        self.assertEqual(panel._kesehatan_koneksi(self._iso(47)), ("●", "hijau"))

    def test_setengah_basi_kuning(self):
        self.assertEqual(panel._kesehatan_koneksi(self._iso(4 * 24)), ("●", "kuning"))

    def test_basi_merah_alarm(self):
        self.assertEqual(panel._kesehatan_koneksi(self._iso(8 * 24)), ("⚠", "merah"))

    def test_belum_pernah_netral_bukan_alarm(self):
        self.assertEqual(panel._kesehatan_koneksi(None), ("○", "abu"))

    def test_iso_rusak_tak_melempar(self):
        self.assertEqual(panel._kesehatan_koneksi("bukan-tanggal"), ("○", "abu"))

    def test_usia_relatif_terbaca(self):
        self.assertEqual(panel._usia_relatif(None), "belum ada rekam")
        self.assertIn("jam lalu", panel._usia_relatif(self._iso(5)))
        self.assertIn("hari lalu", panel._usia_relatif(self._iso(3 * 24)))


class Token(unittest.TestCase):
    def test_token_ada_dipangkas(self):
        with mock.patch.dict(os.environ, {"INGAT_TOKEN": "  abc123  "}):
            self.assertEqual(panel.token_server(), "abc123")

    def test_token_kosong_jadi_none(self):
        with mock.patch("ingat.jauh.baca_token", return_value=""):
            self.assertIsNone(panel.token_server())

    def test_token_hilang_jadi_none(self):
        with mock.patch("ingat.jauh.baca_token", return_value=""):
            self.assertIsNone(panel.token_server())


class Siapkan(unittest.TestCase):
    """Tombol pandu-pasang menyalin folder ekstensi/MCPB ke ~/.ingat. Uji logika salin
    (mode source: sumber = folder repo pasang/*)."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ingat-siapkan-")
        self._p = mock.patch.object(panel, "DIR_INGAT", self.dir)
        self._p.start()

    def tearDown(self):
        self._p.stop()
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_siapkan_ekstensi_menyalin_manifest(self):
        p = panel.siapkan_ekstensi()
        self.assertEqual(p, os.path.join(self.dir, "browser-extension"))
        self.assertTrue(os.path.isfile(os.path.join(p, "manifest.json")),
                        "manifest.json ekstensi harus ikut tersalin")

    def test_siapkan_ekstensi_idempoten(self):
        panel.siapkan_ekstensi()
        p = panel.siapkan_ekstensi()  # dirs_exist_ok=True → tak melempar
        self.assertTrue(os.path.isdir(p))

    def test_siapkan_mcpb_menyalin(self):
        p = panel.siapkan_mcpb()
        self.assertEqual(p, os.path.join(self.dir, "mcpb"))
        self.assertTrue(os.path.isdir(p))


class JendelaKoneksi(KasusTk):
    """Smoke test: jendela Koneksi AI benar-benar terbangun (Tk asli) di atas store nyata.

    Memakai harness Tk bersama dari uji_panel_gui. Sejak tombol Sambungkan ada, jendela ini
    memeriksa status DI THREAD: tanpa tiruan ia menyentuh jaringan sungguhan, dan threadnya
    bisa hidup lebih lama dari root-nya — thread yang memegang referensi widget terakhir
    membuat Tcl menggugurkan seluruh proses uji, bukan cuma uji ini yang gagal."""

    def setUp(self):
        super().setUp()
        self.dir = tempfile.mkdtemp(prefix="ingat-konwin-")
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.store = Store(os.path.join(self.dir, "s"), PenyematLokal())
        self.store.tambah_episode("x", sumber="mcp", tier="I", lingkup="peran:asisten-ai",
                                  jenis_kejadian="sukses", ringkas="r", instrumen=["x"], sesi="s1")

    def test_terbangun_tanpa_galat(self):
        class AppStub:
            pass
        a = AppStub()
        a.store = self.store
        ref = {}

        def bangun():
            win = self._catat(panel.bangun_jendela_koneksi(self.root, a, lambda *_: None))
            win.withdraw()
            ref["win"] = win

        with mock.patch("ingat.sambung.status",
                        return_value={"lampu": "kuning", "pesan": "-", "butir": []}):
            self.assertTrue(self._putar(bangun, lambda: "win" in ref))
            self.assertTrue(ref["win"].winfo_exists())


if __name__ == "__main__":
    unittest.main()
