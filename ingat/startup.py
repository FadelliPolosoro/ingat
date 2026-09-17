# SPDX-License-Identifier: Apache-2.0
"""Nyala-otomatis Panel Kendali saat Windows menyala — lewat folder Startup pengguna.

Keputusan (K29 lanjutan): yang dipakai adalah folder
`%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Startup`, BUKAN registry
(`Run`) dan BUKAN Task Scheduler. Alasannya bukan teknis melainkan soal siapa yang
memegang kendali: folder itu tidak butuh hak admin, isinya kelihatan di File Explorer,
dan kalau panel rusak Tuan Muda bisa membatalkannya sendiri dengan satu kali Delete —
tanpa regedit, tanpa taskschd.msc.

Dua metode penulisan, dipilih otomatis:

1. **Pintasan `.lnk`** (utama). `pythoncom`/`win32com` TIDAK terpasang di mesin ini dan
   menambahkannya berarti menambah dependensi biner ke aplikasi yang sengaja nol-dependency,
   jadi COM `WScript.Shell` dipanggil lewat PowerShell yang sudah ada di setiap Windows.
   Path dikirim lewat variabel lingkungan, bukan disisipkan ke teks perintah — supaya path
   berspasi, tanda kutip, atau `&` tidak pernah ikut diurai oleh PowerShell.
2. **Berkas `.cmd`** (cadangan). Dipakai bila PowerShell tidak ada/gagal, atau diminta
   eksplisit. Lebih jelek (ada kedip jendela konsol sekejap saat boot) tapi selalu berhasil
   dan isinya bisa dibaca manusia.

Status SELALU dibaca dari disk (berkas ada atau tidak), tidak pernah dari berkas preferensi:
kalau Tuan Muda menghapus pintasannya lewat File Explorer, tombol di panel ikut mati sendiri.

Modul ini bebas Tkinter. Seluruh fungsi menerima `folder` supaya uji bisa menyuntikkan
direktori sementara dan tidak pernah menyentuh folder Startup asli.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

NAMA_LNK = "ingat-panel.lnk"
NAMA_CMD = "ingat-panel.cmd"

#: Kedua nama diperiksa saat status/nonaktifkan — entri lama metode lain harus ikut bersih.
NAMA_ENTRI = (NAMA_LNK, NAMA_CMD)

#: Entri auto-start ingat era sebelumnya (13 Sep 2026): menyalakan server serve(8765)+pantau(8790)
#: sebagai proses terpisah. Panel K29 menjalankan kedua server IN-PROCESS, jadi bila keduanya hidup
#: port sudah terpakai saat panel naik. Hanya DIDETEKSI, tidak dihapus otomatis — berkas itu dibuat
#: pemasangan lain dan penghapusannya keputusan Tuan Muda.
NAMA_LAWAS = ("ingat-autostart.vbs", "ingat-autostart.cmd")

_SUBDIR_STARTUP = ("Microsoft", "Windows", "Start Menu", "Programs", "Startup")

# Jangan munculkan jendela konsol hitam saat PowerShell dipanggil dari .exe windowed.
_TANPA_JENDELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def folder_startup(folder: str | None = None) -> str:
    """Folder Startup pengguna. `folder` (dipakai uji) menggantikan lokasi asli."""
    if folder:
        return os.path.abspath(os.path.expanduser(folder))
    appdata = os.environ.get("APPDATA")
    if not appdata:
        # Bukan Windows, atau APPDATA dilucuti — jangan menebak, biar pemanggil yang memutuskan.
        raise RuntimeError("APPDATA tidak ada — folder Startup Windows tak bisa ditentukan")
    return os.path.join(appdata, *_SUBDIR_STARTUP)


def sedang_beku() -> bool:
    """True bila berjalan sebagai .exe hasil PyInstaller, bukan dari source."""
    return bool(getattr(sys, "frozen", False))


def _pythonw() -> str:
    """Penafsir tanpa jendela konsol. python.exe akan menyisakan jendela hitam menganga
    sepanjang panel hidup — pythonw.exe tidak."""
    exe = sys.executable or ""
    kandidat = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.isfile(kandidat):
        return kandidat
    return exe or shutil.which("pythonw") or shutil.which("python") or "python"


def target_peluncuran() -> dict:
    """Apa yang harus diluncurkan saat boot, sesuai cara aplikasi ini sedang dijalankan.

    Beku  → .exe itu sendiri, tanpa argumen.
    Source→ pythonw.exe + skrip peluncur panel di repo (`pasang/exe/ingat-panel.py`).
            Bukan `-m ingat`: itu CLI, bukan panel.
    """
    if sedang_beku():
        exe = os.path.abspath(sys.executable)
        return {"exe": exe, "argumen": [], "kerja": os.path.dirname(exe), "beku": True}
    akar = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return {"exe": _pythonw(),
            "argumen": [os.path.join(akar, "pasang", "exe", "ingat-panel.py")],
            "kerja": akar,
            "beku": False}


def _kutip(bagian: str, untuk_cmd: bool = False) -> str:
    """SELALU dikutip. ``untuk_cmd=True`` juga menggandakan ``%`` → ``%%`` agar cmd tidak
    mengembangkan variabel lingkungan di dalam path (kutip ganda TIDAK melindungi ``%``)."""
    if len(bagian) >= 2 and bagian.startswith('"') and bagian.endswith('"'):
        isi = bagian[1:-1]
    else:
        isi = bagian
    if untuk_cmd:
        isi = isi.replace("%", "%%")
    return f'"{isi}"'


def _baris_argumen(argumen: list[str]) -> str:
    return " ".join(_kutip(a) for a in argumen)


def _powershell() -> str | None:
    lewat = shutil.which("powershell") or shutil.which("pwsh")
    if lewat:
        return lewat
    baku = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                        "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    return baku if os.path.isfile(baku) else None


_SKRIP_PS = (
    "$w = New-Object -ComObject WScript.Shell; "
    "$s = $w.CreateShortcut($env:INGAT_LNK); "
    "$s.TargetPath = $env:INGAT_TARGET; "
    "$s.Arguments = $env:INGAT_ARGS; "
    "$s.WorkingDirectory = $env:INGAT_KERJA; "
    "$s.Description = 'Panel Kendali ingat'; "
    "$s.Save()"
)


def _tulis_lnk(jalur: str, exe: str, argumen: list[str], kerja: str) -> bool:
    ps = _powershell()
    if not ps:
        return False
    lingkungan = dict(os.environ)
    lingkungan.update({"INGAT_LNK": jalur, "INGAT_TARGET": exe,
                       "INGAT_ARGS": _baris_argumen(argumen), "INGAT_KERJA": kerja})
    try:
        hasil = subprocess.run(
            [ps, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", _SKRIP_PS],
            env=lingkungan, capture_output=True, timeout=30, creationflags=_TANPA_JENDELA)
    except (OSError, subprocess.SubprocessError):
        return False
    return hasil.returncode == 0 and os.path.isfile(jalur)


def _tulis_cmd(jalur: str, exe: str, argumen: list[str], kerja: str) -> None:
    # `start` memperlakukan argumen berkutip PERTAMA sebagai judul jendela; tanpa "" kosong
    # di depan, path exe berspasi akan jadi judul dan tidak ada apa pun yang dijalankan.
    baris = ['@echo off', f'cd /d {_kutip(kerja, untuk_cmd=True)} || exit /b 1',
             ('start "" ' + _kutip(exe, untuk_cmd=True) + (" " + " ".join(_kutip(a, untuk_cmd=True) for a in argumen) if argumen else "")).rstrip()]
    with open(jalur, "w", encoding="utf-8", newline="\r\n") as f:
        f.write("\n".join(baris) + "\n")


def _entri_ada(dir_startup: str) -> list[str]:
    return [os.path.join(dir_startup, n) for n in NAMA_ENTRI
            if os.path.isfile(os.path.join(dir_startup, n))]


def entri_lawas(folder: str | None = None) -> list[str]:
    """Entri auto-start ingat generasi lama yang masih nangkring di folder Startup.
    Dikembalikan supaya panel bisa memperingatkan — bukan untuk dihapus diam-diam."""
    try:
        dir_startup = folder_startup(folder)
    except RuntimeError:
        return []
    return [os.path.join(dir_startup, n) for n in NAMA_LAWAS
            if os.path.isfile(os.path.join(dir_startup, n))]


def status_startup(folder: str | None = None) -> dict:
    """Keadaan NYATA di disk. `aktif` False bila pengguna menghapus pintasannya sendiri."""
    try:
        dir_startup = folder_startup(folder)
    except RuntimeError as e:
        # Kunci yang sama persis dengan jalur normal: panel membaca `folder` tanpa .get()
        # dan KeyError di sini akan muncul sebagai traceback saat menggambar centang.
        return {"aktif": False, "berkas": None, "metode": None, "target": None,
                "lawas": [], "folder": None, "galat": str(e)}
    lawas = entri_lawas(dir_startup)
    ada = _entri_ada(dir_startup)
    if not ada:
        return {"aktif": False, "berkas": None, "metode": None, "target": None,
                "lawas": lawas, "folder": dir_startup, "galat": None}
    berkas = ada[0]
    metode = "lnk" if berkas.endswith(".lnk") else "cmd"
    target = None
    if metode == "cmd":
        # Isi .cmd bisa dibaca langsung; isi .lnk biner dan membacanya butuh COM —
        # tak sepadan hanya untuk menampilkan path di panel.
        try:
            with open(berkas, encoding="utf-8") as f:
                isi = f.read()
            for baris in isi.splitlines():
                if baris.lower().startswith("start "):
                    target = baris[len('start ""'):].strip()
                    break
        except OSError:
            pass
    return {"aktif": True, "berkas": berkas, "metode": metode, "target": target,
            "lawas": lawas, "folder": dir_startup, "galat": None}


def nonaktifkan_startup(folder: str | None = None) -> dict:
    """Hapus semua entri startup ingat. Aman dipanggil saat sudah mati (tidak error)."""
    try:
        dir_startup = folder_startup(folder)
    except RuntimeError as e:
        # Dipanggil panel lewat alih_startup(False) untuk menggambar centang: melempar di sini
        # berarti traceback sampai ke UI. Tanpa folder Startup, mematikan toh sudah tercapai.
        return {"aktif": False, "dihapus": [], "folder": None, "galat": str(e)}
    dihapus = []
    for jalur in _entri_ada(dir_startup):
        try:
            os.remove(jalur)
            dihapus.append(jalur)
        except OSError:
            pass
    return {"aktif": False, "dihapus": dihapus, "folder": dir_startup, "galat": None}


def aktifkan_startup(folder: str | None = None, exe: str | None = None,
                     argumen: list[str] | None = None, kerja: str | None = None,
                     paksa_cmd: bool = False) -> dict:
    """Pasang nyala-otomatis. Idempoten: entri lama (metode apa pun) dibersihkan lebih dulu,
    sehingga memanggil dua kali tetap menyisakan tepat satu entri.

    `exe`/`argumen`/`kerja` boleh dikosongkan — diisi dari `target_peluncuran()`.
    Bawaan `argumen` hanya ikut bila `exe` juga bawaan.
    """
    dir_startup = folder_startup(folder)
    os.makedirs(dir_startup, exist_ok=True)

    bawaan = target_peluncuran()
    exe_bawaan = not exe
    exe = bawaan["exe"] if exe_bawaan else os.path.abspath(os.path.expanduser(exe))

    if argumen is not None:
        argumen = list(argumen)
    else:
        # Argumen bawaan adalah skrip peluncur panel — menyuntikkannya ke exe pilihan
        # pemanggil membuat program lain dijalankan dengan skrip panel sebagai argumen.
        argumen = list(bawaan["argumen"]) if exe_bawaan else []

    if not kerja:
        # exe bawaan dari source adalah pythonw.exe di folder instalasi Python; dirname-nya
        # membuat panel mencari konfigurasi.json di sana, bukan di akar repo.
        kerja = bawaan["kerja"] if exe_bawaan else (os.path.dirname(exe) or bawaan["kerja"])

    nonaktifkan_startup(folder)

    metode = "cmd"
    jalur = os.path.join(dir_startup, NAMA_CMD)
    if not paksa_cmd and _tulis_lnk(os.path.join(dir_startup, NAMA_LNK), exe, argumen, kerja):
        metode, jalur = "lnk", os.path.join(dir_startup, NAMA_LNK)
    else:
        _tulis_cmd(jalur, exe, argumen, kerja)

    return {"aktif": True, "berkas": jalur, "metode": metode, "exe": exe,
            "argumen": argumen, "kerja": kerja, "folder": dir_startup}


def alih_startup(nyala: bool, folder: str | None = None) -> dict:
    """Satu pintu untuk tombol/centang di panel."""
    return aktifkan_startup(folder=folder) if nyala else nonaktifkan_startup(folder=folder)
