# SPDX-License-Identifier: Apache-2.0
"""Rapikan nama memori (heuristik) — judul bersih dari ringkas/isi verbatim, non-destruktif."""
from __future__ import annotations

import os
import shutil
import tempfile
import types
import unittest

from ingat import judul_memori as J
from ingat.simpan import Store
from ingat.vektor import PenyematLokal


def _ep(ringkas="", sumber="mcp", waktu="2026-09-15T10:00:00+00:00"):
    return types.SimpleNamespace(ringkas=ringkas, sumber=sumber, waktu=waktu, isi_ref="", id="ep-x")


class Heuristik(unittest.TestCase):
    def test_gemini_verbatim_jadi_pesan_asli(self):
        isi = ("[percakapan gemini.google.com/spark] 1 pesan (percakapan berganti)\n\n"
               "17:23:17 user: Where should we start?\nCompare Indonesian dividend stocks")
        j = J.judul_heuristik(_ep("Percakapan gemini.google.com: 1 pesan", "browser:gemini.google.com"), isi)
        self.assertEqual(j, "Where should we start?")

    def test_bash_gagal_jadi_program(self):
        self.assertEqual(J.judul_heuristik(_ep("Bash gagal: wc -l /a/b/c.html", "claude-code")),
                         "Perintah gagal: wc")

    def test_bash_gagal_lewati_envvar_dan_wrapper(self):
        self.assertEqual(J.judul_heuristik(_ep("Bash gagal: MSYS_NO_PATHCONV=1 timeout 25 curl -s x", "claude-code")),
                         "Perintah gagal: curl")

    def test_nama_tool_mcp(self):
        self.assertEqual(J.judul_heuristik(_ep("mcp__abc__VPS_setRootPasswordV1 gagal: ...", "claude-code")),
                         "Alat VPS_setRootPasswordV1 gagal")

    def test_sesi_claude_code(self):
        self.assertEqual(J.judul_heuristik(_ep("Sesi Claude Code: 76 langkah (Bash, Edit)", "claude-code")),
                         "Sesi Claude Code · 76 langkah")

    def test_ringkas_bermakna_dipakai_apa_adanya(self):
        j = J.judul_heuristik(_ep("Gerbang deploy menolak kandidat yang sehat sebagian", "mcp"))
        self.assertEqual(j, "Gerbang deploy menolak kandidat yang sehat sebagian")

    def test_prefiks_histori_dibuang(self):
        j = J.judul_heuristik(_ep("Chat Claude Code (histori): Analisa folder terlampir", "claude-code-histori"))
        self.assertEqual(j, "Analisa folder terlampir")

    def test_generik_tanpa_isi_jatuh_ke_label_sumber(self):
        j = J.judul_heuristik(_ep("Percakapan gemini.google.com: 3 pesan", "browser:gemini.google.com"))
        self.assertEqual(j, "Gemini · 2026-09-15")

    def test_judul_panjang_dipotong(self):
        panjang = "Kata " * 30
        j = J.judul_heuristik(_ep(panjang.strip(), "mcp"))
        self.assertTrue(j.endswith("…"))
        self.assertLessEqual(len(j), 65)

    def test_huruf_pertama_dikapitalkan(self):
        self.assertTrue(J.judul_heuristik(_ep("apa itu ingat menurutmu", "mcp"))[0].isupper())


class SidecarStore(unittest.TestCase):
    """rapikan menulis ke tabel sidecar; episode asli (ringkas/sumber) TAK berubah; kosongkan = undo."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ingat-judul-")
        self.store = Store(os.path.join(self.dir, "s"), PenyematLokal())

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _tambah(self, isi, sumber, ringkas):
        return self.store.tambah_episode(isi, sumber=sumber, tier="I", lingkup="peran:asisten-ai",
                                         jenis_kejadian="sukses", ringkas=ringkas, instrumen=["x"], sesi="s1")

    def test_rapikan_tulis_lalu_undo(self):
        e1 = self._tambah("17:00:00 user: Bagaimana setup Caddy?", "browser:gemini.google.com",
                          "Percakapan gemini.google.com: 1 pesan")
        e2 = self._tambah("apa saja", "mcp", "Gerbang deploy menolak kandidat sehat sebagian")
        hasil = J.rapikan(self.store)
        self.assertEqual(hasil["diproses"], 2)
        self.assertEqual(hasil["ditulis"], 2)
        # judul tersimpan & terbaca
        self.assertEqual(J.judul_untuk(self.store, e1.id), "Bagaimana setup Caddy?")
        self.assertEqual(J.judul_untuk(self.store, e2.id), "Gerbang deploy menolak kandidat sehat sebagian")
        self.assertEqual(J.berapa_berjudul(self.store), 2)
        # NON-DESTRUKTIF: episode asli tak berubah
        self.assertEqual(self.store.episode(e1.id).ringkas, "Percakapan gemini.google.com: 1 pesan")
        self.assertEqual(self.store.episode(e2.id).sumber, "mcp")
        # undo
        self.assertEqual(J.kosongkan(self.store), 2)
        self.assertIsNone(J.judul_untuk(self.store, e1.id))

    def test_dry_run_tak_menulis(self):
        self._tambah("halo", "mcp", "Sesuatu yang bermakna panjangnya")
        J.rapikan(self.store, tulis=False)
        self.assertEqual(J.berapa_berjudul(self.store), 0)

    def test_set_dan_hapus_judul_satuan(self):
        e = self._tambah("x", "mcp", "ringkas")
        J.set_judul(self.store, e.id, "  Judul Manual  ")
        self.assertEqual(J.judul_untuk(self.store, e.id), "Judul Manual")
        self.assertEqual(J.semua_judul(self.store), {e.id: "Judul Manual"})
        J.hapus_judul(self.store, e.id)
        self.assertIsNone(J.judul_untuk(self.store, e.id))

    def test_hapus_episode_lenyapkan_baris_vektor_judul(self):
        e = self._tambah("isi verbatim", "mcp", "ringkas")
        J.set_judul(self.store, e.id, "judul")
        self.assertEqual(self.store.db.execute(
            "SELECT COUNT(*) FROM vektor WHERE item_id=?", (e.id,)).fetchone()[0], 1)
        self.assertTrue(self.store.hapus_episode(e.id))
        J.hapus_judul(self.store, e.id)
        self.assertIsNone(self.store.episode(e.id))
        self.assertEqual(self.store.db.execute(
            "SELECT COUNT(*) FROM vektor WHERE item_id=?", (e.id,)).fetchone()[0], 0)
        self.assertIsNone(J.judul_untuk(self.store, e.id))
        self.assertFalse(self.store.hapus_episode("ep-tak-ada"))


class JendelaJudul(unittest.TestCase):
    """Smoke test: jendela 'Rapikan nama memori' terbangun (Tk asli) di atas store nyata."""

    def setUp(self):
        try:
            from .uji_panel_gui import KasusTk  # noqa: F401
        except Exception as e:
            self.skipTest("harness Tk tidak tersedia: " + str(e))
        self.dir = tempfile.mkdtemp(prefix="ingat-juwin-")
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.store = Store(os.path.join(self.dir, "s"), PenyematLokal())
        self.store.tambah_episode("halo dunia", sumber="mcp", tier="I", lingkup="peran:asisten-ai",
                                  jenis_kejadian="sukses", ringkas="Sesuatu yang bermakna cukup panjang", instrumen=["x"], sesi="s1")

    def test_terbangun_tanpa_galat(self):
        from .uji_panel_gui import KasusTk
        from ingat import panel

        class _K(KasusTk):
            def runTest(self):  # pragma: no cover
                pass
        k = _K(); k.setUp()
        try:
            class AppStub:
                pass
            a = AppStub(); a.store = self.store
            ref = {}

            def bangun():
                win = k._catat(panel.bangun_jendela_judul(k.root, a, lambda *_: None))
                win.withdraw(); ref["win"] = win
            self.assertTrue(k._putar(bangun, lambda: "win" in ref))
            self.assertTrue(ref["win"].winfo_exists())
        finally:
            k.tearDown()


class JendelaMemori(unittest.TestCase):
    """Smoke test: jendela 'Kelola memori' terbangun (Tk asli) di atas store nyata."""

    def setUp(self):
        try:
            from .uji_panel_gui import KasusTk  # noqa: F401
        except Exception as e:
            self.skipTest("harness Tk tidak tersedia: " + str(e))
        self.dir = tempfile.mkdtemp(prefix="ingat-memwin-")
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.store = Store(os.path.join(self.dir, "s"), PenyematLokal())
        self.store.tambah_episode("isi", sumber="mcp", tier="I", lingkup="peran:asisten-ai",
                                  jenis_kejadian="sukses", ringkas="Sebuah memori uji", instrumen=["x"], sesi="s1")

    def test_terbangun_tanpa_galat(self):
        from .uji_panel_gui import KasusTk
        from ingat import panel

        class _K(KasusTk):
            def runTest(self):  # pragma: no cover
                pass
        k = _K(); k.setUp()
        try:
            class AppStub:
                pass
            a = AppStub(); a.store = self.store
            ref = {}

            def bangun():
                win = k._catat(panel.bangun_jendela_memori(k.root, a, lambda *_: None))
                win.withdraw(); ref["win"] = win
            self.assertTrue(k._putar(bangun, lambda: "win" in ref))
            self.assertTrue(ref["win"].winfo_exists())
        finally:
            k.tearDown()


class JendelaRecall(unittest.TestCase):
    """Smoke test: jendela 'Pratinjau recall' terbangun; memanggil gateway.muat_startup (di-stub)."""

    def setUp(self):
        try:
            from .uji_panel_gui import KasusTk  # noqa: F401
        except Exception as e:
            self.skipTest("harness Tk tidak tersedia: " + str(e))

    def test_terbangun_tanpa_galat(self):
        from .uji_panel_gui import KasusTk
        from ingat import panel

        class _K(KasusTk):
            def runTest(self):  # pragma: no cover
                pass
        k = _K(); k.setUp()
        try:
            class GatewayStub:
                def muat_startup(self, lingkup="global", sesi="", **_):
                    return {"peta": [f"# peta · {lingkup}"], "aturan": ["pelajaran: contoh"],
                            "pointer": [], "token": {"peta": 4, "aturan": 3, "total": 7}}

            class AppStub:
                pass
            a = AppStub(); a.gateway = GatewayStub()
            ref = {}

            def bangun():
                win = k._catat(panel.bangun_jendela_recall(k.root, a, lambda *_: None))
                win.withdraw(); ref["win"] = win
            self.assertTrue(k._putar(bangun, lambda: "win" in ref))
            self.assertTrue(ref["win"].winfo_exists())
        finally:
            k.tearDown()


if __name__ == "__main__":
    unittest.main()
