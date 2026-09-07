# SPDX-License-Identifier: Apache-2.0
"""Konsistensi ekstensi browser: setiap situs yang di-match content script HARUS punya entri selektor
dan muncul di daftar situs halaman opsi. Lahir dari kelalaian nyata: Perplexity tertinggal di tiga tempat sekaligus."""
from __future__ import annotations

import json
import os
import re
import unittest

AKAR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT = os.path.join(AKAR, "pasang", "browser-extension")


def _host_dari_pola(pola: str) -> str:
    return re.sub(r"^https?://", "", pola).split("/")[0]


class EkstensiKonsisten(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(EXT, "manifest.json"), encoding="utf-8") as f:
            self.manifest = json.load(f)
        with open(os.path.join(EXT, "selectors-default.json"), encoding="utf-8") as f:
            self.selektor = json.load(f)
        with open(os.path.join(EXT, "options.js"), encoding="utf-8") as f:
            m = re.search(r"const SITUS = \[(.*?)\];", f.read(), re.S)
            self.situs_opsi = set(re.findall(r"'([^']+)'", m.group(1)))

    def test_manifest_v3_dan_izin_hanya_situs_ai_plus_lokal(self):
        self.assertEqual(self.manifest["manifest_version"], 3)
        for h in self.manifest["host_permissions"]:
            self.assertTrue(h.startswith("https://") or h.startswith("http://127.0.0.1") or h.startswith("http://localhost"), h)

    def test_setiap_situs_match_punya_selektor_dan_ada_di_opsi(self):
        hosts = {_host_dari_pola(p) for p in self.manifest["content_scripts"][0]["matches"]}
        self.assertGreaterEqual(len(hosts), 9)
        for h in sorted(hosts):
            self.assertIn(h, self.selektor, f"{h} di-match content script tapi tidak punya entri selektor")
            self.assertIn(h, self.situs_opsi, f"{h} di-match content script tapi tidak muncul di halaman opsi")
            self.assertIn(f"https://{h}/*", self.manifest["host_permissions"], f"{h} tanpa host_permissions")

    def test_setiap_situs_punya_kunci_compose_untuk_fitur_suntik(self):
        """Suntik memori (8 Sep 2026) butuh peran ketiga 'compose'; kalau lupa ditambah saat situs baru
        masuk, tombol suntik akan gagal diam-diam tanpa uji ini yang menegur."""
        for h, cfg in self.selektor.items():
            if h.startswith("_"):
                continue
            self.assertIn("compose", cfg, f"{h} tidak punya kunci 'compose' di selectors-default.json")

    def test_perplexity_ada_di_semua_tempat(self):
        for h in ("www.perplexity.ai", "perplexity.ai"):
            self.assertIn(h, self.selektor)
            self.assertIn(h, self.situs_opsi)

    def test_selektor_kosong_diberi_label_jujur(self):
        """Situs yang selektornya (user/assistant/compose) kosong harus menyatakan itu — bukan diam-diam gagal."""
        for h, cfg in self.selektor.items():
            if h.startswith("_"):
                continue
            if not (cfg.get("user") and cfg.get("assistant") and cfg.get("compose")):
                self.assertIn("Pilih elemen", cfg.get("verifikasi", ""), h)

    def test_content_js_dan_background_js_dan_popup_js_sintaks_valid(self):
        """Verifikasi sintaks JS lewat `node --check` — sejauh yang bisa dilakukan tanpa browser sungguhan."""
        import shutil
        import subprocess
        node = shutil.which("node")
        if not node:
            self.skipTest("node tidak tersedia di lingkungan uji ini")
        for berkas in ("content.js", "background.js", "popup.js", "options.js"):
            r = subprocess.run([node, "--check", os.path.join(EXT, berkas)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, f"{berkas}: {r.stderr}")

    def test_popup_html_punya_tombol_suntik_dengan_peringatan_tidak_auto_kirim(self):
        with open(os.path.join(EXT, "popup.html"), encoding="utf-8") as f:
            html = f.read()
        self.assertIn('id="suntik"', html)
        self.assertIn("tidak pernah mengirim otomatis", html.lower())

    def test_suntik_otomatis_hanya_pada_percakapan_kosong(self):
        """Auto-mulai (8 Sep 2026) hanya boleh menembak saat kotak DAN daftar pesan benar-benar kosong,
        sekali per percakapan (sessionStorage), dan bisa dimatikan lewat toggle autoMulai."""
        with open(os.path.join(EXT, "content.js"), encoding="utf-8") as f:
            ct = f.read()
        self.assertIn("percakapanBenarBenarKosong", ct)
        self.assertIn("sessionStorage", ct, "harus mencegah suntik berulang di percakapan yang sama")
        self.assertIn("autoMulai", ct, "harus bisa dimatikan pengguna")
        awal = ct.index("async function cekMulaiOtomatis")
        akhir = ct.index("\n  }", awal)
        badan = ct[awal:akhir]
        self.assertIn("trim() !== ''", badan, "harus mengecek kotak ketik benar-benar kosong sebelum menyuntik")

    def test_auto_mulai_lewat_jalur_kode_yang_sama_dengan_suntik_manual(self):
        """auto_mulai HARUS memanggil suntikKe (jalur yang sama dengan tombol manual) — bukan jalur
        kedua yang bisa diam-diam melanggar jaminan tidak-pernah-submit."""
        with open(os.path.join(EXT, "background.js"), encoding="utf-8") as f:
            bg = f.read()
        awal = bg.index("if (msg.jenis === 'auto_mulai'")
        akhir = bg.index("return;", awal)
        self.assertIn("suntikKe(", bg[awal:akhir])

    def test_pengingat_relevansi_tidak_pernah_menyisipkan_otomatis(self):
        """Badge/hint (cekRelevansi) hanya boleh MEMBERI TAHU (setBadgeText, storage), tidak pernah
        memanggil sisipkan_teks sendiri — itu tetap harus lewat klik pengguna di popup."""
        with open(os.path.join(EXT, "background.js"), encoding="utf-8") as f:
            bg = f.read()
        awal = bg.index("async function cekRelevansi")
        akhir = bg.index("\n}", awal)
        badan = bg[awal:akhir]
        self.assertNotIn("sisipkan_teks", badan, "cekRelevansi tidak boleh menyisipkan apa pun, hanya memberi tahu")
        self.assertIn("setBadgeText", badan)

    def test_suntik_lagi_melacak_id_supaya_tidak_duplikat(self):
        with open(os.path.join(EXT, "background.js"), encoding="utf-8") as f:
            bg = f.read()
        self.assertIn("idTerkirim", bg)
        self.assertIn("TANGGA_ANGGARAN", bg, "eskalasi anggaran token bertahap (cicilan) harus ada")

    def test_popup_punya_elemen_hint_dan_suntik_lagi(self):
        with open(os.path.join(EXT, "popup.html"), encoding="utf-8") as f:
            html = f.read()
        self.assertIn('id="hintRelevansi"', html)
        self.assertIn('id="suntikLagi"', html)

    def test_background_js_tidak_pernah_memanggil_submit_atau_klik_kirim(self):
        """Jaminan tertulis di README: fitur ini tidak pernah men-submit. Pola ini menangkap kalau
        suatu saat kode diam-diam ditambah pemicu submit/klik tombol kirim."""
        with open(os.path.join(EXT, "background.js"), encoding="utf-8") as f:
            bg = f.read()
        with open(os.path.join(EXT, "content.js"), encoding="utf-8") as f:
            ct = f.read()
        for terlarang in (".submit(", "requestSubmit", "click()"):
            self.assertNotIn(terlarang, bg, f"background.js memuat '{terlarang}' — melanggar jaminan tidak auto-kirim")
            self.assertNotIn(terlarang, ct, f"content.js memuat '{terlarang}' — melanggar jaminan tidak auto-kirim")


if __name__ == "__main__":
    unittest.main()
