# SPDX-License-Identifier: Apache-2.0
"""SELARAS tiket 2+3: DB Store lama (vektor inline, AUTOINCREMENT) bermigrasi ke kontrak v2 tanpa kehilangan data;
identitas embedder ditegakkan; dua koleksi per pelajaran (R12) dipakai gateway."""
from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
import unittest

from ingat import skema
from ingat.gate import Gate
from ingat.gateway import Gateway
from ingat.simpan import Store, IdentitasEmbedderTidakCocok, VERSI_KONTRAK
from ingat.vektor import PenyematLokal, ke_blob

AKAR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKEMA_LAMA = os.path.join(AKAR, "skema", "versi", "python-store-v0.2.sql")
KONTRAK = os.path.join(AKAR, "skema", "ingat.sql")
FP = "proyek:fp-dashboard"


class MigrasiStoreLama(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ingat-mig-")
        self.data = os.path.join(self.dir, "data")
        os.makedirs(os.path.join(self.data, "dingin"))
        self.penyemat = PenyematLokal()
        # DB lama: vektor inline + AUTOINCREMENT n
        db = sqlite3.connect(os.path.join(self.data, "ingat.sqlite"))
        with open(SKEMA_LAMA, encoding="utf-8") as f:
            db.executescript(f.read())
        v = self.penyemat.semat("Ketiadaan hasil satu tool bukan ketiadaan objek\nMenyimpulkan tidak ada X dari tool kosong\nCari jalur kedua")
        db.execute("INSERT INTO pelajaran(id,pelajaran,pemicu,tindakan,lingkup,status,keyakinan,bukti,kontra,instrumen_saat_dibuat,"
                   "berlaku_untuk,dibuat,vektor,model_embedding) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   ("pl-lama", "Ketiadaan hasil satu tool bukan ketiadaan objek", "Menyimpulkan tidak ada X dari tool kosong",
                    "Cari jalur kedua", FP, "aturan", 0.8, "[]", "[]", "[]", "{}", "2026-01-01", ke_blob(v), self.penyemat.nama))
        db.execute("INSERT INTO metrik(waktu,nama,nilai,konteks) VALUES('2026-01-01T00:00:00','uji',1,'{}')")
        db.execute("INSERT INTO metrik(waktu,nama,nilai,konteks) VALUES('2026-01-02T00:00:00','uji',2,'{}')")
        db.execute("INSERT INTO riwayat_status(waktu,jenis,item_id,dari,ke,oleh,alasan) VALUES('2026-01-01','pelajaran','pl-lama','usulan','aturan','manusia','uji')")
        db.commit(); db.close()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _kolom(self, db, tabel):
        return [r[1] for r in db.execute(f"PRAGMA table_info({tabel})")]

    def test_migrasi_ke_kontrak_v2_tanpa_kehilangan_data(self):
        store = Store(self.data, self.penyemat)
        db = store.db
        self.assertEqual(db.execute("SELECT nilai FROM meta WHERE kunci='versi_kontrak'").fetchone()[0], VERSI_KONTRAK)
        # vektor pindah ke tabel vektor, kolom lama hilang
        self.assertEqual(db.execute("SELECT COUNT(*) FROM vektor WHERE item_id='pl-lama' AND koleksi='isi'").fetchone()[0], 1)
        self.assertNotIn("vektor", self._kolom(db, "pelajaran"))
        self.assertNotIn("model_embedding", self._kolom(db, "pelajaran"))
        # identitas tercatat dari model lama, cocok dengan penyemat sekarang
        self.assertEqual(db.execute("SELECT model FROM identitas_embedder WHERE koleksi='isi'").fetchone()[0], self.penyemat.nama)
        # AUTOINCREMENT n -> id, data urut tetap
        for tabel in ("metrik", "riwayat_status", "panggilan_ingat"):
            kolom = self._kolom(db, tabel)
            self.assertIn("id", kolom, tabel)
            self.assertNotIn("n", kolom, tabel)
        self.assertEqual([r[0] for r in db.execute("SELECT nilai FROM metrik WHERE nama='uji' ORDER BY id")], [1.0, 2.0])
        self.assertEqual(db.execute("SELECT COUNT(*) FROM riwayat_status").fetchone()[0], 1)
        # objek lama termuat dengan vektor isi (pemicu belum ada: DB lama tidak punya koleksi itu)
        p = store.pelajaran("pl-lama")
        self.assertTrue(p._vektor)
        self.assertEqual(p._vektor_pemicu, [])
        # simpan ulang -> koleksi pemicu terbentuk (R12)
        store.simpan_pelajaran(p)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM vektor WHERE item_id='pl-lama'").fetchone()[0], 2)
        # transisi_status terisi dari skema.py
        self.assertGreater(db.execute("SELECT COUNT(*) FROM transisi_status").fetchone()[0], 15)
        # buka ulang: migrasi idempoten
        store.db.close()
        Store(self.data, self.penyemat).db.close()


class IdentitasDanKoleksi(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ingat-idk-")
        self.data = os.path.join(self.dir, "data")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_ganti_model_ditolak_kecuali_bangun_ulang(self):
        store = Store(self.data, PenyematLokal(dim=512))
        p = skema.Pelajaran(id="pl-1", pelajaran="A", pemicu="B", tindakan="C", lingkup=FP, status="aturan", keyakinan=0.8)
        store.simpan_pelajaran(p)
        store.db.close()
        with self.assertRaises(IdentitasEmbedderTidakCocok):
            Store(self.data, PenyematLokal(dim=256))
        store2 = Store(self.data, PenyematLokal(dim=256), bangun_ulang_vektor=True)
        self.assertEqual(store2.db.execute("SELECT dimensi FROM identitas_embedder WHERE koleksi='isi'").fetchone()[0], 256)
        self.assertEqual(len(store2.pelajaran("pl-1")._vektor), 256)
        self.assertEqual(len(store2.pelajaran("pl-1")._vektor_pemicu), 256)
        store2.db.close()

    def test_dua_koleksi_dan_pemicu_menemukan_pelajaran(self):
        """R12: query yang cocok dengan PEMICU (bukan isi) tetap menemukan pelajaran."""
        store = Store(self.data, PenyematLokal())
        p = skema.Pelajaran(id="pl-r12", pelajaran="Xanadu quorvat blimp zetta", tindakan="Ylem gorsk plint",
                            pemicu="akan menyimpulkan tidak ada objek karena satu tool mengembalikan kosong",
                            lingkup=FP, status="aturan", keyakinan=0.9, ditinjau_manusia=True)
        store.simpan_pelajaran(p)
        self.assertEqual({r[0] for r in store.db.execute("SELECT koleksi FROM vektor WHERE item_id='pl-r12'")}, {"isi", "pemicu"})
        gw = Gateway(store)
        hasil = gw.ingat("tool mengembalikan kosong, hendak menyimpulkan tidak ada objek", FP)
        self.assertIn("pl-r12", [i["id"] for i in hasil["item"]], hasil)


class KontrakSubset(unittest.TestCase):
    def test_setiap_kolom_kontrak_ada_di_store_python(self):
        d = tempfile.mkdtemp(prefix="ingat-ks-")
        try:
            store = Store(os.path.join(d, "data"), PenyematLokal())
            kontrak = sqlite3.connect(":memory:")
            with open(KONTRAK, encoding="utf-8") as f:
                kontrak.executescript(f.read())
            tabel = [r[0] for r in kontrak.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
            for t in tabel:
                kolom_kontrak = {r[1] for r in kontrak.execute(f"PRAGMA table_info({t})")}
                kolom_python = {r[1] for r in store.db.execute(f"PRAGMA table_info({t})")}
                self.assertTrue(kolom_python, f"tabel kontrak '{t}' tidak ada di Store")
                self.assertEqual(kolom_kontrak - kolom_python, set(), f"kolom kontrak hilang di Store.{t}")
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
