# SPDX-License-Identifier: Apache-2.0
"""Fase 5 — penyambungan tiga modul (startup, sambung, cari_memori) ke panel.

Hanya helper bebas-Tkinter: teks peringatan, warna lampu, baris hasil, pesan galat.
Jendela sungguhannya diuji di uji/uji_panel_gui.py (butuh layar, jadi terpisah).
"""
from __future__ import annotations

import unittest
from unittest import mock

from ingat import panel


class HelperStartup(unittest.TestCase):
    def test_tanpa_entri_lawas_tak_ada_peringatan(self):
        self.assertIsNone(panel.pesan_lawas_startup({"aktif": True, "lawas": [], "folder": "C:/x"}))
        self.assertIsNone(panel.pesan_lawas_startup({}))

    def test_peringatan_menyebut_berkas_dan_folder(self):
        st = {"aktif": True, "lawas": [r"C:\Startup\ingat-autostart.vbs"], "folder": r"C:\Startup"}
        pesan = panel.pesan_lawas_startup(st)
        self.assertIn("ingat-autostart.vbs", pesan)
        self.assertIn(r"C:\Startup", pesan)
        # dibaca orang yang tidak paham IT: tak boleh ada istilah port/bind/proses
        for istilah in ("port", "bind", "traceback", "exception"):
            self.assertNotIn(istilah, pesan.lower())

    def test_peringatan_tanpa_kunci_folder_tak_melempar(self):
        st = {"lawas": [r"C:\Startup\ingat-autostart.cmd"]}
        self.assertIn(r"C:\Startup", panel.pesan_lawas_startup(st))

    def test_pesan_alih_startup(self):
        hidup = panel.pesan_alih_startup(True, {"aktif": True, "folder": r"C:\Startup"})
        self.assertIn("DIHIDUPKAN", hidup)
        self.assertIn(r"C:\Startup", hidup)
        mati = panel.pesan_alih_startup(False, {"aktif": False, "dihapus": [r"C:\Startup\a.lnk"]})
        self.assertIn("DIMATIKAN", mati)
        self.assertIn("1", mati)
        self.assertIn("DIMATIKAN", panel.pesan_alih_startup(False, {}))

    def test_status_startup_aman_menelan_galat(self):
        with mock.patch("ingat.startup.status_startup", side_effect=OSError("disk")):
            st = panel.status_startup_aman()
        self.assertFalse(st["aktif"])
        self.assertEqual(st["lawas"], [])
        self.assertIsNone(st.get("folder"))  # panel selalu memakai .get, bukan []

    def test_status_startup_aman_meneruskan_hasil_asli(self):
        with mock.patch("ingat.startup.status_startup", return_value={"aktif": True, "lawas": ["x"]}):
            self.assertTrue(panel.status_startup_aman()["aktif"])


class HelperSambung(unittest.TestCase):
    def test_warna_lampu(self):
        self.assertEqual(panel.warna_lampu("hijau"), "#15803d")
        self.assertEqual(panel.warna_lampu("kuning"), "#b45309")
        self.assertEqual(panel.warna_lampu("merah"), "#b91c1c")
        self.assertEqual(panel.warna_lampu(None), "#6b7280")
        self.assertEqual(panel.warna_lampu("ungu"), "#6b7280")

    def test_baris_butir(self):
        ok = panel.baris_butir_sambung({"nama": "Claude Desktop", "ok": True, "pesan": "Terpasang."})
        self.assertTrue(ok.startswith("✓ Claude Desktop"))
        self.assertIn("Terpasang.", ok)
        self.assertTrue(panel.baris_butir_sambung({"nama": "Server ingat", "ok": False, "pesan": "mati"})
                        .startswith("✗ "))
        self.assertIsInstance(panel.baris_butir_sambung({}), str)


class HelperCari(unittest.TestCase):
    def test_baris_hasil_tanpa_angka_skor(self):
        baris = panel.baris_hasil_cari({"jenis": "episode", "ringkas": "rapat tender",
                                        "tanggal": "2026-09-18", "skor": 0.6123})
        self.assertIn("[episode]", baris)
        self.assertIn("rapat tender", baris)
        self.assertIn("2026-09-18", baris)
        self.assertNotIn("0.61", baris)

    def test_baris_hasil_skor_none_tak_jadi_nol(self):
        baris = panel.baris_hasil_cari({"jenis": "pelajaran", "ringkas": "x", "skor": None})
        self.assertNotIn("0", baris)

    def test_baris_hasil_jatuh_ke_kutipan(self):
        self.assertIn("isi panjang", panel.baris_hasil_cari({"jenis": "norma", "kutipan": "isi panjang"}))

    def test_pesan_sumber(self):
        self.assertIn("riwayat", panel.pesan_sumber_cari("riwayat"))
        self.assertEqual(panel.pesan_sumber_cari("gerbang"), "")
        self.assertEqual(panel.pesan_sumber_cari(None), "")

    def test_teks_bukti(self):
        t = panel.teks_bukti({"waktu": "2026-09-18T10:30:00", "ringkas": "rapat", "isi": "isi verbatim"})
        self.assertIn("2026-09-18 10:30", t)
        self.assertIn("rapat", t)
        self.assertTrue(t.rstrip().endswith("isi verbatim"))
        self.assertEqual(panel.teks_bukti({}), "")

    def test_pesan_galat_bukti_bebas_istilah_python(self):
        for e in (PermissionError("tier S"), KeyError("episode x"), RuntimeError("boom")):
            pesan = panel.pesan_galat_bukti(e)
            for istilah in ("error", "exception", "traceback", "none", "tier"):
                self.assertNotIn(istilah, pesan.lower(), pesan)
        self.assertIn("rahasia", panel.pesan_galat_bukti(PermissionError()).lower())


if __name__ == "__main__":
    unittest.main()
