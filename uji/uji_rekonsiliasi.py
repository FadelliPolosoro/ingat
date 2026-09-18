# SPDX-License-Identifier: Apache-2.0
"""C — rekonsiliasi store ↔ vault: deteksi divergensi, perbaiki bukti korup, tulis vault hilang."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest

from ingat import rekonsiliasi
from ingat.vault import Vault
from ingat.simpan import Store
from ingat.vektor import PenyematLokal


class _Basis(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="ingat-rekon-")
        self.data = os.path.join(self.root, "data")
        os.makedirs(self.data)
        self.store = Store(self.data, PenyematLokal())
        self.vault_path = os.path.join(self.root, "vault")
        self.vault = Vault(self.vault_path)

    def tearDown(self):
        try:
            self.store.db.close()
        except Exception:
            pass
        shutil.rmtree(self.root, ignore_errors=True)

    def _ep(self, isi="x"):
        return self.store.tambah_episode(isi, sumber="uji", tier="I",
                                         lingkup="peran:uji", jenis_kejadian="sukses",
                                         ringkas="r", instrumen=["x"], sesi="s1")


class PeriksaTest(_Basis):
    def test_selaras_nol_masalah(self):
        ep = self._ep()
        self.store.simpan_pelajaran(self.store._dari_baris("pelajaran",
            {"id": "pl-aaa", "pelajaran": "x", "pemicu": "y", "tindakan": "z",
             "lingkup": "peran:uji", "status": "usulan", "keyakinan": 0.5,
             "bukti": json.dumps([ep.id]), "kontra": "[]",
             "instrumen_saat_dibuat": "[]", "berlaku_untuk": "{}",
             "tier_maks": "I", "tinjau_ulang": 0, "ditinjau_manusia": 0,
             "veto_manusia": None, "versi": 1}))
        self.vault.tulis_usulan_pelajaran(self.store.pelajaran("pl-aaa"), [ep.ringkas])
        lap = rekonsiliasi.periksa(self.store, self.vault_path)
        self.assertEqual(lap["ringkasan"]["vault_hilang"], 0)
        self.assertEqual(lap["ringkasan"]["bukti_korup"], 0)

    def test_vault_hilang_terdeteksi(self):
        ep = self._ep()
        self.store.simpan_pelajaran(self.store._dari_baris("pelajaran",
            {"id": "pl-bbb", "pelajaran": "x", "pemicu": "y", "tindakan": "z",
             "lingkup": "peran:uji", "status": "usulan", "keyakinan": 0.5,
             "bukti": json.dumps([ep.id]), "kontra": "[]",
             "instrumen_saat_dibuat": "[]", "berlaku_untuk": "{}",
             "tier_maks": "I", "tinjau_ulang": 0, "ditinjau_manusia": 0,
             "veto_manusia": None, "versi": 1}))
        lap = rekonsiliasi.periksa(self.store, self.vault_path)
        self.assertEqual(lap["ringkasan"]["vault_hilang"], 1)
        self.assertEqual(lap["vault_hilang"][0]["id"], "pl-bbb")

    def test_bukti_korup_terdeteksi(self):
        sampah = [" ", ",", "-", "0", "1", "ep-valid-001"]
        self.store.simpan_pelajaran(self.store._dari_baris("pelajaran",
            {"id": "pl-ccc", "pelajaran": "x", "pemicu": "y", "tindakan": "z",
             "lingkup": "peran:uji", "status": "usulan", "keyakinan": 0.5,
             "bukti": json.dumps(sampah), "kontra": "[]",
             "instrumen_saat_dibuat": "[]", "berlaku_untuk": "{}",
             "tier_maks": "I", "tinjau_ulang": 0, "ditinjau_manusia": 0,
             "veto_manusia": None, "versi": 1}))
        lap = rekonsiliasi.periksa(self.store, self.vault_path)
        self.assertEqual(lap["ringkasan"]["bukti_korup"], 1)
        self.assertEqual(lap["bukti_korup"][0]["sampah"], 5)
        self.assertEqual(lap["bukti_korup"][0]["bersih"], 1)


class PerbaikiTest(_Basis):
    def test_bukti_dibersihkan(self):
        sampah = [" ", ",", "ep-valid-001", "ep-valid-002", "0"]
        self.store.simpan_pelajaran(self.store._dari_baris("pelajaran",
            {"id": "pl-ddd", "pelajaran": "x", "pemicu": "y", "tindakan": "z",
             "lingkup": "peran:uji", "status": "usulan", "keyakinan": 0.5,
             "bukti": json.dumps(sampah), "kontra": "[]",
             "instrumen_saat_dibuat": "[]", "berlaku_untuk": "{}",
             "tier_maks": "I", "tinjau_ulang": 0, "ditinjau_manusia": 0,
             "veto_manusia": None, "versi": 1}))
        lap = rekonsiliasi.perbaiki(self.store, self.vault_path, self.vault)
        self.assertEqual(len(lap["bukti_diperbaiki"]), 1)
        self.assertEqual(lap["bukti_diperbaiki"][0]["sesudah"], 2)
        p = self.store.pelajaran("pl-ddd")
        self.assertEqual(p.bukti, ["ep-valid-001", "ep-valid-002"])

    def test_vault_hilang_ditulis(self):
        ep = self._ep("isi penting")
        self.store.simpan_pelajaran(self.store._dari_baris("pelajaran",
            {"id": "pl-eee", "pelajaran": "x", "pemicu": "y", "tindakan": "z",
             "lingkup": "peran:uji", "status": "usulan", "keyakinan": 0.5,
             "bukti": json.dumps([ep.id]), "kontra": "[]",
             "instrumen_saat_dibuat": "[]", "berlaku_untuk": "{}",
             "tier_maks": "I", "tinjau_ulang": 0, "ditinjau_manusia": 0,
             "veto_manusia": None, "versi": 1}))
        lap = rekonsiliasi.perbaiki(self.store, self.vault_path, self.vault)
        self.assertIn("pl-eee", lap["vault_ditulis"])
        self.assertTrue(os.path.isfile(os.path.join(self.vault_path, "pelajaran", "_usulan", "pl-eee.md")))

    def test_duplikat_bukti_dihilangkan(self):
        dupl = ["ep-valid-001", "ep-valid-001", "ep-valid-002"]
        self.store.simpan_pelajaran(self.store._dari_baris("pelajaran",
            {"id": "pl-fff", "pelajaran": "x", "pemicu": "y", "tindakan": "z",
             "lingkup": "peran:uji", "status": "usulan", "keyakinan": 0.5,
             "bukti": json.dumps(dupl), "kontra": "[]",
             "instrumen_saat_dibuat": "[]", "berlaku_untuk": "{}",
             "tier_maks": "I", "tinjau_ulang": 0, "ditinjau_manusia": 0,
             "veto_manusia": None, "versi": 1}))
        lap = rekonsiliasi.perbaiki(self.store, self.vault_path, self.vault)
        self.assertEqual(len(lap["bukti_diperbaiki"]), 1)
        p = self.store.pelajaran("pl-fff")
        self.assertEqual(p.bukti, ["ep-valid-001", "ep-valid-002"])


if __name__ == "__main__":
    unittest.main()
