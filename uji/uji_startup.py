# SPDX-License-Identifier: Apache-2.0
"""Uji nyala-otomatis Windows (folder Startup). Bebas layar dan bebas Tkinter.

Folder Startup asli TIDAK PERNAH disentuh: tiap uji menyuntikkan direktori sementara
lewat parameter `folder`."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from ingat import startup

EXE_BERSPASI = r"C:\Program Files\ingat\ingat-panel.exe"


class Dasar(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ingat-startup-")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def isi_folder(self):
        return sorted(os.listdir(self.dir))


class FolderTarget(Dasar):
    def test_folder_disuntikkan_menggantikan_asli(self):
        self.assertEqual(startup.folder_startup(self.dir), os.path.abspath(self.dir))

    def test_folder_asli_dari_appdata(self):
        with mock.patch.dict(os.environ, {"APPDATA": r"C:\Users\Uji\AppData\Roaming"}):
            jalur = startup.folder_startup()
        self.assertTrue(jalur.endswith(os.path.join("Programs", "Startup")))
        self.assertIn("Start Menu", jalur)

    def test_tanpa_appdata_menolak_menebak(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                startup.folder_startup()
            self.assertFalse(startup.status_startup()["aktif"])

    def test_target_saat_beku_adalah_exe_sendiri(self):
        with mock.patch.object(sys, "frozen", True, create=True), \
             mock.patch.object(sys, "executable", EXE_BERSPASI):
            t = startup.target_peluncuran()
        self.assertTrue(t["beku"])
        self.assertEqual(t["exe"], EXE_BERSPASI)
        self.assertEqual(t["argumen"], [])

    def test_target_saat_dari_source_adalah_skrip_panel(self):
        with mock.patch.object(sys, "frozen", False, create=True):
            t = startup.target_peluncuran()
        self.assertFalse(t["beku"])
        self.assertEqual(len(t["argumen"]), 1)
        self.assertTrue(t["argumen"][0].endswith(os.path.join("pasang", "exe", "ingat-panel.py")))
        self.assertTrue(os.path.isfile(t["argumen"][0]), "skrip peluncur panel tidak ada di repo")


class Cmd(Dasar):
    def aktif(self, **kw):
        return startup.aktifkan_startup(folder=self.dir, paksa_cmd=True, **kw)

    def test_aktifkan_membuat_entri_dan_status_ikut(self):
        self.assertFalse(startup.status_startup(self.dir)["aktif"])
        hasil = self.aktif(exe=EXE_BERSPASI)
        self.assertEqual(hasil["metode"], "cmd")
        s = startup.status_startup(self.dir)
        self.assertTrue(s["aktif"])
        self.assertEqual(s["berkas"], hasil["berkas"])

    def test_path_berspasi_dikutip(self):
        self.aktif(exe=EXE_BERSPASI)
        with open(os.path.join(self.dir, startup.NAMA_CMD), encoding="utf-8") as f:
            isi = f.read()
        self.assertIn('"' + EXE_BERSPASI + '"', isi)
        # judul kosong wajib, kalau tidak path berkutip dibaca `start` sebagai judul jendela
        self.assertIn('start "" "', isi)
        self.assertIn('cd /d "C:\\Program Files\\ingat"', isi)

    def test_argumen_berspasi_ikut_dikutip(self):
        skrip = r"C:\repo saya\pasang\exe\ingat-panel.py"
        self.aktif(exe=r"C:\Python\pythonw.exe", argumen=[skrip], kerja=r"C:\repo saya")
        with open(os.path.join(self.dir, startup.NAMA_CMD), encoding="utf-8") as f:
            isi = f.read()
        self.assertIn('"' + skrip + '"', isi)

    def test_aktifkan_dua_kali_tidak_menggandakan(self):
        self.aktif(exe=EXE_BERSPASI)
        self.aktif(exe=EXE_BERSPASI)
        self.assertEqual(self.isi_folder(), [startup.NAMA_CMD])

    def test_nonaktifkan_saat_sudah_mati_tidak_error(self):
        h = startup.nonaktifkan_startup(self.dir)
        self.assertEqual(h["dihapus"], [])
        self.assertFalse(startup.status_startup(self.dir)["aktif"])

    def test_nonaktifkan_menghapus_entri(self):
        self.aktif(exe=EXE_BERSPASI)
        h = startup.nonaktifkan_startup(self.dir)
        self.assertEqual(len(h["dihapus"]), 1)
        self.assertEqual(self.isi_folder(), [])

    def test_status_membaca_disk_bukan_prefs(self):
        self.aktif(exe=EXE_BERSPASI)
        os.remove(os.path.join(self.dir, startup.NAMA_CMD))  # seolah dihapus lewat File Explorer
        self.assertFalse(startup.status_startup(self.dir)["aktif"])

    def test_entri_metode_lain_ikut_dibersihkan(self):
        palsu = os.path.join(self.dir, startup.NAMA_LNK)
        with open(palsu, "wb") as f:
            f.write(b"lnk lama")
        self.aktif(exe=EXE_BERSPASI)
        self.assertEqual(self.isi_folder(), [startup.NAMA_CMD])

    def test_folder_dibuat_bila_belum_ada(self):
        dalam = os.path.join(self.dir, "belum", "ada")
        startup.aktifkan_startup(folder=dalam, exe=EXE_BERSPASI, paksa_cmd=True)
        self.assertTrue(startup.status_startup(dalam)["aktif"])

    def test_alih_startup_dua_arah(self):
        with mock.patch.object(startup, "_tulis_lnk", return_value=False):
            startup.alih_startup(True, folder=self.dir)
            self.assertTrue(startup.status_startup(self.dir)["aktif"])
        startup.alih_startup(False, folder=self.dir)
        self.assertFalse(startup.status_startup(self.dir)["aktif"])

    def test_entri_lawas_dilaporkan_tapi_tidak_dihapus(self):
        lawas = os.path.join(self.dir, "ingat-autostart.vbs")
        with open(lawas, "w", encoding="utf-8") as f:
            f.write("' auto-start server generasi lama\n")
        self.assertEqual(startup.entri_lawas(self.dir), [lawas])
        self.aktif(exe=EXE_BERSPASI)
        s = startup.status_startup(self.dir)
        self.assertEqual(s["lawas"], [lawas])
        self.assertTrue(os.path.isfile(lawas), "entri lawas milik pengguna tak boleh dihapus sendiri")
        startup.nonaktifkan_startup(self.dir)
        self.assertTrue(os.path.isfile(lawas))

    def test_tanpa_entri_lawas_daftar_kosong(self):
        self.assertEqual(startup.entri_lawas(self.dir), [])
        self.assertEqual(startup.status_startup(self.dir)["lawas"], [])

    def test_jatuh_ke_cmd_bila_powershell_gagal(self):
        with mock.patch.object(startup, "_tulis_lnk", return_value=False):
            hasil = startup.aktifkan_startup(folder=self.dir, exe=EXE_BERSPASI)
        self.assertEqual(hasil["metode"], "cmd")


class Baku(Dasar):
    """Apa yang dipakai saat panel memanggil aktifkan_startup() tanpa exe/argumen/kerja."""

    def exe_lain(self):
        """Program pihak lain di folder ber-&: menguji dua hal sekaligus (baku vs override,
        dan pengutipan)."""
        kerja = os.path.join(self.dir, "R&D")
        os.makedirs(kerja, exist_ok=True)
        exe = os.path.join(kerja, "app.exe")
        with open(exe, "wb") as f:
            f.write(b"MZ")
        return exe, kerja

    def isi_cmd(self):
        with open(os.path.join(self.dir, startup.NAMA_CMD), encoding="utf-8") as f:
            return f.read()

    def test_kerja_baku_dari_target_peluncuran_bukan_folder_exe(self):
        bawaan = startup.target_peluncuran()
        hasil = startup.aktifkan_startup(folder=self.dir, paksa_cmd=True)
        self.assertEqual(hasil["kerja"], bawaan["kerja"])
        self.assertNotEqual(hasil["kerja"], os.path.dirname(bawaan["exe"]))
        self.assertIn('cd /d "' + bawaan["kerja"] + '"', self.isi_cmd())

    def test_kerja_masih_ikut_exe_saat_exe_disebut(self):
        startup.aktifkan_startup(folder=self.dir, exe=EXE_BERSPASI, paksa_cmd=True)
        self.assertIn('cd /d "' + os.path.dirname(EXE_BERSPASI) + '"', self.isi_cmd())

    def test_argumen_baku_tidak_ikut_saat_exe_diganti(self):
        exe, kerja = self.exe_lain()
        hasil = startup.aktifkan_startup(folder=self.dir, exe=exe, kerja=kerja, paksa_cmd=True)
        self.assertEqual(hasil["argumen"], [])
        self.assertNotIn("ingat-panel.py", self.isi_cmd())

    def test_argumen_baku_tetap_ikut_saat_exe_baku(self):
        bawaan = startup.target_peluncuran()
        hasil = startup.aktifkan_startup(folder=self.dir, paksa_cmd=True)
        self.assertEqual(hasil["argumen"], bawaan["argumen"])


class Pengutipan(Dasar):
    def test_kutip_semua_karakter_berbahaya_cmd(self):
        for bagian in (r"C:\a\R&D", "C:\\a\\b^c", "C:\\a\\b(1)", "C:\\a\\%TEMP%", r"C:\a\b"):
            self.assertEqual(startup._kutip(bagian), '"' + bagian + '"', bagian)

    def test_kutip_tidak_menggandakan_yang_sudah_berkutip(self):
        self.assertEqual(startup._kutip('"C:\\a b"'), '"C:\\a b"')

    @unittest.skipUnless(os.name == "nt", "sintaks cmd hanya berlaku di Windows")
    def test_baris_cd_ber_ampersand_jalan_di_cmd_sungguhan(self):
        kerja = os.path.join(self.dir, "R&D")
        os.makedirs(kerja, exist_ok=True)
        startup.aktifkan_startup(folder=self.dir, exe=os.path.join(kerja, "app.exe"),
                                 kerja=kerja, paksa_cmd=True)
        with open(os.path.join(self.dir, startup.NAMA_CMD), encoding="utf-8") as f:
            isi = f.read()
        baris_cd = next(b for b in isi.splitlines() if b.lower().startswith("cd /d"))
        # shell=True, bukan daftar argumen: list2cmdline meng-escape kutip dengan backslash
        # (`\"`) yang tak dimengerti cmd, jadi baris yang diuji tak lagi sama dengan aslinya.
        hasil = subprocess.run(baris_cd + " && cd", shell=True, capture_output=True, text=True)
        self.assertEqual(hasil.returncode, 0, hasil.stdout + hasil.stderr)
        self.assertEqual(hasil.stdout.strip().lower(), kerja.lower())


class TanpaAppdata(Dasar):
    """APPDATA dilucuti: panel tetap menggambar centang, jadi tak boleh ada traceback
    maupun bentuk kembalian yang berubah-ubah."""

    def test_status_tetap_punya_kunci_folder(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            galat = startup.status_startup()
        self.assertIn("folder", galat)
        self.assertIsNone(galat["folder"])
        self.assertTrue(galat["galat"])

    def test_kunci_status_sama_saat_galat_dan_normal(self):
        normal = startup.status_startup(self.dir)
        with mock.patch.dict(os.environ, {}, clear=True):
            galat = startup.status_startup()
        self.assertEqual(sorted(galat), sorted(normal))

    def test_nonaktifkan_mengembalikan_dict_bukan_melempar(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            hasil = startup.nonaktifkan_startup()
        self.assertFalse(hasil["aktif"])
        self.assertEqual(hasil["dihapus"], [])
        self.assertIsNone(hasil["folder"])
        self.assertTrue(hasil["galat"])

    def test_kunci_nonaktifkan_sama_saat_galat_dan_normal(self):
        normal = startup.nonaktifkan_startup(self.dir)
        with mock.patch.dict(os.environ, {}, clear=True):
            galat = startup.nonaktifkan_startup()
        self.assertEqual(sorted(galat), sorted(normal))

    def test_alih_mati_mengembalikan_dict_bukan_melempar(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            hasil = startup.alih_startup(False)
        self.assertFalse(hasil["aktif"])
        self.assertTrue(hasil["galat"])


@unittest.skipUnless(os.name == "nt" and startup._powershell(), "butuh PowerShell Windows")
class Lnk(Dasar):
    def test_lnk_sungguhan_dibuat_dan_terbaca_status(self):
        hasil = startup.aktifkan_startup(folder=self.dir, exe=EXE_BERSPASI)
        self.assertEqual(hasil["metode"], "lnk", "pembuatan .lnk lewat PowerShell gagal")
        jalur = os.path.join(self.dir, startup.NAMA_LNK)
        self.assertGreater(os.path.getsize(jalur), 0)
        s = startup.status_startup(self.dir)
        self.assertTrue(s["aktif"])
        self.assertEqual(s["metode"], "lnk")

    def test_lnk_menyimpan_path_berspasi_utuh(self):
        startup.aktifkan_startup(folder=self.dir, exe=EXE_BERSPASI)
        with open(os.path.join(self.dir, startup.NAMA_LNK), "rb") as f:
            mentah = f.read()
        self.assertIn("ingat-panel.exe".encode("utf-16-le"), mentah)
        self.assertIn("Program Files".encode("utf-16-le"), mentah)

    def test_lnk_idempoten_dan_nonaktifkan_bersih(self):
        startup.aktifkan_startup(folder=self.dir, exe=EXE_BERSPASI)
        startup.aktifkan_startup(folder=self.dir, exe=EXE_BERSPASI)
        self.assertEqual(self.isi_folder(), [startup.NAMA_LNK])
        startup.nonaktifkan_startup(self.dir)
        self.assertEqual(self.isi_folder(), [])


if __name__ == "__main__":
    unittest.main()
