# SPDX-License-Identifier: Apache-2.0
"""Impor histori Claude Code (Jalur A): baca transkrip JSONL -> episode ep-histori-<sesi>.
Idempoten, tak menimpa hook (ep-sesi-<sesi>), relay menolak tulis."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest

from ingat.aplikasi import Aplikasi, muat_konfig
from ingat import impor_claude


def rec(**k):
    return json.dumps(k, ensure_ascii=False)


class UjiImporClaude(unittest.TestCase):
    def setUp(self):
        os.environ.pop("INGAT_LINGKUP", None)  # jangan sampai env menimpa derivasi per-proyek
        self.dir = tempfile.mkdtemp(prefix="ingat-imporcc-")
        k = muat_konfig(None)
        k["dir_data"] = self.dir + "/data"
        k["vault"] = self.dir + "/vault"
        self.app = Aplikasi(k)
        self.root = os.path.join(self.dir, "projects")
        tr = os.path.join(self.root, "C--proj-Memori")
        os.makedirs(tr)
        cwd = "/tmp/AI-Workspace/Memori"
        # sesX: percakapan nyata (thinking/tool_use/tool_result harus dilewati)
        with open(os.path.join(tr, "sesX.jsonl"), "w", encoding="utf-8") as f:
            f.write(rec(type="summary", note="meta") + "\n")
            f.write(rec(type="user", sessionId="sesX", cwd=cwd,
                        message={"role": "user", "content": "gimana cara pakai ingat"}) + "\n")
            f.write(rec(type="assistant", sessionId="sesX",
                        message={"role": "assistant", "content": [
                            {"type": "thinking", "thinking": "x"},
                            {"type": "text", "text": "jalankan ingat pasang"},
                            {"type": "tool_use", "name": "Bash", "input": {}}]}) + "\n")
            f.write(rec(type="user", sessionId="sesX",
                        message={"role": "user", "content": [{"type": "tool_result", "content": "ok"}]}) + "\n")
            f.write(rec(type="system", content="reminder") + "\n")
        # sesY: sudah ditangani hook (ep-sesi ada) -> harus dilewati
        with open(os.path.join(tr, "sesY.jsonl"), "w", encoding="utf-8") as f:
            f.write(rec(type="user", sessionId="sesY", cwd=cwd,
                        message={"role": "user", "content": "halo"}) + "\n")
        self.app.store.tambah_episode("sesi lama hook", id="ep-sesi-sesY", sumber="claude-code",
                                      tier="I", lingkup="global", jenis_kejadian="sukses", ringkas="hook")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_kering_menyusun_rencana_tanpa_menulis(self):
        h = impor_claude.impor_histori(self.app, root=self.root, tulis=False)
        self.assertEqual(h["ditemukan"], 2)
        self.assertEqual(h["akan_diimpor"], 1)          # sesX
        self.assertEqual(h["dilewati_sudah_ada"], 1)    # sesY (ep-sesi ada)
        r = h["rencana"][0]
        self.assertEqual(r["giliran"], 2)               # user + teks assistant; thinking/tool dilewati
        self.assertIn("gimana cara pakai ingat", r["ringkas"])
        self.assertTrue(r["lingkup"].startswith("proyek:"), r["lingkup"])
        self.assertIsNone(self.app.store.episode("ep-histori-sesX"))  # kering: belum menulis

    def test_tulis_lalu_idempoten(self):
        h1 = impor_claude.impor_histori(self.app, root=self.root, tulis=True)
        self.assertEqual(h1["diimpor"], 1)
        ep = self.app.store.episode("ep-histori-sesX")
        self.assertIsNotNone(ep)
        self.assertEqual(ep.sumber, "claude-code-histori")
        self.assertEqual(ep.jenis_kejadian, "sukses")
        # jalankan lagi: tidak menggandakan
        h2 = impor_claude.impor_histori(self.app, root=self.root, tulis=True)
        self.assertEqual(h2["diimpor"], 0)
        self.assertEqual(h2["dilewati_sudah_ada"], 2)   # sesX (histori) + sesY (hook)

    def test_relay_menolak_tulis(self):
        self.app.relay = True
        h = impor_claude.impor_histori(self.app, root=self.root, tulis=True)
        self.assertIn("galat", h)
        self.assertIsNone(self.app.store.episode("ep-histori-sesX"))


if __name__ == "__main__":
    unittest.main()
