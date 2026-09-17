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


class JendelaKoneksi(unittest.TestCase):
    """Smoke test: jendela Koneksi AI benar-benar terbangun (Tk asli), bukan cuma helper.
    Dilewati bila lingkungan tak punya display Tk."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ingat-konwin-")
        self.store = Store(os.path.join(self.dir, "s"), PenyematLokal())
        self.store.tambah_episode("x", sumber="mcp", tier="I", lingkup="peran:asisten-ai",
                                  jenis_kejadian="sukses", ringkas="r", instrumen=["x"], sesi="s1")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_terbangun_tanpa_galat(self):
        try:
            import tkinter as tk
            root = tk.Tk()
        except Exception as e:  # tanpa display (CI headless)
            self.skipTest("tanpa display Tk: " + str(e))
        root.withdraw()

        class AppStub:
            pass
        a = AppStub()
        a.store = self.store
        try:
            win = panel.bangun_jendela_koneksi(root, a, lambda *_: None)
            root.update_idletasks()
            root.update()
            self.assertTrue(win.winfo_exists())
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
