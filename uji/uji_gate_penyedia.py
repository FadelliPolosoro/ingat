# SPDX-License-Identifier: Apache-2.0
"""Gate P/I/S (Bab 9) dan konektor penyedia LLM (K1: sepuluh preset). Tanpa jaringan nyata —
transport HTTP disuntik palsu. Ini menutup celah: sebelumnya gate.py dan penyedia.py tanpa uji sama sekali."""
from __future__ import annotations

import json
import os
import unittest
from unittest import mock

from ingat.gate import Gate, GateDitolak
from ingat.penyedia import PRESET, bangun_penyedia, daftar_preset, PenyediaAnthropic, PenyediaOpenAICompat, PenyediaGagal


class GateTierS(unittest.TestCase):
    def test_tier_s_selalu_kosong_apa_pun_konfigurasinya(self):
        """Bab 9: tier S tidak pernah masuk penyedia LLM — bukan kebijakan, tapi dipaksa di konstruktor."""
        g = Gate({"P": ["claude"], "I": ["lokal"], "S": ["claude", "lokal", "deepseek"]})
        self.assertEqual(g.izin("S"), [])
        self.assertFalse(g.boleh("claude", "S"))
        self.assertIsNone(g.pilih("S", {"claude": object(), "lokal": object()}))

    def test_pilih_hanya_yang_benar_benar_terkonfigurasi(self):
        g = Gate({"P": ["claude", "openai"], "I": []})
        self.assertEqual(g.pilih("P", {"openai": object()}), "openai", "claude diizinkan tapi tidak terkonfigurasi; openai yang dipakai")
        self.assertIsNone(g.pilih("P", {}))
        self.assertIsNone(g.pilih("I", {"lokal": object()}), "I tidak mengizinkan siapa pun di konfigurasi ini")

    def test_konfigurasi_kosong_tidak_mengizinkan_apa_pun(self):
        g = Gate(None)
        self.assertEqual(g.izin("P"), [])
        self.assertEqual(g.izin("I"), [])
        self.assertEqual(g.izin("S"), [])


class PresetPenyedia(unittest.TestCase):
    def test_sepuluh_preset_dua_protokol_saja(self):
        wajib = {"claude", "openai", "perplexity", "deepseek", "kimi", "grok", "glm", "nemotron", "gemini", "lokal"}
        self.assertEqual(wajib, set(PRESET))
        for pid, p in PRESET.items():
            self.assertIn(p["jenis"], ("anthropic", "openai_compatible"), pid)
            self.assertTrue(p["base_url"].startswith("http"), pid)
            self.assertTrue(p["env"].isupper(), pid)

    def test_gemini_pakai_lapisan_kompatibilitas_openai_resmi(self):
        """Diverifikasi web search Sep 2026: generativelanguage.googleapis.com/v1beta/openai/ + GEMINI_API_KEY."""
        g = PRESET["gemini"]
        self.assertEqual(g["jenis"], "openai_compatible")
        self.assertIn("generativelanguage.googleapis.com", g["base_url"])
        self.assertIn("openai", g["base_url"])
        self.assertEqual(g["env"], "GEMINI_API_KEY")

    def test_bangun_penyedia_kosong_tanpa_kunci_bukan_galat(self):
        """.env.contoh: 'Kosong = penyedia dilewati (bukan galat)'."""
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertEqual(bangun_penyedia({}), {})
            self.assertEqual(bangun_penyedia({"claude": {"aktif": True}}), {})

    def test_bangun_penyedia_dengan_kunci_menghasilkan_objek_benar(self):
        with mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-uji", "GEMINI_API_KEY": "g-uji"}, clear=True):
            pen = bangun_penyedia({"claude": {"aktif": True}, "gemini": {"aktif": True}})
        self.assertIsInstance(pen["claude"], PenyediaAnthropic)
        self.assertIsInstance(pen["gemini"], PenyediaOpenAICompat)

    def test_override_base_url_dan_model_tanpa_ubah_kode(self):
        """K3 (repo README): base URL dan model selalu bisa ditimpa di konfigurasi.json."""
        with mock.patch.dict("os.environ", {"MOONSHOT_API_KEY": "m-uji"}, clear=True):
            pen = bangun_penyedia({"kimi": {"aktif": True, "base_url": "https://proxy-internal.example/v1", "model": "kimi-lain"}})
        self.assertEqual(pen["kimi"].base_url.rstrip("/"), "https://proxy-internal.example/v1")
        self.assertEqual(pen["kimi"].model, "kimi-lain")

    def test_daftar_preset_tidak_membocorkan_env_var_kunci(self):
        keluar = json.dumps(daftar_preset())
        self.assertNotIn("API_KEY=", keluar)  # nama env var boleh, nilai kunci tidak pernah ada di sini


class TransportPalsu(unittest.TestCase):
    """Konektor benar-benar dipanggil, tapi HTTP disuntik palsu — nol jaringan nyata."""

    def test_anthropic_tanya_parse_respons(self):
        p = PenyediaAnthropic(id_="claude", base_url="https://api.anthropic.com", api_key="x", model="claude-sonnet-4-5")
        with mock.patch("ingat.penyedia._post_json", return_value={"content": [{"type": "text", "text": "Halo"}]}) as m:
            jawab = p.tanya("sistem", "user", maks_token=50)
        self.assertEqual(jawab, "Halo")
        _, badan, header, _ = m.call_args[0][0], m.call_args[0][1], m.call_args[0][2], m.call_args[0][3]
        self.assertEqual(header.get("x-api-key"), "x")
        self.assertEqual(badan["model"], "claude-sonnet-4-5")

    def test_openai_compat_tanya_parse_respons(self):
        p = PenyediaOpenAICompat(id_="deepseek", base_url="https://api.deepseek.com/v1", api_key="x", model="deepseek-chat")
        with mock.patch("ingat.penyedia._post_json", return_value={"choices": [{"message": {"content": "Halo"}}]}) as m:
            jawab = p.tanya("sistem", "user", maks_token=50)
        self.assertEqual(jawab, "Halo")
        _, badan, header, _ = m.call_args[0]
        self.assertEqual(header.get("Authorization"), "Bearer x")
        self.assertEqual(badan["model"], "deepseek-chat")

    def test_kegagalan_jaringan_dilempar_sebagai_penyediagagal(self):
        p = PenyediaOpenAICompat(id_="deepseek", base_url="https://api.deepseek.com/v1", api_key="x", model="deepseek-chat")
        with mock.patch("ingat.penyedia._post_json", side_effect=PenyediaGagal("HTTP 500")):
            with self.assertRaises(PenyediaGagal):
                p.tanya("sistem", "user")


class KunciCatatanDiBlokPenyedia(unittest.TestCase):
    """Regresi: `_catatan` di blok `penyedia` pernah merobohkan server saat start.

    Ditemukan waktu deploy ke VPS 8 Sep 2026, bukan dari membaca kode: `bangun_penyedia`
    mengulang SEMUA kunci, termasuk `_catatan` yang nilainya string, lalu memanggil `.get`
    di atasnya → AttributeError. Karena `konfigurasi.contoh.json` selalu memuat kunci itu,
    setiap orang yang menyalin contoh ke konfigurasi.json pasti kena.
    """

    def test_kunci_awalan_garis_bawah_dilewati(self):
        hasil = bangun_penyedia({"_catatan": "ini catatan untuk manusia", "lokal": {"aktif": False}})
        self.assertEqual(hasil, {}, "kunci `_catatan` harus dilewati, bukan diperlakukan sebagai penyedia")

    def test_nilai_bukan_objek_dilewati_bukan_meledak(self):
        for sampah in ("teks", 123, ["daftar"], None):
            with self.subTest(sampah=sampah):
                self.assertEqual(bangun_penyedia({"aneh": sampah}), {},
                                 f"nilai {type(sampah).__name__} harus dilewati diam-diam, bukan melempar AttributeError")

    def test_konfigurasi_contoh_yang_sungguhan_dikirim_tidak_merobohkan(self):
        """Penjaga paling penting: berkas yang BENAR-BENAR kami kirim ke pengguna harus bisa dimuat."""
        akar = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(akar, "konfigurasi.contoh.json"), encoding="utf-8") as f:
            contoh = json.load(f)
        self.assertIn("_catatan", contoh["penyedia"],
                      "uji ini kehilangan maknanya kalau `_catatan` sudah tidak ada di contoh — sesuaikan ujinya")
        hasil = bangun_penyedia(contoh["penyedia"])
        self.assertEqual(hasil, {}, "semua penyedia di contoh ber-aktif:false, jadi hasilnya harus kosong — bukan galat")


if __name__ == "__main__":
    unittest.main()
