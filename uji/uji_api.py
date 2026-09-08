# SPDX-License-Identifier: Apache-2.0
"""Uji REST API (ingat/api.py) — server nyata di port bebas, dipukul via urllib. Sebelumnya modul ini
TANPA UJI SAMA SEKALI. Fokus: /episode (jalur masuk ekstensi browser + dashboard mana pun), auth, rate limit."""
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

from ingat.aplikasi import Aplikasi, KONFIG_DEFAULT
from ingat.api import buat_handler
from ingat import api as modul_api


class ServerUji(unittest.TestCase):
    def setUp(self):
        modul_api._LAJU.clear()  # _LAJU per-IP global antar-modul; bersihkan supaya tiap uji independen
        self.dir = tempfile.mkdtemp(prefix="ingat-api-")
        k = json.loads(json.dumps(KONFIG_DEFAULT))
        k["dir_data"] = os.path.join(self.dir, "data")
        k["vault"] = os.path.join(self.dir, "vault")
        self.app = Aplikasi(k)
        self.token = "token-uji-panjang-24-karakter-lebih"
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), buat_handler(self.app, self.token, {"laju_per_menit": 3}))
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def _pukul(self, metode, path, badan=None, token=None):
        url = f"http://127.0.0.1:{self.port}{path}"
        data = json.dumps(badan).encode() if badan is not None else None
        req = urllib.request.Request(url, data=data, method=metode)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if token is not None:
            req.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode())

    def test_sehat_tanpa_token(self):
        status, _ = self._pukul("GET", "/sehat")
        self.assertEqual(status, 200)

    def test_episode_wajib_token(self):
        status, badan = self._pukul("POST", "/episode", {"isi": "x", "sumber": "uji", "tier": "I", "lingkup": "global",
                                                          "jenis_kejadian": "sukses", "ringkas": "x"})
        self.assertEqual(status, 401)
        status, badan = self._pukul("POST", "/episode", {"isi": "x"}, token="token-salah-tapi-24-karakter-panjang")
        self.assertEqual(status, 401)

    def test_episode_seperti_dari_ekstensi_browser(self):
        """Payload persis bentuk yang dikirim background.js: isi, sumber browser:<host>, langkah, sesi."""
        badan = {
            "isi": "[percakapan chatgpt.com/c/abc] 2 pesan\n\n10:00:00 user: tolong jelaskan X\n10:00:05 assistant: begini caranya...",
            "sumber": "browser:chatgpt.com", "tier": "I", "lingkup": "peran:asisten-ai",
            "jenis_kejadian": "sukses", "ringkas": "Percakapan chatgpt.com: 2 pesan",
            "instrumen": ["browser:chatgpt.com"], "langkah": ["🧑 tolong jelaskan X", "🤖 begini caranya..."],
            "sesi": "chatgpt.com:/c/abc",
        }
        status, hasil = self._pukul("POST", "/episode", badan, token=self.token)
        self.assertEqual(status, 201, hasil)
        ep = self.app.store.episode(hasil["id"])
        self.assertEqual(ep.sumber, "browser:chatgpt.com")
        self.assertEqual(ep.lingkup, "peran:asisten-ai")
        self.assertEqual(ep.sesi, "chatgpt.com:/c/abc")
        self.assertEqual(len(ep.langkah), 2)

    def test_episode_koreksi_dari_browser_bobot_5(self):
        status, hasil = self._pukul("POST", "/episode", {
            "isi": "[koreksi] jangan asumsikan begitu", "sumber": "browser:claude.ai", "tier": "I",
            "lingkup": "peran:asisten-ai", "jenis_kejadian": "koreksi", "ringkas": "jangan asumsikan begitu",
            "instrumen": ["browser:claude.ai"], "sesi": "claude.ai:/chat/xyz",
        }, token=self.token)
        self.assertEqual(status, 201, hasil)
        self.assertEqual(hasil["bobot"], 5)

    def test_kredensial_dalam_percakapan_browser_tetap_diredaksi(self):
        """K10 tidak bergantung pada sumbernya — /episode tetap lewat Store.tambah_episode."""
        status, hasil = self._pukul("POST", "/episode", {
            "isi": "kuncinya sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789 ya",
            "sumber": "browser:chatgpt.com", "tier": "I", "lingkup": "global",
            "jenis_kejadian": "sukses", "ringkas": "berbagi kunci API",
        }, token=self.token)
        self.assertEqual(status, 201, hasil)
        isi = self.app.store.buka_dingin(self.app.store.episode(hasil["id"]).isi_ref)["isi"]
        self.assertNotIn("sk-ant-api03", isi)
        self.assertIn("[REDAKSI:kunci-anthropic]", isi)

    def test_rate_limit_per_ip(self):
        ok = 0
        for _ in range(5):
            status, _ = self._pukul("POST", "/episode", {"isi": "x", "sumber": "uji", "tier": "I", "lingkup": "global",
                                                          "jenis_kejadian": "sukses", "ringkas": "x"}, token=self.token)
            if status == 201:
                ok += 1
        self.assertLessEqual(ok, 3, "laju_per_menit=3 di setUp harus menolak sisanya")

    def test_ingat_endpoint(self):
        self._pukul("POST", "/episode", {"isi": "x", "sumber": "uji", "tier": "I", "lingkup": "global",
                                         "jenis_kejadian": "sukses", "ringkas": "kejadian tentang tool kosong"}, token=self.token)
        status, hasil = self._pukul("POST", "/ingat", {"query": "tool kosong", "lingkup": "global"}, token=self.token)
        self.assertEqual(status, 200, hasil)
        self.assertIn("item", hasil)

    def test_openapi_tidak_perlu_token(self):
        status, hasil = self._pukul("GET", "/openapi.json")
        self.assertEqual(status, 200)
        self.assertIn("/episode", hasil.get("paths", {}))

    # ---- yang dipakai hook mode jauh (ingat/jauh.py) --------------------------------
    def test_episode_dengan_id_meng_upsert_bukan_menambah(self):
        """Hook Stop mengirim id deterministik tiap kali sesi berhenti. Tanpa `id` diteruskan, tiap
        Stop membuat episode baru — banjir yang justru dicegah desain anti-banjir di tangkap.py."""
        badan = {"isi": "langkah pertama", "id": "ep-sesi-uji-jauh", "sumber": "claude-code", "tier": "I",
                 "lingkup": "proyek:uji", "jenis_kejadian": "sukses", "ringkas": "sesi 1 langkah"}
        status1, j1 = self._pukul("POST", "/episode", badan, token=self.token)
        badan["isi"] = "langkah pertama dan kedua"
        status2, j2 = self._pukul("POST", "/episode", badan, token=self.token)
        self.assertEqual((status1, status2), (201, 201))
        self.assertEqual(j1["id"], "ep-sesi-uji-jauh", "id yang dikirim klien harus dipakai apa adanya")
        self.assertEqual(j2["id"], j1["id"], "pengiriman kedua harus menimpa episode yang sama")
        jumlah = self.app.store.db.execute(
            "SELECT COUNT(*) FROM episode WHERE id=?", ("ep-sesi-uji-jauh",)).fetchone()[0]
        self.assertEqual(jumlah, 1, f"harus tetap satu baris setelah dua kiriman, dapat {jumlah}")

    def test_metrik_bisa_ditulis_lewat_post(self):
        """Tanpa endpoint ini, alarm Bab 11 (`sesi_tanpa_episode`) mati diam-diam di mode jauh."""
        status, jawab = self._pukul("POST", "/metrik", {"nama": "sesi_tanpa_episode", "nilai": 1,
                                                        "konteks": {"sesi": "abc", "lingkup": "proyek:uji"}},
                                    token=self.token)
        self.assertEqual(status, 200)
        self.assertTrue(jawab.get("ok"))
        baris = self.app.store.db.execute(
            "SELECT nama, nilai, konteks FROM metrik WHERE nama='sesi_tanpa_episode'").fetchone()
        self.assertIsNotNone(baris, "metrik yang dikirim lewat HTTP harus mendarat di tabel metrik")
        self.assertEqual(baris[1], 1.0)
        self.assertIn("abc", baris[2], "konteks sesi harus ikut tersimpan")

    def test_metrik_post_tetap_wajib_token(self):
        status, _ = self._pukul("POST", "/metrik", {"nama": "x", "nilai": 1})
        self.assertEqual(status, 401, "endpoint tulis baru tidak boleh terbuka tanpa token")


if __name__ == "__main__":
    unittest.main()
