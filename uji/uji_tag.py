# SPDX-License-Identifier: Apache-2.0
"""Tag otomatis per episode — heuristik deterministik + CRUD tabel sidecar."""
from __future__ import annotations

import os
import shutil
import tempfile
import types
import unittest

from ingat import tag as T
from ingat.simpan import Store
from ingat.vektor import PenyematLokal


def _ep(ringkas="", sumber="mcp", jenis="sukses", tier="I", waktu="2026-09-19T10:00:00+00:00"):
    return types.SimpleNamespace(
        ringkas=ringkas, sumber=sumber, jenis_kejadian=jenis,
        tier=tier, waktu=waktu, isi_ref="", id="ep-x",
    )


class Heuristik(unittest.TestCase):
    def test_tag_heuristik_platform(self):
        tags = T.tag_heuristik(_ep(sumber="mcp"))
        self.assertIn("claude-desktop", tags)

    def test_tag_heuristik_jenis(self):
        tags = T.tag_heuristik(_ep(jenis="gagal"))
        self.assertIn("debug", tags)

    def test_tag_heuristik_kata_kunci(self):
        tags = T.tag_heuristik(_ep(ringkas="deploy server berhasil"))
        self.assertIn("deploy", tags)
        self.assertIn("server", tags)

    def test_tag_heuristik_maks_4(self):
        tags = T.tag_heuristik(_ep(
            sumber="mcp", jenis="gagal", tier="S",
            ringkas="deploy server api database config test ui",
        ))
        self.assertLessEqual(len(tags), 4)

    def test_tag_heuristik_browser_tak_dikenal(self):
        tags = T.tag_heuristik(_ep(sumber="browser:random.com"))
        self.assertIn("web", tags)

    def test_tag_heuristik_keputusan(self):
        tags = T.tag_heuristik(_ep(jenis="keputusan"))
        self.assertIn("keputusan", tags)

    def test_tag_heuristik_tier_s(self):
        tags = T.tag_heuristik(_ep(tier="S"))
        self.assertIn("rahasia", tags)

    def test_tag_heuristik_judul_diperhitungkan(self):
        tags = T.tag_heuristik(_ep(ringkas="sesuatu"), judul="setup enkripsi baru")
        self.assertIn("konfigurasi", tags)
        self.assertIn("keamanan", tags)


class SidecarStore(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ingat-tag-")
        self.store = Store(os.path.join(self.dir, "s"), PenyematLokal())

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _tambah(self, ringkas, sumber="mcp", jenis="sukses"):
        return self.store.tambah_episode(
            "isi", sumber=sumber, tier="I", lingkup="peran:asisten-ai",
            jenis_kejadian=jenis, ringkas=ringkas, instrumen=["x"], sesi="s1",
        )

    def test_tandai_menulis_ke_db(self):
        e = self._tambah("deploy server baru")
        hasil = T.tandai(self.store)
        self.assertGreaterEqual(hasil["ditulis"], 1)
        tags = T.tag_untuk(self.store, e.id)
        self.assertTrue(len(tags) > 0)

    def test_tandai_skip_yang_sudah(self):
        e = self._tambah("deploy baru")
        T.tandai(self.store)
        n1 = T.tandai(self.store)["ditulis"]
        self.assertEqual(n1, 0)

    def test_set_tag_manual(self):
        e = self._tambah("sesuatu")
        T.tandai(self.store)
        T.set_tag(self.store, e.id, ["manual-a", "manual-b"])
        tags = T.tag_untuk(self.store, e.id)
        self.assertEqual(tags, ["manual-a", "manual-b"])

    def test_hapus_tag(self):
        e = self._tambah("deploy")
        T.tandai(self.store)
        T.hapus_tag(self.store, e.id)
        self.assertEqual(T.tag_untuk(self.store, e.id), [])

    def test_daftar_tag_unik(self):
        self._tambah("deploy server", sumber="mcp")
        self._tambah("deploy api", sumber="panel")
        T.tandai(self.store)
        daftar = T.daftar_tag_unik(self.store)
        tags = [d["tag"] for d in daftar]
        self.assertIn("deploy", tags)
        for d in daftar:
            if d["tag"] == "deploy":
                self.assertEqual(d["jumlah"], 2)

    def test_episode_dengan_tag(self):
        e1 = self._tambah("deploy baru")
        e2 = self._tambah("sesuatu lain")
        T.tandai(self.store)
        ids = T.episode_dengan_tag(self.store, "deploy")
        self.assertIn(e1.id, ids)
        self.assertNotIn(e2.id, ids)

    def test_semua_tag(self):
        e = self._tambah("deploy server")
        T.tandai(self.store)
        m = T.semua_tag(self.store)
        self.assertIn(e.id, m)
        self.assertIsInstance(m[e.id], list)


if __name__ == "__main__":
    unittest.main()
