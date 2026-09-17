# SPDX-License-Identifier: Apache-2.0
"""Satu tombol "Sambungkan" — pasang `ingat` sebagai server MCP di Claude Desktop.

Kenapa ada: menyambung selama ini menuntut pengguna menyunting `claude_desktop_config.json`
dengan tangan. Tuan Muda menulis, persis, "saya hanya lulusan SMP, tidak paham IT". Satu koma
salah di berkas itu mematikan SEMUA server MCP di Claude Desktop, bukan hanya milik ingat.
Modul ini memindahkan pekerjaan tersebut ke kode.

Empat kontrak yang tidak boleh dilanggar:

1. **Punya orang lain tidak disentuh.** Berkas dibaca utuh, hanya kunci `mcpServers.ingat`
   yang disisipkan/diperbarui, sisanya ditulis kembali apa adanya. Sebelum menulis selalu
   ada cadangan berlabel waktu.
2. **Idempoten.** Menekan "Sambungkan" sepuluh kali menghasilkan satu entri, dan sembilan
   kali terakhir tidak menulis apa pun (tidak ada cadangan sampah).
3. **Tidak pernah melempar jejak galat Python ke muka pengguna.** Setiap jalur gagal
   mengembalikan kalimat bahasa Indonesia yang bisa ditindaklanjuti orang awam.
4. **JSON rusak tidak ditimpa diam-diam.** Berkas rusak berarti berhenti dan lapor; menimpa
   berarti menghapus server MCP aplikasi lain yang mungkin masih tercatat di sana.

Bebas Tkinter dan bebas jaringan pada jalur bakunya — panel cukup memanggil `sambungkan()`
lalu `status()` dan menggambar lampu hijau/merah dari hasilnya.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import sys

NAMA_SERVER = "ingat"
KUNCI_SERVER = "mcpServers"
NAMA_BERKAS_KONFIG = "claude_desktop_config.json"

# Claude Desktop versi 2026 memasang ingat sebagai ekstensi MCPB, bukan lewat mcpServers.
# Status harus mengakui jalur itu juga, kalau tidak lampu merah padahal sambungannya hidup.
BERKAS_PASANGAN_EKSTENSI = "extensions-installations.json"
DIR_PENGATURAN_EKSTENSI = "Claude Extensions Settings"


class SambungGagal(Exception):
    """Kegagalan yang pesannya sudah layak ditampilkan apa adanya ke pengguna."""


# ---- lokasi berkas ------------------------------------------------------------

def dir_claude() -> str:
    """Folder data Claude Desktop pada sistem ini."""
    if sys.platform.startswith("win"):
        basis = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
        return os.path.join(basis, "Claude")
    if sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~"), "Library", "Application Support", "Claude")
    return os.path.join(os.path.expanduser("~"), ".config", "Claude")


def path_konfigurasi(dir_data: str | None = None) -> str:
    return os.path.join(dir_data or dir_claude(), NAMA_BERKAS_KONFIG)


def path_konfigurasi_ingat() -> str:
    return os.path.join(os.path.expanduser("~"), ".ingat", "konfigurasi.json")


def claude_terpasang(dir_data: str | None = None) -> bool:
    """Ada foldernya = aplikasinya pernah jalan. Berkas konfigurasi boleh belum ada."""
    return os.path.isdir(dir_data or dir_claude())


# ---- entri server -------------------------------------------------------------

def _akar_paket() -> str | None:
    """Folder induk paket `ingat` — None bila sedang berjalan dari .exe (sumbernya temporer)."""
    if getattr(sys, "frozen", False):
        return None
    akar = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return akar if os.path.exists(os.path.join(akar, "ingat", "__init__.py")) else None


def python_untuk_mcp() -> str | None:
    """Interpreter yang akan dijalankan Claude Desktop.

    `sys.executable` tidak bisa dipakai begitu saja: saat panel berjalan sebagai .exe hasil
    PyInstaller, nilainya adalah panel itu sendiri — bukan Python yang bisa menjalankan
    `-m ingat`. `python.exe`, bukan `python3`: nama itu tidak ada di Windows.
    """
    calon: list[str | None] = []
    if not getattr(sys, "frozen", False) and sys.executable:
        calon.append(sys.executable)
    calon += [shutil.which("python"), shutil.which("python3")]
    calon.append(os.path.join(os.path.expanduser("~"), "AppData", "Local", "Programs",
                              "Python", "Python312", "python.exe"))
    for c in calon:
        if c and os.path.exists(c) and not _alias_python3_windows(c):
            return c
    return None


def _alias_python3_windows(jalur: str) -> bool:
    """Benar bila `jalur` adalah `python3` di Windows — bukan interpreter sungguhan.

    Windows tidak pernah memasang `python3.exe`; yang ada di PATH biasanya alias Microsoft
    Store berukuran nol byte yang justru membuka halaman toko. Berkasnya ada (lolos
    os.path.exists), tapi dijalankan Claude Desktop ia langsung mati dan host MCP kehilangan
    stdio — "Server disconnected" tanpa sebab yang kelihatan.
    """
    if not sys.platform.startswith("win"):
        return False
    return os.path.basename(jalur).lower() in ("python3.exe", "python3")


def entri_ingat(python_exe: str | None = None, konfig_ingat: str | None = None,
                token: str | None = None, akar: str | None = None) -> dict:
    """Bentuk entri `mcpServers.ingat` yang diinginkan.

    Perintahnya sengaja langsung `python -m ingat ... mcp`, tanpa skrip peluncur perantara.
    Peluncur MCPB pernah memakai `os.execv` dan patah di Windows: exec di sana = spawn + exit,
    proses asli keluar, host MCP kehilangan pipe stdio, hasilnya "Server disconnected".
    Dijalankan langsung oleh host, stdin/stdout tetap milik host sejak detik pertama.
    """
    if token is None:
        from .jauh import baca_token
        token = baca_token(None)
    entri: dict = {
        "command": python_exe or python_untuk_mcp() or "python",
        "args": ["-m", "ingat", "--konfig", konfig_ingat or path_konfigurasi_ingat(), "mcp"],
    }
    lingkungan = {}
    if token:
        lingkungan["INGAT_TOKEN"] = token
    if akar is None:
        akar = _akar_paket()
    if akar:
        # Claude Desktop memanggil python dari folder kerjanya sendiri. Tanpa ini, `-m ingat`
        # hanya jalan kalau paketnya kebetulan sudah ter-pip-install di interpreter tersebut.
        lingkungan["PYTHONPATH"] = akar
    if lingkungan:
        entri["env"] = lingkungan
    return entri


# ---- baca / tulis konfigurasi -------------------------------------------------

def baca_konfigurasi(path: str) -> dict:
    """Isi berkas konfigurasi. Berkas belum ada → dict kosong (bukan galat)."""
    if not os.path.exists(path):
        return {}
    try:
        # utf-8-sig, bukan utf-8: BOM lumrah di Windows setelah berkas disunting editor lama,
        # dan isinya tetap sah — memvonisnya "rusak" berarti menuduh pengguna tanpa sebab.
        # UnicodeDecodeError ditangkap DI SINI, bukan di sekitar json.loads: pendekodean terjadi
        # saat f.read(), dan galat itu turunan ValueError — OSError tidak pernah menangkapnya.
        with open(path, encoding="utf-8-sig") as f:
            isi = f.read()
    except OSError as e:
        raise SambungGagal(
            "Berkas pengaturan Claude Desktop tidak bisa dibuka:\n" + path +
            "\nTutup Claude Desktop, lalu coba lagi."
        ) from e
    except UnicodeDecodeError as e:
        raise SambungGagal(
            "Berkas pengaturan Claude Desktop tidak bisa dibaca (huruf di dalamnya bukan UTF-8):\n"
            + path +
            "\nBuka berkas itu di Notepad, simpan ulang dengan Encoding: UTF-8, lalu coba lagi."
            "\nIngat tidak menimpanya supaya server lain di berkas itu tidak ikut hilang."
        ) from e
    if not isi.strip():
        return {}
    try:
        data = json.loads(isi)
    except json.JSONDecodeError as e:
        raise SambungGagal(
            "Berkas pengaturan Claude Desktop tidak bisa dibaca (isinya rusak):\n" + path +
            "\nIngat tidak menimpanya supaya server lain di berkas itu tidak ikut hilang."
        ) from e
    if not isinstance(data, dict):
        raise SambungGagal(
            "Berkas pengaturan Claude Desktop bentuknya tidak seperti seharusnya:\n" + path +
            "\nIngat tidak menimpanya supaya tidak ada yang ikut hilang."
        )
    return data


def buat_cadangan(path: str) -> str | None:
    """Salin berkas ke `<nama>.cadangan-YYYYMMDD-HHMMSS`. None bila memang belum ada berkasnya."""
    if not os.path.exists(path):
        return None
    cap = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    tujuan = f"{path}.cadangan-{cap}"
    n = 1
    while os.path.exists(tujuan):
        tujuan = f"{path}.cadangan-{cap}-{n}"
        n += 1
    try:
        shutil.copy2(path, tujuan)
    except OSError as e:
        raise SambungGagal(
            "Gagal membuat cadangan pengaturan Claude Desktop di:\n" + tujuan +
            "\nIngat berhenti di sini — tidak ada yang diubah."
        ) from e
    return tujuan


def _tulis_konfigurasi(path: str, data: dict) -> None:
    """Tulis lewat berkas sementara lalu ganti — supaya listrik mati di tengah tulis tidak
    meninggalkan konfigurasi separuh yang membuat Claude Desktop kehilangan semua server."""
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        sementara = path + ".tmp-ingat"
        with open(sementara, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(sementara, path)
    except OSError as e:
        raise SambungGagal(
            "Gagal menyimpan pengaturan Claude Desktop:\n" + path +
            "\nTutup Claude Desktop, lalu coba lagi."
        ) from e


# ---- tombol Sambungkan --------------------------------------------------------

def sambungkan(path: str | None = None, python_exe: str | None = None,
               konfig_ingat: str | None = None, token: str | None = None,
               akar: str | None = None, paksa: bool = False) -> dict:
    """Pasang/perbarui entri `ingat` di konfigurasi MCP Claude Desktop.

    `paksa=True` hanya untuk satu keadaan: berkas lama rusak dan pengguna sudah diberi tahu
    bahwa isinya akan dibuang. Cadangannya tetap dibuat lebih dulu.

    Kembalian: {"berhasil", "berubah", "pesan", "cadangan", "path"}.
    """
    path = path or path_konfigurasi()
    dir_data = os.path.dirname(path)
    hasil = {"berhasil": False, "berubah": False, "pesan": "", "cadangan": None, "path": path}

    if not claude_terpasang(dir_data):
        hasil["pesan"] = ("Claude Desktop belum ditemukan di komputer ini. Pasang dan jalankan "
                          "Claude Desktop sekali dulu, lalu tekan Sambungkan lagi.")
        return hasil
    if python_exe is None and python_untuk_mcp() is None:
        hasil["pesan"] = ("Python tidak ditemukan di komputer ini. Pasang Python 3.12 lebih dulu, "
                          "lalu tekan Sambungkan lagi.")
        return hasil

    try:
        try:
            data = baca_konfigurasi(path)
        except SambungGagal as e:
            if not paksa:
                hasil["pesan"] = str(e)
                return hasil
            hasil["cadangan"] = buat_cadangan(path)
            data = {}

        diinginkan = entri_ingat(python_exe, konfig_ingat, token, akar)
        server = data.get(KUNCI_SERVER)
        if not isinstance(server, dict):
            server = {}
        if server.get(NAMA_SERVER) == diinginkan and isinstance(data.get(KUNCI_SERVER), dict):
            hasil.update(berhasil=True, berubah=False,
                         pesan="Sudah tersambung. Tidak ada yang perlu diubah.")
            return hasil

        sudah_ada = NAMA_SERVER in server
        if hasil["cadangan"] is None:
            hasil["cadangan"] = buat_cadangan(path)
        server[NAMA_SERVER] = diinginkan
        data[KUNCI_SERVER] = server
        _tulis_konfigurasi(path, data)
    except SambungGagal as e:
        hasil["pesan"] = str(e)
        return hasil

    hasil.update(berhasil=True, berubah=True,
                 pesan=("Sambungan ingat diperbarui. Tutup lalu buka lagi Claude Desktop."
                        if sudah_ada else
                        "Tersambung. Tutup lalu buka lagi Claude Desktop supaya ingat muncul."))
    return hasil


def putuskan(path: str | None = None) -> dict:
    """Cabut entri `ingat` saja. Server MCP milik aplikasi lain tetap tinggal."""
    path = path or path_konfigurasi()
    hasil = {"berhasil": False, "berubah": False, "pesan": "", "cadangan": None, "path": path}
    try:
        data = baca_konfigurasi(path)
    except SambungGagal as e:
        hasil["pesan"] = str(e)
        return hasil
    server = data.get(KUNCI_SERVER)
    if not isinstance(server, dict) or NAMA_SERVER not in server:
        hasil.update(berhasil=True, pesan="Memang belum tersambung. Tidak ada yang dicabut.")
        return hasil
    try:
        hasil["cadangan"] = buat_cadangan(path)
        del server[NAMA_SERVER]
        data[KUNCI_SERVER] = server
        _tulis_konfigurasi(path, data)
    except SambungGagal as e:
        hasil["pesan"] = str(e)
        return hasil
    hasil.update(berhasil=True, berubah=True,
                 pesan="Sambungan ingat dicabut. Tutup lalu buka lagi Claude Desktop.")
    return hasil


# ---- status siap-tampil -------------------------------------------------------

def mcpb_terpasang(dir_data: str | None = None) -> bool:
    """ingat terpasang sebagai ekstensi MCPB dan tidak dimatikan pengguna."""
    dir_data = dir_data or dir_claude()
    try:
        with open(os.path.join(dir_data, BERKAS_PASANGAN_EKSTENSI), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return False
    ekstensi = data.get("extensions") if isinstance(data, dict) else None
    if not isinstance(ekstensi, dict):
        return False
    for id_ekstensi, info in ekstensi.items():
        nama = ((info or {}).get("manifest") or {}).get("name") if isinstance(info, dict) else None
        if nama != NAMA_SERVER and not str(id_ekstensi).endswith("." + NAMA_SERVER):
            continue
        setelan = os.path.join(dir_data, DIR_PENGATURAN_EKSTENSI, f"{id_ekstensi}.json")
        try:
            with open(setelan, encoding="utf-8") as f:
                aktif = json.load(f).get("isEnabled", True)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            aktif = True  # berkas setelan tak terbaca bukan berarti dimatikan
        if aktif:
            return True
    return False


def entri_terpasang(path: str | None = None) -> dict | None:
    """Entri `ingat` yang sedang tercatat, atau None. Berkas rusak dianggap None."""
    try:
        data = baca_konfigurasi(path or path_konfigurasi())
    except SambungGagal:
        return None
    server = data.get(KUNCI_SERVER)
    if not isinstance(server, dict):
        return None
    entri = server.get(NAMA_SERVER)
    return entri if isinstance(entri, dict) else None


def status(path: str | None = None, dir_data: str | None = None, penguji=None,
           host: str = "http://127.0.0.1:8765") -> dict:
    """Keadaan sambungan dalam bentuk yang tinggal digambar jadi lampu.

    `penguji(host, token) -> (ok, pesan)` disuntik di uji supaya modul ini tidak pernah
    menyentuh jaringan sungguhan saat diuji. Bakunya memakai `panel.uji_koneksi`.
    """
    path = path or path_konfigurasi(dir_data)
    dir_data = dir_data or os.path.dirname(path)
    butir = []

    ada_claude = claude_terpasang(dir_data)
    butir.append({"nama": "Claude Desktop", "ok": ada_claude,
                  "pesan": "Terpasang di komputer ini." if ada_claude else
                           "Belum ditemukan. Pasang Claude Desktop dulu."})

    entri = entri_terpasang(path)
    lewat_mcpb = mcpb_terpasang(dir_data)
    if entri is not None:
        pesan_entri = "Ingat sudah terdaftar di pengaturan Claude Desktop."
    elif lewat_mcpb:
        pesan_entri = "Ingat terpasang sebagai ekstensi Claude Desktop."
    else:
        pesan_entri = "Belum terdaftar. Tekan tombol Sambungkan."
    butir.append({"nama": "Entri ingat", "ok": entri is not None or lewat_mcpb, "pesan": pesan_entri})

    if penguji is None:
        from .panel import token_server, uji_koneksi
        penguji = lambda h, _t=None: uji_koneksi(h, token_server())  # noqa: E731
    try:
        hidup, pesan_server = penguji(host, None)
    except Exception:
        # Pemeriksa koneksi tidak boleh menjatuhkan tampilan status.
        hidup, pesan_server = False, "Server ingat tidak bisa diperiksa."
    butir.append({"nama": "Server ingat", "ok": bool(hidup), "pesan": str(pesan_server)})

    if not butir[0]["ok"] or not butir[1]["ok"]:
        lampu, ringkas = "merah", "Belum tersambung."
    elif not butir[2]["ok"]:
        lampu, ringkas = "kuning", "Sudah terdaftar, tapi server ingat belum hidup."
    else:
        lampu, ringkas = "hijau", "Tersambung dan hidup."
    return {"lampu": lampu, "pesan": ringkas, "butir": butir}
