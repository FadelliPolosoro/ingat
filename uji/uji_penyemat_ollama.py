# SPDX-License-Identifier: Apache-2.0
"""Uji adapter Ollama tanpa jaringan: pembuka disuntik. Memastikan prefiks e5, potong 1.500, normalisasi, cek dimensi."""
from __future__ import annotations

import io
import json
import math
import unittest

from ingat.vektor import PenyematOllama


class _Respons(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _pembuka_palsu(rekam: list, dim: int = 4, jumlah: int = 1):
    def buka(req, timeout=None):
        rekam.append(json.loads(req.data.decode()))
        emb = [[1.0, 2.0, 2.0, 0.0][:dim] + [0.0] * max(0, dim - 4) for _ in range(jumlah)]
        return _Respons(json.dumps({"embeddings": emb}).encode())
    return buka


class Ollama(unittest.TestCase):
    def test_prefiks_potong_normalisasi(self):
        rekam: list = []
        p = PenyematOllama(host="http://127.0.0.1:11434/", model="ingat-e5-base", dim=4, pembuka=_pembuka_palsu(rekam))
        v = p.semat("x" * 3000)
        self.assertEqual(rekam[0]["model"], "ingat-e5-base")
        self.assertTrue(rekam[0]["input"].startswith("passage: "))
        self.assertEqual(len(rekam[0]["input"]), len("passage: ") + 1500)
        self.assertAlmostEqual(math.sqrt(sum(x * x for x in v)), 1.0, places=6)
        p.semat_query("tanya")
        self.assertTrue(rekam[1]["input"].startswith("query: "))

    def test_dimensi_tidak_cocok_error_keras(self):
        p = PenyematOllama(dim=8, pembuka=_pembuka_palsu([], dim=4))
        with self.assertRaises(RuntimeError):
            p.semat("apa saja")

    def test_jumlah_vektor_salah(self):
        p = PenyematOllama(dim=4, pembuka=_pembuka_palsu([], dim=4, jumlah=2))
        with self.assertRaises(RuntimeError):
            p.semat("apa saja")


if __name__ == "__main__":
    unittest.main()
