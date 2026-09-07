# SPDX-License-Identifier: Apache-2.0
"""K25: autentikasi Google OAuth2 untuk dashboard. Transport Google disuntik palsu — nol jaringan nyata.
Alur diuji lewat server sungguhan (port bebas): mulai -> callback -> cookie sesi -> /dashboard/data."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest import mock

from ingat import api as modul_api
from ingat.api import buat_handler
from ingat.aplikasi import Aplikasi, KONFIG_DEFAULT
from ingat.auth_google import (
    AuthGagal, ambil_cookie, baca_sesi, buat_sesi, email_diizinkan, url_masuk, verifikasi_id_token,
)


class SesiCookie(unittest.TestCase):
    def test_bulat_balik_dan_tanda_tangan(self):
        c = buat_sesi("fadelli@example.com", "rahasia-uji-24-karakter-plus")
        self.assertEqual(baca_sesi(c, "rahasia-uji-24-karakter-plus"), "fadelli@example.com")

    def test_rahasia_salah_ditolak(self):
        c = buat_sesi("fadelli@example.com", "rahasia-a-yang-benar-24kar")
        self.assertIsNone(baca_sesi(c, "rahasia-b-yang-salah-24kar"))

    def test_cookie_dirusak_ditolak(self):
        c = buat_sesi("fadelli@example.com", "rahasia-uji-24-karakter-plus")
        rusak = c[:-2] + ("xx" if c[-2:] != "xx" else "yy")
        self.assertIsNone(baca_sesi(rusak, "rahasia-uji-24-karakter-plus"))

    def test_kadaluwarsa(self):
        c = buat_sesi("fadelli@example.com", "rahasia-uji-24-karakter-plus", umur_detik=-10)
        self.assertIsNone(baca_sesi(c, "rahasia-uji-24-karakter-plus"))

    def test_ambil_cookie_dari_header(self):
        h = "a=1; ingat_sesi=abc123; b=2"
        self.assertEqual(ambil_cookie(h, "ingat_sesi"), "abc123")
        self.assertIsNone(ambil_cookie(h, "tidak_ada"))
        self.assertIsNone(ambil_cookie("", "ingat_sesi"))


class Allowlist(unittest.TestCase):
    def test_pencocokan_tanpa_peduli_besar_kecil_huruf_dan_spasi(self):
        self.assertTrue(email_diizinkan("Fadelli@Example.com", [" fadelli@example.com "]))
        self.assertFalse(email_diizinkan("orang.lain@example.com", ["fadelli@example.com"]))
        self.assertFalse(email_diizinkan("siapa@saja.com", []))  # allowlist kosong = tidak ada yang diizinkan


class TransportPalsu(unittest.TestCase):
    def test_url_masuk_memuat_state_dan_scope(self):
        u = url_masuk("client-x", "https://d/auth/google/callback", "state-123")
        self.assertIn("state=state-123", u)
        self.assertIn("scope=openid+email", u)
        self.assertIn("client_id=client-x", u)

    def test_verifikasi_token_menolak_audience_salah(self):
        def palsu(req, timeout=15):
            class R:
                def read(self_): return json.dumps({"aud": "client-lain", "email": "x@y.com", "email_verified": "true"}).encode()
                def __enter__(self_): return self_
                def __exit__(self_, *a): return False
            return R()
        with self.assertRaises(AuthGagal):
            verifikasi_id_token("token-apa-saja", "client-benar", pembuka=palsu)

    def test_verifikasi_token_menolak_email_tak_terverifikasi(self):
        def palsu(req, timeout=15):
            class R:
                def read(self_): return json.dumps({"aud": "c", "email": "x@y.com", "email_verified": "false"}).encode()
                def __enter__(self_): return self_
                def __exit__(self_, *a): return False
            return R()
        with self.assertRaises(AuthGagal):
            verifikasi_id_token("t", "c", pembuka=palsu)

    def test_verifikasi_token_sukses(self):
        def palsu(req, timeout=15):
            class R:
                def read(self_): return json.dumps({"aud": "c", "email": "fadelli@example.com", "email_verified": "true"}).encode()
                def __enter__(self_): return self_
                def __exit__(self_, *a): return False
            return R()
        self.assertEqual(verifikasi_id_token("t", "c", pembuka=palsu), "fadelli@example.com")


class AlurServerNyata(unittest.TestCase):
    def setUp(self):
        modul_api._LAJU.clear()
        self.dir = tempfile.mkdtemp(prefix="ingat-authg-")
        k = json.loads(json.dumps(KONFIG_DEFAULT))
        k["dir_data"] = os.path.join(self.dir, "data"); k["vault"] = os.path.join(self.dir, "vault")
        k["auth"] = {"allowed_emails": ["fadelli@example.com"], "redirect_uri": "https://uji.contoh/auth/google/callback"}
        self.app = Aplikasi(k)
        self.token = "token-authg-uji-24-karakter-plus"
        self.google = {"client_id": "client-uji", "client_secret": "secret-uji", "sesi_rahasia": "sesi-rahasia-uji-24-karakter"}
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), buat_handler(self.app, self.token, {"laju_per_menit": 500}, self.google))
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.dasar = f"http://127.0.0.1:{self.port}"

    def tearDown(self):
        self.server.shutdown(); self.server.server_close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def _req(self, metode, path, badan=None, cookie=None, ikuti=False):
        req = urllib.request.Request(self.dasar + path, data=(json.dumps(badan).encode() if badan is not None else None), method=metode)
        if badan is not None:
            req.add_header("Content-Type", "application/json")
        if cookie:
            req.add_header("Cookie", cookie)
        opener = urllib.request.build_opener(urllib.request.HTTPRedirectHandler if ikuti else NoRedirect)
        try:
            with opener.open(req, timeout=5) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    def test_mulai_redirect_ke_google_dengan_state_cookie(self):
        status, header, _ = self._req("GET", "/auth/google/mulai")
        self.assertEqual(status, 302)
        self.assertIn("accounts.google.com", header["Location"])
        self.assertIn("ingat_state=", header.get("Set-Cookie", ""))

    def test_mulai_tanpa_client_id_501(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), buat_handler(self.app, self.token, {"laju_per_menit": 500}, {}))
        port = server.server_address[1]
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{port}/auth/google/mulai")
            opener = urllib.request.build_opener(NoRedirect)
            try:
                opener.open(req, timeout=5)
                self.fail("harus 501")
            except urllib.error.HTTPError as e:
                self.assertEqual(e.code, 501)
        finally:
            server.shutdown(); server.server_close()

    def test_callback_state_tidak_cocok_ditolak(self):
        status, _, _ = self._req("GET", "/auth/google/callback?code=x&state=salah", cookie="ingat_state=benar")
        self.assertEqual(status, 400)

    def test_alur_penuh_login_lalu_akses_dashboard_lewat_cookie(self):
        status, header, _ = self._req("GET", "/auth/google/mulai")
        state = header["Set-Cookie"].split("ingat_state=")[1].split(";")[0]

        with mock.patch("ingat.api.tukar_kode", return_value={"id_token": "token-palsu"}), \
             mock.patch("ingat.api.verifikasi_id_token", return_value="fadelli@example.com"):
            status, header, _ = self._req("GET", f"/auth/google/callback?code=abc&state={state}", cookie=f"ingat_state={state}")
        self.assertEqual(status, 302)
        self.assertEqual(header["Location"], "/dashboard")
        set_cookie_sesi = [v for k, v in header.items() if k == "Set-Cookie"] if isinstance(header, dict) else []
        cookie_sesi_baris = header.get("Set-Cookie", "")
        self.assertIn("ingat_sesi=", cookie_sesi_baris)
        sesi_val = cookie_sesi_baris.split("ingat_sesi=")[1].split(";")[0]

        # /dashboard/data lewat cookie sesi, TANPA Authorization header
        status, _, badan = self._req("POST", "/dashboard/data", {}, cookie=f"ingat_sesi={sesi_val}")
        self.assertEqual(status, 200, badan)

    def test_email_tidak_di_allowlist_ditolak_403(self):
        status, header, _ = self._req("GET", "/auth/google/mulai")
        state = header["Set-Cookie"].split("ingat_state=")[1].split(";")[0]
        with mock.patch("ingat.api.tukar_kode", return_value={"id_token": "token-palsu"}), \
             mock.patch("ingat.api.verifikasi_id_token", return_value="orang.lain@example.com"):
            status, _, badan = self._req("GET", f"/auth/google/callback?code=abc&state={state}", cookie=f"ingat_state={state}")
        self.assertEqual(status, 403, badan)

    def test_keluar_menghapus_cookie(self):
        status, header, _ = self._req("GET", "/auth/keluar")
        self.assertEqual(status, 302)
        self.assertIn("ingat_sesi=; Path=/; Max-Age=0", header["Set-Cookie"])

    def test_sesi_endpoint(self):
        status, _, badan = self._req("GET", "/auth/sesi")
        self.assertEqual(json.loads(badan), {"masuk": False, "email": None})


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


if __name__ == "__main__":
    unittest.main()
