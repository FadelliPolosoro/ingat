# SPDX-License-Identifier: Apache-2.0
"""Enkripsi/dekripsi 4-layer — roundtrip v2, backward compat v1, sandi salah, berkas rusak, integrasi backup."""
from __future__ import annotations

import json
import os
import shutil
import struct
import tempfile
import unittest

from ingat import kripto
from ingat.simpan import Store
from ingat.vektor import PenyematLokal


class KriptoV2Unit(unittest.TestCase):
    """Layer 1-4: format INGAT2."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ingat-kripto-")
        self.plain = os.path.join(self.tmp, "data.bin")
        with open(self.plain, "wb") as f:
            f.write(b"rahasia tier S verbatim " * 100)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_roundtrip_v2(self):
        enc = os.path.join(self.tmp, "data.enc")
        dec = os.path.join(self.tmp, "data.dec")
        kripto.enkripsi(self.plain, enc, "sandiKuat123!")
        kripto.dekripsi(enc, dec, "sandiKuat123!")
        with open(self.plain, "rb") as f:
            asli = f.read()
        with open(dec, "rb") as f:
            hasil = f.read()
        self.assertEqual(asli, hasil)

    def test_format_v2_magic(self):
        enc = os.path.join(self.tmp, "data.enc")
        kripto.enkripsi(self.plain, enc, "sandiKuat123!")
        with open(enc, "rb") as f:
            magic = f.read(6)
        self.assertEqual(magic, b"INGAT2")

    def test_versi_enkripsi(self):
        enc = os.path.join(self.tmp, "data.enc")
        kripto.enkripsi(self.plain, enc, "sandiKuat123!")
        self.assertEqual(kripto.versi_enkripsi(enc), 2)
        self.assertIsNone(kripto.versi_enkripsi(self.plain))

    def test_output_berbeda_tiap_kali(self):
        """Salt+nonce acak → output selalu berbeda walau input+sandi sama."""
        enc1 = os.path.join(self.tmp, "e1.enc")
        enc2 = os.path.join(self.tmp, "e2.enc")
        kripto.enkripsi(self.plain, enc1, "sandiKuat123!")
        kripto.enkripsi(self.plain, enc2, "sandiKuat123!")
        with open(enc1, "rb") as f:
            d1 = f.read()
        with open(enc2, "rb") as f:
            d2 = f.read()
        self.assertNotEqual(d1, d2)

    def test_sandi_salah_ditolak(self):
        enc = os.path.join(self.tmp, "data.enc")
        kripto.enkripsi(self.plain, enc, "sandiKuat123!")
        with self.assertRaises(ValueError) as ctx:
            kripto.dekripsi(enc, os.path.join(self.tmp, "bad.dec"), "sandiSalah99")
        self.assertIn("gagal", str(ctx.exception).lower())

    def test_berkas_bukan_enkripsi_ditolak(self):
        with self.assertRaises(ValueError) as ctx:
            kripto.dekripsi(self.plain, os.path.join(self.tmp, "x.dec"), "apapun12345678")
        self.assertIn("magic", str(ctx.exception).lower())

    def test_sandi_terlalu_pendek_ditolak(self):
        with self.assertRaises(ValueError):
            kripto.enkripsi(self.plain, os.path.join(self.tmp, "x.enc"), "abc")

    def test_adalah_terenkripsi(self):
        enc = os.path.join(self.tmp, "data.enc")
        kripto.enkripsi(self.plain, enc, "sandiKuat123!")
        self.assertTrue(kripto.adalah_terenkripsi(enc))
        self.assertFalse(kripto.adalah_terenkripsi(self.plain))

    def test_header_terpotong_ditolak(self):
        enc = os.path.join(self.tmp, "potong.enc")
        with open(enc, "wb") as f:
            f.write(kripto._MAGIC_V2 + b"\x02\x00" + b"\x01" * 10)
        with self.assertRaises(ValueError):
            kripto.dekripsi(enc, os.path.join(self.tmp, "y.dec"), "sandiApapun1234")

    def test_tamper_ciphertext_ditolak(self):
        """L3: modifikasi ciphertext terdeteksi oleh HMAC total."""
        enc = os.path.join(self.tmp, "data.enc")
        kripto.enkripsi(self.plain, enc, "sandiKuat123!")
        with open(enc, "rb") as f:
            raw = bytearray(f.read())
        # flip satu byte di tengah ciphertext (setelah header 60 + hmac_header 32)
        pos = 60 + 32 + 10
        raw[pos] ^= 0xFF
        with open(enc, "wb") as f:
            f.write(raw)
        with self.assertRaises(ValueError) as ctx:
            kripto.dekripsi(enc, os.path.join(self.tmp, "t.dec"), "sandiKuat123!")
        pesan = str(ctx.exception).lower()
        self.assertTrue("hmac" in pesan or "rusak" in pesan or "gagal" in pesan)

    def test_tamper_header_ditolak(self):
        """L4: modifikasi header terdeteksi oleh HMAC header."""
        enc = os.path.join(self.tmp, "data.enc")
        kripto.enkripsi(self.plain, enc, "sandiKuat123!")
        with open(enc, "rb") as f:
            raw = bytearray(f.read())
        # flip timestamp byte
        raw[10] ^= 0xFF
        with open(enc, "wb") as f:
            f.write(raw)
        with self.assertRaises(ValueError) as ctx:
            kripto.dekripsi(enc, os.path.join(self.tmp, "t.dec"), "sandiKuat123!")
        self.assertIn("header", str(ctx.exception).lower())


class BackwardCompatV1(unittest.TestCase):
    """Dekripsi berkas format lama (INGAT1) masih berfungsi."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ingat-v1compat-")
        self.plain = os.path.join(self.tmp, "data.bin")
        with open(self.plain, "wb") as f:
            f.write(b"data lama format v1 " * 50)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _enkripsi_v1(self, masuk, keluar, sandi):
        """Simulasi enkripsi format v1 (INGAT1)."""
        import base64
        from cryptography.fernet import Fernet
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        from cryptography.hazmat.primitives import hashes

        salt = os.urandom(16)
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32,
                         salt=salt, iterations=600_000)
        kunci = base64.urlsafe_b64encode(kdf.derive(sandi.encode("utf-8")))
        with open(masuk, "rb") as f:
            data = f.read()
        token = Fernet(kunci).encrypt(data)
        with open(keluar, "wb") as f:
            f.write(b"INGAT1")
            f.write(salt)
            f.write(token)

    def test_dekripsi_v1_masih_berfungsi(self):
        enc = os.path.join(self.tmp, "old.enc")
        dec = os.path.join(self.tmp, "old.dec")
        self._enkripsi_v1(self.plain, enc, "sandiLama12345")
        kripto.dekripsi(enc, dec, "sandiLama12345")
        with open(self.plain, "rb") as f:
            asli = f.read()
        with open(dec, "rb") as f:
            hasil = f.read()
        self.assertEqual(asli, hasil)

    def test_v1_terdeteksi_sebagai_terenkripsi(self):
        enc = os.path.join(self.tmp, "old.enc")
        self._enkripsi_v1(self.plain, enc, "sandiLama12345")
        self.assertTrue(kripto.adalah_terenkripsi(enc))
        self.assertEqual(kripto.versi_enkripsi(enc), 1)


class BackupTerenkripsi(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="ingat-bkenc-")
        self.ingat = os.path.join(self.root, "ingat")
        self.data = os.path.join(self.ingat, "data")
        os.makedirs(self.data)
        self.store = Store(self.data, PenyematLokal())
        self.ep = self.store.tambah_episode("isi rahasia tier S", sumber="uji", tier="S",
                                            lingkup="peran:asisten-ai", jenis_kejadian="sukses",
                                            ringkas="r", instrumen=["x"], sesi="s1")
        with open(os.path.join(self.ingat, "konfigurasi.json"), "w", encoding="utf-8") as f:
            json.dump({"dir_data": self.data}, f)

    def tearDown(self):
        try:
            self.store.db.close()
        except Exception:
            pass
        shutil.rmtree(self.root, ignore_errors=True)

    def test_backup_terenkripsi_roundtrip(self):
        from ingat.backup import buat_backup, pulihkan_backup
        meta = buat_backup(self.ingat, sandi="sandiKuatUntukBackup!")
        self.assertTrue(meta["berkas"].endswith(".enc"))
        self.assertTrue(meta.get("terenkripsi"))
        self.assertTrue(kripto.adalah_terenkripsi(meta["berkas"]))
        self.assertEqual(kripto.versi_enkripsi(meta["berkas"]), 2)

        target = os.path.join(self.root, "baru")
        lap = pulihkan_backup(meta["berkas"], target, sandi="sandiKuatUntukBackup!")
        st2 = Store(os.path.join(target, "data"), PenyematLokal())
        try:
            ep2 = st2.episode(self.ep.id)
            self.assertIsNotNone(ep2)
        finally:
            st2.db.close()

    def test_restore_tanpa_sandi_ditolak(self):
        from ingat.backup import buat_backup, pulihkan_backup
        meta = buat_backup(self.ingat, sandi="sandiKuatUntukBackup!")
        with self.assertRaises(ValueError) as ctx:
            pulihkan_backup(meta["berkas"], os.path.join(self.root, "baru2"))
        self.assertIn("sandi", str(ctx.exception).lower())

    def test_restore_sandi_salah_ditolak(self):
        from ingat.backup import buat_backup, pulihkan_backup
        meta = buat_backup(self.ingat, sandi="sandiKuatUntukBackup!")
        with self.assertRaises(ValueError):
            pulihkan_backup(meta["berkas"], os.path.join(self.root, "baru3"),
                            sandi="sandiSalahBanget123")


class RestoreKonfigTarget(unittest.TestCase):
    """Sinkron data ke mesin lain tidak boleh menimpa konfigurasi.json mesin tujuan.

    Insiden 18 Sep 2026: restore laptop→VPS menimpa konfig VPS dengan konfig laptop;
    `dir_data` jadi path Windows ("C:\\Users\\...") yang di-resolve relatif terhadap
    working directory servis, sehingga server membuka store kosong di lokasi salah.
    """

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="ingat-konfig-")
        self.asal = os.path.join(self.root, "asal")
        os.makedirs(os.path.join(self.asal, "data"))
        st = Store(os.path.join(self.asal, "data"), PenyematLokal())
        st.tambah_episode("isi", sumber="uji", tier="I", lingkup="peran:uji",
                          jenis_kejadian="sukses", ringkas="r", instrumen=["x"], sesi="s1")
        st.db.close()
        with open(os.path.join(self.asal, "konfigurasi.json"), "w", encoding="utf-8") as f:
            json.dump({"dir_data": "C:\\Users\\Laptop\\.ingat\\data",
                       "jauh": {"host": "https://relay-lama.example"}}, f)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_tanpa_konfig_menyisakan_konfig_target(self):
        from ingat.backup import buat_backup, pulihkan_backup
        meta = buat_backup(self.asal)
        target = os.path.join(self.root, "tujuan")
        os.makedirs(target)
        konfig_target = {"dir_data": "/root/.ingat/data", "server": {"host": "0.0.0.0"}}
        with open(os.path.join(target, "konfigurasi.json"), "w", encoding="utf-8") as f:
            json.dump(konfig_target, f)

        lap = pulihkan_backup(meta["berkas"], target, timpa=True, pulihkan_konfig=False)
        self.assertFalse(lap["konfig_dipulihkan"])
        with open(os.path.join(target, "konfigurasi.json"), encoding="utf-8") as f:
            sesudah = json.load(f)
        self.assertEqual(sesudah, konfig_target)
        self.assertNotIn("jauh", sesudah)
        self.assertTrue(os.path.isfile(os.path.join(target, "data", "ingat.sqlite")))

    def test_default_tetap_memulihkan_konfig(self):
        """Pindah perangkat (default) tetap membawa konfig — perilaku lama tidak berubah."""
        from ingat.backup import buat_backup, pulihkan_backup
        meta = buat_backup(self.asal)
        target = os.path.join(self.root, "tujuan2")
        lap = pulihkan_backup(meta["berkas"], target)
        self.assertTrue(lap["konfig_dipulihkan"])
        with open(os.path.join(target, "konfigurasi.json"), encoding="utf-8") as f:
            sesudah = json.load(f)
        self.assertEqual(sesudah["dir_data"], "C:\\Users\\Laptop\\.ingat\\data")


if __name__ == "__main__":
    unittest.main()
