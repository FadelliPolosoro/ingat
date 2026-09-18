# SPDX-License-Identifier: Apache-2.0
"""A1 — backup & restore portabel (engine lokal).

Membungkus SELURUH keadaan ingat jadi satu tarball: store (SQLite + penyimpanan dingin),
vault (pelajaran/prosedur/norma), dan konfigurasi. Tujuannya "pindah perangkat": pulihkan
di mesin baru → lanjut kerja seolah tak pernah berpindah.

Dua sifat yang dijaga:
1. **Snapshot SQLite konsisten** lewat API backup bawaan (`sqlite3.Connection.backup`), BUKAN
   menyalin berkas saat WAL hidup — kalau tidak, `-wal` yang belum ter-checkpoint (bisa MB-an)
   hilang dan store dipulihkan basi. Snapshot menghasilkan satu `ingat.sqlite` utuh.
2. **Checksum SHA-256** berdampingan (`<tar>.sha256`) — restore menolak tarball yang rusak/terpotong.

PERINGATAN tier S: tarball memuat episode tier S VERBATIM (K10). Aman untuk simpanan lokal
(folder/USB) yang tetap di kendali Tuan Muda. Untuk diunggah ke hosting pihak ketiga, ia WAJIB
dienkripsi lebih dulu — tier S tak boleh keluar mesin dalam bentuk terbaca (K28/K30). Enkripsi
adalah lapisan berikutnya, sebelum jalur FTP disambung.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shutil
import sqlite3
import tarfile
import tempfile

VERSI_BACKUP = 1
_AKAR_ARSIP = "ingat-backup"  # nama folder di dalam tarball


def _versi() -> str:
    try:
        from . import __version__
        return __version__
    except Exception:
        return "?"


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blok in iter(lambda: f.read(65536), b""):
            h.update(blok)
    return h.hexdigest()


def _snapshot_db(src: str, dest: str) -> None:
    """Snapshot SQLite konsisten (menangkap WAL) via API backup, bukan salin berkas mentah."""
    s = sqlite3.connect(src)
    try:
        d = sqlite3.connect(dest)
        try:
            s.backup(d)
        finally:
            d.close()
    finally:
        s.close()


def _hitung(db_path: str) -> dict:
    """Jumlah item per tabel — untuk metadata (verifikasi kasar setelah restore)."""
    conn = sqlite3.connect(db_path)
    try:
        out = {}
        for tabel in ("episode", "pelajaran", "prosedur", "norma"):
            try:
                out[tabel] = conn.execute(f"SELECT COUNT(*) FROM {tabel}").fetchone()[0]
            except sqlite3.Error:
                out[tabel] = None
        return out
    finally:
        conn.close()


def _extract_aman(tar: tarfile.TarFile, dest: str) -> None:
    """Ekstrak dengan pagar path-traversal (Python 3.12: filter='data')."""
    try:
        tar.extractall(dest, filter="data")
    except TypeError:  # Python < 3.12 tak punya parameter filter
        tar.extractall(dest)


def buat_backup(dir_ingat: str, keluar: str | None = None, sandi: str | None = None) -> dict:
    """Bungkus keadaan ingat di `dir_ingat` (~/.ingat) jadi tarball di `keluar`.
    Bila `sandi` diberikan → tarball dienkripsi (ekstensi `.tar.gz.enc`).
    Bila `keluar` None → `dir_ingat/backup/ingat-backup-<waktu>.tar.gz[.enc]`. Kembalikan metadata."""
    dir_ingat = os.path.abspath(os.path.expanduser(dir_ingat))
    dir_data = os.path.join(dir_ingat, "data")
    db = os.path.join(dir_data, "ingat.sqlite")
    if not os.path.isfile(db):
        raise FileNotFoundError(f"store tidak ditemukan: {db}")

    waktu = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    if keluar is None:
        outdir = os.path.join(dir_ingat, "backup")
        os.makedirs(outdir, exist_ok=True)
        keluar = os.path.join(outdir, f"ingat-backup-{waktu}.tar.gz")
    keluar = os.path.abspath(os.path.expanduser(keluar))
    os.makedirs(os.path.dirname(keluar) or ".", exist_ok=True)

    stage = tempfile.mkdtemp(prefix="ingat-backup-")
    try:
        os.makedirs(os.path.join(stage, "data"), exist_ok=True)
        _snapshot_db(db, os.path.join(stage, "data", "ingat.sqlite"))
        for sub in ("dingin", "sesi"):
            src = os.path.join(dir_data, sub)
            if os.path.isdir(src):
                shutil.copytree(src, os.path.join(stage, "data", sub))
        vault = os.path.join(dir_ingat, "vault")
        if os.path.isdir(vault):
            shutil.copytree(vault, os.path.join(stage, "vault"))
        cfg = os.path.join(dir_ingat, "konfigurasi.json")
        if os.path.isfile(cfg):
            shutil.copy2(cfg, os.path.join(stage, "konfigurasi.json"))

        meta = {
            "versi_backup": VERSI_BACKUP,
            "waktu": dt.datetime.now().isoformat(timespec="seconds"),
            "ingat_versi": _versi(),
            "jumlah": _hitung(os.path.join(stage, "data", "ingat.sqlite")),
        }
        with open(os.path.join(stage, "metadata.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        with tarfile.open(keluar, "w:gz") as tar:
            tar.add(stage, arcname=_AKAR_ARSIP)

        if sandi:
            from .kripto import enkripsi
            berkas_enc = keluar + ".enc"
            enkripsi(keluar, berkas_enc, sandi)
            os.remove(keluar)
            keluar = berkas_enc
            meta["terenkripsi"] = True

        sha = _sha256(keluar)
        with open(keluar + ".sha256", "w", encoding="utf-8") as f:
            f.write(sha + "  " + os.path.basename(keluar) + "\n")

        meta["berkas"] = keluar
        meta["sha256"] = sha
        meta["ukuran"] = os.path.getsize(keluar)
        return meta
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def pulihkan_backup(berkas: str, target: str, timpa: bool = False,
                    verifikasi: bool = True, sandi: str | None = None,
                    pulihkan_konfig: bool = True) -> dict:
    """Pulihkan tarball `berkas` ke `target` (~/.ingat). Menolak bila target sudah berisi
    store kecuali `timpa=True`. Verifikasi checksum bila `<berkas>.sha256` ada.
    Bila berkas terenkripsi (magic INGAT1/INGAT2), `sandi` wajib diberikan.

    `pulihkan_konfig=False` menyisakan konfigurasi.json milik mesin tujuan. Wajib dipakai
    saat sinkron data ke mesin lain (mis. laptop → VPS): konfig memuat path absolut khas
    mesin asal (`dir_data`, `vault`) dan blok `jauh`/`server`; menimpanya membuat mesin
    tujuan menunjuk path yang tidak ada, atau lebih buruk, mengarahkan tulisan ke host lain."""
    berkas = os.path.abspath(os.path.expanduser(berkas))
    if not os.path.isfile(berkas):
        raise FileNotFoundError(berkas)

    if verifikasi:
        sha_file = berkas + ".sha256"
        if os.path.isfile(sha_file):
            with open(sha_file, encoding="utf-8") as f:
                isi_sha = f.read().split()
            harap = isi_sha[0] if isi_sha else ""
            nyata = _sha256(berkas)
            if not harap or harap != nyata:
                raise ValueError(f"checksum tidak cocok: harap {harap[:12]}… != nyata {nyata[:12]}…")

    from .kripto import adalah_terenkripsi
    _berkas_dec = None
    if adalah_terenkripsi(berkas):
        if not sandi:
            raise ValueError("Berkas terenkripsi — sandi wajib diberikan (--sandi)")
        from .kripto import dekripsi
        _berkas_dec = berkas + ".dec.tar.gz"
        dekripsi(berkas, _berkas_dec, sandi)
        berkas = _berkas_dec

    target = os.path.abspath(os.path.expanduser(target))
    if os.path.isdir(os.path.join(target, "data")) and not timpa:
        raise FileExistsError(f"target sudah berisi data ({target}); pakai timpa=True untuk menimpa")

    stage = tempfile.mkdtemp(prefix="ingat-restore-")
    try:
        with tarfile.open(berkas, "r:gz") as tar:
            _extract_aman(tar, stage)
        akar = os.path.join(stage, _AKAR_ARSIP)
        if not os.path.isdir(akar):
            raise ValueError(f"struktur backup tak dikenali (tak ada folder {_AKAR_ARSIP})")
        with open(os.path.join(akar, "metadata.json"), encoding="utf-8") as f:
            meta = json.load(f)
        if meta.get("versi_backup") != VERSI_BACKUP:
            raise ValueError(f"versi backup '{meta.get('versi_backup')}' tak dikenal (diharap {VERSI_BACKUP})")

        os.makedirs(target, exist_ok=True)
        for sub in ("data", "vault"):
            src = os.path.join(akar, sub)
            if os.path.isdir(src):
                dst = os.path.join(target, sub)
                if os.path.isdir(dst):
                    if not timpa:
                        raise FileExistsError(f"{dst} sudah ada; pakai timpa=True")
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
        cfg = os.path.join(akar, "konfigurasi.json")
        if os.path.isfile(cfg) and pulihkan_konfig:
            shutil.copy2(cfg, os.path.join(target, "konfigurasi.json"))
            meta["konfig_dipulihkan"] = True
        else:
            meta["konfig_dipulihkan"] = False

        meta["dipulihkan_ke"] = target
        return meta
    finally:
        shutil.rmtree(stage, ignore_errors=True)
        if _berkas_dec and os.path.isfile(_berkas_dec):
            os.remove(_berkas_dec)


# ── Unggah backup ke VPS via SCP ──

def unggah_ke_vps(berkas: str, host: str = "ingat-vps",
                  dir_tujuan: str = "/opt/ingat/backup",
                  sandi: str | None = None) -> dict:
    """Unggah tarball backup (terenkripsi bila `sandi`) ke VPS via SCP.

    Alur: buat backup → enkripsi (bila sandi) → SCP ke VPS → verifikasi checksum di VPS.
    `host` adalah alias SSH (~/.ssh/config) atau user@host.
    K28: tier S wajib dienkripsi sebelum keluar mesin.
    """
    import subprocess

    berkas = os.path.abspath(os.path.expanduser(berkas))
    if not os.path.isfile(berkas):
        raise FileNotFoundError(f"berkas backup tidak ditemukan: {berkas}")

    nama = os.path.basename(berkas)
    sha_lokal = _sha256(berkas)
    sha_berkas = berkas + ".sha256"
    if not os.path.isfile(sha_berkas):
        with open(sha_berkas, "w", encoding="utf-8") as f:
            f.write(sha_lokal + "  " + nama + "\n")

    try:
        subprocess.run(
            ["ssh", host, "mkdir", "-p", dir_tujuan],
            check=True, capture_output=True, timeout=15,
        )
    except (subprocess.SubprocessError, OSError) as e:
        return {"ok": False, "galat": f"gagal buat folder di VPS: {e}"}

    try:
        subprocess.run(
            ["scp", berkas, sha_berkas, f"{host}:{dir_tujuan}/"],
            check=True, capture_output=True, timeout=300,
        )
    except (subprocess.SubprocessError, OSError) as e:
        return {"ok": False, "galat": f"gagal SCP: {e}"}

    try:
        r = subprocess.run(
            ["ssh", host, "cd", dir_tujuan, "&&", "sha256sum", "-c", nama + ".sha256"],
            capture_output=True, text=True, timeout=15,
        )
        checksum_ok = r.returncode == 0
    except (subprocess.SubprocessError, OSError):
        checksum_ok = False

    return {
        "ok": True,
        "berkas": nama,
        "tujuan": f"{host}:{dir_tujuan}/{nama}",
        "sha256": sha_lokal,
        "checksum_vps": "cocok" if checksum_ok else "gagal-verifikasi",
        "ukuran": os.path.getsize(berkas),
    }


def backup_dan_unggah(dir_ingat: str, host: str = "ingat-vps",
                      dir_tujuan: str = "/opt/ingat/backup",
                      sandi: str | None = None) -> dict:
    """Buat backup, enkripsi (bila sandi), lalu unggah ke VPS — satu langkah.

    K28: jika sandi diberikan, tarball dienkripsi 4-lapis (INGAT2) sebelum keluar mesin.
    K30: laptop otoritatif, VPS menyimpan cadangan — bukan sebaliknya.
    """
    meta = buat_backup(dir_ingat, sandi=sandi)
    hasil_unggah = unggah_ke_vps(meta["berkas"], host=host, dir_tujuan=dir_tujuan)
    meta["unggah"] = hasil_unggah
    return meta
