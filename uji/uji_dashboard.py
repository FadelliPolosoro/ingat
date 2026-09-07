# SPDX-License-Identifier: Apache-2.0
"""K23: dashboard visual (Papan Bukti). bangun_graf() = logika edge terstruktur (bukan wikilink generik):
bukti-bersama, mengganti, instrumen. Plus endpoint server nyata /dashboard dan /dashboard/data."""
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

from ingat import skema
from ingat import api as modul_api
from ingat.api import buat_handler
from ingat.aplikasi import Aplikasi, KONFIG_DEFAULT
from ingat.dashboard import bangun_graf

FP = "proyek:fp-dashboard"


class BangunGraf(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ingat-dash-")
        k = json.loads(json.dumps(KONFIG_DEFAULT))
        k["dir_data"] = os.path.join(self.dir, "data"); k["vault"] = os.path.join(self.dir, "vault")
        self.app = Aplikasi(k)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _pelajaran(self, id_, bukti=(), **kw):
        p = skema.Pelajaran(id=id_, pelajaran=f"P {id_}", pemicu="x", tindakan="y", lingkup=FP,
                            status="aturan", keyakinan=0.8, bukti=list(bukti), ditinjau_manusia=True, **kw)
        self.app.store.simpan_pelajaran(p)
        return p

    def test_dua_pelajaran_berbagi_bukti_menghasilkan_edge_bukti_bersama(self):
        self._pelajaran("pl-a", bukti=["ep-1", "ep-2"])
        self._pelajaran("pl-b", bukti=["ep-2", "ep-3"])
        self._pelajaran("pl-c", bukti=["ep-9"])  # tidak berbagi apa pun
        g = bangun_graf(self.app)
        pasangan = {frozenset((e["a"], e["b"])) for e in g["edges"] if e["jenis"] == "bukti-bersama"}
        self.assertIn(frozenset(("pl-a", "pl-b")), pasangan)
        self.assertNotIn(frozenset(("pl-a", "pl-c")), pasangan)
        self.assertNotIn(frozenset(("pl-b", "pl-c")), pasangan)

    def test_norma_mengganti_menghasilkan_edge_terarah(self):
        lama = skema.Norma(id="nr-lama", norma="Perpres 16/2018", jenis="perpres", status="dicabut", berlaku_sejak="2018-01-01")
        baru = skema.Norma(id="nr-baru", norma="Perpres 46/2025", jenis="perpres", status="berlaku", berlaku_sejak="2025-01-01", mengganti=["nr-lama"])
        self.app.store.simpan_norma(lama)
        self.app.store.simpan_norma(baru)
        g = bangun_graf(self.app)
        self.assertIn({"a": "nr-baru", "b": "nr-lama", "jenis": "mengganti"}, g["edges"])

    def test_instrumen_ke_pelajaran_yang_lahir_darinya(self):
        self.app.store.simpan_instrumen(skema.Instrumen(id="hostinger-mcp", nama="Hostinger MCP"))
        self._pelajaran("pl-x", instrumen_saat_dibuat=["hostinger-mcp"])
        g = bangun_graf(self.app)
        self.assertIn({"a": "hostinger-mcp", "b": "pl-x", "jenis": "instrumen"}, g["edges"])

    def test_lingkup_menyaring_node_tapi_global_selalu_ikut(self):
        self._pelajaran("pl-fp")
        p_global = skema.Pelajaran(id="pl-g", pelajaran="G", pemicu="x", tindakan="y", lingkup="global", status="aturan", keyakinan=0.8)
        self.app.store.simpan_pelajaran(p_global)
        self._pelajaran2 = skema.Pelajaran(id="pl-garnivo", pelajaran="Grn", pemicu="x", tindakan="y", lingkup="proyek:garnivo", status="aturan", keyakinan=0.8)
        self.app.store.simpan_pelajaran(self._pelajaran2)
        g = bangun_graf(self.app, lingkup=FP)
        id_ = {n["id"] for n in g["nodes"]}
        self.assertIn("pl-fp", id_); self.assertIn("pl-g", id_); self.assertNotIn("pl-garnivo", id_)

    def test_hasil_selalu_json_serializable(self):
        self._pelajaran("pl-a")
        json.dumps(bangun_graf(self.app))  # tidak boleh melempar (mis. datetime.date lolos)

    def test_instrumen_tanpa_target_tidak_menghasilkan_edge_yatim(self):
        self._pelajaran("pl-x", instrumen_saat_dibuat=["tidak-ada-instrumen-ini"])
        g = bangun_graf(self.app)
        self.assertEqual([e for e in g["edges"] if e["jenis"] == "instrumen"], [])


class EndpointServer(unittest.TestCase):
    def setUp(self):
        modul_api._LAJU.clear()
        self.dir = tempfile.mkdtemp(prefix="ingat-dashapi-")
        k = json.loads(json.dumps(KONFIG_DEFAULT))
        k["dir_data"] = os.path.join(self.dir, "data"); k["vault"] = os.path.join(self.dir, "vault")
        self.app = Aplikasi(k)
        self.token = "token-dashboard-uji-24-karakter-plus"
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), buat_handler(self.app, self.token, {"laju_per_menit": 500}))
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.dasar = f"http://127.0.0.1:{self.port}"

    def tearDown(self):
        self.server.shutdown(); self.server.server_close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def _get(self, path):
        req = urllib.request.Request(self.dasar + path, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, r.read(), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read(), dict(e.headers)

    def _post(self, path, badan, token=None):
        req = urllib.request.Request(self.dasar + path, data=json.dumps(badan).encode(), method="POST")
        req.add_header("Content-Type", "application/json")
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_halaman_dashboard_publik_tanpa_token(self):
        status, isi, header = self._get("/dashboard")
        self.assertEqual(status, 200)
        self.assertIn("text/html", header.get("Content-Type", ""))
        self.assertIn(b"Papan Bukti", isi)
        self.assertIn(b"INGAT_TOKEN".lower(), isi.lower())  # gerbang menyebut token, bukan data sungguhan

    def test_data_dashboard_wajib_token(self):
        status, _ = self._post("/dashboard/data", {})
        self.assertEqual(status, 401)

    def test_data_dashboard_dengan_token_mengembalikan_struktur_benar(self):
        p = skema.Pelajaran(id="pl-1", pelajaran="X", pemicu="y", tindakan="z", lingkup="global", status="aturan", keyakinan=0.7)
        self.app.store.simpan_pelajaran(p)
        status, hasil = self._post("/dashboard/data", {}, token=self.token)
        self.assertEqual(status, 200, hasil)
        self.assertIn("nodes", hasil); self.assertIn("edges", hasil)
        self.assertTrue(any(n["id"] == "pl-1" for n in hasil["nodes"]))


if __name__ == "__main__":
    unittest.main()
