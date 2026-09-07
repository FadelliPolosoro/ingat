# SPDX-License-Identifier: Apache-2.0
"""Migrasi v1→v2 harus menghasilkan struktur yang identik dengan DDL v2 segar (kolom, tabel, versi)."""
from __future__ import annotations

import os
import sqlite3
import unittest

AKAR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V1 = os.path.join(AKAR, "skema", "versi", "ingat-v1.sql")
V2 = os.path.join(AKAR, "skema", "ingat.sql")
MIGRASI = os.path.join(AKAR, "skema", "migrasi", "002-v1-ke-v2.sql")


def _struktur(db: sqlite3.Connection) -> dict[str, list[str]]:
    tabel = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    return {t: sorted(r[1] for r in db.execute(f"PRAGMA table_info({t})")) for t in tabel}


class Migrasi(unittest.TestCase):
    def test_v1_plus_migrasi_sama_dengan_v2_segar(self):
        lama = sqlite3.connect(":memory:")
        lama.executescript(open(V1, encoding="utf-8").read())
        lama.executescript(open(MIGRASI, encoding="utf-8").read())
        segar = sqlite3.connect(":memory:")
        segar.executescript(open(V2, encoding="utf-8").read())
        self.assertEqual(_struktur(lama), _struktur(segar), "kolom/tabel hasil migrasi harus identik dengan DDL v2")
        for db in (lama, segar):
            self.assertEqual(db.execute("SELECT nilai FROM meta WHERE kunci='versi_kontrak'").fetchone()[0], "2")
        # transisi pemulihan hadir di keduanya
        for db in (lama, segar):
            n = db.execute("SELECT COUNT(*) FROM transisi_status WHERE dari='dipersempit' AND ke IN ('aturan','aktif') AND oleh='manusia'").fetchone()[0]
            self.assertEqual(n, 2)

    def test_v1_diarsipkan_masih_v1(self):
        db = sqlite3.connect(":memory:")
        db.executescript(open(V1, encoding="utf-8").read())
        self.assertEqual(db.execute("SELECT nilai FROM meta WHERE kunci='versi_kontrak'").fetchone()[0], "1")


if __name__ == "__main__":
    unittest.main()
