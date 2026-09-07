# SPDX-License-Identifier: Apache-2.0
"""Embedding dan pencarian kemiripan (Lapis Indeks, Bab 10.1).

Dua penyemat:
- PenyematLokal  : hashed TF (kata + trigram karakter), tanpa model, tanpa jaringan.
                   Cukup untuk pencocokan pemicu/tugas; kualitas semantik terbatas.
- PenyematHTTP   : endpoint /embeddings OpenAI-compatible (OpenAI, DeepSeek, NIM,
                   atau endpoint privat vLLM/Ollama). Direkomendasikan untuk produksi.

Skor hibrida = 0.6*kosinus + 0.4*tumpang-tindih kata, supaya penyemat lokal
tetap andal saat kata kunci persis muncul.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import urllib.request
from array import array

_KATA = re.compile(r"[a-z0-9_]+")
_STOP = {
    "yang", "dan", "di", "ke", "dari", "untuk", "dengan", "ini", "itu", "atau", "pada", "adalah",
    "the", "a", "an", "of", "to", "in", "on", "for", "and", "or", "is", "are", "be",
    "akan", "sudah", "belum", "tidak", "bukan", "saat", "bila", "jika", "karena", "sebagai",
}


def tokenkan(teks: str) -> list[str]:
    return [t for t in _KATA.findall(teks.lower()) if t not in _STOP and len(t) > 1]


class PenyematLokal:
    nama = "lokal-hash-v1"

    def __init__(self, dim: int = 512):
        self.dim = dim

    def _slot(self, token: str) -> int:
        return int.from_bytes(hashlib.blake2b(token.encode(), digest_size=4).digest(), "big") % self.dim

    def semat(self, teks: str) -> list[float]:
        v = [0.0] * self.dim
        kata = tokenkan(teks)
        for k in kata:
            v[self._slot("w:" + k)] += 2.0
            if len(k) >= 5:
                for i in range(len(k) - 2):
                    v[self._slot("c:" + k[i:i + 3])] += 0.5
        # sublinear tf
        v = [math.log1p(x) if x else 0.0 for x in v]
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]


class PenyematHTTP:
    def __init__(self, base_url: str, api_key: str, model: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.nama = f"http:{model}"

    def semat(self, teks: str) -> list[float]:
        badan = json.dumps({"model": self.model, "input": teks[:8000]}).encode()
        req = urllib.request.Request(
            f"{self.base_url}/embeddings", data=badan, method="POST",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            data = json.loads(r.read().decode())
        v = data["data"][0]["embedding"]
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]


class PenyematOllama:
    """Ollama native /api/embed (K5). Prefiks e5 'query: '/'passage: ', potong 1.500 karakter
    (jendela 512 token), normalisasi L2. Host wajib eksplisit; tidak ada fallback ke API eksternal.
    `pembuka` dapat disuntik untuk uji tanpa jaringan."""

    MAKS_KARAKTER = 1500

    def __init__(self, host: str = "http://127.0.0.1:11434", model: str = "ingat-e5-base",
                 dim: int = 768, prefiks: bool = True, timeout: int = 60, pembuka=None):
        self.host = host.rstrip("/")
        self.model = model
        self.dim = dim
        self.prefiks = prefiks
        self.timeout = timeout
        self.nama = f"ollama:{model}"
        self._pembuka = pembuka or urllib.request.urlopen

    def _semat(self, teks: str, peran: str) -> list[float]:
        masukan = (f"{peran}: " if self.prefiks else "") + teks[: self.MAKS_KARAKTER]
        badan = json.dumps({"model": self.model, "input": masukan}).encode()
        req = urllib.request.Request(f"{self.host}/api/embed", data=badan, method="POST",
                                     headers={"Content-Type": "application/json"})
        with self._pembuka(req, timeout=self.timeout) as r:
            data = json.loads(r.read().decode())
        emb = data.get("embeddings") or []
        if len(emb) != 1:
            raise RuntimeError(f"Ollama mengembalikan {len(emb)} vektor untuk 1 teks")
        v = emb[0]
        if len(v) != self.dim:
            raise RuntimeError(f"dimensi {len(v)} ≠ {self.dim} ({self.model}); identitas model tidak cocok")
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]

    def semat(self, teks: str) -> list[float]:
        # Dipanggil untuk query maupun dokumen; Store menyematkan `ringkas` (dokumen) → 'passage'.
        return self._semat(teks, "passage")

    def semat_query(self, teks: str) -> list[float]:
        return self._semat(teks, "query")


def ke_blob(v: list[float]) -> bytes:
    return array("f", v).tobytes()


def dari_blob(b: bytes | None) -> list[float]:
    if not b:
        return []
    a = array("f")
    a.frombytes(b)
    return list(a)


def kosinus(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))  # keduanya sudah dinormalisasi


def tumpang_tindih(q: str, teks: str) -> float:
    a, b = set(tokenkan(q)), set(tokenkan(teks))
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def skor_hibrida(qvec: list[float], q: str, vec: list[float], teks: str) -> float:
    return 0.6 * max(0.0, kosinus(qvec, vec)) + 0.4 * tumpang_tindih(q, teks)


def mmr(qvec: list[float], kandidat: list[dict], k: int, lam: float = 0.7) -> list[dict]:
    """Maximal Marginal Relevance. kandidat: dict dengan 'skor' dan 'vektor'."""
    terpilih: list[dict] = []
    sisa = list(kandidat)
    while sisa and len(terpilih) < k:
        terbaik, nilai_terbaik = None, -1e9
        for c in sisa:
            redundansi = max((kosinus(c["vektor"], t["vektor"]) for t in terpilih), default=0.0)
            nilai = lam * c["skor"] - (1 - lam) * redundansi
            if nilai > nilai_terbaik:
                terbaik, nilai_terbaik = c, nilai
        terpilih.append(terbaik)
        sisa.remove(terbaik)
    return terpilih


def centroid(vektor: list[list[float]]) -> list[float]:
    if not vektor:
        return []
    dim = len(vektor[0])
    s = [0.0] * dim
    for v in vektor:
        for i, x in enumerate(v):
            s[i] += x
    n = math.sqrt(sum(x * x for x in s)) or 1.0
    return [x / n for x in s]
