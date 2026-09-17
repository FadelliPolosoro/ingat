# SPDX-License-Identifier: Apache-2.0
"""Uji kotak cari panel: pembungkus Gateway.ingat(), riwayat JSON, dan penanganan
keadaan buruk (store kosong, Ollama mati, identitas embedder tak cocok).

Semua tanpa layar dan tanpa jaringan: penyemat lokal + `pembuka` yang disuntik.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
import urllib.error
from unittest import mock

from ingat import cari_memori, skema
from ingat.gateway import Gateway
from ingat.simpan import IdentitasEmbedderTidakCocok, Store
from ingat.vektor import PenyematLokal

RINGKAS = "rapat anggaran tender komdigi januari"


class _Balas:
    """Tiruan objek respons urllib (context manager dengan .read())."""

    def __init__(self, data):
        self._d = json.dumps(data).encode()

    def read(self):
        return self._d

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _GerbangGagal:
    def __init__(self, galat):
        self.galat = galat

    def ingat(self, *a, **k):
        raise self.galat


class Dasar(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ingat-cari-")
        self.dir_data = os.path.join(self.dir, "data")
        os.makedirs(self.dir_data)
        self._p = mock.patch.object(cari_memori, "DIR_INGAT", self.dir)
        self._p.start()
        self.store = Store(self.dir_data, PenyematLokal(512))
        self.gerbang = Gateway(self.store)

    def tearDown(self):
        self._p.stop()
        try:
            self.store.db.close()
        except Exception:
            pass
        shutil.rmtree(self.dir, ignore_errors=True)

    def _episode(self, ringkas=RINGKAS, isi="catatan lengkap rapat"):
        return self.store.tambah_episode(isi, sumber="uji", tier="I", lingkup="global",
                                         jenis_kejadian="sukses", ringkas=ringkas)


class Potong(unittest.TestCase):
    def test_pendek_tidak_diubah(self):
        self.assertEqual(cari_memori.potong_kutipan("halo dunia"), "halo dunia")

    def test_spasi_berlebih_dirapikan(self):
        self.assertEqual(cari_memori.potong_kutipan("halo \n  dunia "), "halo dunia")

    def test_panjang_dipotong_di_batas_kata(self):
        teks = "kata " * 200
        hasil = cari_memori.potong_kutipan(teks, 50)
        self.assertLessEqual(len(hasil), 51)
        self.assertTrue(hasil.endswith("…"))
        self.assertNotIn("kat…", hasil)

    def test_kunci_pertanyaan_menormalkan(self):
        self.assertEqual(cari_memori.kunci_pertanyaan("  Berapa   Anggaran Tender? "),
                         cari_memori.kunci_pertanyaan("berapa anggaran tender"))
        self.assertEqual(cari_memori.kunci_pertanyaan("   "), "")


class Rapikan(unittest.TestCase):
    def test_item_kehilangan_awalan_metadata(self):
        mentah = {"item": [{"jenis": "pelajaran", "id": "L-1", "skor": 0.9, "bendera": ["belum_ditinjau"],
                            "teks": "[pelajaran L-1 · aturan · keyakinan 0.80 · lingkup global] "
                                    "Selalu cek HPS dulu | Pemicu: tender | Tindakan: buka RAB"}],
                  "pointer": []}
        baris = cari_memori.rapikan_hasil(mentah)
        self.assertEqual(baris[0]["ringkas"], "Selalu cek HPS dulu")
        self.assertIn("pelajaran L-1", baris[0]["kutipan"])
        self.assertIsNone(baris[0]["id_episode"])
        self.assertEqual(baris[0]["bendera"], ["belum_ditinjau"])

    def test_pointer_episode_membawa_id_episode(self):
        mentah = {"item": [], "pointer": [{"jenis": "episode", "id": "ep-1", "ringkas": "rapat", "skor": 0.5}]}
        baris = cari_memori.rapikan_hasil(mentah)
        self.assertEqual(baris[0]["id_episode"], "ep-1")

    def test_kutipan_dibatasi_panjangnya(self):
        mentah = {"item": [{"jenis": "norma", "id": "N-1", "teks": "x" * 900, "skor": 0.4}], "pointer": []}
        baris = cari_memori.rapikan_hasil(mentah)
        self.assertLessEqual(len(baris[0]["kutipan"]), cari_memori.PANJANG_KUTIPAN + 1)

    def test_maks_membatasi_jumlah_baris(self):
        mentah = {"item": [], "pointer": [{"jenis": "episode", "id": f"ep-{i}", "ringkas": "a", "skor": 0.4}
                                          for i in range(10)]}
        self.assertEqual(len(cari_memori.rapikan_hasil(mentah, maks=3)), 3)


class CariNyata(Dasar):
    def test_menemukan_episode_dengan_tanggal_dan_id(self):
        ep = self._episode()
        jawab = cari_memori.cari(RINGKAS, gerbang=self.gerbang, store=self.store)
        self.assertEqual(jawab["sumber"], "gerbang")
        ids = [h["id_episode"] for h in jawab["hasil"]]
        self.assertIn(ep.id, ids)
        baris = [h for h in jawab["hasil"] if h["id_episode"] == ep.id][0]
        self.assertEqual(baris["tanggal"], ep.waktu[:10])
        self.assertTrue(baris["kutipan"])

    def test_store_kosong_memberi_pesan_ramah(self):
        jawab = cari_memori.cari("apa saja", gerbang=self.gerbang, store=self.store)
        self.assertEqual(jawab["hasil"], [])
        self.assertIn("Belum ada memori", jawab["pesan"])
        self.assertNotEqual(jawab["sumber"], "galat")

    def test_ada_memori_tapi_tak_cocok(self):
        self._episode()
        jawab = cari_memori.cari("perkara yang sama sekali lain", gerbang=self.gerbang, store=self.store)
        self.assertEqual(jawab["hasil"], [])
        self.assertIn("Tidak ada memori", jawab["pesan"])

    def test_pertanyaan_kosong_tidak_menyentuh_gerbang(self):
        jawab = cari_memori.cari("   ", gerbang=_GerbangGagal(AssertionError("tidak boleh dipanggil")))
        self.assertEqual(jawab["sumber"], "kosong")
        self.assertEqual(jawab["hasil"], [])


class Riwayat(Dasar):
    def test_pertanyaan_berulang_dijawab_dari_riwayat(self):
        self._episode()
        pertama = cari_memori.cari(RINGKAS, gerbang=self.gerbang, store=self.store)
        self.assertEqual(pertama["sumber"], "gerbang")
        # gerbang diganti yang selalu gagal: kalau dihitung ulang, uji ini jatuh
        kedua = cari_memori.cari(RINGKAS.upper() + " ?", gerbang=_GerbangGagal(RuntimeError("dihitung ulang")))
        self.assertEqual(kedua["sumber"], "riwayat")
        self.assertEqual(kedua["hasil"], pertama["hasil"])

    def test_riwayat_basi_dihitung_ulang(self):
        self._episode()
        cari_memori.cari(RINGKAS, gerbang=self.gerbang, store=self.store)
        entri = cari_memori.muat_riwayat()
        entri[0]["waktu"] = "2020-01-01T00:00:00+00:00"
        cari_memori.simpan_riwayat(entri)
        self.assertIsNone(cari_memori.ambil_dari_riwayat(RINGKAS))

    def test_riwayat_rusak_jatuh_ke_kosong(self):
        with open(os.path.join(self.dir, cari_memori.BERKAS_RIWAYAT), "w", encoding="utf-8") as f:
            f.write("{bukan json")
        self.assertEqual(cari_memori.muat_riwayat(), [])

    def test_riwayat_dipangkas_dan_tanpa_duplikat(self):
        for i in range(cari_memori.MAKS_RIWAYAT + 5):
            cari_memori.catat_riwayat(f"pertanyaan {i}", [])
        cari_memori.catat_riwayat("pertanyaan 0", [])
        daftar = cari_memori.muat_riwayat()
        self.assertEqual(len(daftar), cari_memori.MAKS_RIWAYAT)
        self.assertEqual(daftar[0]["kunci"], "pertanyaan 0")
        self.assertEqual(sum(1 for e in daftar if e["kunci"] == "pertanyaan 0"), 1)

    def test_hapus_riwayat(self):
        cari_memori.catat_riwayat("apa pun", [])
        cari_memori.hapus_riwayat()
        self.assertEqual(cari_memori.muat_riwayat(), [])


class KeadaanBuruk(Dasar):
    def test_ollama_mati_tidak_melempar(self):
        jawab = cari_memori.cari("apa pun", gerbang=_GerbangGagal(urllib.error.URLError("tak nyambung")))
        self.assertEqual(jawab["sumber"], "galat")
        self.assertEqual(jawab["hasil"], [])
        self.assertIn("Ollama", jawab["pesan"])

    def test_identitas_embedder_menyarankan_bangun_ulang(self):
        galat = IdentitasEmbedderTidakCocok("koleksi 'isi' dibangun dengan model lain")
        jawab = cari_memori.cari("apa pun", gerbang=_GerbangGagal(galat))
        self.assertIn("bangun-ulang-vektor", jawab["pesan"])
        self.assertEqual(jawab["hasil"], [])

    def test_galat_tak_dikenal_tetap_ramah(self):
        jawab = cari_memori.cari("apa pun", gerbang=_GerbangGagal(ValueError("aneh")))
        self.assertEqual(jawab["pesan"], cari_memori.PESAN["umum"])

    def test_galat_tidak_masuk_riwayat(self):
        cari_memori.cari("apa pun", gerbang=_GerbangGagal(ValueError("aneh")))
        self.assertEqual(cari_memori.muat_riwayat(), [])


class LewatHTTP(Dasar):
    def _pembuka(self, data):
        def buka(req, timeout=None):
            self.permintaan = req
            return _Balas(data)
        return buka

    def test_cari_memakai_endpoint_ingat(self):
        data = {"item": [{"jenis": "pelajaran", "id": "L-9", "teks": "[pelajaran L-9 · aturan] Cek dulu", "skor": 0.7}],
                "pointer": []}
        jawab = cari_memori.cari("cek dulu", host="http://127.0.0.1:8765", token="rahasia",
                                 pembuka=self._pembuka(data))
        self.assertEqual(jawab["sumber"], "http")
        self.assertEqual(jawab["hasil"][0]["id"], "L-9")
        self.assertEqual(self.permintaan.full_url, "http://127.0.0.1:8765/ingat")
        self.assertEqual(self.permintaan.get_header("Authorization"), "Bearer rahasia")

    def test_token_ditolak_memberi_pesan_token(self):
        def buka(req, timeout=None):
            raise urllib.error.HTTPError("http://127.0.0.1:8765/ingat", 401, "Unauthorized", {}, None)

        jawab = cari_memori.cari("apa pun", host="http://127.0.0.1:8765", token="salah", pembuka=buka)
        self.assertEqual(jawab["pesan"], cari_memori.PESAN["token_ditolak"])

    def test_server_mati_memberi_pesan_server(self):
        def buka(req, timeout=None):
            raise urllib.error.HTTPError("http://127.0.0.1:8765/ingat", 500, "boom", {}, None)

        jawab = cari_memori.cari("apa pun", host="http://127.0.0.1:8765", token="x", pembuka=buka)
        self.assertEqual(jawab["pesan"], cari_memori.PESAN["server_mati"])


class _GerbangTiruan:
    """Gerbang palsu yang selalu mengembalikan `jumlah` item dan menghitung pemanggilan."""

    def __init__(self, jumlah=15):
        self.jumlah = jumlah
        self.panggil = 0

    def ingat(self, *a, **k):
        self.panggil += 1
        return {"item": [{"jenis": "pelajaran", "id": f"L-{i}", "skor": 0.5,
                          "teks": f"[pelajaran L-{i} · aturan] baris ke-{i}"} for i in range(self.jumlah)],
                "pointer": []}


class RiwayatTidakMenutupiMemoriBaru(Dasar):
    def test_episode_baru_membatalkan_entri_riwayat(self):
        kosong = cari_memori.cari(RINGKAS, gerbang=self.gerbang, store=self.store)
        self.assertEqual(kosong["hasil"], [])
        ep = self._episode()
        lagi = cari_memori.cari(RINGKAS, gerbang=self.gerbang, store=self.store)
        self.assertEqual(lagi["sumber"], "gerbang")
        self.assertIn(ep.id, [h["id_episode"] for h in lagi["hasil"]])

    def test_pelajaran_baru_membatalkan_entri_riwayat(self):
        g = _GerbangTiruan(jumlah=1)
        cari_memori.cari(RINGKAS, gerbang=g, store=self.store)
        self.store.simpan_pelajaran(skema.Pelajaran(id="L-baru", pelajaran="cek HPS dulu", pemicu="tender",
                                                    tindakan="buka RAB", lingkup="global", status="aturan"))
        lagi = cari_memori.cari(RINGKAS, gerbang=g, store=self.store)
        self.assertEqual(lagi["sumber"], "gerbang")
        self.assertEqual(g.panggil, 2)

    def test_store_tak_berubah_tetap_hemat_lewat_riwayat(self):
        self._episode()
        pertama = cari_memori.cari(RINGKAS, gerbang=self.gerbang, store=self.store)
        self.assertEqual(pertama["sumber"], "gerbang")
        kedua = cari_memori.cari(RINGKAS.upper() + " ?", store=self.store,
                                 gerbang=_GerbangGagal(RuntimeError("tidak boleh dihitung ulang")))
        self.assertEqual(kedua["sumber"], "riwayat")
        self.assertEqual(kedua["hasil"], pertama["hasil"])


class PesanJalurRiwayat(Dasar):
    def test_store_kosong_tetap_berpesan_store_kosong(self):
        pertama = cari_memori.cari("apa saja", gerbang=self.gerbang, store=self.store)
        self.assertEqual(pertama["pesan"], cari_memori.PESAN["store_kosong"])
        kedua = cari_memori.cari("apa saja", store=self.store,
                                 gerbang=_GerbangGagal(RuntimeError("tidak boleh dihitung ulang")))
        self.assertEqual(kedua["sumber"], "riwayat")
        self.assertEqual(kedua["pesan"], cari_memori.PESAN["store_kosong"])

    def test_ada_memori_tapi_tak_cocok_tetap_berpesan_tanpa_hasil(self):
        self._episode()
        pertama = cari_memori.cari("perkara yang sama sekali lain", gerbang=self.gerbang, store=self.store)
        self.assertEqual(pertama["pesan"], cari_memori.PESAN["tanpa_hasil"])
        kedua = cari_memori.cari("perkara yang sama sekali lain", gerbang=self.gerbang, store=self.store)
        self.assertEqual(kedua["sumber"], "riwayat")
        self.assertEqual(kedua["pesan"], cari_memori.PESAN["tanpa_hasil"])


class MaksPadaRiwayat(Dasar):
    def test_minta_lebih_banyak_dihitung_ulang(self):
        g = _GerbangTiruan(jumlah=15)
        tiga = cari_memori.cari(RINGKAS, gerbang=g, store=self.store, maks=3)
        self.assertEqual(len(tiga["hasil"]), 3)
        banyak = cari_memori.cari(RINGKAS, gerbang=g, store=self.store, maks=20)
        self.assertEqual(banyak["sumber"], "gerbang")
        self.assertEqual(len(banyak["hasil"]), 15)
        self.assertEqual(g.panggil, 2)

    def test_minta_lebih_sedikit_tetap_dari_riwayat(self):
        g = _GerbangTiruan(jumlah=15)
        cari_memori.cari(RINGKAS, gerbang=g, store=self.store, maks=8)
        dua = cari_memori.cari(RINGKAS, gerbang=g, store=self.store, maks=2)
        self.assertEqual(dua["sumber"], "riwayat")
        self.assertEqual(len(dua["hasil"]), 2)
        self.assertEqual(g.panggil, 1)


class SkorPointer(unittest.TestCase):
    def test_pointer_tanpa_skor_tidak_dipalsukan_nol(self):
        mentah = {"item": [], "pointer": [{"jenis": "pelajaran", "id": "L-7", "ringkas": "cek HPS", "bendera": []}]}
        baris = cari_memori.rapikan_hasil(mentah)
        self.assertIsNone(baris[0]["skor"])

    def test_pointer_berskor_tetap_membawa_nilainya(self):
        mentah = {"item": [], "pointer": [{"jenis": "episode", "id": "ep-1", "ringkas": "rapat", "skor": 0.42}]}
        self.assertEqual(cari_memori.rapikan_hasil(mentah)[0]["skor"], 0.42)


class SkorPointerNyata(Dasar):
    def test_pointer_luapan_anggaran_tidak_semuanya_nol(self):
        for i in range(6):
            self.store.simpan_pelajaran(skema.Pelajaran(id=f"L-{i}", pelajaran=f"{RINGKAS} catatan {i}",
                                                        pemicu="tender", tindakan="buka RAB", lingkup="global",
                                                        status="aturan", keyakinan=0.8, ditinjau_manusia=True))
        gerbang = Gateway(self.store, {"anggaran_tarik": 40})
        jawab = cari_memori.cari(RINGKAS, gerbang=gerbang, store=self.store, maks=20)
        self.assertTrue(jawab["hasil"])
        # pointer luapan anggaran tidak membawa skor dari Gateway; 0.0 akan membuat hasil
        # peringkat teratas tampak tak relevan, jadi yang benar adalah "tidak diketahui"
        self.assertNotIn(0.0, [h["skor"] for h in jawab["hasil"]])
        self.assertIn(None, [h["skor"] for h in jawab["hasil"]])


if __name__ == "__main__":
    unittest.main()
