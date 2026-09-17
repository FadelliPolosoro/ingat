# SPDX-License-Identifier: Apache-2.0
"""A1 — backup/restore portabel. Round-trip lengkap (store+vault+config), snapshot SQLite
konsisten (WAL tertangkap), checksum SHA-256 menolak tarball rusak, pagar timpa & versi."""
from __future__ import annotations

import json
import os
import shutil
import tarfile
import tempfile
import unittest

from ingat import backup
from ingat.simpan import Store
from ingat.vektor import PenyematLokal


class BackupRestore(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="ingat-bk-")
        self.ingat = os.path.join(self.root, "ingat")
        self.data = os.path.join(self.ingat, "data")
        os.makedirs(self.data)
        self.store = Store(self.data, PenyematLokal())
        self.ep = self.store.tambah_episode("isi rahasia verbatim", sumber="uji", tier="I",
                                            lingkup="peran:asisten-ai", jenis_kejadian="sukses",
                                            ringkas="r", instrumen=["x"], sesi="s1")
        v = os.path.join(self.ingat, "vault", "pelajaran")
        os.makedirs(v)
        with open(os.path.join(v, "pel-1.md"), "w", encoding="utf-8") as f:
            f.write("# pelajaran uji\n")
        with open(os.path.join(self.ingat, "konfigurasi.json"), "w", encoding="utf-8") as f:
            json.dump({"dir_data": self.data, "embedding": {"jenis": "lokal", "dim": 512}}, f)

    def tearDown(self):
        try:
            self.store.db.close()
        except Exception:
            pass
        shutil.rmtree(self.root, ignore_errors=True)

    def test_backup_membuat_tarball_dan_checksum(self):
        meta = backup.buat_backup(self.ingat)
        self.assertTrue(os.path.isfile(meta["berkas"]))
        self.assertTrue(os.path.isfile(meta["berkas"] + ".sha256"))
        self.assertEqual(meta["versi_backup"], backup.VERSI_BACKUP)
        self.assertGreaterEqual(meta["jumlah"]["episode"], 1)

    def test_roundtrip_pulih_lengkap(self):
        meta = backup.buat_backup(self.ingat)
        target = os.path.join(self.root, "baru")
        backup.pulihkan_backup(meta["berkas"], target)
        st2 = Store(os.path.join(target, "data"), PenyematLokal())
        try:
            ep2 = st2.episode(self.ep.id)
            self.assertIsNotNone(ep2, "id episode harus bertahan lintas backup")
            self.assertEqual(st2.buka_dingin(ep2.isi_ref)["isi"], "isi rahasia verbatim",
                             "isi verbatim (dingin) harus utuh")
        finally:
            st2.db.close()
        self.assertTrue(os.path.isfile(os.path.join(target, "vault", "pelajaran", "pel-1.md")),
                        "vault harus ikut pulih")
        self.assertTrue(os.path.isfile(os.path.join(target, "konfigurasi.json")),
                        "konfigurasi harus ikut pulih")

    def test_checksum_rusak_ditolak(self):
        meta = backup.buat_backup(self.ingat)
        with open(meta["berkas"], "r+b") as f:
            f.seek(20)
            f.write(b"\x00\x00\x00\x00")
        with self.assertRaises(ValueError):
            backup.pulihkan_backup(meta["berkas"], os.path.join(self.root, "baru2"))

    def test_target_berisi_tanpa_timpa_ditolak(self):
        meta = backup.buat_backup(self.ingat)
        target = os.path.join(self.root, "berisi")
        os.makedirs(os.path.join(target, "data"))
        with self.assertRaises(FileExistsError):
            backup.pulihkan_backup(meta["berkas"], target)

    def test_timpa_menggantikan(self):
        meta = backup.buat_backup(self.ingat)
        target = os.path.join(self.root, "timpa")
        os.makedirs(os.path.join(target, "data"))
        backup.pulihkan_backup(meta["berkas"], target, timpa=True)
        self.assertTrue(os.path.isfile(os.path.join(target, "data", "ingat.sqlite")))

    def test_versi_tak_dikenal_ditolak(self):
        stage = tempfile.mkdtemp(prefix="ingat-aneh-")
        os.makedirs(os.path.join(stage, "ingat-backup", "data"))
        with open(os.path.join(stage, "ingat-backup", "metadata.json"), "w", encoding="utf-8") as f:
            json.dump({"versi_backup": 999}, f)
        tar = os.path.join(self.root, "aneh.tar.gz")
        with tarfile.open(tar, "w:gz") as t:
            t.add(os.path.join(stage, "ingat-backup"), arcname="ingat-backup")
        with self.assertRaises(ValueError):
            backup.pulihkan_backup(tar, os.path.join(self.root, "x"), verifikasi=False)


if __name__ == "__main__":
    unittest.main()
