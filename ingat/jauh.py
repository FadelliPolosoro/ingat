# SPDX-License-Identifier: Apache-2.0
"""Hook menulis ke server `ingat` jauh (VPS) alih-alih ke store di disk mesin ini.

Kenapa ada: `tangkap.py` semula hanya bisa menulis ke SQLite lokal. Begitu perangkatnya berganti —
laptop baru, HP, tablet — memorinya tertinggal di mesin lama, dan tiap mesin punya versi ingatan
sendiri yang tidak pernah bertemu. Modul ini memberi `Penangkap` objek ber-antarmuka sama
(`.store.tambah_episode`, `.store.catat_metrik`, `.gateway.muat_startup`) yang di dalamnya panggilan
HTTPS ke satu server. Perangkat jadi bisa dibuang; servernya yang menyimpan.

Tiga kontrak yang tidak boleh dilanggar:

1. **Hook tidak pernah memblokir Claude.** Server mati, DNS gagal, jaringan lambat — semuanya harus
   selesai cepat dan senyap. Timeout pendek, satu percobaan, tanpa retry berlapis.
2. **Tidak ada episode yang hilang karena jaringan.** Kegagalan kirim masuk `spool.jsonl` di disk,
   lalu dikirim ulang pada panggilan berikutnya yang berhasil. Ini yang membedakan "mode jauh" dari
   "mode jauh yang diam-diam membuang data".
3. **`id` diteruskan apa adanya.** Hook Stop memakai id deterministik supaya satu sesi menghasilkan
   satu episode yang di-upsert. Tanpa itu tiap Stop membuat episode baru — banjir yang justru
   dicegah desain aslinya.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

MAKS_SPOOL = 5000          # baris; di atas ini yang tertua dibuang — spool adalah penyangga, bukan arsip
TIMEOUT_BAWAAN = 5.0


class JauhGagal(Exception):
    """Server tidak terjangkau atau menolak. Selalu ditangkap di dalam modul ini — tidak pernah naik ke hook."""


@dataclass
class EpisodeJauh:
    """Sebagian `skema.Episode` yang benar-benar dipakai pemanggil (hanya `.id` yang dibaca `Penangkap`)."""
    id: str
    bobot: int = 1
    isi_ref: str | None = None


def baca_token(konfig: dict | None = None) -> str:
    """Env `INGAT_TOKEN` → berkas `~/.ingat/token` → `jauh.token` di konfigurasi.

    Berkas diutamakan di atas konfigurasi karena hook sering jalan tanpa mewarisi environment
    shell, dan menaruh token di `konfigurasi.json` membuatnya ikut tersalin saat konfigurasi
    dibagikan atau dicadangkan.
    """
    t = os.environ.get("INGAT_TOKEN", "").strip()
    if t:
        return t
    berkas = os.path.expanduser("~/.ingat/token")
    if os.path.exists(berkas):
        with open(berkas, encoding="utf-8") as f:
            t = f.read().strip()
        if t:
            return t
    return str(((konfig or {}).get("jauh") or {}).get("token") or "").strip()


class KlienJauh:
    """POST JSON ke server ingat. `pembuka` disuntik di uji — modul ini tidak pernah menyentuh jaringan sungguhan saat diuji."""

    def __init__(self, host: str, token: str, timeout: float = TIMEOUT_BAWAAN,
                 pembuka: Callable[..., Any] | None = None):
        self.host = host.rstrip("/")
        self.token = token
        self.timeout = timeout
        self._pembuka = pembuka or urllib.request.urlopen

    def post(self, jalur: str, badan: dict) -> dict:
        data = json.dumps(badan, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(f"{self.host}{jalur}", data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        try:
            with self._pembuka(req, timeout=self.timeout) as r:
                mentah = r.read().decode("utf-8")
            return json.loads(mentah) if mentah.strip() else {}
        except urllib.error.HTTPError as e:
            # 4xx bukan masalah jaringan — men-spool-nya berarti mengulang permintaan yang memang
            # salah sampai kiamat. Hanya 5xx yang layak dicoba lagi nanti.
            raise JauhGagal(f"HTTP {e.code}") from e
        except Exception as e:
            raise JauhGagal(str(e)) from e

    @staticmethod
    def layak_diulang(galat: JauhGagal) -> bool:
        pesan = str(galat)
        if pesan.startswith("HTTP 4"):
            return False
        return True


class _DasarJauh:
    def __init__(self, klien: KlienJauh, dir_spool: str):
        self.klien = klien
        self.dir_spool = dir_spool
        self.spool = os.path.join(dir_spool, "spool.jsonl")

    # ---- spool -------------------------------------------------------------------
    def _tulis_spool(self, jalur: str, badan: dict):
        try:
            os.makedirs(self.dir_spool, exist_ok=True)
            with open(self.spool, "a", encoding="utf-8") as f:
                f.write(json.dumps({"jalur": jalur, "badan": badan}, ensure_ascii=False) + "\n")
            self._pangkas_spool()
        except OSError:
            pass  # disk penuh/berkas terkunci: tetap tidak boleh menggagalkan hook

    def _pangkas_spool(self):
        try:
            with open(self.spool, encoding="utf-8") as f:
                baris = f.readlines()
            if len(baris) > MAKS_SPOOL:
                with open(self.spool, "w", encoding="utf-8") as f:
                    f.writelines(baris[-MAKS_SPOOL:])
        except OSError:
            pass

    def kuras_spool(self) -> int:
        """Kirim ulang yang tertunda. Berhenti pada kegagalan pertama — urutan episode dipertahankan."""
        if not os.path.exists(self.spool):
            return 0
        try:
            with open(self.spool, encoding="utf-8") as f:
                baris = [b for b in f if b.strip()]
        except OSError:
            return 0
        terkirim = 0
        for i, b in enumerate(baris):
            try:
                item = json.loads(b)
                self.klien.post(item["jalur"], item["badan"])
                terkirim += 1
            except JauhGagal:
                self._tulis_ulang_sisa(baris[i:])
                return terkirim
            except (ValueError, KeyError):
                continue  # baris rusak dibuang, bukan menghentikan sisanya
        try:
            os.remove(self.spool)
        except OSError:
            pass
        return terkirim

    def _tulis_ulang_sisa(self, sisa: list[str]):
        try:
            with open(self.spool, "w", encoding="utf-8") as f:
                f.writelines(sisa)
        except OSError:
            pass

    def _kirim(self, jalur: str, badan: dict) -> dict | None:
        """Kirim; spool bila gagal karena jaringan. Mengembalikan None kalau tidak sampai ke server."""
        try:
            self.kuras_spool()
            return self.klien.post(jalur, badan)
        except JauhGagal as e:
            if KlienJauh.layak_diulang(e):
                self._tulis_spool(jalur, badan)
            return None


class StoreJauh(_DasarJauh):
    """Bagian `Store` yang dipakai `Penangkap` — sisanya sengaja tidak ada supaya salah pakai ketahuan cepat."""

    def tambah_episode(self, isi: str, **meta) -> EpisodeJauh:
        badan: dict = {"isi": isi}
        for k in ("id", "sumber", "tier", "lingkup", "jenis_kejadian", "ringkas", "instrumen", "langkah", "sesi"):
            if k in meta and meta[k] is not None:
                badan[k] = meta[k]
        jawab = self._kirim("/episode", badan)
        if jawab and jawab.get("id"):
            return EpisodeJauh(id=str(jawab["id"]), bobot=int(jawab.get("bobot", 1)), isi_ref=jawab.get("isi_ref"))
        # Tertunda di spool: id lokal sementara supaya pemanggil tetap dapat sesuatu yang bisa dicatat.
        return EpisodeJauh(id=str(meta.get("id") or "tertunda"), bobot=1)

    def catat_metrik(self, nama: str, nilai: float, **konteks):
        self._kirim("/metrik", {"nama": nama, "nilai": nilai, "konteks": konteks})


class GatewayJauh(_DasarJauh):
    """Bagian `Gateway` yang dipakai `Penangkap`: hanya `muat_startup`."""

    def muat_startup(self, lingkup: str, sesi: str | None = None, **_) -> dict:
        # Sengaja TIDAK lewat `_kirim`: ini operasi BACA. Men-spool-nya berarti mengirim ulang
        # permintaan startup yang jawabannya sudah tidak relevan, sekadar mengotori antrean tulis.
        # Spool yang tertunda tetap dikuras di sini karena SessionStart adalah kesempatan paling awal
        # dalam satu sesi untuk menyusulkan episode sesi sebelumnya yang gagal terkirim.
        try:
            self.kuras_spool()
            jawab = self.klien.post("/startup", {"lingkup": lingkup, "sesi": sesi or ""})
        except JauhGagal:
            jawab = None
        # Server tak terjangkau saat SessionStart: mulai tanpa konteks memori — merosot pelan-pelan,
        # bukan menggagalkan sesi.
        return jawab if jawab else {"peta": [], "aturan": [], "pointer": [], "token": 0}


class AplikasiJauh:
    """Pengganti `Aplikasi` untuk hook. Sengaja hanya punya `.store` dan `.gateway`."""

    def __init__(self, klien: KlienJauh, dir_spool: str):
        self.store = StoreJauh(klien, dir_spool)
        self.gateway = GatewayJauh(klien, dir_spool)


def bangun_aplikasi_jauh(konfig: dict, pembuka: Callable[..., Any] | None = None) -> AplikasiJauh | None:
    """`None` bila konfigurasi tidak meminta mode jauh — pemanggil lanjut dengan store lokal."""
    j = konfig.get("jauh") or {}
    host = str(j.get("host") or "").strip()
    if not host:
        return None
    klien = KlienJauh(host, baca_token(konfig), float(j.get("timeout_detik", TIMEOUT_BAWAAN)), pembuka)
    return AplikasiJauh(klien, str(konfig.get("dir_data") or os.path.expanduser("~/.ingat/data")))
