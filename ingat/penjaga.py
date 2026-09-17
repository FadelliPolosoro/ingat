# SPDX-License-Identifier: Apache-2.0
"""Layer 9+10: Penjaga keamanan — deteksi intrusi, eskalasi pertahanan, notifikasi.

Melacak percobaan gagal per IP dengan eskalasi eksponensial:
  3 gagal  → respons diperlambat 2 detik
  5 gagal  → ban 5 menit
  10 gagal → ban 1 jam
  20 gagal → ban 24 jam
  50 gagal → ban 7 hari + notifikasi KRITIS

Setiap percobaan dicatat: timestamp, IP, alasan, user-agent.
Data persisten di SQLite (survive restart). Notifikasi via webhook (opsional).
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from urllib.request import Request, urlopen

_log = logging.getLogger("ingat.penjaga")

_ESKALASI = [
    (3, 2, "delay"),           # 3 gagal → delay 2 detik
    (5, 300, "ban"),           # 5 gagal → ban 5 menit
    (10, 3600, "ban"),         # 10 gagal → ban 1 jam
    (20, 86400, "ban"),        # 20 gagal → ban 24 jam
    (50, 604800, "ban_kritis"),  # 50 gagal → ban 7 hari + notif
]

_DDL = """
CREATE TABLE IF NOT EXISTS penjaga_gagal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ip TEXT NOT NULL,
    waktu REAL NOT NULL,
    alasan TEXT,
    user_agent TEXT
);
CREATE TABLE IF NOT EXISTS penjaga_ban (
    ip TEXT PRIMARY KEY,
    sampai REAL NOT NULL,
    level INTEGER DEFAULT 0,
    total_gagal INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_penjaga_gagal_ip ON penjaga_gagal(ip);
CREATE INDEX IF NOT EXISTS idx_penjaga_ban_sampai ON penjaga_ban(sampai);
"""


_IP_AMAN = frozenset({"127.0.0.1", "::1", "localhost"})


class Penjaga:
    """Penjaga keamanan server ingat."""

    def __init__(self, db_path: str | None = None, webhook: str | None = None,
                 ip_aman: set[str] | None = None):
        if db_path is None:
            db_path = os.path.join(os.path.expanduser("~"), ".ingat", "penjaga.sqlite")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._db_path = db_path
        self._lock = threading.Lock()
        self._webhook = webhook
        self._ip_aman = ip_aman if ip_aman is not None else _IP_AMAN
        self._db = sqlite3.connect(db_path, check_same_thread=False)
        self._db.executescript(_DDL)
        self._bersihkan_kadaluarsa()

    # ------------------------------------------------------------------
    # API publik
    # ------------------------------------------------------------------

    def catat_gagal(self, ip: str, alasan: str = "", user_agent: str = "") -> dict:
        """Catat percobaan gagal. Kembalikan tindakan: {aksi, detik, level}."""
        if ip in self._ip_aman:
            return {"aksi": "ok", "detik": 0, "level": 0}
        kini = time.time()
        with self._lock:
            self._db.execute(
                "INSERT INTO penjaga_gagal (ip, waktu, alasan, user_agent) VALUES (?,?,?,?)",
                (ip, kini, alasan, user_agent),
            )
            self._db.commit()

            total = self._total_gagal(ip)
            aksi = self._tentukan_aksi(total)

            if aksi["aksi"] in ("ban", "ban_kritis"):
                sampai = kini + aksi["detik"]
                self._db.execute(
                    "INSERT OR REPLACE INTO penjaga_ban (ip, sampai, level, total_gagal) VALUES (?,?,?,?)",
                    (ip, sampai, aksi["level"], total),
                )
                self._db.commit()
                _log.warning("IP %s diban %d detik (level %d, total gagal: %d)",
                             ip, aksi["detik"], aksi["level"], total)

            if aksi["aksi"] == "ban_kritis":
                self._notif_kritis(ip, total, alasan)

            return aksi

    def ip_diblokir(self, ip: str) -> float:
        """Kembalikan sisa detik ban, atau 0 jika tidak diban."""
        if ip in self._ip_aman:
            return 0.0
        kini = time.time()
        with self._lock:
            row = self._db.execute(
                "SELECT sampai FROM penjaga_ban WHERE ip=?", (ip,)
            ).fetchone()
        if row and row[0] > kini:
            return row[0] - kini
        return 0.0

    def delay_untuk(self, ip: str) -> float:
        """Kembalikan detik delay yang harus diterapkan (0 jika tidak perlu)."""
        if ip in self._ip_aman:
            return 0.0
        with self._lock:
            total = self._total_gagal(ip)
        if total >= 3:
            return min(2.0 * (total // 3), 10.0)
        return 0.0

    def statistik(self) -> dict:
        """Ringkasan keamanan untuk /metrik."""
        with self._lock:
            kini = time.time()
            total_gagal = self._db.execute("SELECT COUNT(*) FROM penjaga_gagal").fetchone()[0]
            ban_aktif = self._db.execute(
                "SELECT COUNT(*) FROM penjaga_ban WHERE sampai > ?", (kini,)
            ).fetchone()[0]
            ip_unik = self._db.execute(
                "SELECT COUNT(DISTINCT ip) FROM penjaga_gagal"
            ).fetchone()[0]
            terbaru = self._db.execute(
                "SELECT ip, waktu, alasan FROM penjaga_gagal ORDER BY waktu DESC LIMIT 5"
            ).fetchall()
        return {
            "total_percobaan_gagal": total_gagal,
            "ban_aktif": ban_aktif,
            "ip_unik_gagal": ip_unik,
            "terbaru": [
                {"ip": r[0], "waktu": r[1], "alasan": r[2]} for r in terbaru
            ],
        }

    def reset_ip(self, ip: str) -> None:
        """Hapus semua catatan gagal dan ban untuk IP (untuk admin)."""
        with self._lock:
            self._db.execute("DELETE FROM penjaga_gagal WHERE ip=?", (ip,))
            self._db.execute("DELETE FROM penjaga_ban WHERE ip=?", (ip,))
            self._db.commit()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _total_gagal(self, ip: str) -> int:
        batas = time.time() - 604800  # hitung 7 hari terakhir
        row = self._db.execute(
            "SELECT COUNT(*) FROM penjaga_gagal WHERE ip=? AND waktu > ?",
            (ip, batas),
        ).fetchone()
        return row[0] if row else 0

    def _tentukan_aksi(self, total: int) -> dict:
        aksi = {"aksi": "ok", "detik": 0, "level": 0}
        for batas, detik, tipe in _ESKALASI:
            if total >= batas:
                aksi = {"aksi": tipe, "detik": detik, "level": batas}
        return aksi

    def _bersihkan_kadaluarsa(self) -> None:
        kini = time.time()
        self._db.execute("DELETE FROM penjaga_ban WHERE sampai < ?", (kini,))
        batas_lama = kini - 30 * 86400  # buang log > 30 hari
        self._db.execute("DELETE FROM penjaga_gagal WHERE waktu < ?", (batas_lama,))
        self._db.commit()

    def _notif_kritis(self, ip: str, total: int, alasan: str) -> None:
        pesan = (
            f"[INGAT PENJAGA] KRITIS: IP {ip} diban 7 hari "
            f"({total} percobaan gagal). Alasan terakhir: {alasan}"
        )
        _log.critical(pesan)
        if self._webhook:
            threading.Thread(
                target=self._kirim_webhook,
                args=(pesan,),
                daemon=True,
            ).start()

    def _kirim_webhook(self, pesan: str) -> None:
        try:
            data = json.dumps({"text": pesan, "content": pesan}).encode("utf-8")
            req = Request(self._webhook, data=data, method="POST")
            req.add_header("Content-Type", "application/json")
            with urlopen(req, timeout=10) as resp:
                _log.info("Webhook terkirim: %d", resp.status)
        except Exception as e:
            _log.error("Gagal kirim webhook: %s", e)
