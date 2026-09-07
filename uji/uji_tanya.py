# SPDX-License-Identifier: Apache-2.0
"""Uji konsolidasi berpandu pertanyaan (v0.5): empat jenis pertanyaan, penerapan jawaban lewat vault, dedup."""
from __future__ import annotations

import os
import re
import shutil
import tempfile
import unittest

from ingat import frontmatter, skema
from ingat.gate import Gate
from ingat.konsolidasi import Konsolidator
from ingat.obsidian import Vault
from ingat.simpan import Store
from ingat.tanya import Penanya, interval_tinjau_berikut
from ingat.vektor import PenyematLokal

FP, GAR = "proyek:fp-dashboard", "proyek:garnivo"


def _isi_jawab(path: str, nomor: int, jawaban: dict):
    """Ganti isi blok ```jawab``` pertanyaan ke-`nomor` di berkas tanya."""
    with open(path, encoding="utf-8") as f:
        teks = f.read()
    bagian = re.split(r"(?=<!-- tanya nomor=)", teks)
    for i, b in enumerate(bagian):
        if b.startswith(f"<!-- tanya nomor={nomor} "):
            baris = []
            for k, v in jawaban.items():
                if isinstance(v, dict):
                    baris.append(f"{k}: {{{', '.join(f'{a}: {frontmatter._dump_skalar(c)}' for a, c in v.items())}}}")
                else:
                    baris.append(f"{k}: {frontmatter._dump_skalar(v)}")
            bagian[i] = re.sub(r"```jawab\s*\n.*?```", "```jawab\n" + "\n".join(baris) + "\n```", b, flags=re.S)
    with open(path, "w", encoding="utf-8") as f:
        f.write("".join(bagian))


def _tulis_pelajaran(vault: Vault, meta: dict, folder: str = "pelajaran"):
    path = os.path.join(vault.path, folder, f"{meta['id']}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(frontmatter.dump(meta, "badan"))


class Dasar(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ingat-tanya-")
        self.store = Store(os.path.join(self.dir, "data"), PenyematLokal())
        self.vault = Vault(os.path.join(self.dir, "vault"))
        self.kons = Konsolidator(self.store, Gate({"P": [], "I": []}), {}, self.vault)
        self.penanya = Penanya(self.store, self.vault)
        self.hari = skema.hari_ini()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def episode(self, ringkas: str, lingkup=FP, jenis="kegagalan", sesi="s1", instrumen=("hostinger-mcp",)):
        return self.store.tambah_episode(f"[verbatim] {ringkas}", sumber="uji", tier="I", lingkup=lingkup,
                                         jenis_kejadian=jenis, ringkas=ringkas, instrumen=list(instrumen), sesi=sesi)

    def pelajaran_aturan(self, id_="pl-a", **ekstra):
        meta = {"id": id_, "jenis": "pelajaran", "pelajaran": "Ketiadaan hasil satu tool bukan ketiadaan objek",
                "pemicu": "Menyimpulkan tidak ada X dari satu tool yang kosong", "tindakan": "Cari jalur observasi kedua",
                "lingkup": FP, "status": "aturan", "keyakinan": 0.8, "bukti": [], "kontra": [], "dibuat": "2026-01-01",
                "terakhir_dikonfirmasi": "2026-01-01", "tinjau_setelah": "2026-04-01", **ekstra}
        _tulis_pelajaran(self.vault, meta)
        self.vault.sinkron(self.store)
        return meta


class Generalisasi(Dasar):
    def test_kelompok_menjadi_pertanyaan_lalu_jawaban_manusia_jadi_aturan(self):
        for s in ("s1", "s2", "s3"):
            self.episode("VPS_getProjectListV1 kosong disimpulkan tidak ada workload; deploy manual SSH tak terlihat", sesi=s)
        lap = self.kons.jalankan()
        self.assertEqual(lap["usulan_baru"], 1, lap)
        daftar = self.penanya.susun(self.hari)
        self.assertEqual([q.jenis for q in daftar], ["generalisasi"])
        q = daftar[0]
        self.assertEqual(len(q.bukti), 3)
        path = self.penanya.tulis(daftar, self.hari)
        self.assertTrue(os.path.exists(path))
        # belum dijawab → tidak ditanya dua kali
        self.assertEqual(self.penanya.susun(self.hari), [])
        _isi_jawab(path, 1, {"keputusan": "buat",
                             "pelajaran": "Ketiadaan hasil dari satu instrumen bukan ketiadaan objek",
                             "pemicu": "Akan menyimpulkan tidak ada X dari satu tool yang mengembalikan kosong",
                             "tindakan": "Cek cakupan tool; cari jalur observasi kedua", "lingkup": FP, "alasan": "koreksi nyata"})
        lap = self.penanya.jawab(path, self.hari)
        self.assertEqual(lap["dijawab"], 1, lap)
        p = self.store.pelajaran(q.id)
        self.assertEqual(p.status, "aturan")
        self.assertTrue(p.ditinjau_manusia)
        self.assertEqual(p.sintesis, "manusia")
        self.assertIn("Ketiadaan hasil dari satu instrumen", p.pelajaran)
        self.assertTrue(os.path.exists(os.path.join(self.vault.path, "pelajaran", f"{q.id}.md")))
        self.assertFalse(os.path.exists(os.path.join(self.vault.path, "pelajaran", "_usulan", f"{q.id}.md")))
        self.assertFalse(os.path.exists(path), "berkas tanya harus diarsipkan")
        self.assertTrue(os.path.exists(lap["diarsipkan_ke"]))
        with open(lap["diarsipkan_ke"], encoding="utf-8") as f:
            self.assertEqual(frontmatter.muat(f.read())[0]["status"], "selesai")
        # sudah diputuskan → tidak ditanya lagi
        self.assertEqual(self.penanya.susun(self.hari), [])

    def test_premis_salah_menarik_hipotesis_dan_mencatat_sinyal(self):
        for s in ("s1", "s2", "s3"):
            self.episode("gagal karena alasan yang sama-sama mirip tapi bukan satu hal", sesi=s)
        self.kons.jalankan()
        daftar = self.penanya.susun(self.hari)
        path = self.penanya.tulis(daftar, self.hari)
        _isi_jawab(path, 1, {"keputusan": "premis-salah", "alasan": "tiga episode ini beda penyebab"})
        self.penanya.jawab(path, self.hari)
        self.assertEqual(self.store.pelajaran(daftar[0].id).status, "ditarik")
        sinyal = self.penanya._riwayat("pengelompokan_salah")
        self.assertEqual(len(sinyal), 1)
        self.assertEqual(sinyal[0]["pelajaran"], daftar[0].id)


class Kedaluwarsa(Dasar):
    def test_interval_melebar_tiap_konfirmasi(self):
        """Distributed practice: jarak tinjau berikut = 2× sebelumnya, dibatasi 90..365 hari."""
        self.assertEqual(interval_tinjau_berikut({"terakhir_dikonfirmasi": "2026-01-01", "tinjau_setelah": "2026-04-01"}), 180)
        self.assertEqual(interval_tinjau_berikut({"terakhir_dikonfirmasi": "2026-01-01", "tinjau_setelah": "2026-01-31"}), 90)
        self.assertEqual(interval_tinjau_berikut({"terakhir_dikonfirmasi": "2025-01-01", "tinjau_setelah": "2025-12-01"}), 365)
        self.assertEqual(interval_tinjau_berikut({}), 90)
        self.pelajaran_aturan()  # interval sebelumnya 90 hari → berikutnya 180
        path = self.penanya.tulis(self.penanya.susun(self.hari), self.hari)
        _isi_jawab(path, 1, {"keputusan": "konfirmasi"})
        self.penanya.jawab(path, self.hari)
        self.assertEqual(self.store.pelajaran("pl-a").tinjau_setelah, skema.tambah_hari(self.hari, 180))

    def test_konfirmasi_menggeser_tinjau_setelah(self):
        self.pelajaran_aturan()  # tinjau_setelah 2026-04-01 < hari ini
        daftar = self.penanya.susun(self.hari)
        self.assertEqual([q.jenis for q in daftar], ["kedaluwarsa"])
        path = self.penanya.tulis(daftar, self.hari)
        _isi_jawab(path, 1, {"keputusan": "konfirmasi", "alasan": "masih dipakai"})
        self.penanya.jawab(path, self.hari)
        p = self.store.pelajaran("pl-a")
        self.assertEqual(p.status, "aturan")
        self.assertGreater(p.tinjau_setelah, self.hari)
        self.assertEqual(p.terakhir_dikonfirmasi, self.hari)
        self.assertEqual(self.penanya.susun(self.hari), [])

    def test_tarik_lewat_kedaluwarsa(self):
        self.pelajaran_aturan()
        path = self.penanya.tulis(self.penanya.susun(self.hari), self.hari)
        _isi_jawab(path, 1, {"keputusan": "tarik", "alasan": "sudah tidak relevan"})
        self.penanya.jawab(path, self.hari)
        self.assertEqual(self.store.pelajaran("pl-a").status, "ditarik")


class Konflik(Dasar):
    def test_persempit_dengan_berlaku_untuk(self):
        ep = self.episode("modal Alpine tidak muncul padahal aturan sudah diikuti")
        self.pelajaran_aturan(kontra=[ep.id], tinjau_setelah="2027-01-01")
        daftar = self.penanya.susun(self.hari)
        self.assertEqual([q.jenis for q in daftar], ["konflik"])
        self.assertTrue(any("KONTRA" in b for b in daftar[0].bukti))
        path = self.penanya.tulis(daftar, self.hari)
        _isi_jawab(path, 1, {"keputusan": "persempit", "berlaku_untuk": {"alpine": "3.x"}, "alasan": "hanya build standar"})
        self.penanya.jawab(path, self.hari)
        p = self.store.pelajaran("pl-a")
        self.assertEqual(p.status, "dipersempit")
        self.assertEqual(p.berlaku_untuk, {"alpine": "3.x"})
        self.assertFalse(p.tinjau_ulang)

    def test_tetap_tidak_ditanya_ulang_untuk_kontra_yang_sama(self):
        ep = self.episode("kontra yang salah label")
        self.pelajaran_aturan(kontra=[ep.id], tinjau_setelah="2027-01-01")
        path = self.penanya.tulis(self.penanya.susun(self.hari), self.hari)
        _isi_jawab(path, 1, {"keputusan": "tetap", "alasan": "episode salah label"})
        self.penanya.jawab(path, self.hari)
        self.assertEqual(self.store.pelajaran("pl-a").status, "aturan")
        self.assertEqual(self.penanya.susun(self.hari), [], "kontra yang sama tidak boleh ditanya lagi")
        # kontra BARU → kunci berubah → ditanya lagi
        ep2 = self.episode("kontra kedua yang berbeda", jenis="koreksi")
        p = self.store.pelajaran("pl-a")
        p.kontra = sorted(set(p.kontra) | {ep2.id})
        self.store.simpan_pelajaran(p)
        self.assertEqual([q.jenis for q in self.penanya.susun(self.hari)], ["konflik"])


class Perluasan(Dasar):
    def test_global(self):
        e1 = self.episode("bukti fp", lingkup=FP, sesi="s1")
        e2 = self.episode("bukti garnivo", lingkup=GAR, sesi="s9", instrumen=("zernio",))
        self.pelajaran_aturan(bukti=[e1.id, e2.id], usulan_perluasan_lingkup="global", tinjau_setelah="2027-01-01")
        daftar = self.penanya.susun(self.hari)
        self.assertEqual([q.jenis for q in daftar], ["perluasan"])
        path = self.penanya.tulis(daftar, self.hari)
        _isi_jawab(path, 1, {"keputusan": "global", "alasan": "independen: sesi dan instrumen beda"})
        self.penanya.jawab(path, self.hari)
        p = self.store.pelajaran("pl-a")
        self.assertEqual(p.lingkup, "global")
        self.assertFalse(p.usulan_perluasan_lingkup)
        self.assertEqual(self.penanya.susun(self.hari), [])


class AntiSugesti(Dasar):
    def test_draf_mesin_setelah_blok_jawab_dan_template_kosong(self):
        """Pertanyaan yang mengarahkan menghasilkan ingatan palsu: bukti dulu, draf mesin setelah blok jawab."""
        for s in ("s1", "s2", "s3"):
            self.episode("gagal dengan pola yang sama tiga kali", sesi=s)
        self.kons.jalankan()
        path = self.penanya.tulis(self.penanya.susun(self.hari), self.hari)
        with open(path, encoding="utf-8") as f:
            teks = f.read()
        self.assertLess(teks.index("Bukti:"), teks.index("❓"))
        self.assertLess(teks.index("```jawab"), teks.index("Draf mesin"))
        blok = re.search(r"```jawab\s*\n(.*?)```", teks, re.S).group(1)
        meta = frontmatter.muat("---\n" + blok + "\n---\n")[0]
        self.assertEqual(meta["pelajaran"], "", "template tidak boleh berisi draf mesin")
        self.assertEqual(meta["pemicu"], "")


class Interop(Dasar):
    def test_berkas_tanya_terbaca_parser_subset_tanpa_pyyaml(self):
        """Kontrak frontmatter: satu kunci per baris — berkas yang ditulis dengan PyYAML harus terbaca tanpa PyYAML."""
        self.pelajaran_aturan()
        path = self.penanya.tulis(self.penanya.susun(self.hari), self.hari)
        with open(path, encoding="utf-8") as f:
            teks = f.read()
        self.assertFalse(teks.splitlines()[1].startswith("{"), "frontmatter tidak boleh satu baris flow")
        yaml_asli = frontmatter.yaml
        try:
            frontmatter.yaml = None
            meta, _ = frontmatter.muat(teks)
            self.assertEqual(meta.get("status"), "menunggu")
            self.assertEqual(meta.get("jumlah"), 1)
            self.assertEqual(len(self.penanya._kunci_terbuka()), 1)
        finally:
            frontmatter.yaml = yaml_asli


class Penundaan(Dasar):
    def test_lewati_ditunda_lalu_ditanya_ulang_setelah_hari_tunggu(self):
        self.pelajaran_aturan()
        path = self.penanya.tulis(self.penanya.susun(self.hari), self.hari)
        _isi_jawab(path, 1, {"keputusan": "lewati"})
        lap = self.penanya.jawab(path, self.hari)
        self.assertEqual(lap["ditunda"], 1)
        self.assertEqual(self.penanya.susun(self.hari), [], "baru dilewati: belum ditanya ulang")
        nanti = skema.tambah_hari(self.hari, 31)
        self.assertEqual([q.jenis for q in self.penanya.susun(nanti)], ["kedaluwarsa"], "lewat hari_tunggu: ditanya ulang")

    def test_prioritas_urut_dan_batas_maks(self):
        for i in range(3):
            self.pelajaran_aturan(id_=f"pl-{i}")
        ep = self.episode("kontra")
        self.pelajaran_aturan(id_="pl-k", kontra=[ep.id], tinjau_setelah="2027-01-01")
        penanya = Penanya(self.store, self.vault, {"maks_pertanyaan": 2})
        daftar = penanya.susun(self.hari)
        self.assertEqual(len(daftar), 2)
        self.assertEqual(daftar[0].jenis, "konflik", "konflik berprioritas di atas kedaluwarsa")
        self.assertEqual([q.nomor for q in daftar], [1, 2])


if __name__ == "__main__":
    unittest.main()
