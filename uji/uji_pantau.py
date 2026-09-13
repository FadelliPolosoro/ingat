# SPDX-License-Identifier: Apache-2.0
"""`ingat pantau` — monitor lokal baca-saja. Uji snapshot, handler HTTP (/ dan /data),
dan pagar loopback (tolak host non-loopback karena tanpa auth)."""
from __future__ import annotations

import http.server
import json
import shutil
import tempfile
import threading
import unittest
import urllib.request

from ingat.aplikasi import Aplikasi, muat_konfig
from ingat import pantau, skema


class UjiPantau(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ingat-pantau-")
        k = muat_konfig(None)
        k["dir_data"] = self.dir + "/data"
        k["vault"] = self.dir + "/vault"
        self.app = Aplikasi(k)
        self.app.store.simpan_pelajaran(skema.Pelajaran(
            id="pl-1", pelajaran="x", pemicu="y", tindakan="z", lingkup="global"))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_snapshot_punya_kunci_wajib_tanpa_rahasia(self):
        s = pantau.snapshot(self.app)
        for kunci in ("versi", "mode", "embedding", "dir_data", "metrik"):
            self.assertIn(kunci, s)
        self.assertEqual(s["mode"], "otoritatif")  # relay MATI di konfig default
        self.assertIn("pelajaran_hipotesis", s["metrik"])  # metrik agregat, bukan isi
        # tidak boleh membocorkan token/rahasia
        self.assertNotIn("token", json.dumps(s).lower())

    def test_handler_melayani_html_json_dan_404(self):
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), pantau._buat_handler(self.app))
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            base = f"http://127.0.0.1:{srv.server_address[1]}"
            with urllib.request.urlopen(base + "/data") as r:
                self.assertEqual(r.status, 200)
                data = json.loads(r.read().decode("utf-8"))
                self.assertIn("metrik", data)
            with urllib.request.urlopen(base + "/") as r:
                self.assertEqual(r.status, 200)
                self.assertIn("text/html", r.headers.get("Content-Type", ""))
                self.assertIn(b"ingat", r.read())
            with self.assertRaises(urllib.error.HTTPError) as cm:
                urllib.request.urlopen(base + "/apa-saja")
            self.assertEqual(cm.exception.code, 404)
        finally:
            srv.shutdown()
            srv.server_close()

    def test_tolak_host_non_loopback(self):
        # tanpa auth -> hanya loopback. Host publik harus ditolak SEBELUM bind/buka browser.
        kode = pantau.layani_pantau(self.app, host="0.0.0.0", port=8790, buka=False)
        self.assertEqual(kode, 2)


if __name__ == "__main__":
    unittest.main()
