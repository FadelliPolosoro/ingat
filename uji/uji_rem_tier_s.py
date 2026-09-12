# SPDX-License-Identifier: Apache-2.0
"""K28 — empat rem wajib untuk orkestrasi tier S ke model lokal.

Yang dijaga uji ini, berurutan dari yang paling penting:

1. **Gagal-tertutup.** Tanpa blok `rem_tier_s`, perilaku sama persis seperti sebelum K28:
   tier S tidak pernah sampai ke penyedia mana pun. Satu rem hilang = tertutup lagi.
2. **Ruang lingkup sempit.** Yang dilonggarkan hanya jalur `konsolidasi`. Jalur umum
   (`/tanya`, endpoint `/penyedia`) tetap tertutup walau semua rem lengkap.
3. **Lokal diverifikasi dari alamat, bukan dari nama.** Penyedia bernama "lokal" yang
   base_url-nya cloud tetap ditolak — kalau tidak, rem 1 bisa dilewati dengan menamai ulang.
4. **P11 abstraksi bukan penyamaran** — ditegakkan pada KELUARAN model, bukan masukan.
"""
from __future__ import annotations

import datetime as dt
import os
import shutil
import tempfile
import unittest

from ingat.gate import Gate, GateDitolak
from ingat.konsolidasi import Konsolidator
from ingat.obsidian import Vault
from ingat.rem import RemTierS, alamat_lokal, periksa_abstraksi
from ingat.simpan import Store
from ingat.vektor import PenyematLokal

FP = "proyek:fp-dashboard"

REM_LENGKAP = {"aktif": True, "penyedia": ["lokal"], "anggaran_token_harian": 10_000, "penjaga": "Fadelli"}


class PenyediaPalsu:
    """Bentuknya sama dengan PenyediaOpenAICompat sejauh yang dibaca gate/konsolidasi."""

    def __init__(self, jawaban: str = "{}", base_url: str = "http://ollama:11434/v1"):
        self.base_url = base_url
        self.jawaban = jawaban
        self.dipanggil = 0

    def tanya(self, sistem: str, pesan: str, maks_token: int = 1024, suhu: float = 0.2) -> str:
        self.dipanggil += 1
        return self.jawaban


def gate_dengan(rem: dict | None, penyedia: dict | None = None) -> Gate:
    return Gate({"P": ["claude"], "I": ["lokal"]}, rem, penyedia if penyedia is not None else {"lokal": PenyediaPalsu()})


class GagalTertutup(unittest.TestCase):
    """Setiap rem yang hilang harus menutup gate lagi. Ini inti keamanan K28."""

    def test_tanpa_blok_rem_tier_s_perilaku_sama_seperti_sebelum_k28(self):
        g = gate_dengan(None)
        self.assertEqual(g.izin("S"), [])
        self.assertEqual(g.izin("S", jalur="konsolidasi"), [])
        self.assertIsNone(g.pilih("S", {"lokal": PenyediaPalsu()}, jalur="konsolidasi"))

    def test_konfigurasi_lama_gaya_gate_s_tidak_membuka_apa_pun(self):
        """Regresi: `gate.S` diisi manual (gaya lama) tidak boleh jadi pintu belakang."""
        g = Gate({"P": ["claude"], "I": ["lokal"], "S": ["claude", "lokal"]}, None, {"lokal": PenyediaPalsu()})
        self.assertEqual(g.izin("S"), [])
        self.assertEqual(g.izin("S", jalur="konsolidasi"), [])

    def test_rem4_tanpa_penjaga_manusia_tertutup(self):
        g = gate_dengan({**REM_LENGKAP, "penjaga": ""})
        self.assertEqual(g.izin("S", jalur="konsolidasi"), [])
        self.assertIn("penjaga", g.rem.alasan_tertutup())

    def test_rem4_sakelar_mati_tertutup(self):
        g = gate_dengan({**REM_LENGKAP, "aktif": False})
        self.assertEqual(g.izin("S", jalur="konsolidasi"), [])

    def test_rem3_tanpa_anggaran_harian_tertutup(self):
        g = gate_dengan({**REM_LENGKAP, "anggaran_token_harian": 0})
        self.assertEqual(g.izin("S", jalur="konsolidasi"), [])
        self.assertIn("anggaran", g.rem.alasan_tertutup())

    def test_rem1_penyedia_tidak_terdaftar_tertutup(self):
        g = gate_dengan({**REM_LENGKAP, "penyedia": []})
        self.assertEqual(g.izin("S", jalur="konsolidasi"), [])

    def test_rem1_penyedia_bernama_lokal_tapi_alamatnya_cloud_ditolak(self):
        """Rem 1 diverifikasi dari base_url, bukan dari nama — kalau tidak, cukup menamai ulang untuk lolos."""
        g = gate_dengan(REM_LENGKAP, {"lokal": PenyediaPalsu(base_url="https://api.deepseek.com/v1")})
        self.assertEqual(g.izin("S", jalur="konsolidasi"), [])
        self.assertIn("bukan alamat lokal", g.rem.alasan_tertutup())

    def test_rem1_penyedia_belum_terkonfigurasi_tertutup(self):
        g = gate_dengan(REM_LENGKAP, {})
        self.assertEqual(g.izin("S", jalur="konsolidasi"), [])

    def test_semua_rem_lengkap_baru_terbuka_dan_hanya_di_jalur_konsolidasi(self):
        g = gate_dengan(REM_LENGKAP)
        self.assertEqual(g.izin("S", jalur="konsolidasi"), ["lokal"])
        self.assertEqual(g.izin("S"), [], "jalur umum (/tanya) tetap tertutup — K28 hanya melonggarkan konsolidasi")
        self.assertIsNone(g.pilih("S", {"lokal": PenyediaPalsu()}), "pilih() default jalur umum harus tetap None")
        self.assertEqual(g.pilih("S", {"lokal": PenyediaPalsu()}, jalur="konsolidasi"), "lokal")

    def test_wajib_tetap_menolak_tier_s_di_jalur_umum(self):
        """`Aplikasi.tanya` memakai wajib() — passthrough chat tier S tetap haram walau rem lengkap."""
        g = gate_dengan(REM_LENGKAP)
        with self.assertRaises(GateDitolak):
            g.wajib("lokal", "S")

    def test_tier_p_dan_i_tidak_terpengaruh_k28(self):
        g = gate_dengan(REM_LENGKAP)
        self.assertEqual(g.izin("P"), ["claude"])
        self.assertEqual(g.izin("I"), ["lokal"])


class AlamatLokal(unittest.TestCase):
    def test_alamat_yang_dianggap_lokal(self):
        for u in ("http://127.0.0.1:11434/v1", "http://localhost:11434", "http://[::1]:8000/v1",
                  "http://ollama:11434/v1", "http://192.168.1.10:11434", "http://10.0.0.5:8000",
                  "http://172.16.0.9:8000", "http://vllm.internal:8000/v1"):
            with self.subTest(u=u):
                self.assertTrue(alamat_lokal(u), f"{u} seharusnya lokal")

    def test_alamat_yang_ditolak(self):
        for u in ("https://api.deepseek.com/v1", "https://api.openai.com/v1", "http://8.8.8.8:11434",
                  "https://generativelanguage.googleapis.com/v1beta/openai/", "", "bukan-url", "http://"):
            with self.subTest(u=u):
                self.assertFalse(alamat_lokal(u), f"{u} tidak boleh dianggap lokal")


class AbstraksiP11(unittest.TestCase):
    """P11 — 'abstraksi bukan penyamaran'. Ditegakkan pada KELUARAN model lokal.

    Model lokal boleh MELIHAT tier S (tidak keluar mesin, itu inti K28). Yang dijaga adalah
    apa yang ia HASILKAN: pelajaran harus naik ke tingkat abstraksi yang bisa ditransfer (P8),
    bukan menyalin ulang atau sekadar menutupi angka.
    """

    SUMBER = ("Slip gaji karyawan Budi Santoso NIK 3174091208900007 dengan NPWP 09.254.294.3-407.000 "
              "ditolak sistem payroll karena rekening 1234567890123 salah ketik dua digit terakhir.")

    def test_keluaran_abstrak_lolos(self):
        keluar = ("Validasi nomor identitas hendaknya dilakukan sebelum berkas dikirim ke sistem hilir; "
                  "kesalahan ketik pada digit akhir tidak terdeteksi tanpa checksum.")
        lolos, alasan = periksa_abstraksi(keluar, self.SUMBER)
        self.assertTrue(lolos, alasan)

    def test_keluaran_membawa_nik_ditolak(self):
        lolos, alasan = periksa_abstraksi("Pastikan NIK 3174091208900007 diperiksa ulang.", self.SUMBER)
        self.assertFalse(lolos)
        self.assertIn("nik", alasan)

    def test_keluaran_membawa_kata_kunci_sensitif_ditolak(self):
        lolos, alasan = periksa_abstraksi("Periksa slip gaji sebelum unggah.", self.SUMBER)
        self.assertFalse(lolos)

    def test_keluaran_membawa_deret_angka_panjang_ditolak(self):
        lolos, alasan = periksa_abstraksi("Nomor rujukan 1234567890123 perlu dicek.", self.SUMBER)
        self.assertFalse(lolos)

    def test_salinan_verbatim_ditolak_walau_angkanya_dibuang(self):
        """Inti 'bukan penyamaran': menyalin kalimat sumber lalu menghapus angkanya BUKAN abstraksi."""
        keluar = "Slip gaji karyawan Budi Santoso dengan NPWP ditolak sistem karena rekening salah ketik dua digit terakhir."
        lolos, alasan = periksa_abstraksi(keluar, self.SUMBER)
        self.assertFalse(lolos)
        self.assertIn("verbatim", alasan)

    def test_keluaran_kosong_ditolak(self):
        lolos, _ = periksa_abstraksi("   ", self.SUMBER)
        self.assertFalse(lolos)


class AnggaranHarian(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ingat-rem-")
        self.store = Store(os.path.join(self.dir, "data"), PenyematLokal())
        self.rem = RemTierS(REM_LENGKAP, {"lokal": PenyediaPalsu()})

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_anggaran_kosong_di_awal_hari(self):
        self.assertEqual(self.rem.terpakai_hari_ini(self.store), 0)
        self.assertTrue(self.rem.ada_anggaran(self.store, 500))

    def test_pemakaian_terakumulasi_dan_menutup_saat_lewat(self):
        self.rem.catat_pemakaian(self.store, 6_000, "lokal")
        self.assertEqual(self.rem.terpakai_hari_ini(self.store), 6_000)
        self.assertTrue(self.rem.ada_anggaran(self.store, 3_000))
        self.assertFalse(self.rem.ada_anggaran(self.store, 5_000), "6.000 + 5.000 > 10.000 → harus ditolak")

    def test_pemakaian_hari_lain_tidak_dihitung(self):
        kemarin = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)).isoformat(timespec="seconds")
        self.store.db.execute("INSERT INTO metrik(waktu,nama,nilai,konteks) VALUES(?,?,?,?)",
                              (kemarin, "rem_tier_s_token", 9_999.0, "{}"))
        self.store.db.commit()
        self.assertEqual(self.rem.terpakai_hari_ini(self.store), 0, "anggaran harian harus me-reset per hari UTC")


class KonfigurasiYangDikirim(unittest.TestCase):
    """Penjaga paling penting: berkas yang BENAR-BENAR kami kirim harus gagal-tertutup."""

    def test_konfigurasi_contoh_tidak_membuka_tier_s(self):
        import json

        akar = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(akar, "konfigurasi.contoh.json"), encoding="utf-8") as f:
            contoh = json.load(f)
        rem = RemTierS(contoh.get("rem_tier_s"), {"lokal": PenyediaPalsu()})
        self.assertFalse(rem.terbuka(), "konfigurasi contoh tidak boleh mengirimkan tier S dalam keadaan terbuka")
        self.assertEqual(rem.penyedia_diizinkan(), [])

    def test_kunci_catatan_tidak_merobohkan_rem(self):
        rem = RemTierS({"_catatan": "teks untuk manusia", **REM_LENGKAP}, {"lokal": PenyediaPalsu()})
        self.assertTrue(rem.terbuka(), "kunci `_catatan` harus diabaikan, bukan meledak")


class KonsolidasiTierS(unittest.TestCase):
    """Rem 2, 3, 4 di jalur nyata: episode tier S → sintesis model lokal → pelajaran."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ingat-rem-kons-")
        self.store = Store(os.path.join(self.dir, "data"), PenyematLokal())
        self.vault = Vault(os.path.join(self.dir, "vault"))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def bangun(self, rem: dict | None, jawaban: str):
        pen = {"lokal": PenyediaPalsu(jawaban)}
        gate = Gate({"P": [], "I": ["lokal"]}, rem, pen)
        return Konsolidator(self.store, gate, pen, self.vault, {"hari_dingin": 30}), pen["lokal"]

    def episode_s(self, ringkas: str, sesi: str = "s1"):
        return self.store.tambah_episode(f"[verbatim] {ringkas}", sumber="uji", tier="S", lingkup=FP,
                                         jenis_kejadian="koreksi", ringkas=ringkas, instrumen=["x"], sesi=sesi)

    def test_tanpa_rem_episode_tier_s_tidak_ikut_dikonsolidasi(self):
        self.episode_s("payroll ditolak karena rekening salah ketik")
        kons, pen = self.bangun(None, "{}")
        lap = kons.jalankan()
        self.assertEqual(lap["episode"], 0, "tanpa rem K28, episode tier S tidak boleh diambil sama sekali")
        self.assertEqual(pen.dipanggil, 0, "model lokal tidak boleh dipanggil untuk tier S tanpa rem")

    def test_dengan_rem_lengkap_episode_tier_s_ikut_dan_model_lokal_dipakai(self):
        self.episode_s("payroll ditolak karena rekening salah ketik")
        jawaban = ('{"pelajaran": "Data bernomor identitas perlu diverifikasi checksum sebelum dikirim hilir.",'
                   ' "pemicu": "Akan mengirim berkas berisi nomor identitas ke sistem lain.",'
                   ' "tindakan": "Jalankan verifikasi format dan checksum lebih dulu."}')
        kons, pen = self.bangun(REM_LENGKAP, jawaban)
        lap = kons.jalankan()
        self.assertEqual(lap["episode"], 1)
        self.assertEqual(pen.dipanggil, 1, "model lokal harus dipakai saat keempat rem terpasang")
        p = self.store.pelajaran_semua()[0]
        self.assertEqual(p.tier_maks, "S")
        self.assertTrue(p.sintesis.startswith("llm:"), f"sintesis={p.sintesis}")

    def test_rem4_pelajaran_dari_tier_s_tidak_pernah_naik_otomatis_ke_usulan(self):
        """Bobot koreksi = 5 = AMBANG_USULAN. Untuk P/I ini naik otomatis; untuk S manusia wajib menilai."""
        self.episode_s("payroll ditolak karena rekening salah ketik")
        jawaban = ('{"pelajaran": "Data bernomor identitas perlu diverifikasi checksum sebelum dikirim hilir.",'
                   ' "pemicu": "Akan mengirim berkas berisi nomor identitas ke sistem lain.",'
                   ' "tindakan": "Jalankan verifikasi format dan checksum lebih dulu."}')
        kons, _ = self.bangun(REM_LENGKAP, jawaban)
        lap = kons.jalankan()
        p = self.store.pelajaran_semua()[0]
        self.assertEqual(p.status, "hipotesis", "rem 4: pelajaran turunan tier S menunggu manusia, tidak naik sendiri")
        self.assertEqual(lap["usulan_baru"], 0)
        self.assertTrue(p.tinjau_ulang, "harus ditandai supaya muncul di antrean tanya manusia")

    def test_rem2_keluaran_tidak_abstrak_ditolak_dan_jatuh_ke_heuristik(self):
        self.episode_s("payroll ditolak karena rekening 1234567890123 salah ketik")
        bocor = ('{"pelajaran": "Rekening 1234567890123 salah ketik dua digit terakhir.",'
                 ' "pemicu": "payroll ditolak", "tindakan": "Perbaiki rekening 1234567890123."}')
        kons, pen = self.bangun(REM_LENGKAP, bocor)
        kons.jalankan()
        p = self.store.pelajaran_semua()[0]
        self.assertEqual(pen.dipanggil, 1)
        self.assertEqual(p.sintesis, "heuristik", "keluaran gagal P11 harus dibuang, bukan disimpan")
        self.assertNotIn("1234567890123", p.pelajaran + p.pemicu + p.tindakan)

    def test_rem3_anggaran_habis_menutup_sintesis_llm(self):
        self.episode_s("payroll ditolak karena rekening salah ketik")
        kons, pen = self.bangun({**REM_LENGKAP, "anggaran_token_harian": 10}, "{}")
        kons.jalankan()
        self.assertEqual(pen.dipanggil, 0, "anggaran harian habis → model lokal tidak boleh dipanggil sama sekali")


if __name__ == "__main__":
    unittest.main()
