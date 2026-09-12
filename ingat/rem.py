# SPDX-License-Identifier: Apache-2.0
"""K28 — empat rem wajib untuk orkestrasi tier S ke model lokal.

Sebelum K28, `Gate` menolak tier S ke penyedia inferensi mana pun, tanpa syarat. K28
melonggarkannya **hanya** untuk model yang berjalan di mesin sendiri (tidak keluar mesin),
dan **hanya** bila keempat rem ini terpasang sekaligus:

1. **Gate P/I/S** — penyedia harus terdaftar di `rem_tier_s.penyedia` DAN alamatnya terbukti
   lokal (`alamat_lokal`). Diverifikasi dari `base_url`, bukan dari nama: kalau tidak, rem ini
   bisa dilewati hanya dengan menamai penyedia cloud sebagai "lokal".
2. **Abstraksi P11** — "abstraksi bukan penyamaran". Ditegakkan pada **keluaran** model, bukan
   masukannya. Model lokal memang boleh *melihat* tier S (itu inti K28); yang dijaga adalah apa
   yang ia *hasilkan*: pelajaran wajib naik ke tingkat abstraksi yang bisa ditransfer (P8).
   Menyalin ulang kalimat sumber lalu membuang angkanya adalah penyamaran, bukan abstraksi —
   dan itu ditolak.
3. **Anggaran token harian** — batas atas pemakaian per hari UTC, dihitung dari tabel `metrik`.
4. **Manusia penjaga akhir** — `rem_tier_s.penjaga` wajib menyebut nama manusia, dan pelajaran
   turunan tier S tidak pernah naik status otomatis (ditegakkan di `konsolidasi.py`).

**Gagal-tertutup.** Tanpa blok `rem_tier_s`, atau bila satu rem saja hilang, perilaku kembali
persis seperti sebelum K28. Ruang lingkupnya juga sempit: hanya jalur `konsolidasi`; jalur umum
(`/tanya`) tetap menolak tier S.
"""
from __future__ import annotations

import datetime as dt
import ipaddress
import re
from urllib.parse import urlsplit

from .redaksi import POLA_TIER_S

METRIK_TOKEN = "rem_tier_s_token"

# Batas run kata berurutan yang dianggap salinan verbatim. Lima kata sudah cukup menangkap
# "Slip gaji karyawan Budi Santoso" sementara prosa abstrak yang kebetulan berbagi istilah
# ("sistem", "digit") hanya beririsan satu-dua kata.
AMBANG_RUN_KATA = 5
_ANGKA_PANJANG = re.compile(r"\d{8,}")
_KATA = re.compile(r"[0-9a-zA-ZÀ-ÿ]+")
_SUFIKS_LOKAL = (".local", ".internal", ".localdomain")


def alamat_lokal(base_url: str) -> bool:
    """True hanya untuk alamat yang tidak meninggalkan mesin/jaringan compose.

    Label tunggal (`http://ollama:11434`) diterima karena itulah bentuk DNS Docker yang dipakai
    `docker-compose.yml` — Ollama sengaja tanpa blok `ports`, jadi hanya container di jaringan
    itu yang bisa menjangkaunya.
    """
    if not isinstance(base_url, str) or not base_url:
        return False
    try:
        bagian = urlsplit(base_url)
    except ValueError:
        return False
    if bagian.scheme not in ("http", "https"):
        return False
    host = (bagian.hostname or "").strip(".").lower()
    if not host:
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        return bool(ip.is_loopback or ip.is_private)
    if host == "localhost" or host.endswith(_SUFIKS_LOKAL):
        return True
    return "." not in host


def _kata(teks: str) -> list[str]:
    return [m.group().lower() for m in _KATA.finditer(teks or "")]


def _run_kata_terpanjang(a: str, b: str) -> int:
    """Panjang run kata berurutan terpanjang yang sama persis di kedua teks (LCS substring kata)."""
    ka, kb = _kata(a), _kata(b)
    if not ka or not kb:
        return 0
    sebelum = [0] * (len(kb) + 1)
    terbaik = 0
    for i in range(1, len(ka) + 1):
        kini = [0] * (len(kb) + 1)
        for j in range(1, len(kb) + 1):
            if ka[i - 1] == kb[j - 1]:
                kini[j] = sebelum[j - 1] + 1
                if kini[j] > terbaik:
                    terbaik = kini[j]
        sebelum = kini
    return terbaik


def periksa_abstraksi(keluaran: str, sumber: str) -> tuple[bool, str]:
    """Rem 2 (P11). Kembalikan (lolos, alasan). Urutan sengaja: verbatim diperiksa lebih dulu
    supaya salinan mentah dilaporkan sebagai salinan, bukan sebagai 'memuat kata kunci'."""
    teks = (keluaran or "").strip()
    if not teks:
        return False, "keluaran kosong"
    run = _run_kata_terpanjang(teks, sumber or "")
    if run >= AMBANG_RUN_KATA:
        return False, f"keluaran menyalin verbatim {run} kata berurutan dari sumber (penyamaran, bukan abstraksi)"
    for nama, pola in POLA_TIER_S:
        if pola.search(teks):
            return False, f"keluaran memuat pola tier S: {nama}"
    m = _ANGKA_PANJANG.search(teks)
    if m:
        return False, f"keluaran memuat deret {len(m.group())} digit — identitas konkret, bukan abstraksi"
    return True, ""


def _hari_utc() -> str:
    """Tanggal UTC — `metrik.waktu` ditulis `skema.sekarang()` yang juga UTC. Memakai tanggal
    lokal akan salah-ember di sekitar tengah malam."""
    return dt.datetime.now(dt.timezone.utc).date().isoformat()


class RemTierS:
    def __init__(self, konfig: dict | None, penyedia: dict | None = None):
        k = dict(konfig or {})
        self.aktif = bool(k.get("aktif", False))
        self.daftar = [str(p) for p in (k.get("penyedia") or [])]
        self.anggaran = int(k.get("anggaran_token_harian") or 0)
        self.penjaga = str(k.get("penjaga") or "").strip()
        self.penyedia = penyedia or {}

    def _alasan(self) -> list[str]:
        a: list[str] = []
        if not self.aktif:
            a.append("sakelar rem_tier_s.aktif masih mati")
        if not self.penjaga:
            a.append("rem 4: penjaga manusia (rem_tier_s.penjaga) belum diisi")
        if self.anggaran <= 0:
            a.append("rem 3: anggaran_token_harian belum diisi")
        if not self.daftar:
            a.append("rem 1: rem_tier_s.penyedia kosong")
        for pid in self.daftar:
            obj = self.penyedia.get(pid)
            if obj is None:
                a.append(f"rem 1: penyedia '{pid}' tidak aktif/terkonfigurasi")
            elif not alamat_lokal(getattr(obj, "base_url", "")):
                a.append(f"rem 1: penyedia '{pid}' bukan alamat lokal")
        return a

    def alasan_tertutup(self) -> str:
        return "; ".join(self._alasan())

    def terbuka(self) -> bool:
        return not self._alasan()

    def penyedia_diizinkan(self) -> list[str]:
        if not self.terbuka():
            return []
        return [p for p in self.daftar if p in self.penyedia]

    # ---- rem 3: anggaran harian --------------------------------------------
    def terpakai_hari_ini(self, store) -> float:
        return store.jumlah_metrik(METRIK_TOKEN, _hari_utc())

    def ada_anggaran(self, store, perkiraan_token: int) -> bool:
        if self.anggaran <= 0:
            return False
        return self.terpakai_hari_ini(store) + max(0, int(perkiraan_token)) <= self.anggaran

    def catat_pemakaian(self, store, token: int, penyedia: str) -> None:
        store.catat_metrik(METRIK_TOKEN, float(max(0, int(token))), penyedia=penyedia, penjaga=self.penjaga)
