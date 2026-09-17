# SPDX-License-Identifier: Apache-2.0
"""Tombol "Sambungkan" — pasang ingat ke Claude Desktop tanpa menyunting JSON sendiri.
Semua path dijadikan parameter: uji ini tidak pernah menyentuh konfigurasi Claude Desktop asli,
dan tidak pernah menyentuh jaringan (penguji koneksi disuntik)."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

from ingat import sambung


def _tulis(path: str, isi) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        if isinstance(isi, str):
            f.write(isi)
        else:
            json.dump(isi, f, ensure_ascii=False, indent=2)


def _tulis_bita(path: str, bita: bytes) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(bita)


def _baca(path: str) -> dict:
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


class DasarSambung(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="ingat-sambung-")
        self.dir_claude = os.path.join(self.root, "Claude")
        os.makedirs(self.dir_claude)
        self.konfig = os.path.join(self.dir_claude, sambung.NAMA_BERKAS_KONFIG)
        self.python = os.path.join(self.root, "python.exe")
        with open(self.python, "w", encoding="utf-8") as f:
            f.write("")
        self.arg = {"path": self.konfig, "python_exe": self.python,
                    "konfig_ingat": os.path.join(self.root, "konfigurasi.json"),
                    "token": "rahasia123", "akar": self.root}

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _cadangan(self) -> list[str]:
        return [n for n in os.listdir(self.dir_claude) if ".cadangan-" in n]


class Menyambung(DasarSambung):
    def test_berkas_belum_ada_dibuatkan(self):
        h = sambung.sambungkan(**self.arg)
        self.assertTrue(h["berhasil"], h["pesan"])
        self.assertTrue(h["berubah"])
        self.assertIsNone(h["cadangan"], "tidak ada yang perlu dicadangkan kalau berkasnya belum ada")
        entri = _baca(self.konfig)["mcpServers"]["ingat"]
        self.assertEqual(entri["command"], self.python)
        self.assertIn("mcp", entri["args"])
        self.assertEqual(entri["env"]["INGAT_TOKEN"], "rahasia123")

    def test_entri_aplikasi_lain_tidak_rusak(self):
        _tulis(self.konfig, {"mcpServers": {"filesystem": {"command": "npx", "args": ["x"]}},
                             "preferences": {"tema": "gelap"}})
        h = sambung.sambungkan(**self.arg)
        self.assertTrue(h["berhasil"], h["pesan"])
        data = _baca(self.konfig)
        self.assertEqual(data["mcpServers"]["filesystem"], {"command": "npx", "args": ["x"]})
        self.assertEqual(data["preferences"], {"tema": "gelap"})
        self.assertIn("ingat", data["mcpServers"])

    def test_idempoten_tidak_menggandakan_dan_tidak_menulis_ulang(self):
        sambung.sambungkan(**self.arg)
        jumlah_cadangan = len(self._cadangan())
        for _ in range(3):
            h = sambung.sambungkan(**self.arg)
            self.assertTrue(h["berhasil"], h["pesan"])
            self.assertFalse(h["berubah"], "menekan Sambungkan lagi tidak boleh menulis apa pun")
        server = _baca(self.konfig)["mcpServers"]
        self.assertEqual(list(server), ["ingat"])
        self.assertEqual(len(self._cadangan()), jumlah_cadangan,
                         "tekan berulang tidak boleh menumpuk berkas cadangan")

    def test_entri_lama_diperbarui_dan_dicadangkan(self):
        _tulis(self.konfig, {"mcpServers": {"ingat": {"command": "python3", "args": ["lama"]}}})
        h = sambung.sambungkan(**self.arg)
        self.assertTrue(h["berhasil"], h["pesan"])
        self.assertTrue(h["berubah"])
        self.assertIsNotNone(h["cadangan"])
        self.assertTrue(os.path.exists(h["cadangan"]))
        self.assertEqual(_baca(self.konfig)["mcpServers"]["ingat"]["command"], self.python)
        self.assertEqual(_baca(h["cadangan"])["mcpServers"]["ingat"]["command"], "python3",
                         "cadangan harus berisi versi SEBELUM perubahan")

    def test_token_kosong_tidak_menulis_env_token(self):
        arg = dict(self.arg, token="")
        sambung.sambungkan(**arg)
        env = _baca(self.konfig)["mcpServers"]["ingat"].get("env", {})
        self.assertNotIn("INGAT_TOKEN", env)
        self.assertEqual(env.get("PYTHONPATH"), self.root)

    def test_claude_desktop_tidak_terpasang_ditolak_ramah(self):
        arg = dict(self.arg, path=os.path.join(self.root, "TakAda", sambung.NAMA_BERKAS_KONFIG))
        h = sambung.sambungkan(**arg)
        self.assertFalse(h["berhasil"])
        self.assertIn("Claude Desktop", h["pesan"])
        self.assertNotIn("Traceback", h["pesan"])
        self.assertFalse(os.path.exists(arg["path"]))


class KonfigurasiRusak(DasarSambung):
    def test_json_rusak_tidak_ditimpa(self):
        _tulis(self.konfig, "{ini bukan json")
        h = sambung.sambungkan(**self.arg)
        self.assertFalse(h["berhasil"])
        self.assertIn("rusak", h["pesan"].lower())
        self.assertNotIn("Traceback", h["pesan"])
        with open(self.konfig, encoding="utf-8") as f:
            self.assertEqual(f.read(), "{ini bukan json", "berkas rusak harus ditinggalkan utuh")

    def test_json_rusak_dengan_paksa_dicadangkan_dulu(self):
        _tulis(self.konfig, "{ini bukan json")
        h = sambung.sambungkan(paksa=True, **self.arg)
        self.assertTrue(h["berhasil"], h["pesan"])
        self.assertIsNotNone(h["cadangan"])
        with open(h["cadangan"], encoding="utf-8") as f:
            self.assertEqual(f.read(), "{ini bukan json")
        self.assertIn("ingat", _baca(self.konfig)["mcpServers"])

    def test_berkas_kosong_dianggap_konfigurasi_kosong(self):
        _tulis(self.konfig, "   \n")
        h = sambung.sambungkan(**self.arg)
        self.assertTrue(h["berhasil"], h["pesan"])
        self.assertIn("ingat", _baca(self.konfig)["mcpServers"])

    def test_bentuk_bukan_objek_ditolak(self):
        _tulis(self.konfig, ["bukan", "objek"])
        h = sambung.sambungkan(**self.arg)
        self.assertFalse(h["berhasil"])
        self.assertNotIn("Traceback", h["pesan"])

    def test_mcpservers_bertipe_salah_tidak_menghapus_kunci_lain(self):
        _tulis(self.konfig, {"mcpServers": "entah", "preferences": {"a": 1}})
        h = sambung.sambungkan(**self.arg)
        self.assertTrue(h["berhasil"], h["pesan"])
        data = _baca(self.konfig)
        self.assertIn("ingat", data["mcpServers"])
        self.assertEqual(data["preferences"], {"a": 1})


class EncodingKonfigurasi(DasarSambung):
    """Berkas konfigurasi yang bukan UTF-8 polos: cp1252, UTF-16, dan UTF-8 ber-BOM.

    Pendekodean terjadi saat berkas dibaca, bukan saat JSON diurai. UnicodeDecodeError adalah
    turunan ValueError — bukan OSError — jadi gampang lolos dari penjagaan dan naik mentah
    ke muka pengguna. Kontrak nomor 3 di docstring modul melarang itu.
    """

    # JSON sah, tapi nilainya memuat é (0xE9 dalam cp1252 — bukan UTF-8 yang sah).
    CP1252 = '{"mcpServers": {"lain": {"command": "café"}}}'.encode("cp1252")
    UTF16 = '{"mcpServers": {"lain": {"command": "café"}}}'.encode("utf-16-le")

    def test_cp1252_ditolak_ramah_tanpa_traceback(self):
        _tulis_bita(self.konfig, self.CP1252)
        h = sambung.sambungkan(**self.arg)
        self.assertFalse(h["berhasil"])
        self.assertNotIn("Traceback", h["pesan"])
        self.assertNotIn("UnicodeDecodeError", h["pesan"])
        self.assertIn(self.konfig, h["pesan"])
        with open(self.konfig, "rb") as f:
            self.assertEqual(f.read(), self.CP1252, "berkas yang tak terbaca harus ditinggal utuh")

    def test_utf16_ditolak_ramah_tanpa_traceback(self):
        _tulis_bita(self.konfig, self.UTF16)
        h = sambung.sambungkan(**self.arg)
        self.assertFalse(h["berhasil"])
        self.assertNotIn("Traceback", h["pesan"])
        self.assertNotIn("UnicodeDecodeError", h["pesan"])

    def test_putuskan_tidak_meledak_saat_encoding_asing(self):
        _tulis_bita(self.konfig, self.CP1252)
        h = sambung.putuskan(self.konfig)
        self.assertFalse(h["berhasil"])
        self.assertFalse(h["berubah"])
        self.assertNotIn("Traceback", h["pesan"])

    def test_entri_terpasang_tidak_meledak_saat_encoding_asing(self):
        _tulis_bita(self.konfig, self.CP1252)
        self.assertIsNone(sambung.entri_terpasang(self.konfig))

    def test_status_tetap_menggambar_lampu_merah_saat_encoding_asing(self):
        # Panel memanggil status() untuk menggambar lampu. Kalau ini melempar, panelnya yang
        # jatuh — bukan lampunya yang merah.
        _tulis_bita(self.konfig, self.CP1252)
        s = sambung.status(path=self.konfig, dir_data=self.dir_claude, penguji=Status.HIDUP)
        self.assertEqual(s["lampu"], "merah")
        self.assertFalse(s["butir"][1]["ok"])

    def test_bom_utf8_isinya_sah_tetap_diterima(self):
        # BOM UTF-8 lumrah di Windows setelah berkas disunting editor lama. Isinya sah.
        _tulis_bita(self.konfig, b"\xef\xbb\xbf" + json.dumps(
            {"mcpServers": {"lain": {"command": "npx"}}, "preferences": {"tema": "gelap"}},
        ).encode("utf-8"))
        h = sambung.sambungkan(**self.arg)
        self.assertTrue(h["berhasil"], h["pesan"])
        self.assertNotIn("rusak", h["pesan"].lower())
        data = _baca(self.konfig)
        self.assertIn("ingat", data["mcpServers"])
        self.assertEqual(data["mcpServers"]["lain"], {"command": "npx"})
        self.assertEqual(data["preferences"], {"tema": "gelap"})

    def test_bom_utf8_entri_terpasang_terbaca(self):
        _tulis_bita(self.konfig, b"\xef\xbb\xbf" + json.dumps(
            {"mcpServers": {"ingat": {"command": "python.exe"}}}).encode("utf-8"))
        entri = sambung.entri_terpasang(self.konfig)
        self.assertIsNotNone(entri, "BOM tidak boleh membuat entri yang ada dianggap tak ada")
        self.assertEqual(entri["command"], "python.exe")


class Memutus(DasarSambung):
    def test_putuskan_hanya_mencabut_entri_ingat(self):
        _tulis(self.konfig, {"mcpServers": {"ingat": {"command": "x"}, "lain": {"command": "y"}}})
        h = sambung.putuskan(self.konfig)
        self.assertTrue(h["berhasil"], h["pesan"])
        self.assertTrue(h["berubah"])
        server = _baca(self.konfig)["mcpServers"]
        self.assertNotIn("ingat", server)
        self.assertIn("lain", server)

    def test_putuskan_saat_belum_tersambung_aman(self):
        _tulis(self.konfig, {"mcpServers": {"lain": {"command": "y"}}})
        h = sambung.putuskan(self.konfig)
        self.assertTrue(h["berhasil"])
        self.assertFalse(h["berubah"])
        self.assertEqual(self._cadangan(), [])


class EkstensiMcpb(DasarSambung):
    def _pasang_mcpb(self, aktif=True, id_ekstensi="local.mcpb.fadelli-polosoro.ingat"):
        _tulis(os.path.join(self.dir_claude, sambung.BERKAS_PASANGAN_EKSTENSI),
               {"extensions": {id_ekstensi: {"id": id_ekstensi, "manifest": {"name": "ingat"}}}})
        _tulis(os.path.join(self.dir_claude, sambung.DIR_PENGATURAN_EKSTENSI, id_ekstensi + ".json"),
               {"isEnabled": aktif})

    def test_ekstensi_aktif_terdeteksi(self):
        self._pasang_mcpb()
        self.assertTrue(sambung.mcpb_terpasang(self.dir_claude))

    def test_ekstensi_dimatikan_tidak_dihitung(self):
        self._pasang_mcpb(aktif=False)
        self.assertFalse(sambung.mcpb_terpasang(self.dir_claude))

    def test_tanpa_berkas_pasangan_tidak_meledak(self):
        self.assertFalse(sambung.mcpb_terpasang(self.dir_claude))

    def test_ekstensi_aplikasi_lain_bukan_ingat(self):
        _tulis(os.path.join(self.dir_claude, sambung.BERKAS_PASANGAN_EKSTENSI),
               {"extensions": {"local.mcpb.x.lain": {"manifest": {"name": "lain"}}}})
        self.assertFalse(sambung.mcpb_terpasang(self.dir_claude))


class Status(DasarSambung):
    HIDUP = staticmethod(lambda h, t=None: (True, "tersambung"))
    MATI = staticmethod(lambda h, t=None: (False, "server tak merespons"))

    def test_merah_saat_belum_terdaftar(self):
        s = sambung.status(path=self.konfig, dir_data=self.dir_claude, penguji=self.HIDUP)
        self.assertEqual(s["lampu"], "merah")
        self.assertEqual([b["nama"] for b in s["butir"]],
                         ["Claude Desktop", "Entri ingat", "Server ingat"])
        self.assertFalse(s["butir"][1]["ok"])

    def test_merah_saat_claude_desktop_tak_ada(self):
        kosong = os.path.join(self.root, "TakAda")
        s = sambung.status(path=os.path.join(kosong, sambung.NAMA_BERKAS_KONFIG),
                           dir_data=kosong, penguji=self.HIDUP)
        self.assertEqual(s["lampu"], "merah")
        self.assertFalse(s["butir"][0]["ok"])

    def test_kuning_saat_terdaftar_tapi_server_mati(self):
        sambung.sambungkan(**self.arg)
        s = sambung.status(path=self.konfig, dir_data=self.dir_claude, penguji=self.MATI)
        self.assertEqual(s["lampu"], "kuning")
        self.assertTrue(s["butir"][1]["ok"])
        self.assertFalse(s["butir"][2]["ok"])

    def test_hijau_saat_semua_siap(self):
        sambung.sambungkan(**self.arg)
        s = sambung.status(path=self.konfig, dir_data=self.dir_claude, penguji=self.HIDUP)
        self.assertEqual(s["lampu"], "hijau")
        self.assertTrue(all(b["ok"] for b in s["butir"]))

    def test_terpasang_lewat_ekstensi_mcpb_juga_dihitung(self):
        _tulis(os.path.join(self.dir_claude, sambung.BERKAS_PASANGAN_EKSTENSI),
               {"extensions": {"local.mcpb.fadelli-polosoro.ingat": {"manifest": {"name": "ingat"}}}})
        s = sambung.status(path=self.konfig, dir_data=self.dir_claude, penguji=self.HIDUP)
        self.assertEqual(s["lampu"], "hijau")

    def test_penguji_meledak_tidak_menjatuhkan_status(self):
        def meledak(h, t=None):
            raise RuntimeError("jaringan kacau")
        s = sambung.status(path=self.konfig, dir_data=self.dir_claude, penguji=meledak)
        self.assertFalse(s["butir"][2]["ok"])
        self.assertNotIn("RuntimeError", s["butir"][2]["pesan"])

    def test_konfigurasi_rusak_tidak_menjatuhkan_status(self):
        _tulis(self.konfig, "{rusak")
        s = sambung.status(path=self.konfig, dir_data=self.dir_claude, penguji=self.HIDUP)
        self.assertEqual(s["lampu"], "merah")
        self.assertFalse(s["butir"][1]["ok"])


class BentukEntri(DasarSambung):
    def test_perintah_langsung_bukan_skrip_peluncur(self):
        e = sambung.entri_ingat(self.python, "C:/k.json", "t", self.root)
        self.assertEqual(e["args"][:2], ["-m", "ingat"])
        self.assertEqual(e["args"][-1], "mcp")
        self.assertIn("C:/k.json", e["args"])

    def _sebut_python3(self, jalur: str | None) -> bool:
        return jalur is not None and os.path.basename(jalur).lower() in ("python3.exe", "python3")

    def test_python_untuk_mcp_bukan_python3(self):
        p = sambung.python_untuk_mcp()
        self.assertTrue(p is None or os.path.exists(p))
        if sys.platform.startswith("win"):
            self.assertFalse(self._sebut_python3(p),
                             f"di Windows python3 hanya alias Microsoft Store, bukan interpreter: {p}")

    def test_alias_python3_windows_tidak_pernah_dipilih(self):
        # Keadaan nyata: panel berjalan sebagai .exe (sys.executable = panel, bukan Python) dan
        # PATH cuma punya alias Microsoft Store `python3.exe` — berkas yang ada tapi hanya
        # membuka halaman toko, sehingga host MCP langsung kehilangan stdio.
        alias = os.path.join(self.root, "WindowsApps", "python3.exe")
        os.makedirs(os.path.dirname(alias), exist_ok=True)
        with open(alias, "w", encoding="utf-8") as f:
            f.write("")
        with mock.patch.object(sys, "platform", "win32"), \
                mock.patch.object(sys, "frozen", True, create=True), \
                mock.patch.object(sambung.shutil, "which",
                                  side_effect=lambda n: alias if n == "python3" else None):
            p = sambung.python_untuk_mcp()
        self.assertNotEqual(p, alias, "alias Microsoft Store tidak boleh dipakai sebagai interpreter")
        self.assertFalse(self._sebut_python3(p), f"nama python3 tidak ada di Windows: {p}")

    def test_python_asli_tetap_dipilih_saat_tersedia(self):
        asli = os.path.join(self.root, "Python312", "python.exe")
        os.makedirs(os.path.dirname(asli), exist_ok=True)
        with open(asli, "w", encoding="utf-8") as f:
            f.write("")
        with mock.patch.object(sys, "platform", "win32"), \
                mock.patch.object(sys, "frozen", True, create=True), \
                mock.patch.object(sambung.shutil, "which",
                                  side_effect=lambda n: asli if n == "python" else None):
            self.assertEqual(sambung.python_untuk_mcp(), asli)


if __name__ == "__main__":
    unittest.main()
