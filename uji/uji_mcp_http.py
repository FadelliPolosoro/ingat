# SPDX-License-Identifier: Apache-2.0
"""MCP Streamable HTTP (K19): alur persis yang dilakukan claude.ai Custom Connector — initialize → notifications/initialized
→ tools/list → tools/call — lewat server nyata di port bebas, dengan token di path (URL rahasia) dan Bearer."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import unittest
import io
import contextlib
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from ingat import api as modul_api
from ingat.api import buat_handler
from ingat.aplikasi import Aplikasi, KONFIG_DEFAULT
from ingat.mcp_http import ambil_token_dari_path, tangani_http
from ingat.mcp_stdio import tangani_pesan


class Murni(unittest.TestCase):
    def test_token_dari_path(self):
        self.assertIsNone(ambil_token_dari_path("/mcp"))
        self.assertIsNone(ambil_token_dari_path("/mcp/"))
        self.assertEqual(ambil_token_dari_path("/mcp/abc123"), "abc123")
        self.assertEqual(ambil_token_dari_path("/mcp/abc123/"), "abc123")

    def test_tangani_pesan_dipakai_dua_transport(self):
        """Refactor: stdio dan HTTP memakai fungsi yang sama — tidak ada dua implementasi protokol."""
        r = tangani_pesan(None, {"jsonrpc": "2.0", "id": 1, "method": "ping"})
        self.assertEqual(r["result"], {})
        self.assertIsNone(tangani_pesan(None, {"jsonrpc": "2.0", "method": "notifications/initialized"}))
        r = tangani_pesan(None, {"jsonrpc": "2.0", "id": 2, "method": "apa-ini"})
        self.assertEqual(r["error"]["code"], -32601)


class ServerMcp(unittest.TestCase):
    def setUp(self):
        modul_api._LAJU.clear()
        self.dir = tempfile.mkdtemp(prefix="ingat-mcp-")
        k = json.loads(json.dumps(KONFIG_DEFAULT))
        k["dir_data"] = os.path.join(self.dir, "data")
        k["vault"] = os.path.join(self.dir, "vault")
        self.app = Aplikasi(k)
        self.token = "token-mcp-uji-yang-panjangnya-cukup-24"
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), buat_handler(self.app, self.token, {"laju_per_menit": 500}))
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.dasar = f"http://127.0.0.1:{self.port}"

    def tearDown(self):
        self.server.shutdown(); self.server.server_close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def _req(self, metode, path, badan=None, bearer=None, sesi=None):
        req = urllib.request.Request(self.dasar + path, data=(json.dumps(badan).encode() if badan is not None else None), method=metode)
        if badan is not None:
            req.add_header("Content-Type", "application/json")
        if bearer:
            req.add_header("Authorization", f"Bearer {bearer}")
        if sesi:
            req.add_header("Mcp-Session-Id", sesi)
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                raw = r.read()
                return r.status, dict(r.headers), (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as e:
            raw = e.read()
            return e.code, dict(e.headers), (json.loads(raw) if raw else None)

    def _rpc(self, id_, method, params=None):
        d = {"jsonrpc": "2.0", "method": method}
        if id_ is not None:
            d["id"] = id_
        if params is not None:
            d["params"] = params
        return d

    def test_alur_custom_connector_dengan_url_rahasia(self):
        p = f"/mcp/{self.token}"
        # initialize → 200 + Mcp-Session-Id + protokol
        st, h, b = self._req("POST", p, self._rpc(1, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "claude.ai"}}))
        self.assertEqual(st, 200, b)
        self.assertEqual(b["result"]["serverInfo"]["name"], "ingat")
        self.assertEqual(h.get("MCP-Protocol-Version"), "2025-06-18")
        sesi = h.get("Mcp-Session-Id"); self.assertTrue(sesi)
        # notifikasi → 202 tanpa badan
        st, _, b = self._req("POST", p, self._rpc(None, "notifications/initialized"), sesi=sesi)
        self.assertEqual(st, 202); self.assertIsNone(b)
        # tools/list → 4 pintu, tanpa tool hapus
        st, _, b = self._req("POST", p, self._rpc(2, "tools/list"), sesi=sesi)
        nama = {t["name"] for t in b["result"]["tools"]}
        self.assertEqual(nama, {"ingat", "muat_startup", "buka_bukti", "catat_episode"})
        # tools/call catat_episode → episode tersimpan lewat Store (redaksi berlaku)
        st, _, b = self._req("POST", p, self._rpc(3, "tools/call", {"name": "catat_episode", "arguments": {
            "isi": "dari claude.ai: kunci sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789", "lingkup": "global",
            "jenis_kejadian": "koreksi", "ringkas": "koreksi dari chat claude.ai", "sumber": "claude.ai"}}), sesi=sesi)
        self.assertEqual(st, 200, b)
        self.assertFalse(b["result"]["isError"], b)
        hasil = json.loads(b["result"]["content"][0]["text"])
        self.assertEqual(hasil["bobot"], 5)
        isi = self.app.store.buka_dingin(self.app.store.episode(hasil["id"]).isi_ref)["isi"]
        self.assertNotIn("sk-ant-api03", isi)
        # tools/call ingat → item/pointer
        st, _, b = self._req("POST", p, self._rpc(4, "tools/call", {"name": "ingat", "arguments": {"query": "koreksi chat", "lingkup": "global"}}), sesi=sesi)
        self.assertEqual(st, 200)
        self.assertIn("item", json.loads(b["result"]["content"][0]["text"]))

    def test_bearer_juga_diterima_di_path_polos(self):
        st, _, b = self._req("POST", "/mcp", self._rpc(1, "ping"), bearer=self.token)
        self.assertEqual(st, 200, b)

    def test_tanpa_token_401_tanpa_arahan_oauth(self):
        st, h, _ = self._req("POST", "/mcp", self._rpc(1, "ping"))
        self.assertEqual(st, 401)
        self.assertNotIn("WWW-Authenticate", h, "server tidak menawarkan OAuth; jangan mengarahkan klien ke discovery yang tidak ada")
        st, _, _ = self._req("POST", "/mcp/token-salah-tapi-panjang-24-karakter", self._rpc(1, "ping"))
        self.assertEqual(st, 401)

    def test_metode_lain_sesuai_spek(self):
        p = f"/mcp/{self.token}"
        st, h, _ = self._req("GET", p)
        self.assertEqual(st, 405); self.assertIn("POST", h.get("Allow", ""))
        st, _, _ = self._req("HEAD", p)
        self.assertEqual(st, 200)
        st, _, _ = self._req("DELETE", p)
        self.assertEqual(st, 200)

    def test_token_di_path_tidak_bocor_ke_log_server(self):
        """Bug yang sempat lolos: log_message mencetak path mentah; token di URL harus diredaksi (K10)."""
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            st, _, _ = self._req("POST", f"/mcp/{self.token}", self._rpc(1, "ping"))
        self.assertEqual(st, 200)
        self.assertNotIn(self.token, out.getvalue(), "token bocor ke stdout/log server")
        self.assertIn("[REDAKSI]", out.getvalue())

    def test_batch_dan_parse_error(self):
        p = f"/mcp/{self.token}"
        st, _, b = self._req("POST", p, [self._rpc(1, "ping"), self._rpc(2, "tools/list")])
        self.assertEqual(st, 200); self.assertEqual(len(b), 2)
        req = urllib.request.Request(self.dasar + p, data=b"{bukan json", method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            urllib.request.urlopen(req, timeout=5)
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)


if __name__ == "__main__":
    unittest.main()
