"""Uji hitungan_tinjau — badge panel + data monitor."""
import os, shutil, tempfile, unittest

from ingat.simpan import Store
from ingat.vektor import PenyematLokal
from ingat import panel, skema


class HitunganTinjau(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ingat-tinjau-")
        self.store = Store(os.path.join(self.dir, "s"), PenyematLokal())

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_kosong_tanpa_item(self):
        h = panel.hitungan_tinjau(self.store)
        self.assertEqual(h["total"], 0)
        self.assertEqual(h["daftar"], [])

    def test_pelajaran_tinjau_ulang_terhitung(self):
        p = skema.Pelajaran(
            id=skema.id_baru("pl"), pelajaran="uji", pemicu="x",
            tindakan="y", lingkup="global", status="aturan", keyakinan=0.8,
            tinjau_ulang=True, dibuat=skema.sekarang(),
        )
        self.store.simpan_pelajaran(p)
        h = panel.hitungan_tinjau(self.store)
        self.assertEqual(h["total"], 1)
        self.assertEqual(h["pelajaran"], 1)
        self.assertEqual(h["prosedur"], 0)
        self.assertEqual(len(h["daftar"]), 1)
        self.assertEqual(h["daftar"][0]["jenis"], "pelajaran")

    def test_tidak_tinjau_ulang_tidak_terhitung(self):
        p = skema.Pelajaran(
            id=skema.id_baru("pl"), pelajaran="ok", pemicu="x",
            tindakan="y", lingkup="global", status="aturan", keyakinan=0.9,
            tinjau_ulang=False, dibuat=skema.sekarang(),
        )
        self.store.simpan_pelajaran(p)
        self.assertEqual(panel.hitungan_tinjau(self.store)["total"], 0)

    def test_prosedur_tinjau_ulang_terhitung(self):
        p = skema.Prosedur(
            id=skema.id_baru("pr"), prosedur="proses uji", tugas_pemicu="x",
            langkah=["a"], lingkup="global", status="aktif",
            tinjau_ulang=True, dibuat=skema.sekarang(),
        )
        self.store.simpan_prosedur(p)
        h = panel.hitungan_tinjau(self.store)
        self.assertEqual(h["total"], 1)
        self.assertEqual(h["prosedur"], 1)
        self.assertEqual(h["pelajaran"], 0)

    def test_campuran(self):
        pl = skema.Pelajaran(
            id=skema.id_baru("pl"), pelajaran="a", pemicu="x",
            tindakan="y", lingkup="global", tinjau_ulang=True, dibuat=skema.sekarang(),
        )
        pr = skema.Prosedur(
            id=skema.id_baru("pr"), prosedur="b", tugas_pemicu="x",
            langkah=["a"], lingkup="global", tinjau_ulang=True, dibuat=skema.sekarang(),
        )
        self.store.simpan_pelajaran(pl)
        self.store.simpan_prosedur(pr)
        h = panel.hitungan_tinjau(self.store)
        self.assertEqual(h["total"], 2)
        self.assertEqual(h["pelajaran"], 1)
        self.assertEqual(h["prosedur"], 1)
        self.assertEqual(len(h["daftar"]), 2)


if __name__ == "__main__":
    unittest.main()
