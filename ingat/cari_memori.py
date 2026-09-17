# SPDX-License-Identifier: Apache-2.0
"""Kotak cari panel: pertanyaan bebas -> potongan memori yang relevan.

TANPA model generatif (keputusan Tuan Muda). Yang keluar adalah KUTIPAN memori apa adanya
dari Gateway.ingat() — modul ini hanya membungkus dan merapikan untuk layar, tidak membuat
jalur retrieval baru dan tidak mengarang kalimat.

Bebas Tkinter supaya bisa diuji tanpa layar.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import urllib.error
import urllib.request

from . import skema
from .aplikasi import Aplikasi, muat_konfig
from .simpan import IdentitasEmbedderTidakCocok

PANJANG_KUTIPAN = 220
MAKS_HASIL = 8
MAKS_RIWAYAT = 50
UMUR_RIWAYAT_JAM = 24
# Dipakai saat isi store tidak bisa diperiksa (pencarian lewat HTTP, atau entri riwayat lama
# tanpa sidik): entri hanya dipercaya beberapa menit. Tanpa batas pendek ini, memori yang baru
# dicatat tidak akan terlihat sampai UMUR_RIWAYAT_JAM lewat — persis guna sistem ini yang hilang.
UMUR_RIWAYAT_TANPA_SIDIK_MENIT = 10

DIR_INGAT = os.path.join(os.path.expanduser("~"), ".ingat")
BERKAS_RIWAYAT = "riwayat-cari.json"

PESAN = {
    "kosong_pertanyaan": "Ketik dulu yang ingin dicari.",
    "store_kosong": "Belum ada memori yang tersimpan. Catat dulu beberapa episode, baru pencarian ada isinya.",
    "tanpa_hasil": "Tidak ada memori yang cukup dekat dengan pertanyaan itu. Coba kata lain atau lebih spesifik.",
    "identitas": ("Indeks pencarian dibuat dengan model penyemat yang berbeda, jadi hasilnya tidak bisa dipercaya. "
                  "Jalankan sekali di terminal: ingat bangun-ulang-vektor — lalu coba cari lagi."),
    "penyemat_mati": "Mesin pencari (Ollama) belum menyala atau tidak bisa dihubungi. Nyalakan Ollama, lalu coba lagi.",
    "penyemat_aneh": "Mesin pencari menjawab tidak sesuai. Periksa model Ollama 'ingat-e5-base', lalu coba lagi.",
    "server_mati": "Server ingat tidak merespons. Nyalakan servernya, atau cari langsung tanpa server.",
    "token_ditolak": "Server menolak token. Periksa INGAT_TOKEN, lalu coba lagi.",
    "umum": "Pencarian gagal dijalankan. Coba sebentar lagi.",
}


# ---- potong & rapikan --------------------------------------------------------
def potong_kutipan(teks: str, batas: int = PANJANG_KUTIPAN) -> str:
    """Potong di batas kata supaya baris daftar tidak melebar dan kata tidak terbelah."""
    t = " ".join(str(teks or "").split())
    if len(t) <= batas:
        return t
    potong = t[:batas]
    spasi = potong.rfind(" ")
    if spasi > batas // 2:
        potong = potong[:spasi]
    return potong.rstrip(" ,;:.-") + "…"


def _inti(teks: str) -> str:
    """Buang awalan metadata `[pelajaran L-1 · aturan …]` dan ekor `| Pemicu: …` dari hasil render Gateway."""
    t = re.sub(r"^\[[^\]]*\]\s*", "", str(teks or "")).strip()
    return t.split(" | ", 1)[0].strip()


def kunci_pertanyaan(pertanyaan: str) -> str:
    """Kunci pencocokan riwayat: beda huruf besar/kecil, spasi, dan tanda tanya bukan pertanyaan baru."""
    t = " ".join(str(pertanyaan or "").lower().split())
    return t.strip(" ?!.,;:")


def _tanggal(store, jenis: str, id_: str) -> str:
    if store is None:
        return ""
    if jenis not in ("episode", "pelajaran", "prosedur", "norma"):
        return ""
    try:
        obj = getattr(store, jenis)(id_)
    except Exception:
        return ""
    for atribut in ("waktu", "dibuat", "berlaku_sejak"):
        nilai = getattr(obj, atribut, None)
        if nilai:
            return str(nilai)[:10]
    return ""


def rapikan_hasil(mentah: dict, store=None, maks: int = MAKS_HASIL) -> list[dict]:
    """Ubah keluaran Gateway.ingat() jadi baris siap tampil. Murni, tanpa jaringan.

    `skor` bernilai None bila sumbernya tidak membawa skor — cabang pointer luapan anggaran di
    Gateway menyusun dict tanpa kunci itu. Penerima wajib memperlakukan None sebagai
    "tidak diketahui", bukan nol.
    """
    baris: list[dict] = []
    for i in (mentah or {}).get("item", []):
        teks = i.get("teks", "")
        baris.append({
            "jenis": i.get("jenis", ""),
            "id": i.get("id", ""),
            "ringkas": potong_kutipan(_inti(teks), 90),
            "kutipan": potong_kutipan(teks),
            "tanggal": _tanggal(store, i.get("jenis", ""), i.get("id", "")),
            "skor": i.get("skor", None),
            "bendera": list(i.get("bendera") or []),
            # hanya episode yang punya bukti verbatim untuk dibuka (L-bukti)
            "id_episode": i.get("id") if i.get("jenis") == "episode" else None,
        })
    for p in (mentah or {}).get("pointer", []):
        ringkas = p.get("ringkas", "")
        baris.append({
            "jenis": p.get("jenis", ""),
            "id": p.get("id", ""),
            "ringkas": potong_kutipan(_inti(ringkas), 90),
            # isi verbatim episode sengaja TIDAK dibuka di sini: membuka bukti adalah tindakan
            # eksplisit (dan tier S dijaga). Panel memakai id_episode untuk membukanya bila diminta.
            "kutipan": potong_kutipan(ringkas),
            "tanggal": _tanggal(store, p.get("jenis", ""), p.get("id", "")),
            # pointer luapan anggaran datang tanpa kunci 'skor'; 0.0 akan membuat hasil peringkat
            # teratas tampak paling tidak relevan, dan bercampur dengan skor asli pointer episode
            "skor": p.get("skor", None),
            "bendera": list(p.get("bendera") or []),
            "id_episode": p.get("id") if p.get("jenis") == "episode" else None,
        })
    return baris[: max(0, int(maks))]


# ---- riwayat pencarian -------------------------------------------------------
# Disimpan sebagai JSON di ~/.ingat/riwayat-cari.json, bukan SQLite: ini catatan UI
# milik panel (puluhan baris, sekali tulis per pencarian), sedangkan store SQLite terikat
# kontrak memori (tanpa DELETE, identitas embedder). Menaruhnya di sana berarti menambah
# tabel + migrasi untuk data yang boleh dibuang kapan saja.
def _path_riwayat() -> str:
    return os.path.join(DIR_INGAT, BERKAS_RIWAYAT)


def muat_riwayat() -> list[dict]:
    """Baca riwayat; berkas hilang/rusak → daftar kosong, bukan galat."""
    try:
        with open(_path_riwayat(), encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    return [d for d in data if isinstance(d, dict) and d.get("kunci")]


def simpan_riwayat(daftar: list[dict]) -> None:
    try:
        os.makedirs(DIR_INGAT, exist_ok=True)
        with open(_path_riwayat(), "w", encoding="utf-8") as f:
            json.dump(daftar[:MAKS_RIWAYAT], f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def sidik_store(store) -> str:
    """Sidik jari isi store: jumlah baris + cap waktu terbaru tiap tabel memori.

    Dipakai membatalkan entri riwayat begitu ada memori baru. Tanpa ini pertanyaan yang sama
    dijawab dari catatan lama sampai UMUR_RIWAYAT_JAM, sehingga episode/pelajaran yang baru
    dicatat tidak bisa ditemukan seharian. Store tak bisa dibaca → "" = tidak diketahui.
    """
    if store is None:
        return ""
    try:
        baris = store.db.execute(
            "SELECT (SELECT COUNT(*) FROM episode), (SELECT MAX(waktu) FROM episode),"
            " (SELECT COUNT(*) FROM pelajaran), (SELECT MAX(dibuat) FROM pelajaran),"
            " (SELECT COUNT(*) FROM prosedur), (SELECT MAX(dibuat) FROM prosedur),"
            " (SELECT COUNT(*) FROM norma), (SELECT MAX(disusun_pada) FROM norma),"
            " (SELECT COUNT(*) FROM riwayat_status), (SELECT MAX(waktu) FROM riwayat_status)").fetchone()
    except Exception:
        return ""
    return "|".join("" if n is None else str(n) for n in baris)


def catat_riwayat(pertanyaan: str, hasil: list[dict], lingkup: str = "global", sumber: str = "gerbang",
                  pesan: str = "", maks: int | None = None, store=None) -> dict:
    """Simpan pertanyaan + hasilnya di depan daftar; entri lama dengan kunci sama dibuang.

    `pesan` dan `maks` ikut dicatat supaya jawaban dari riwayat identik dengan jawaban hitung
    ulang: pesannya sama, dan permintaan yang lebih panjang tidak dilayani potongan lama.
    """
    entri = {"pertanyaan": str(pertanyaan or ""), "kunci": kunci_pertanyaan(pertanyaan), "lingkup": lingkup,
             "waktu": skema.sekarang(), "jumlah": len(hasil), "sumber": sumber, "hasil": hasil,
             "pesan": str(pesan or ""), "maks": int(maks) if maks is not None else len(hasil),
             "sidik": sidik_store(store)}
    lama = [e for e in muat_riwayat() if e.get("kunci") != entri["kunci"] or e.get("lingkup") != lingkup]
    simpan_riwayat([entri] + lama)
    return entri


def _umur_jam(waktu: str) -> float:
    try:
        t = dt.datetime.fromisoformat(str(waktu))
    except Exception:
        return float("inf")
    if t.tzinfo is None:
        t = t.replace(tzinfo=dt.timezone.utc)
    return (dt.datetime.now(dt.timezone.utc) - t).total_seconds() / 3600.0


def _maks_entri(e: dict) -> int:
    """Berapa banyak baris yang boleh dilayani entri ini — entri lama tanpa kolom `maks`
    hanya dipercaya sebanyak baris yang benar-benar tersimpan."""
    try:
        m = int(e.get("maks") or 0)
    except (TypeError, ValueError):
        m = 0
    return m or len(e.get("hasil") or [])


def ambil_dari_riwayat(pertanyaan: str, lingkup: str = "global",
                       umur_jam: float = UMUR_RIWAYAT_JAM, maks: int | None = None,
                       store=None) -> dict | None:
    """Entri riwayat yang masih sah untuk pertanyaan ini — dasar hemat token: pertanyaan
    berulang dijawab dari catatan, tanpa menyemat dan memeringkat ulang.

    Entri dibatalkan bila store sudah berubah sejak entri dicatat, atau bila entri dicatat
    untuk permintaan yang lebih pendek daripada `maks` sekarang (tombol "tampilkan lebih
    banyak" harus tetap menambah baris).
    """
    kunci = kunci_pertanyaan(pertanyaan)
    if not kunci:
        return None
    sidik_kini = sidik_store(store)
    for e in muat_riwayat():
        if e.get("kunci") != kunci or e.get("lingkup", "global") != lingkup:
            continue
        sidik_lama = str(e.get("sidik") or "")
        if sidik_kini and sidik_lama:
            if sidik_lama != sidik_kini:
                continue  # ada tulisan baru ke store: entri ini sudah ketinggalan, berapa pun umurnya
            batas = umur_jam
        else:  # salah satu sidik tak diketahui — entri hanya dipercaya beberapa menit
            batas = min(umur_jam, UMUR_RIWAYAT_TANPA_SIDIK_MENIT / 60.0)
        if _umur_jam(e.get("waktu", "")) > batas:
            continue
        if maks is not None and _maks_entri(e) < int(maks):
            continue
        return e
    return None


def hapus_riwayat() -> None:
    simpan_riwayat([])


# ---- sumber hasil ------------------------------------------------------------
def buka_gerbang(konfig: dict | None = None):
    """Rakit Gateway + Store dari konfigurasi yang sama dengan API/CLI.

    `bangun_ulang_vektor` sengaja TIDAK dinyalakan: menyemat ulang 300+ episode adalah
    keputusan pengguna (perintah `ingat bangun-ulang-vektor`), bukan efek samping mencari.
    """
    app = Aplikasi(konfig or muat_konfig())
    return app.gateway, app.store


def store_kosong(store) -> bool:
    try:
        n = store.db.execute(
            "SELECT (SELECT COUNT(*) FROM episode)+(SELECT COUNT(*) FROM pelajaran)"
            "+(SELECT COUNT(*) FROM prosedur)+(SELECT COUNT(*) FROM norma)").fetchone()[0]
    except Exception:
        return False
    return not n


def cari_lewat_http(pertanyaan: str, host: str, token: str, lingkup: str = "global",
                    sesi: str = "panel", timeout: float = 10.0, pembuka=None) -> dict:
    """POST /ingat pada server yang sudah hidup. `pembuka` dapat disuntik untuk uji tanpa jaringan."""
    badan = json.dumps({"query": pertanyaan, "lingkup": lingkup, "sesi": sesi}).encode()
    req = urllib.request.Request((host or "").rstrip("/") + "/ingat", data=badan, method="POST",
                                 headers={"Content-Type": "application/json",
                                          "Authorization": "Bearer " + (token or "")})
    with (pembuka or urllib.request.urlopen)(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _pesan_galat(e: Exception) -> str:
    if isinstance(e, IdentitasEmbedderTidakCocok):
        return PESAN["identitas"]
    if isinstance(e, urllib.error.HTTPError):
        return PESAN["token_ditolak"] if e.code in (401, 403) else PESAN["server_mati"]
    if isinstance(e, (urllib.error.URLError, OSError, TimeoutError)):
        return PESAN["penyemat_mati"]
    if isinstance(e, RuntimeError):
        return PESAN["penyemat_aneh"]
    return PESAN["umum"]


def cari(pertanyaan: str, lingkup: str = "global", maks: int = MAKS_HASIL, gerbang=None, store=None,
         host: str | None = None, token: str | None = None, konfig: dict | None = None,
         pakai_riwayat: bool = True, sesi: str = "panel", pembuka=None) -> dict:
    """Cari memori untuk satu pertanyaan bebas.

    Urutan sumber: riwayat yang masih sah → `gerbang` yang diberikan → HTTP (bila `host`
    diisi) → Gateway lokal dari konfigurasi. Semua kegagalan jadi hasil kosong + pesan bahasa
    Indonesia; tidak ada galat mentah yang naik ke UI.
    """
    jawab = {"pertanyaan": str(pertanyaan or ""), "lingkup": lingkup, "hasil": [], "pesan": "",
             "sumber": "", "waktu": skema.sekarang()}
    if not kunci_pertanyaan(pertanyaan):
        jawab["pesan"] = PESAN["kosong_pertanyaan"]
        jawab["sumber"] = "kosong"
        return jawab

    # Store dibuka SEBELUM riwayat diperiksa: tanpa store, kesahihan entri tidak bisa diuji dan
    # memori yang baru dicatat akan tersembunyi. Membuka store hanya SQLite — yang mahal
    # (menyemat + memeringkat) tetap dilewati kalau entri riwayat masih sah.
    tutup_store = False
    galat_buka: Exception | None = None
    if gerbang is None and not host:
        try:
            gerbang, store = buka_gerbang(konfig)
            tutup_store = True
        except Exception as e:  # riwayat masih boleh menjawab; galat baru dilaporkan bila tidak ada
            galat_buka = e

    try:
        if pakai_riwayat:
            lama = ambil_dari_riwayat(pertanyaan, lingkup, maks=maks, store=store)
            if lama is not None:
                jawab["hasil"] = lama.get("hasil", [])[:maks]
                jawab["sumber"] = "riwayat"
                jawab["waktu"] = lama.get("waktu", jawab["waktu"])
                pesan = str(lama.get("pesan") or "")
                # entri lama (sebelum kolom `pesan` ada) tidak tahu kenapa hasilnya kosong
                jawab["pesan"] = pesan or ("" if jawab["hasil"] else PESAN["tanpa_hasil"])
                return jawab

        try:
            if galat_buka is not None:
                raise galat_buka
            if gerbang is not None:
                mentah = gerbang.ingat(pertanyaan, lingkup, sesi=sesi)
                asal = "gerbang"
            else:
                mentah = cari_lewat_http(pertanyaan, host or "", token or "", lingkup, sesi, pembuka=pembuka)
                asal = "http"
        except Exception as e:
            jawab["pesan"] = _pesan_galat(e)
            jawab["sumber"] = "galat"
            return jawab

        jawab["hasil"] = rapikan_hasil(mentah, store, maks)
        jawab["sumber"] = asal
        if not jawab["hasil"]:
            jawab["pesan"] = PESAN["store_kosong"] if (store is not None and store_kosong(store)) else PESAN["tanpa_hasil"]
        catat_riwayat(pertanyaan, jawab["hasil"], lingkup, asal, pesan=jawab["pesan"], maks=maks, store=store)
    finally:
        if tutup_store and store is not None:
            try:
                store.db.close()
            except Exception:
                pass
    return jawab
