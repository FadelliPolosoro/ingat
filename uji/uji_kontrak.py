# SPDX-License-Identifier: Apache-2.0
"""Kunci tiga arah: tabel transisi_status di skema/ingat.sql (kontrak) harus identik dengan
TRANSISI + HANYA_MANUSIA di ingat/skema.py. Port TypeScript menguji hal yang sama terhadap SQL.
"""
from __future__ import annotations

import os
import re
import unittest

from ingat import skema

AKAR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SQL = os.path.join(AKAR, "skema", "ingat.sql")


def transisi_dari_sql() -> set[tuple[str, str, str, str]]:
    teks = open(SQL, encoding="utf-8").read()
    blok = teks.split("INSERT OR IGNORE INTO transisi_status", 1)[1].split(";", 1)[0]
    return set(re.findall(r"\(\s*'(\w+)',\s*'(\w+)',\s*'(\w+)',\s*'(\w+)'\s*\)", blok))


def transisi_dari_python() -> set[tuple[str, str, str, str]]:
    hasil = set()
    for jenis, peta in skema.TRANSISI.items():
        for dari, tujuan in peta.items():
            for ke in tujuan:
                oleh = "manusia" if (jenis, dari, ke) in skema.HANYA_MANUSIA else "keduanya"
                hasil.add((jenis, dari, ke, oleh))
    return hasil


class Kontrak(unittest.TestCase):
    def test_transisi_identik_dengan_kontrak_sql(self):
        sql, py = transisi_dari_sql(), transisi_dari_python()
        self.assertTrue(sql, "tabel transisi_status kosong / tidak terbaca")
        self.assertEqual(py - sql, set(), f"ada di Python, tidak di kontrak: {py - sql}")
        self.assertEqual(sql - py, set(), f"ada di kontrak, tidak di Python: {sql - py}")

    def test_transisi_manusia_ditolak_untuk_mesin(self):
        for jenis, dari, ke, oleh in transisi_dari_sql():
            if oleh == "manusia":
                with self.assertRaises(skema.TransisiTerlarang, msg=f"{jenis} {dari}->{ke} oleh mesin harus ditolak"):
                    skema.periksa_transisi(jenis, dari, ke, "mesin")
                skema.periksa_transisi(jenis, dari, ke, "manusia")


if __name__ == "__main__":
    unittest.main()
