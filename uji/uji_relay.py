# SPDX-License-Identifier: Apache-2.0
"""K30 — mode relay: VPS turun pangkat jadi pintu masuk BACA-SAJA untuk tier P/I.

Kenapa ini penegakan keamanan, bukan sekadar konfigurasi: laptop jadi mesin otoritatif dan
tier S tidak boleh pernah menyentuh VPS. Jalan paling kokoh ke sana bukan "deteksi lalu hapus"
(dua langkah yang bisa gagal diam-diam), melainkan **menutup seluruh jalur tulis** di relay —
tidak ada tulis yang mendarat, jadi tidak ada tier S yang bisa tiba. Itu opsi A yang dipilih
Tuan Muda 13 Sep 2026.

Sisi baca sudah aman sejak sebelumnya: `Gateway.buka_bukti` menolak tier S tanpa `sertakan_S`,
dan jalur HTTP tidak pernah mengirim flag itu.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from ingat import api as modul_api
from ingat.api import buat_handler
from ingat.aplikasi import Aplikasi, KONFIG_DEFAULT
from ingat.mcp_stdio import tangani_pesan, tools_untuk

TOKEN = "token-uji-panjang-24-karakter-lebih"


class _Dasar(unittest.TestCase):
    relay = False

    def setUp(self):
        modul_api._LAJU.clear()
        self.dir = tempfile.mkdtemp(prefix="ingat-relay-")
        k = json.loads(json.dumps(KONFIG_DEFAULT))
        k["dir_data"] = os.path.join(self.dir, "data")
        k["vault"] = os.path.join(self.dir, "vault")
        k["relay"] = {"aktif": self.relay}
        self.app = Aplikasi(k)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), buat_handler(self.app, TOKEN, {"laju_per_menit": 500}))
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def pukul(self, metode, path, badan=None):
        url = f"http://127.0.0.1:{self.port}{path}"
        data = json.dumps(badan).encode() if badan is not None else None
        req = urllib.request.Request(url, data=data, method=metode)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {TOKEN}")
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode())

    EPISODE = {"isi": "x", "sumber": "uji", "tier": "I", "lingkup": "global",
               "jenis_kejadian": "sukses", "ringkas": "x"}


class RelayMati(_Dasar):
    """Default. Tanpa blok `relay`, server berperilaku persis seperti sebelum K30."""

    relay = False

    def test_tulis_jalan_seperti_biasa(self):
        self.assertEqual(self.pukul("POST", "/episode", self.EPISODE)[0], 201)
        self.assertEqual(self.pukul("POST", "/konsolidasi", {})[0], 200)

    def test_mcp_menawarkan_catat_episode(self):
        nama = {t["name"] for t in tools_untuk(self.app)}
        self.assertIn("catat_episode", nama)


class RelayAktif(_Dasar):
    relay = True

    def test_semua_jalur_tulis_ditolak_403(self):
        for path, badan in (("/episode", self.EPISODE),
                            ("/metrik", {"nama": "x", "nilai": 1}),
                            ("/tanya", {"penyedia": "lokal", "pesan": "p", "lingkup": "global"}),
                            ("/konsolidasi", {}),
                            ("/sinkron", {}),
                            ("/instrumen", {"id": "i", "nama": "I"}),
                            ("/prosedur/pr-1/eksekusi", {"berhasil": True})):
            with self.subTest(path=path):
                status, isi = self.pukul("POST", path, badan)
                self.assertEqual(status, 403, f"{path} harus ditolak di relay, dapat {status}")
                self.assertIn("relay", json.dumps(isi).lower())

    def test_episode_tier_s_tidak_bisa_mendarat_sama_sekali(self):
        """Inti K30: bukan 'terdeteksi lalu dihapus', tapi tidak pernah tiba."""
        status, _ = self.pukul("POST", "/episode", {**self.EPISODE, "tier": "S", "isi": "NIK 3174091208900007"})
        self.assertEqual(status, 403)
        self.assertEqual(self.app.store.episode_semua(), [], "tidak boleh ada episode tersimpan di relay")

    def test_baca_tetap_jalan(self):
        for path, badan in (("/ingat", {"query": "apa", "lingkup": "global"}),
                            ("/startup", {"lingkup": "global"}),
                            ("/dashboard/data", {})):
            with self.subTest(path=path):
                self.assertEqual(self.pukul("POST", path, badan)[0], 200, f"{path} adalah baca, harus tetap jalan")
        self.assertEqual(self.pukul("GET", "/metrik")[0], 200, "GET /metrik adalah baca")
        self.assertEqual(self.pukul("GET", "/sehat")[0], 200)

    def test_mcp_tidak_menawarkan_tool_tulis(self):
        nama = {t["name"] for t in tools_untuk(self.app)}
        self.assertNotIn("catat_episode", nama, "relay tidak boleh mengiklankan tool tulis")
        self.assertEqual(nama, {"ingat", "muat_startup", "buka_bukti"})

    def test_mcp_catat_episode_ditolak_walau_dipanggil_langsung(self):
        """Menyembunyikan dari tools/list saja tidak cukup — klien bisa memanggil namanya begitu saja."""
        jawab = tangani_pesan(self.app, {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                         "params": {"name": "catat_episode",
                                                    "arguments": {"isi": "x", "lingkup": "global",
                                                                  "jenis_kejadian": "sukses", "ringkas": "x"}}})
        teks = json.dumps(jawab).lower()
        self.assertIn("relay", teks)
        self.assertEqual(self.app.store.episode_semua(), [])


if __name__ == "__main__":
    unittest.main()
