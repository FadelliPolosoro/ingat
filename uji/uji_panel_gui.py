# SPDX-License-Identifier: Apache-2.0
"""Fase 5 — jendela panel dibangun sungguhan lalu dikemudikan tanpa layar terlihat.

Hanya di sini NameError/AttributeError di dalam closure jendela bisa tertangkap: mengimpor
ingat.panel saja tidak pernah menjalankan isi `bangun_jendela_*` maupun `jalankan()`.

Dua jebakan Tk yang menentukan bentuk berkas ini:

1. Thread pekerja memanggil `root.after()`; Tk MENOLAK itu bila thread utama belum masuk
   mainloop ("main thread is not in main loop"), jadi `root.update()` saja tidak cukup —
   jendela harus dibangun dan ditekan DARI DALAM mainloop (lihat `_kemudikan`).
2. SATU root Tk dipakai bersama seluruh berkas, dan thread pekerja selalu ditunggu habis
   sebelum jendelanya dibuang. Membuat/membuang interpreter Tk berkali-kali, atau
   membiarkan thread memegang referensi widget terakhir, membuat Tcl menggugurkan seluruh
   proses uji ("Tcl_AsyncDelete: async handler deleted by the wrong thread") — bukan satu
   uji gagal, tapi `discover` mati di tengah jalan.

Keduanya batasan harness, bukan perilaku panel: di aplikasi sungguhan mainloop selalu jalan
dan rootnya cuma satu seumur proses. Tanpa layar (CI headless) seluruh berkas ini di-skip.
"""
from __future__ import annotations

import shutil
import tempfile
import threading
import time
import unittest
from unittest import mock

from ingat import panel

_ROOT: dict = {"tk": None, "gagal": None}


def _root_bersama(kasus):
    import tkinter as tk
    if _ROOT["gagal"]:
        raise unittest.SkipTest(_ROOT["gagal"])
    if _ROOT["tk"] is None:
        try:
            r = tk.Tk()
        except Exception as e:
            _ROOT["gagal"] = "tanpa layar: " + str(e)
            raise unittest.SkipTest(_ROOT["gagal"])
        r.withdraw()
        _ROOT["tk"] = r
    return _ROOT["tk"]


def tearDownModule():
    r = _ROOT.get("tk")
    _ROOT["tk"] = None
    if r is not None:
        try:
            r.destroy()
        except Exception:
            pass


def _kemudikan(root, mulai, syarat, batas=5.0):
    """Jalankan `mulai()` di dalam mainloop, lalu putar sampai `syarat()` benar."""
    hasil = {"ok": False}
    henti = time.time() + batas

    def periksa():
        try:
            if syarat():
                hasil["ok"] = True
                root.quit()
                return
        except Exception:
            pass
        if time.time() > henti:
            root.quit()
            return
        root.after(20, periksa)

    def awal():
        try:
            mulai()
        finally:
            root.after(20, periksa)

    root.after(0, awal)
    root.mainloop()
    return hasil["ok"]


def _widget(induk):
    """Semua widget turunan, rata. Jendela dikemudikan lewat ini karena bangun_jendela_*
    mengembalikan Toplevel, bukan kamus widget."""
    keluar = []
    for w in induk.winfo_children():
        keluar.append(w)
        keluar.extend(_widget(w))
    return keluar


def _cari_widget(induk, kelas, teks=None):
    for w in _widget(induk):
        if w.winfo_class() != kelas:
            continue
        if teks is None:
            return w
        try:
            if str(w.cget("text")) == teks:
                return w
        except Exception:
            continue
    return None


def _label_teks(win):
    return [str(w.cget("text")) for w in _widget(win) if w.winfo_class() == "TLabel"]


class KasusTk(unittest.TestCase):
    """Induk: satu root bersama, thread ditunggu habis, jendela dibuang di tearDown."""

    def setUp(self):
        self.root = _root_bersama(self)
        self.thread_awal = set(threading.enumerate())
        self.jendela = []

    def tearDown(self):
        # urutan wajib: tunggu thread habis -> baru buang jendela (lihat docstring modul)
        _kemudikan(self.root, lambda: None, lambda: not self._sisa_thread(), 5.0)
        for t in self._sisa_thread():
            t.join(1.0)
        for w in reversed(self.jendela):
            try:
                w.destroy()
            except Exception:
                pass
        self.jendela = []

    def _sisa_thread(self):
        return [t for t in threading.enumerate() if t not in self.thread_awal and t.is_alive()]

    def _putar(self, mulai, syarat, batas=5.0):
        """Keluar dari mainloop hanya bila syarat terpenuhi DAN thread pekerja sudah habis.

        Keluar selagi masih ada thread yang akan memanggil root.after membuat Tk melempar
        "main thread is not in main loop", dan thread itu bisa jadi pemegang referensi widget
        terakhir — persis jalan menuju Tcl_AsyncDelete yang menggugurkan proses uji."""
        return _kemudikan(self.root, mulai, lambda: syarat() and not self._sisa_thread(), batas)

    def _catat(self, win):
        self.jendela.append(win)
        return win


class AppPalsu:
    def __init__(self, gateway=None):
        self.gateway = gateway
        self.store = None
        self.konfig = {}


class GatewayPalsu:
    def __init__(self, hasil=None, galat=None):
        self.hasil, self.galat, self.dipanggil = hasil, galat, []

    def buka_bukti(self, id_, sesi=""):
        self.dipanggil.append(id_)
        if self.galat is not None:
            raise self.galat
        return self.hasil


JAWAB_ISI = {
    "pertanyaan": "tender",
    "hasil": [{"jenis": "episode", "id": "ep1", "ringkas": "rapat tender komdigi",
               "kutipan": "isi lengkap rapat tender komdigi", "tanggal": "2026-09-18",
               "skor": 0.8, "bendera": [], "id_episode": "ep1"},
              {"jenis": "pelajaran", "id": "pl1", "ringkas": "selalu cek HPS",
               "kutipan": "selalu cek HPS sebelum kirim", "tanggal": "2026-09-01",
               "skor": None, "bendera": [], "id_episode": None}],
    "pesan": "", "sumber": "gerbang",
}


class JendelaCari(KasusTk):
    def setUp(self):
        super().setUp()
        self.gerbang = GatewayPalsu(hasil={"id": "ep1", "waktu": "2026-09-18T09:00:00",
                                           "ringkas": "rapat", "isi": "catatan asli verbatim"})
        self.app = AppPalsu(self.gerbang)
        self.ref = {}

    def _bangun(self, win_args=(), teks="tender"):
        win = self._catat(panel.bangun_jendela_cari(self.root, self.app, lambda *_: None, *win_args))
        win.withdraw()
        self.ref["win"] = win
        _cari_widget(win, "TEntry").insert(0, teks)
        _cari_widget(win, "TButton", "Cari").invoke()

    def _cari(self, syarat, teks="tender", batas=5.0):
        ok = self._putar(lambda: self._bangun(teks=teks),
                         lambda: syarat(self.ref["win"]), batas)
        return self.ref.get("win"), ok

    def _klik_bukti(self, syarat, batas=5.0):
        win = self.ref["win"]
        return self._putar(lambda: _cari_widget(win, "TButton", "Buka catatan aslinya").invoke(),
                           lambda: syarat(win), batas)

    def test_hasil_masuk_daftar_dan_isi(self):
        with mock.patch("ingat.cari_memori.cari", return_value=JAWAB_ISI) as tiruan:
            win, ok = self._cari(lambda w: _cari_widget(w, "Listbox").size() == 2)
            self.assertTrue(ok, "hasil tak masuk daftar")
            self.assertEqual(tiruan.call_args.args[0], "tender")
            self.assertIn("rapat tender komdigi", _cari_widget(win, "Listbox").get(0))
            self.assertIn("isi lengkap rapat tender komdigi", _cari_widget(win, "Text").get("1.0", "end"))
            self.assertNotIn("disabled", _cari_widget(win, "TButton", "Buka catatan aslinya").state())

    def test_pencarian_memakai_gerbang_yang_disuntik(self):
        gerbang, store = object(), object()
        with mock.patch("ingat.cari_memori.cari", return_value=JAWAB_ISI) as tiruan:
            self._putar(lambda: self._bangun((gerbang, store)), lambda: tiruan.called)
            self.assertIs(tiruan.call_args.kwargs["gerbang"], gerbang)
            self.assertIs(tiruan.call_args.kwargs["store"], store)

    def test_hasil_kosong_pakai_label_bukan_messagebox(self):
        kosong = {"pertanyaan": "x", "hasil": [], "sumber": "galat",
                  "pesan": "Mesin pencari (Ollama) belum menyala."}
        with mock.patch("ingat.cari_memori.cari", return_value=kosong), \
                mock.patch("tkinter.messagebox.showerror") as galat:
            _, ok = self._cari(lambda w: any("Ollama" in t for t in _label_teks(w)), "apa saja")
            self.assertTrue(ok, "pesan kosong tak tampil di label")
            galat.assert_not_called()

    def test_sumber_riwayat_diberitahukan(self):
        with mock.patch("ingat.cari_memori.cari", return_value=dict(JAWAB_ISI, sumber="riwayat")):
            _, ok = self._cari(lambda w: any("riwayat" in t for t in _label_teks(w)))
            self.assertTrue(ok)

    def test_cari_melempar_tak_sampai_layar(self):
        with mock.patch("ingat.cari_memori.cari", side_effect=RuntimeError("meledak")):
            win, ok = self._cari(lambda w: any("gagal" in t.lower() for t in _label_teks(w)))
            self.assertTrue(ok)
            for t in _label_teks(win):
                self.assertNotIn("RuntimeError", t)
                self.assertNotIn("meledak", t)

    def test_buka_bukti_menampilkan_isi_verbatim(self):
        with mock.patch("ingat.cari_memori.cari", return_value=JAWAB_ISI):
            _, ok = self._cari(lambda w: _cari_widget(w, "Listbox").size() == 2)
            self.assertTrue(ok)
            self.assertTrue(self._klik_bukti(
                lambda w: "catatan asli verbatim" in _cari_widget(w, "Text").get("1.0", "end")))
            self.assertEqual(self.gerbang.dipanggil, ["ep1"])

    def test_buka_bukti_tier_s_jadi_kalimat_biasa(self):
        self.gerbang.galat = PermissionError("episode ep1 tier S")
        with mock.patch("ingat.cari_memori.cari", return_value=JAWAB_ISI):
            win, ok = self._cari(lambda w: _cari_widget(w, "Listbox").size() == 2)
            self.assertTrue(ok)
            self.assertTrue(self._klik_bukti(lambda w: any("rahasia" in t for t in _label_teks(w))))
            for t in _label_teks(win):
                self.assertNotIn("PermissionError", t)


STATUS_HIJAU = {"lampu": "hijau", "pesan": "Tersambung dan hidup.",
                "butir": [{"nama": "Claude Desktop", "ok": True, "pesan": "Terpasang di komputer ini."},
                          {"nama": "Entri ingat", "ok": True, "pesan": "Sudah terdaftar."},
                          {"nama": "Server ingat", "ok": True, "pesan": "hidup"}]}


class JendelaKoneksi(KasusTk):
    """Tombol Sambungkan + lampu status, tanpa menyentuh Claude Desktop sungguhan."""

    def setUp(self):
        super().setUp()
        self.app = AppPalsu()
        # jendela ini juga menggambar status klien dari store — cukup dikosongkan
        p = mock.patch.object(panel, "status_koneksi", return_value=[])
        p.start()
        self.addCleanup(p.stop)
        self.ref = {}

    def _buka(self, syarat, aksi=None, batas=5.0):
        def mulai():
            win = self._catat(panel.bangun_jendela_koneksi(self.root, self.app, lambda *_: None))
            win.withdraw()
            self.ref["win"] = win
            if aksi:
                aksi(win)
        ok = self._putar(mulai, lambda: syarat(self.ref["win"]), batas)
        return self.ref.get("win"), ok

    @staticmethod
    def _lampu(win):
        return [w for w in _widget(win) if w.winfo_class() == "Label" and str(w.cget("text")) == "●"]

    def test_lampu_hijau_dan_tiga_butir(self):
        with mock.patch("ingat.sambung.status", return_value=STATUS_HIJAU):
            win, ok = self._buka(lambda w: self._lampu(w) and str(self._lampu(w)[0].cget("fg")) == "#15803d")
            self.assertTrue(ok, "lampu sambungan tak jadi hijau")
            self.assertEqual(len(self._lampu(win)), 1)
            gabung = "\n".join(t.get("1.0", "end") for t in _widget(win) if t.winfo_class() == "Text")
            self.assertIn("✓ Claude Desktop", gabung)
            self.assertIn("✓ Server ingat", gabung)

    def test_tombol_mcpb_tetap_ada(self):
        with mock.patch("ingat.sambung.status", return_value=STATUS_HIJAU):
            win, _ = self._buka(lambda w: self._lampu(w) and str(self._lampu(w)[0].cget("fg")) != "#6b7280")
            self.assertIsNotNone(_cari_widget(win, "TButton", "Siapkan MCPB (Claude Desktop)"),
                                 "jalur MCPB tak boleh hilang — itu yang terbukti hidup di Claude Desktop 2026")
            self.assertIsNotNone(_cari_widget(win, "TButton", "Siapkan ekstensi web"))
            self.assertIsNotNone(_cari_widget(win, "TButton", "Sambungkan"))

    def test_status_melempar_jadi_lampu_merah(self):
        with mock.patch("ingat.sambung.status", side_effect=OSError("berkas")):
            _, ok = self._buka(lambda w: self._lampu(w) and str(self._lampu(w)[0].cget("fg")) == "#b91c1c")
            self.assertTrue(ok)

    def test_sambung_berhasil_pakai_showinfo(self):
        hasil = {"berhasil": True, "berubah": True, "pesan": "Tersambung. Tutup lalu buka lagi Claude Desktop."}
        with mock.patch("ingat.sambung.status", return_value=STATUS_HIJAU), \
                mock.patch("ingat.sambung.sambungkan", return_value=hasil) as sambung, \
                mock.patch("tkinter.messagebox.showinfo") as info, \
                mock.patch("tkinter.messagebox.showerror") as galat:
            _, ok = self._buka(lambda w: info.called,
                               lambda w: _cari_widget(w, "TButton", "Sambungkan").invoke())
            self.assertTrue(ok)
            galat.assert_not_called()
            self.assertFalse(sambung.call_args.kwargs.get("paksa", False))
            self.assertIn("Claude Desktop", str(info.call_args.args[1]))

    def test_sambung_gagal_pakai_pesan_modul_apa_adanya(self):
        pesan = "Claude Desktop belum ditemukan di komputer ini."
        with mock.patch("ingat.sambung.status", return_value=STATUS_HIJAU), \
                mock.patch("ingat.sambung.sambungkan", return_value={"berhasil": False, "pesan": pesan}), \
                mock.patch("tkinter.messagebox.showerror") as galat:
            _, ok = self._buka(lambda w: galat.called,
                               lambda w: _cari_widget(w, "TButton", "Sambungkan").invoke())
            self.assertTrue(ok)
            self.assertEqual(str(galat.call_args.args[1]), pesan)

    def test_berkas_rusak_ditawarkan_paksa(self):
        rusak = {"berhasil": False, "pesan": "Berkas pengaturan Claude Desktop rusak (bukan JSON yang sah)."}
        sukses = {"berhasil": True, "pesan": "Tersambung."}
        with mock.patch("ingat.sambung.status", return_value=STATUS_HIJAU), \
                mock.patch("ingat.sambung.sambungkan", side_effect=[rusak, sukses]) as sambung, \
                mock.patch("tkinter.messagebox.askyesno", return_value=True) as tanya, \
                mock.patch("tkinter.messagebox.showinfo") as info:
            _, ok = self._buka(lambda w: info.called,
                               lambda w: _cari_widget(w, "TButton", "Sambungkan").invoke())
            self.assertTrue(ok)
            tanya.assert_called_once()
            self.assertEqual(sambung.call_count, 2)
            self.assertTrue(sambung.call_args_list[1].kwargs["paksa"])

    def test_sambungkan_melempar_tak_bocorkan_traceback(self):
        with mock.patch("ingat.sambung.status", return_value=STATUS_HIJAU), \
                mock.patch("ingat.sambung.sambungkan", side_effect=ValueError("boom")), \
                mock.patch("tkinter.messagebox.showerror") as galat:
            _, ok = self._buka(lambda w: galat.called,
                               lambda w: _cari_widget(w, "TButton", "Sambungkan").invoke())
            self.assertTrue(ok)
            self.assertNotIn("boom", str(galat.call_args.args[1]))
            self.assertNotIn("ValueError", str(galat.call_args.args[1]))

    def test_putuskan_minta_konfirmasi_dulu(self):
        with mock.patch("ingat.sambung.status", return_value=STATUS_HIJAU), \
                mock.patch("ingat.sambung.putuskan") as putus, \
                mock.patch("tkinter.messagebox.askyesno", return_value=False) as tanya:
            self._buka(lambda w: tanya.called,
                       lambda w: _cari_widget(w, "TButton", "Putuskan").invoke())
            tanya.assert_called_once()
            putus.assert_not_called()


class StorePalsu:
    def ringkasan_metrik(self):
        return {"episode_aktif": 3, "pelajaran_aktif": 1, "prosedur_aktif": 0, "alarm": []}


class PanelUtama(KasusTk):
    """Bangun SELURUH jendela utama lewat jalankan(), tanpa mainloop dan tanpa server.

    Isi `jalankan()` adalah satu closure raksasa: NameError di dalamnya tidak akan pernah
    terlihat dari `import ingat.panel`, hanya dari membangunnya sungguhan seperti ini.
    `tkinter.Tk` diganti Toplevel di bawah root bersama — root Tk kedua di satu proses
    adalah interpreter Tcl kedua, dan itu yang menggugurkan proses uji."""

    def setUp(self):
        super().setUp()
        import tkinter as tk
        self.dir = tempfile.mkdtemp(prefix="ingat-panel-")
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        kasus = self

        class TopDiam(tk.Toplevel):
            """mainloop pertama (milik jalankan) dilewati; sesudahnya mainloop asli dipakai
            supaya uji bisa mengemudikan thread pekerja."""

            def __init__(self, *a, **k):
                super().__init__(kasus.root)
                self.withdraw()
                kasus.jendela.append(self)
                kasus.ref = self
                self._sudah_dilewati = False

            def mainloop(self, *a, **k):
                if not self._sudah_dilewati:
                    self._sudah_dilewati = True
                    return None
                return super().mainloop(*a, **k)

        self.app = AppPalsu(GatewayPalsu())
        self.app.store = StorePalsu()
        self.app.konfig = {"embedding": {"jenis": "lokal", "model": "e5"}, "vault": None}
        self.app.relay = False
        for sasaran, nilai in (("tkinter.Tk", TopDiam),
                               ("ingat.aplikasi.Aplikasi", mock.Mock(return_value=self.app)),
                               ("ingat.aplikasi.muat_konfig", mock.Mock(return_value={})),
                               ("ingat.api.jalankan_server", mock.Mock()),
                               ("ingat.pantau.layani_pantau", mock.Mock())):
            p = mock.patch(sasaran, nilai)
            p.start()
            self.addCleanup(p.stop)
        # pemakaian.jsonl + panel-prefs.json jangan menyentuh ~/.ingat milik Tuan Muda
        p = mock.patch.object(panel, "DIR_INGAT", self.dir)
        p.start()
        self.addCleanup(p.stop)

    def _jalankan(self, st_startup):
        with mock.patch("ingat.startup.status_startup", return_value=st_startup):
            self.assertEqual(panel.jalankan(None), 0)
        return self.ref

    @staticmethod
    def _centang(win):
        for w in _widget(win):
            if w.winfo_class() == "TCheckbutton" and "Nyala otomatis" in str(w.cget("text")):
                return w
        return None

    def _nilai_centang(self, cb):
        return str(self.root.getvar(str(cb.cget("variable")))) in ("1", "True", "true")

    @staticmethod
    def _log(win):
        return "\n".join(t.get("1.0", "end") for t in _widget(win) if t.winfo_class() == "Text")

    def test_panel_terbangun_dengan_tombol_dan_centang_baru(self):
        win = self._jalankan({"aktif": True, "lawas": [], "folder": r"C:\Startup", "galat": None})
        self.assertIsNotNone(_cari_widget(win, "TButton", "Cari memori"))
        self.assertIsNotNone(_cari_widget(win, "TButton", "Koneksi AI"))
        cb = self._centang(win)
        self.assertIsNotNone(cb, "centang nyala-otomatis tak terpasang")
        # centang dibaca dari DISK, bukan dari panel-prefs.json yang masih kosong
        self.assertTrue(self._nilai_centang(cb))

    def test_centang_mati_bila_pintasan_tak_ada(self):
        win = self._jalankan({"aktif": False, "lawas": [], "folder": r"C:\Startup", "galat": None})
        self.assertFalse(self._nilai_centang(self._centang(win)))

    def test_entri_lawas_diperingatkan_di_log(self):
        win = self._jalankan({"aktif": True, "folder": r"C:\Startup",
                              "lawas": [r"C:\Startup\ingat-autostart.vbs"], "galat": None})
        log = self._log(win)
        self.assertIn("ingat-autostart.vbs", log)
        self.assertIn("PERHATIAN", log)

    def test_mematikan_centang_memanggil_alih_startup(self):
        win = self._jalankan({"aktif": True, "lawas": [], "folder": r"C:\Startup", "galat": None})
        cb = self._centang(win)
        mati = {"aktif": False, "dihapus": [r"C:\Startup\ingat-panel.lnk"], "folder": r"C:\Startup"}
        with mock.patch("ingat.startup.alih_startup", return_value=mati) as alih, \
                mock.patch("ingat.startup.status_startup", return_value={"aktif": False, "lawas": []}):
            ok = self._putar(cb.invoke, lambda: "DIMATIKAN" in self._log(win))
            self.assertTrue(ok, self._log(win))
            alih.assert_called_once_with(False)
            self.assertFalse(self._nilai_centang(cb))

    def test_gagal_menyalakan_mengembalikan_centang_ke_keadaan_disk(self):
        win = self._jalankan({"aktif": False, "lawas": [], "folder": r"C:\Startup", "galat": None})
        cb = self._centang(win)
        with mock.patch("ingat.startup.alih_startup", side_effect=OSError("akses ditolak")), \
                mock.patch("ingat.startup.status_startup", return_value={"aktif": False, "lawas": []}):
            ok = self._putar(cb.invoke, lambda: "GAGAL" in self._log(win))
            self.assertTrue(ok, self._log(win))
            # centang tidak boleh berbohong: pintasannya memang tidak jadi dibuat
            self.assertFalse(self._nilai_centang(cb))
            self.assertNotIn("akses ditolak", self._log(win))

    def test_tombol_cari_membuka_jendela_cari(self):
        win = self._jalankan({"aktif": False, "lawas": [], "folder": None, "galat": None})
        with mock.patch("ingat.cari_memori.cari", return_value=JAWAB_ISI):
            _cari_widget(win, "TButton", "Cari memori").invoke()
        anak = [w for w in win.winfo_children() if w.winfo_class() == "Toplevel"]
        self.assertEqual(len(anak), 1)
        self.jendela.append(anak[0])
        self.assertIsNotNone(_cari_widget(anak[0], "TButton", "Cari"))


if __name__ == "__main__":
    unittest.main()
