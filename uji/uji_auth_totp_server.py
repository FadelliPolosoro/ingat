# SPDX-License-Identifier: Apache-2.0
"""K26: rute server /auth/totp/masuk — jalur mandiri, tidak bergantung Google. Fokus: kode benar
diterima+cookie disetel, kode salah ditolak, dan PEMBATAS LAJU KETAT (5/5menit) benar-benar menyala."""
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
from ingat.auth_totp import buat_rahasia, kode_sekarang


class ServerTotp(unittest.TestCase):
    def setUp(self):
        modul_api._LAJU.clear(); modul_api._LAJU_TOTP.clear()
        self.dir = tempfile.mkdtemp(prefix="ingat-totp-")
        k = json.loads(json.dumps(KONFIG_DEFAULT))
        k["dir_data"] = os.path.join(self.dir, "data"); k["vault"] = os.path.join(self.dir, "vault")
        self.app = Aplikasi(k)
        self.token = "token-totp-uji-24-karakter-plus"
        self.rahasia = buat_rahasia()
        self.sesi_rahasia = "sesi-rahasia-totp-uji-24-karakter"
        self.server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            buat_handler(self.app, self.token, {"laju_per_menit": 500}, {}, self.rahasia, self.sesi_rahasia),
        )
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.dasar = f"http://127.0.0.1:{self.port}"

    def tearDown(self):
        self.server.shutdown(); self.server.server_close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def _post(self, path, badan):
        req = urllib.request.Request(self.dasar + path, data=json.dumps(badan).encode(), method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, dict(r.headers), json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), json.loads(e.read())

    def test_kode_benar_diterima_dan_set_cookie(self):
        status, header, badan = self._post("/auth/totp/masuk", {"kode": kode_sekarang(self.rahasia)})
        self.assertEqual(status, 200, badan)
        self.assertTrue(badan["masuk"])
        self.assertIn("ingat_sesi=", header.get("Set-Cookie", ""))

    def test_kode_salah_ditolak_401(self):
        salah = f"{(int(kode_sekarang(self.rahasia)) + 1) % 1_000_000:06d}"
        status, _, _ = self._post("/auth/totp/masuk", {"kode": salah})
        self.assertEqual(status, 401)

    def test_totp_belum_dikonfigurasi_501(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), buat_handler(self.app, self.token, {"laju_per_menit": 500}, {}, "", ""))
        port = server.server_address[1]
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{port}/auth/totp/masuk",
                                         data=json.dumps({"kode": "000000"}).encode(), method="POST")
            req.add_header("Content-Type", "application/json")
            try:
                urllib.request.urlopen(req, timeout=5)
                self.fail("harus 501")
            except urllib.error.HTTPError as e:
                self.assertEqual(e.code, 501)
        finally:
            server.shutdown(); server.server_close()

    def test_pembatas_laju_ketat_5_per_5_menit(self):
        """Ruang kode 6-digit jauh lebih kecil dari token — harus jauh lebih ketat dari batas laju umum."""
        salah = "000000" if kode_sekarang(self.rahasia) != "000000" else "111111"
        kode_status = []
        for _ in range(8):
            status, _, _ = self._post("/auth/totp/masuk", {"kode": salah})
            kode_status.append(status)
        self.assertEqual(kode_status.count(401), 5, kode_status)  # 5 percobaan diproses (semuanya salah -> 401)
        self.assertEqual(kode_status.count(429), 3, kode_status)  # sisanya diblokir batas laju

    def test_badan_bukan_json_objek_400(self):
        req = urllib.request.Request(self.dasar + "/auth/totp/masuk", data=b"[1,2,3]", method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            urllib.request.urlopen(req, timeout=5)
            self.fail("harus 400")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)


if __name__ == "__main__":
    unittest.main()
