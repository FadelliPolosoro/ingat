"""Adapter Screenpipe -> ingat: impor tangkapan layar dan transkripsi audio sebagai episode.

Screenpipe (mediar-ai/screenpipe) menangkap layar+audio terus-menerus, menyimpan ke
SQLite lokal. Modul ini membaca database Screenpipe dan mengimpor ke store ingat.

Strategi: batch import, idempoten (skip yang sudah diimpor via tanda `sesi`).
"""
from __future__ import annotations

import os
import sqlite3

from . import skema  # noqa: F401


def _cari_db_screenpipe() -> str | None:
    """Cari database Screenpipe di lokasi default per OS."""
    kandidat = [
        os.path.expanduser("~/.screenpipe/db.sqlite"),
        os.path.expanduser("~/AppData/Local/screenpipe/db.sqlite"),
        os.path.expanduser("~/Library/Application Support/screenpipe/db.sqlite"),
    ]
    for p in kandidat:
        if os.path.isfile(p):
            return p
    return None


def _baca_tangkapan_layar(db_path: str, sejak: str | None = None, batas: int = 100) -> list[dict]:
    """Baca tangkapan layar (OCR text) dari Screenpipe DB."""
    conn = sqlite3.connect(db_path, timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        tabel = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}

        if "ocr_text" in tabel:
            q = """SELECT f.id, f.timestamp, f.app_name, f.window_name, o.text
                   FROM frames f JOIN ocr_text o ON f.id = o.frame_id
                   WHERE length(o.text) > 10"""
            params: list = []
            if sejak:
                q += " AND f.timestamp > ?"
                params.append(sejak)
            q += " ORDER BY f.timestamp DESC LIMIT ?"
            params.append(batas)
        elif "frames" in tabel:
            q = ("SELECT id, timestamp, app_name, window_name, ocr_text as text "
                 "FROM frames WHERE length(ocr_text) > 10")
            params = []
            if sejak:
                q += " AND timestamp > ?"
                params.append(sejak)
            q += " ORDER BY timestamp DESC LIMIT ?"
            params.append(batas)
        else:
            return []

        return [dict(r) for r in conn.execute(q, params).fetchall()]
    except Exception:
        return []
    finally:
        conn.close()


def _baca_transkripsi(db_path: str, sejak: str | None = None, batas: int = 100) -> list[dict]:
    """Baca transkripsi audio dari Screenpipe DB."""
    conn = sqlite3.connect(db_path, timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        tabel = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        if "audio_transcriptions" not in tabel:
            return []
        q = ("SELECT id, timestamp, transcription, device_name "
             "FROM audio_transcriptions WHERE length(transcription) > 10")
        params: list = []
        if sejak:
            q += " AND timestamp > ?"
            params.append(sejak)
        q += " ORDER BY timestamp DESC LIMIT ?"
        params.append(batas)
        return [dict(r) for r in conn.execute(q, params).fetchall()]
    except Exception:
        return []
    finally:
        conn.close()


def _sesi_screenpipe(jenis: str, sp_id) -> str:
    """ID sesi deterministik untuk deduplikasi."""
    return f"ep-screenpipe-{jenis}-{sp_id}"


def impor(store, db_path: str | None = None, sejak: str | None = None,
          batas: int = 100, tier: str = "I") -> dict:
    """Impor tangkapan layar + transkripsi audio dari Screenpipe ke store ingat.

    Idempoten: episode dengan sesi ep-screenpipe-* yang sudah ada di-skip.
    """
    if db_path is None:
        db_path = _cari_db_screenpipe()
    if not db_path or not os.path.isfile(db_path):
        return {"layar": 0, "audio": 0, "skip": 0, "galat": 0,
                "pesan": f"Database Screenpipe tidak ditemukan. Cari di: {db_path or '(default)'}"}

    sesi_ada: set[str] = set()
    for ep in store.episode_semua():
        s = getattr(ep, "sesi", "") or ""
        if s.startswith("ep-screenpipe-"):
            sesi_ada.add(s)

    hasil = {"layar": 0, "audio": 0, "skip": 0, "galat": 0}

    for item in _baca_tangkapan_layar(db_path, sejak, batas):
        sesi = _sesi_screenpipe("layar", item["id"])
        if sesi in sesi_ada:
            hasil["skip"] += 1
            continue
        try:
            app_name = item.get("app_name", "") or ""
            window = item.get("window_name", "") or ""
            teks = item.get("text", "") or ""
            ringkas = f"{app_name}: {window}"[:80] if app_name else teks[:80]
            store.tambah_episode(
                isi=teks,
                sumber="screenpipe:screen",
                tier=tier,
                lingkup="global",
                jenis_kejadian="pola",
                ringkas=ringkas,
                instrumen=["screenpipe"],
                sesi=sesi,
            )
            hasil["layar"] += 1
        except Exception:
            hasil["galat"] += 1

    for item in _baca_transkripsi(db_path, sejak, batas):
        sesi = _sesi_screenpipe("audio", item["id"])
        if sesi in sesi_ada:
            hasil["skip"] += 1
            continue
        try:
            teks = item.get("transcription", "") or ""
            device = item.get("device_name", "") or ""
            ringkas = f"Transkripsi: {teks[:70]}"
            store.tambah_episode(
                isi=teks,
                sumber="screenpipe:audio",
                tier=tier,
                lingkup="global",
                jenis_kejadian="pola",
                ringkas=ringkas,
                instrumen=["screenpipe", device] if device else ["screenpipe"],
                sesi=sesi,
            )
            hasil["audio"] += 1
        except Exception:
            hasil["galat"] += 1

    return hasil


def status(db_path: str | None = None) -> dict:
    """Cek status koneksi Screenpipe: apakah DB ada, berapa rekam tersedia."""
    if db_path is None:
        db_path = _cari_db_screenpipe()
    if not db_path or not os.path.isfile(db_path):
        return {"terhubung": False, "jalur": db_path, "pesan": "Database tidak ditemukan"}

    conn = sqlite3.connect(db_path, timeout=5)
    try:
        tabel = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        info: dict = {"terhubung": True, "jalur": db_path, "tabel": sorted(tabel)}
        if "frames" in tabel:
            info["layar"] = conn.execute("SELECT COUNT(*) FROM frames").fetchone()[0]
        if "audio_transcriptions" in tabel:
            info["audio"] = conn.execute("SELECT COUNT(*) FROM audio_transcriptions").fetchone()[0]
        return info
    except Exception as e:
        return {"terhubung": False, "jalur": db_path, "pesan": str(e)}
    finally:
        conn.close()
