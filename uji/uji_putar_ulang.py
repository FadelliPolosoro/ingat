# SPDX-License-Identifier: Apache-2.0
"""Uji penerimaan putar-ulang (Bab 12 spek) — berjalan offline, tanpa penyedia LLM.

Kasus U1–U5 diambil dari kesalahan nyata proyek; U6 memakai norma FIKTIF
(nr-uji-*) supaya tidak ada tanggal hukum yang dikarang di dalam fixture.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest

from ingat import frontmatter, skema
from ingat.gate import Gate
from ingat.gateway import Gateway
from ingat.konsolidasi import Konsolidator
from ingat.vault import Vault
from ingat.simpan import Store
from ingat.vektor import PenyematLokal

FP, GAR = "proyek:fp-dashboard", "proyek:garnivo"


def _tulis(path: str, meta: dict, badan: str = ""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(frontmatter.dump(meta, badan))


class Dasar(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ingat-uji-")
        self.store = Store(os.path.join(self.dir, "data"), PenyematLokal())
        self.vault = Vault(os.path.join(self.dir, "vault"))
        self.gate = Gate({"P": [], "I": []})
        self.kons = Konsolidator(self.store, self.gate, {}, self.vault)
        self.gw = Gateway(self.store)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def setujui_usulan(self, jenis: str):
        """Simulasi manusia: pindahkan semua berkas _usulan/ ke folder induk lalu sinkron."""
        src = os.path.join(self.vault.path, jenis, "_usulan")
        for nama in os.listdir(src):
            shutil.move(os.path.join(src, nama), os.path.join(self.vault.path, jenis, nama))
        return self.vault.sinkron(self.store)

    def episode(self, ringkas, lingkup, jenis="koreksi", instrumen=(), langkah=(), sesi="s1", tier="P"):
        return self.store.tambah_episode(f"[verbatim] {ringkas}\n" + "detail " * 40, sumber="uji", tier=tier, lingkup=lingkup,
                                         jenis_kejadian=jenis, ringkas=ringkas, instrumen=list(instrumen), langkah=list(langkah), sesi=sesi)


class U1_TitikButaInstrumen(Dasar):
    def test_pelajaran_menyala_sebelum_kesimpulan_salah(self):
        self.episode("Menyimpulkan tidak ada beban kerja di VPS karena tool VPS_getProjectListV1 mengembalikan daftar kosong; "
                     "ternyata deploy manual via SSH tidak terlihat oleh tool itu", FP, instrumen=["hostinger-mcp"])
        lap = self.kons.jalankan()
        self.assertEqual(lap["usulan_baru"], 1, lap)
        self.assertEqual(self.setujui_usulan("pelajaran")["galat"], [])
        aturan = self.store.pelajaran_semua(("aturan",))
        self.assertEqual(len(aturan), 1)
        self.assertTrue(aturan[0].ditinjau_manusia)
        hasil = self.gw.ingat("tool mengembalikan daftar kosong, hendak menyimpulkan tidak ada beban kerja di VPS", FP)
        self.assertIn(aturan[0].id, [i["id"] for i in hasil["item"]], hasil)
        startup = self.gw.muat_startup(FP)
        self.assertTrue(any(aturan[0].id in a for a in startup["aturan"]))
        # R8: episode masih aktif setelah konsolidasi pertama; didinginkan pada run berikutnya setelah induk disetujui
        self.assertEqual(self.store.episode_semua()[0].status, "aktif")
        self.assertGreaterEqual(self.kons.jalankan()["didinginkan"], 1)
        ep = self.store.episode_semua()[0]
        self.assertEqual(ep.status, "didinginkan")
        self.assertIn("verbatim", self.gw.buka_bukti(ep.id)["isi"])


class U2_VerifikasiBerkasSebelumKlaimSelesai(Dasar):
    def test_prosedur_cocok_tugas(self):
        _tulis(os.path.join(self.vault.path, "prosedur", "pr-u2.md"), {
            "id": "pr-u2", "prosedur": "Verifikasi keberadaan berkas di disk sebelum melaporkan selesai",
            "tugas_pemicu": "melaporkan berkas selesai ditulis ke disk", "lingkup": "global",
            "langkah": ["tulis berkas", "jalankan test -f <path> atau Test-Path di PowerShell", "baru laporkan selesai"],
            "uji": "test -f <path>", "status": "aktif"})
        self.assertEqual(self.vault.sinkron(self.store)["prosedur"], 1)
        hasil = self.gw.ingat("jelajah.mjs sudah selesai?", FP, tugas="melaporkan berkas jelajah.mjs selesai ditulis ke disk")
        self.assertIn("pr-u2", [i["id"] for i in hasil["item"]], hasil)
        self.assertEqual(hasil["item"][0]["jenis"], "prosedur")  # query 'cara' -> prosedur di atas pelajaran


class U3_PrasyaratVersi(Dasar):
    def test_berlaku_untuk_menyaring_l_aturan(self):
        _tulis(os.path.join(self.vault.path, "pelajaran", "pl-u3.md"), {
            "id": "pl-u3", "pelajaran": "Cek prasyarat versi pustaka sebelum integrasi komponen UI",
            "pemicu": "Akan mengintegrasikan pustaka UI ke halaman yang versinya belum diverifikasi",
            "tindakan": "Verifikasi versi Tailwind di halaman target dulu", "lingkup": FP,
            "berlaku_untuk": {"tailwind": "3"}, "status": "aturan", "keyakinan": 0.9})
        self.vault.sinkron(self.store)
        cocok = self.gw.muat_startup(FP, lingkungan={"tailwind": "3.4"})
        self.assertTrue(any("pl-u3" in a for a in cocok["aturan"]))
        beda = self.gw.muat_startup(FP, lingkungan={"tailwind": "4.1"})
        self.assertFalse(any("pl-u3" in a for a in beda["aturan"]))
        self.assertIn("versi_berbeda", [b for p in beda["pointer"] for b in p["bendera"]])
        tarik = self.gw.ingat("integrasi pustaka UI ke halaman", FP, lingkungan={"tailwind": "4.1"})
        self.assertIn("versi_berbeda", tarik["bendera"])


class U4_ProsedurDalamLingkup(Dasar):
    def test_npm_ci_hanya_di_fp_dashboard(self):
        _tulis(os.path.join(self.vault.path, "prosedur", "pr-u4.md"), {
            "id": "pr-u4", "prosedur": "Pasang dependensi Node dengan hook pengaman aktif",
            "tugas_pemicu": "npm ci atau npm install di repo yang memakai jaga.mjs", "lingkup": FP,
            "langkah": ["npm ci --ignore-scripts", "npx playwright install chromium"], "uji": "node -e \"require('playwright')\"", "status": "aktif"})
        self.vault.sinkron(self.store)
        tugas = "pasang dependensi npm ci di repo"
        ada = self.gw.ingat("cara pasang dependensi", FP, tugas=tugas)
        self.assertIn("pr-u4", [i["id"] for i in ada["item"]], ada)
        tidak = self.gw.ingat("cara pasang dependensi", GAR, tugas=tugas)
        self.assertNotIn("pr-u4", [i["id"] for i in tidak["item"]])


class U5_LingkupNegatif(Dasar):
    def test_pelajaran_garnivo_tidak_menyala_di_fp(self):
        _tulis(os.path.join(self.vault.path, "pelajaran", "pl-u5.md"), {
            "id": "pl-u5", "pelajaran": "Metrik follows Instagram lewat Graph API selalu nol untuk post tersinkron; bukan sinyal konversi",
            "pemicu": "Akan menafsirkan metrik follows dari Graph API sebagai konversi",
            "tindakan": "Pakai metrik reach dan profile visits; abaikan follows", "lingkup": GAR, "status": "aturan", "keyakinan": 0.9})
        self.vault.sinkron(self.store)
        q = "menafsirkan metrik follows Instagram Graph API sebagai konversi"
        self.assertIn("pl-u5", [i["id"] for i in self.gw.ingat(q, GAR)["item"]])
        self.assertNotIn("pl-u5", [i["id"] for i in self.gw.ingat(q, FP)["item"]])
        self.assertFalse(any("pl-u5" in a for a in self.gw.muat_startup(FP)["aturan"]))


class U6_NormaBitemporal(Dasar):
    def setUp(self):
        super().setUp()
        _tulis(os.path.join(self.vault.path, "norma", "nr-uji-lama.md"), {
            "id": "nr-uji-lama", "norma": "Perpres Uji 1/2020", "judul": "Pengadaan barang/jasa (fiktif untuk uji)",
            "jenis": "perpres", "berlaku_sejak": "2020-01-15", "dicabut_oleh": "nr-uji-baru",
            "peralihan": "Paket yang prosesnya dimulai sebelum peraturan pengganti berlaku diselesaikan dengan peraturan ini.",
            "sumber_dokumen": "fixture"}, "Isi fiktif peraturan pengadaan lama.")
        _tulis(os.path.join(self.vault.path, "norma", "nr-uji-baru.md"), {
            "id": "nr-uji-baru", "norma": "Perpres Uji 2/2024", "judul": "Pengadaan barang/jasa (fiktif untuk uji)",
            "jenis": "perpres", "berlaku_sejak": "2024-06-01", "mengganti": ["nr-uji-lama"],
            "alasan": "Menimbang: penyederhanaan proses (fiktif)", "sumber_dokumen": "fixture"}, "Isi fiktif peraturan pengadaan baru.")
        _tulis(os.path.join(self.vault.path, "norma", "_konsolidasi", "nr-uji-konsol.md"), {
            "id": "nr-uji-konsol", "norma": "Perpres Uji (konsolidasi)", "judul": "Tampilan gabungan",
            "disusun_dari": ["nr-uji-lama", "nr-uji-baru"], "disusun_pada": "2024-07-01", "disusun_oleh": "mesin",
            "berlaku_untuk_tanggal": "2024-07-01"}, "Gabungan fiktif.")
        self.assertEqual(self.vault.sinkron(self.store)["galat"], [])

    def test_versi_lama_untuk_peristiwa_lama(self):
        lama = self.store.norma("nr-uji-lama")
        self.assertEqual(lama.status, "dicabut")
        self.assertEqual(lama.berlaku_sampai, "2024-06-01")
        hasil = self.gw.ingat("aturan pengadaan barang jasa untuk kontrak", FP, tanggal_peristiwa="2023-06-01")
        ids = [i["id"] for i in hasil["item"]]
        self.assertIn("nr-uji-lama", ids, hasil)
        self.assertNotIn("nr-uji-baru", ids)
        item = next(i for i in hasil["item"] if i["id"] == "nr-uji-lama")
        self.assertIn("versi_lama_masih_mengikat", item["bendera"])
        self.assertIn("Peralihan:", item["teks"])
        self.assertEqual(hasil["asumsi"], [])

    def test_tanpa_tanggal_versi_baru_dan_asumsi(self):
        hasil = self.gw.ingat("aturan pengadaan barang jasa untuk kontrak", FP)
        ids = [i["id"] for i in hasil["item"]]
        self.assertIn("nr-uji-baru", ids)
        self.assertNotIn("nr-uji-lama", ids)
        self.assertTrue(any("diasumsikan hari ini" in a for a in hasil["asumsi"]))
        # tampilan konsolidasi hanya untuk tanggalnya sendiri, selalu berbendera
        k = self.gw.ingat("pengadaan barang jasa konsolidasi", FP, tanggal_peristiwa="2024-07-01")
        item = next((i for i in k["item"] if i["id"] == "nr-uji-konsol"), None)
        self.assertIsNotNone(item, k)
        self.assertIn("tampilan_konsolidasi", item["bendera"])
        self.assertTrue(item["peringkat"] > next(i["peringkat"] for i in k["item"] if i["id"] == "nr-uji-baru"))


class U7_AntiSpalko(Dasar):
    def test_anggaran_ditegakkan(self):
        for i in range(1000):
            e = self.episode(f"episode dingin nomor {i} tentang hal {i % 17} pada pekerjaan {i % 5}", FP, jenis="sukses", sesi=f"s{i % 9}")
            self.store.ubah_status("episode", e.id, "didinginkan", "mesin", "uji")
        for i in range(50):
            p = skema.Pelajaran(id=f"pl-u7-{i:02d}", pelajaran=f"Aturan aktif nomor {i} tentang pekerjaan {i % 5} " + "penjelasan panjang " * 8,
                                pemicu=f"Kondisi {i} muncul", tindakan=f"Lakukan langkah {i}", lingkup=FP, status="aturan", keyakinan=0.8, ditinjau_manusia=True)
            self.store.simpan_pelajaran(p)
        s = self.gw.muat_startup(FP)
        self.assertLessEqual(s["token"]["peta"], 300)
        self.assertLessEqual(s["token"]["aturan"], 1500)
        self.assertTrue(s["pointer"], "kelebihan aturan harus jadi pointer, bukan dibuang")
        self.assertFalse(any("RAHASIA_ISI" in a or "episode dingin" in a for a in s["aturan"]))
        h = self.gw.ingat("pekerjaan 3 kondisi", FP)
        self.assertLessEqual(h["token"], h["anggaran"])
        self.assertLessEqual(len(h["item"]), 5)
        rasio = self.gw.rasio_konteks(s["token"]["total"] + h["token"], 128_000)
        self.assertFalse(rasio["alarm"])


class U8_AntiFobia(Dasar):
    def test_koreksi_tunggal_terkunci_di_lingkup_asal(self):
        self.episode("Memakai hashtag lama yang sudah pensiun pada unggahan baru Garnivo", GAR, instrumen=["zernio"])
        lap = self.kons.jalankan()
        self.assertEqual(lap["usulan_baru"], 1)
        u = self.store.pelajaran_semua(("usulan",))[0]
        self.assertEqual(u.lingkup, GAR)
        q = "memakai hashtag lama pada unggahan baru"
        di_gar = self.gw.ingat(q, GAR)
        self.assertIn(u.id, [i["id"] for i in di_gar["item"]])
        self.assertIn("belum_ditinjau", di_gar["bendera"])
        self.assertNotIn(u.id, [i["id"] for i in self.gw.ingat(q, FP)["item"]])
        # bukti kedua dari lingkup lain hanya mengusulkan perluasan, tidak melebarkan
        self.episode("Memakai hashtag lama yang sudah pensiun pada unggahan baru Cakti Media", "proyek:caktimedia", instrumen=["zernio"], sesi="s2")
        self.kons.jalankan()
        u2 = self.store.pelajaran(u.id)
        self.assertEqual(u2.lingkup, GAR)
        self.assertEqual(u2.usulan_perluasan_lingkup, "global")


class U9_Ditarik(Dasar):
    def test_ditarik_jadi_peringatan(self):
        _tulis(os.path.join(self.vault.path, "pelajaran", "pl-u9.md"), {
            "id": "pl-u9", "pelajaran": "Tidak ada proyek Hostinger berarti tidak ada beban kerja di VPS",
            "pemicu": "Daftar proyek Hostinger kosong", "tindakan": "Anggap VPS kosong", "lingkup": FP,
            "status": "aturan", "veto_manusia": "2026-09-06 — terbukti salah: deploy manual SSH tidak terlihat"})
        self.vault.sinkron(self.store)
        self.assertEqual(self.store.pelajaran("pl-u9").status, "ditarik")
        h = self.gw.ingat("daftar proyek Hostinger kosong, apakah VPS kosong?", FP)
        self.assertNotIn("pl-u9", [i["id"] for i in h["item"]])
        self.assertIn("pernah_ditarik", h["bendera"])
        self.assertTrue(any("pl-u9" == p["id"] for p in h["peringatan"]), h)


class U10_StateMachine(Dasar):
    def test_transisi_hanya_manusia_dan_terlarang(self):
        p = skema.Pelajaran(id="pl-sm", pelajaran="x", pemicu="y", tindakan="z", lingkup="global", status="hipotesis")
        self.store.simpan_pelajaran(p)
        with self.assertRaises(skema.TransisiTerlarang):
            self.store.ubah_status("pelajaran", "pl-sm", "aturan", "mesin")
        self.store.ubah_status("pelajaran", "pl-sm", "usulan", "mesin")
        with self.assertRaises(skema.TransisiTerlarang):
            self.store.ubah_status("pelajaran", "pl-sm", "aturan", "mesin")
        self.store.ubah_status("pelajaran", "pl-sm", "aturan", "manusia")
        self.assertTrue(self.store.pelajaran("pl-sm").ditinjau_manusia)
        with self.assertRaises(skema.TransisiTerlarang):
            skema.periksa_transisi("norma", "berlaku", "ditarik")
        with self.assertRaises(skema.TransisiTerlarang):
            skema.periksa_transisi("pelajaran", "aturan", "abadi", "manusia")
        self.assertEqual(len(self.store.riwayat("pelajaran", "pl-sm")), 2)


class U11_GateTierS(Dasar):
    def test_tier_s_tersimpan_dengan_pagar(self):
        """K10: tier S TERSIMPAN verbatim; pagarnya di penggunaan — tidak ke LLM, tidak muncul tanpa sertakan_S."""
        ep = self.episode("data payroll", FP, tier="S")
        self.assertEqual(ep.tier, "S")
        self.assertIsNotNone(self.store.episode(ep.id), "episode S harus tersimpan (K10)")
        with self.assertRaises(PermissionError):
            self.gw.buka_bukti(ep.id)
        self.assertIn("data payroll", self.gw.buka_bukti(ep.id, sertakan_S=True)["isi"])
        # pola sensitif menaikkan tier I → S otomatis, tanpa diredaksi
        ep2 = self.episode("NIK 3175012345678901 atas nama X", FP, tier="I")
        self.assertEqual(ep2.tier, "S")
        self.assertIn("3175012345678901", self.gw.buka_bukti(ep2.id, sertakan_S=True)["isi"])
        # episode S tidak masuk pointer ingat() tanpa sertakan_S
        tanpa = self.gw.ingat("data payroll", FP)
        self.assertFalse(any(p["id"] == ep.id for p in tanpa["pointer"]), tanpa["pointer"])
        dengan = self.gw.ingat("data payroll", FP, sertakan_S=True)
        self.assertTrue(any(p["id"] == ep.id for p in dengan["pointer"]), dengan["pointer"])
        g = Gate({"P": ["deepseek"], "I": ["lokal"], "S": ["deepseek"]})
        self.assertEqual(g.izin("S"), [])
        self.assertFalse(g.boleh("deepseek", "I"))
        self.assertTrue(g.boleh("lokal", "I"))


class U12_KontraMendominasi(Dasar):
    def test_aturan_dipersempit_saat_kontra(self):
        _tulis(os.path.join(self.vault.path, "pelajaran", "pl-u12.md"), {
            "id": "pl-u12", "pelajaran": "Modal dan toast Alpine.js gagal diam-diam bila CSP melarang unsafe-eval",
            "pemicu": "Modal atau toast Alpine.js tidak muncul tanpa galat", "tindakan": "Pakai build CSP Alpine",
            "lingkup": FP, "status": "aturan", "keyakinan": 0.8})
        self.vault.sinkron(self.store)
        for s in ("s1", "s2"):
            self.episode("Modal dan toast Alpine.js gagal diam-diam padahal CSP sudah diubah; build CSP Alpine tetap tidak muncul", FP, jenis="kegagalan", sesi=s)
        lap = self.kons.jalankan()
        self.assertGreaterEqual(lap["kontra_ditambah"], 2, lap)
        p = self.store.pelajaran("pl-u12")
        self.assertEqual(p.status, "dipersempit")
        self.assertTrue(p.tinjau_ulang)


class U13_InstrumenBaruDanKedaluwarsa(Dasar):
    def test_tinjau_ulang(self):
        e = self.episode("Menyimpulkan tidak ada beban kerja di VPS karena daftar proyek kosong", FP, instrumen=["dashboard"])
        self.kons.jalankan()
        p = self.store.pelajaran_semua(("usulan",))[0]
        hasil = self.kons.instrumen_baru(skema.Instrumen(id="hostinger-mcp", nama="Hostinger MCP",
                                                         dipasang_sejak=skema.tambah_hari(skema.hari_ini(), 1),
                                                         cakupan="melihat proyek dan beban kerja VPS Hostinger"))
        self.assertIn(p.id, hasil["tinjau_ulang"])
        p = self.store.pelajaran(p.id)
        p.tinjau_ulang = False
        p.tinjau_setelah = "2020-01-01"
        p.terakhir_dikonfirmasi = "2019-12-01"
        self.store.simpan_pelajaran(p)
        self.assertIn(p.id, self.kons.kedaluwarsa()["tinjau_ulang"])
        h = self.gw.ingat("daftar proyek kosong beban kerja VPS", FP)
        self.assertIn("tinjau_ulang", h["bendera"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
