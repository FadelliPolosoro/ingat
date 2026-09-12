# SPDX-License-Identifier: Apache-2.0
"""Store: SQLite untuk indeks & metadata, berkas gzip untuk isi episode (dingin).

Aturan P1: tidak ada DELETE untuk episode/pelajaran/prosedur/norma.
Semua perubahan status lewat `ubah_status()` yang menegakkan state machine.
"""
from __future__ import annotations

import gzip
import json
import os
import sqlite3
import threading
from dataclasses import fields
from typing import Iterable

from . import skema
from .redaksi import redaksi, tandai_tier
from .vektor import ke_blob, dari_blob

_SKEMA_SQL = """
CREATE TABLE IF NOT EXISTS episode (
  id TEXT PRIMARY KEY, waktu TEXT, sumber TEXT, tier TEXT, lingkup TEXT,
  jenis_kejadian TEXT, ringkas TEXT, instrumen TEXT, bobot INTEGER, status TEXT,
  isi TEXT, isi_ref TEXT, langkah TEXT, sesi TEXT, diredaksi TEXT
);
CREATE INDEX IF NOT EXISTS ix_episode_status ON episode(status, tier);
CREATE TABLE IF NOT EXISTS pelajaran (
  id TEXT PRIMARY KEY, pelajaran TEXT, pemicu TEXT, tindakan TEXT, lingkup TEXT,
  status TEXT, keyakinan REAL, bukti TEXT, kontra TEXT, instrumen_saat_dibuat TEXT,
  berlaku_untuk TEXT, tinjau_setelah TEXT, dibuat TEXT, terakhir_dikonfirmasi TEXT,
  tinjau_ulang INTEGER, ditinjau_manusia INTEGER, veto_manusia TEXT, tier_maks TEXT,
  sintesis TEXT, usulan_perluasan_lingkup TEXT, catatan TEXT
);
CREATE TABLE IF NOT EXISTS prosedur (
  id TEXT PRIMARY KEY, prosedur TEXT, tugas_pemicu TEXT, langkah TEXT, lingkup TEXT,
  bentuk TEXT, status TEXT, eksekusi_total INTEGER, eksekusi_berhasil INTEGER,
  gagal_beruntun INTEGER, bukti TEXT, berlaku_untuk TEXT, tinjau_setelah TEXT, uji TEXT,
  ditinjau_manusia INTEGER, veto_manusia TEXT, tinjau_ulang INTEGER, dibuat TEXT,
  tier_maks TEXT, catatan TEXT, tingkat_berhasil REAL, berkas TEXT
);
CREATE TABLE IF NOT EXISTS norma (
  id TEXT PRIMARY KEY, norma TEXT, judul TEXT, jenis TEXT, otoritatif INTEGER,
  berlaku_sejak TEXT, berlaku_sampai TEXT, dicabut_oleh TEXT, dibatalkan_oleh TEXT,
  mengganti TEXT, alasan TEXT, peralihan TEXT, sumber_dokumen TEXT, status TEXT,
  disusun_dari TEXT, disusun_pada TEXT, disusun_oleh TEXT, berlaku_untuk_tanggal TEXT,
  catatan TEXT, isi TEXT, berkas TEXT
);
CREATE TABLE IF NOT EXISTS instrumen (
  id TEXT PRIMARY KEY, nama TEXT, dipasang_sejak TEXT, cakupan TEXT, titik_buta_diketahui TEXT
);
CREATE TABLE IF NOT EXISTS riwayat_status (
  id INTEGER PRIMARY KEY, waktu TEXT, jenis TEXT, item_id TEXT,
  dari TEXT, ke TEXT, oleh TEXT, alasan TEXT
);
CREATE TABLE IF NOT EXISTS metrik (
  id INTEGER PRIMARY KEY, waktu TEXT, nama TEXT, nilai REAL, konteks TEXT
);
CREATE TABLE IF NOT EXISTS panggilan_ingat (
  id INTEGER PRIMARY KEY, waktu TEXT, sesi TEXT, lingkup TEXT, query TEXT,
  jumlah_item INTEGER, token_dipakai INTEGER, jenis TEXT
);
-- Kontrak v2: vektor terpisah dari tabel item; satu baris per (item, jenis, koleksi).
-- koleksi 'isi' = konten; koleksi 'pemicu' = isyarat situasi (R12) untuk pelajaran & prosedur.
CREATE TABLE IF NOT EXISTS vektor (
  item_id TEXT NOT NULL, jenis TEXT NOT NULL, koleksi TEXT NOT NULL,
  dimensi INTEGER NOT NULL, vektor BLOB NOT NULL,
  PRIMARY KEY (item_id, jenis, koleksi)
);
CREATE TABLE IF NOT EXISTS identitas_embedder (
  koleksi TEXT PRIMARY KEY, model TEXT NOT NULL, dimensi INTEGER NOT NULL, dicatat TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS transisi_status (
  jenis TEXT NOT NULL, dari TEXT NOT NULL, ke TEXT NOT NULL, oleh TEXT NOT NULL,
  PRIMARY KEY (jenis, dari, ke)
);
CREATE TABLE IF NOT EXISTS meta (kunci TEXT PRIMARY KEY, nilai TEXT NOT NULL);
"""

_DDL_TABEL = {
    "riwayat_status": "(id INTEGER PRIMARY KEY, waktu TEXT, jenis TEXT, item_id TEXT, dari TEXT, ke TEXT, oleh TEXT, alasan TEXT)",
    "metrik": "(id INTEGER PRIMARY KEY, waktu TEXT, nama TEXT, nilai REAL, konteks TEXT)",
    "panggilan_ingat": "(id INTEGER PRIMARY KEY, waktu TEXT, sesi TEXT, lingkup TEXT, query TEXT, jumlah_item INTEGER, token_dipakai INTEGER, jenis TEXT)",
}

_KOLOM_JSON = {
    "episode": {"instrumen", "langkah", "diredaksi"},
    "pelajaran": {"bukti", "kontra", "instrumen_saat_dibuat", "berlaku_untuk"},
    "prosedur": {"langkah", "bukti", "berlaku_untuk"},
    "norma": {"mengganti", "disusun_dari"},
    "instrumen": {"titik_buta_diketahui"},
}
_KOLOM_BOOL = {
    "pelajaran": {"tinjau_ulang", "ditinjau_manusia"},
    "prosedur": {"ditinjau_manusia", "tinjau_ulang"},
    "norma": {"otoritatif"},
}
_KELAS = {
    "episode": skema.Episode, "pelajaran": skema.Pelajaran, "prosedur": skema.Prosedur,
    "norma": skema.Norma, "instrumen": skema.Instrumen,
}


class IdentitasEmbedderTidakCocok(Exception):
    """Koleksi dibangun dengan model/dimensi lain. Ganti model diam-diam menurunkan recall tanpa gejala —
    ini error keras, bukan peringatan. Bangun ulang: Store(..., bangun_ulang_vektor=True)."""


VERSI_KONTRAK = "2"
KOLEKSI = ("isi", "pemicu")


def _koleksi_teks(jenis: str, obj) -> dict[str, str]:
    """Teks yang di-embed per koleksi (R12: isyarat `pemicu` terpisah dari isi)."""
    if jenis == "episode":
        return {"isi": obj.ringkas}  # isi verbatim hidup di penyimpanan dingin
    if jenis == "pelajaran":
        return {"isi": obj.teks_embedding(), "pemicu": obj.pemicu}
    if jenis == "prosedur":
        return {"isi": obj.teks_embedding(), "pemicu": obj.tugas_pemicu}
    if jenis == "norma":
        return {"isi": obj.teks_embedding()}
    return {}


class Store:
    def __init__(self, dir_data: str, penyemat, bangun_ulang_vektor: bool = False):
        self.dir_data = dir_data
        self.dir_dingin = os.path.join(dir_data, "dingin")
        os.makedirs(self.dir_dingin, mode=0o700, exist_ok=True)
        try:
            os.chmod(self.dir_dingin, 0o700)  # makedirs tidak selalu menegakkan mode pada folder yang sudah ada
        except OSError:
            pass
        self.penyemat = penyemat
        self._kunci = threading.RLock()
        jalur_db = os.path.join(dir_data, "ingat.sqlite")
        db_baru = not os.path.exists(jalur_db)
        self.db = sqlite3.connect(jalur_db, check_same_thread=False)
        if db_baru:
            try:
                os.chmod(jalur_db, 0o600)  # berkas berisi episode verbatim tier S — hanya pemilik yang boleh baca
            except OSError:
                pass  # Windows: bit POSIX tidak berlaku
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        try:
            self.db.executescript(_SKEMA_SQL)
            self._migrasi()
            self._isi_transisi_status()
            self._cek_identitas(bangun_ulang_vektor)
            self.db.execute("INSERT OR REPLACE INTO meta(kunci, nilai) VALUES('versi_kontrak', ?)", (VERSI_KONTRAK,))
            self.db.commit()
        except Exception:
            # jangan tinggalkan transaksi menggantung: koneksi berikutnya akan "database is locked"
            self.db.rollback()
            self.db.close()
            raise

    # ---- migrasi & kontrak -----------------------------------------------------
    def _kolom(self, tabel: str) -> set[str]:
        return {r[1] for r in self.db.execute(f"PRAGMA table_info({tabel})")}

    def _migrasi(self):
        """Migrasi DB lama (pra-kontrak v2). Idempoten: tiap langkah memeriksa keadaan dulu."""
        if "diredaksi" not in self._kolom("episode"):
            self.db.execute("ALTER TABLE episode ADD COLUMN diredaksi TEXT")
        if "isi" not in self._kolom("episode"):  # kontrak v2: kolom ada, selalu NULL (verbatim di isi_ref)
            self.db.execute("ALTER TABLE episode ADD COLUMN isi TEXT")
        for tabel in ("pelajaran", "prosedur", "norma"):
            if "berkas" not in self._kolom(tabel):  # kontrak: path relatif berkas vault
                self.db.execute(f"ALTER TABLE {tabel} ADD COLUMN berkas TEXT")
        if "tingkat_berhasil" not in self._kolom("prosedur"):  # kontrak v2: cache eksekusi_berhasil/eksekusi_total
            self.db.execute("ALTER TABLE prosedur ADD COLUMN tingkat_berhasil REAL")
        # vektor inline -> tabel vektor (SELARAS tiket 2)
        for jenis in ("episode", "pelajaran", "prosedur", "norma"):
            if "vektor" not in self._kolom(jenis):
                continue
            model_lama, dim_lama = None, 0
            for b in self.db.execute(f"SELECT * FROM {jenis} WHERE vektor IS NOT NULL"):
                v = dari_blob(b["vektor"])
                if v:
                    self.db.execute("INSERT OR IGNORE INTO vektor(item_id,jenis,koleksi,dimensi,vektor) VALUES(?,?,?,?,?)",
                                    (b["id"], jenis, "isi", len(v), b["vektor"]))
                    model_lama, dim_lama = model_lama or b["model_embedding"], len(v)
            if model_lama:
                self.db.execute("INSERT OR IGNORE INTO identitas_embedder(koleksi,model,dimensi,dicatat) VALUES('isi',?,?,?)",
                                (model_lama, dim_lama, skema.sekarang()))
            for kol in ("vektor", "model_embedding"):
                try:
                    self.db.execute(f"ALTER TABLE {jenis} DROP COLUMN {kol}")
                except sqlite3.OperationalError:
                    pass  # SQLite < 3.35: kolom lama dibiarkan, tidak dipakai
        # AUTOINCREMENT n -> id INTEGER PRIMARY KEY (SELARAS tiket 3, SQL portabel)
        for tabel, kolom in (("riwayat_status", "waktu, jenis, item_id, dari, ke, oleh, alasan"),
                             ("metrik", "waktu, nama, nilai, konteks"),
                             ("panggilan_ingat", "waktu, sesi, lingkup, query, jumlah_item, token_dipakai, jenis")):
            if "n" in self._kolom(tabel):
                ddl = _DDL_TABEL[tabel]
                self.db.executescript(f"""
                    CREATE TABLE {tabel}__baru {ddl};
                    INSERT INTO {tabel}__baru (id, {kolom}) SELECT n, {kolom} FROM {tabel} ORDER BY n;
                    DROP TABLE {tabel};
                    ALTER TABLE {tabel}__baru RENAME TO {tabel};""")
        self.db.commit()

    def _isi_transisi_status(self):
        """Tabel transisi_status diisi dari peta di skema.py supaya port lain membaca aturan yang sama dari SQL."""
        for jenis, peta in skema.TRANSISI.items():
            for dari, tujuan in peta.items():
                for ke in tujuan:
                    oleh = "manusia" if (jenis, dari, ke) in skema.HANYA_MANUSIA else "keduanya"
                    self.db.execute("INSERT OR IGNORE INTO transisi_status(jenis,dari,ke,oleh) VALUES(?,?,?,?)", (jenis, dari, ke, oleh))

    def _cek_identitas(self, bangun_ulang: bool):
        """Identitas model per koleksi: pertama kali dicatat; berikutnya wajib cocok (nama + dimensi)."""
        dim = int(getattr(self.penyemat, "dim", 0) or 0)
        for koleksi in KOLEKSI:
            b = self.db.execute("SELECT model, dimensi FROM identitas_embedder WHERE koleksi=?", (koleksi,)).fetchone()
            if b is None:
                if dim:
                    self.db.execute("INSERT INTO identitas_embedder(koleksi,model,dimensi,dicatat) VALUES(?,?,?,?)",
                                    (koleksi, self.penyemat.nama, dim, skema.sekarang()))
                continue
            if b["model"] == self.penyemat.nama and (not dim or b["dimensi"] == dim):
                continue
            if not bangun_ulang:
                raise IdentitasEmbedderTidakCocok(
                    f"koleksi '{koleksi}' dibangun dengan {b['model']} ({b['dimensi']}-dim); penyemat sekarang "
                    f"{self.penyemat.nama} ({dim}-dim). Jalankan Store(..., bangun_ulang_vektor=True) untuk menyemat ulang.")
            self.db.execute("DELETE FROM vektor WHERE koleksi=?", (koleksi,))
            self.db.execute("INSERT OR REPLACE INTO identitas_embedder(koleksi,model,dimensi,dicatat) VALUES(?,?,?,?)",
                            (koleksi, self.penyemat.nama, dim, skema.sekarang()))
        if bangun_ulang:
            self.bangun_ulang_vektor()

    def bangun_ulang_vektor(self):
        """Semat ulang semua item dengan penyemat sekarang (setelah ganti model)."""
        for jenis, ambil in (("episode", self.episode_semua), ("pelajaran", self.pelajaran_semua),
                             ("prosedur", self.prosedur_semua), ("norma", self.norma_semua)):
            for obj in ambil():
                self._simpan_vektor(jenis, obj)
        self.db.commit()

    # ---- util --------------------------------------------------------------
    def _ke_baris(self, jenis: str, obj) -> dict:
        d = skema.ke_dict(obj)
        for k in _KOLOM_JSON.get(jenis, ()):
            d[k] = json.dumps(d.get(k) if d.get(k) is not None else ([] if k != "berlaku_untuk" else {}), ensure_ascii=False)
        for k in _KOLOM_BOOL.get(jenis, ()):
            d[k] = 1 if d.get(k) else 0
        return d

    def _muat_vektor(self, jenis: str, ids: list[str]) -> dict[str, dict[str, list[float]]]:
        hasil: dict[str, dict[str, list[float]]] = {}
        for i in range(0, len(ids), 500):
            potong = ids[i:i + 500]
            q = f"SELECT item_id, koleksi, vektor FROM vektor WHERE jenis=? AND item_id IN ({','.join('?' for _ in potong)})"
            for b in self.db.execute(q, [jenis, *potong]):
                hasil.setdefault(b["item_id"], {})[b["koleksi"]] = dari_blob(b["vektor"])
        return hasil

    def _daftar(self, jenis: str, rows) -> list:
        rows = list(rows)
        vek = self._muat_vektor(jenis, [b["id"] for b in rows])
        return [self._dari_baris(jenis, b, vek.get(b["id"], {})) for b in rows]

    def _dari_baris(self, jenis: str, baris: sqlite3.Row, vek: dict[str, list[float]] | None = None):
        d = dict(baris)
        d.pop("vektor", None)  # DB lama yang kolomnya belum bisa di-DROP
        d.pop("model_embedding", None)
        if vek is None:
            vek = self._muat_vektor(jenis, [d["id"]]).get(d["id"], {})
        for k in _KOLOM_JSON.get(jenis, ()):
            try:
                d[k] = json.loads(d[k]) if d.get(k) else ([] if k != "berlaku_untuk" else {})
            except Exception:
                d[k] = [] if k != "berlaku_untuk" else {}
        for k in _KOLOM_BOOL.get(jenis, ()):
            d[k] = bool(d.get(k))
        kelas = _KELAS[jenis]
        nama_kolom = {f.name for f in fields(kelas)}
        obj = kelas(**{k: v for k, v in d.items() if k in nama_kolom})
        obj._vektor = vek.get("isi", [])  # type: ignore[attr-defined]
        obj._vektor_pemicu = vek.get("pemicu", [])  # type: ignore[attr-defined]
        return obj

    def _hitung_vektor(self, jenis: str, obj) -> list[tuple[str, list[float]]]:
        """Panggil penyemat TANPA menyentuh basis data.

        Dipisah dari penulisan supaya pemanggil bisa menyematkan lebih dulu: penyemat adalah
        satu-satunya langkah yang memanggil dunia luar (Ollama) dan yang paling sering gagal.
        """
        return [(koleksi, self.penyemat.semat(teks)) for koleksi, teks in _koleksi_teks(jenis, obj).items()]

    def _simpan_vektor(self, jenis: str, obj, siap: list[tuple[str, list[float]]] | None = None):
        for koleksi, v in (siap if siap is not None else self._hitung_vektor(jenis, obj)):
            self.db.execute("INSERT OR REPLACE INTO vektor(item_id,jenis,koleksi,dimensi,vektor) VALUES(?,?,?,?,?)",
                            (obj.id, jenis, koleksi, len(v), ke_blob(v)))

    def _upsert(self, jenis: str, obj, semat: bool = True, vektor_siap=None):
        d = self._ke_baris(jenis, obj)
        if jenis == "prosedur":  # kontrak v2: tingkat_berhasil = cache, bukan sumber kebenaran
            total = int(getattr(obj, "eksekusi_total", 0) or 0)
            d["tingkat_berhasil"] = (int(getattr(obj, "eksekusi_berhasil", 0) or 0) / total) if total else 0.0
        kolom = ", ".join(d.keys())
        tanda = ", ".join("?" for _ in d)
        with self._kunci:
            try:
                self.db.execute(f"INSERT OR REPLACE INTO {jenis} ({kolom}) VALUES ({tanda})", list(d.values()))
                if semat:
                    self._simpan_vektor(jenis, obj, vektor_siap)
                self.db.commit()
            except BaseException:
                # Tanpa rollback, INSERT yang gagal menggantung di transaksi yang masih terbuka
                # dan akan ikut ter-commit oleh penulis BERIKUTNYA (mis. catat_metrik) — baris
                # muncul di basis data seolah-olah berhasil. Terlihat hanya di proses berumur
                # panjang; di CLI ia tersembunyi karena proses langsung mati.
                self.db.rollback()
                raise

    def catat_metrik(self, nama: str, nilai: float, **konteks):
        with self._kunci:
            self.db.execute("INSERT INTO metrik(waktu,nama,nilai,konteks) VALUES(?,?,?,?)",
                            (skema.sekarang(), nama, float(nilai), json.dumps(konteks, ensure_ascii=False)))
            self.db.commit()

    def jumlah_metrik(self, nama: str, prefiks_waktu: str = "") -> float:
        """Jumlah `nilai` untuk satu metrik, opsional dibatasi awalan `waktu` (mis. '2026-09-13'
        untuk satu hari UTC). Dipakai rem anggaran harian K28 (`ingat/rem.py`)."""
        with self._kunci:
            row = self.db.execute(
                "SELECT COALESCE(SUM(nilai),0) FROM metrik WHERE nama=? AND waktu LIKE ?",
                (nama, f"{prefiks_waktu}%"),
            ).fetchone()
        return float(row[0] if row else 0.0)

    # ---- episode -----------------------------------------------------------
    def simpan_dingin(self, id_: str, isi: dict) -> str:
        sub = os.path.join(self.dir_dingin, id_[3:7], id_[7:9]) if id_.startswith("ep-") else self.dir_dingin
        os.makedirs(sub, exist_ok=True)
        path = os.path.join(sub, f"{id_}.json.gz")
        with gzip.open(path, "wt", encoding="utf-8") as f:
            json.dump(isi, f, ensure_ascii=False)
        # `isi_ref` ikut pindah bersama store (cadangan, migrasi laptop→VPS, ganti perangkat), jadi
        # separatornya TIDAK boleh ikut OS penulis. `os.path.relpath` memberi `\` di Windows; di Linux
        # ref itu jadi nama berkas literal dan bukti verbatim hilang senyap. Kontrak: selalu `/`.
        return os.path.relpath(path, self.dir_data).replace(os.sep, "/")

    @staticmethod
    def _ref_lokal(ref: str) -> str:
        """Ref → path OS ini. Menerima `/` (kontrak) maupun `\\` (store lama yang ditulis Windows)."""
        return ref.replace("\\", "/").replace("/", os.sep)

    def buka_dingin(self, ref: str) -> dict:
        with gzip.open(os.path.join(self.dir_data, self._ref_lokal(ref)), "rt", encoding="utf-8") as f:
            return json.load(f)

    def _hapus_dingin(self, ref: str):
        """Gulung balik blob dingin yang sudah telanjur ditulis."""
        try:
            os.remove(os.path.join(self.dir_data, self._ref_lokal(ref)))
        except OSError:
            pass

    def tambah_episode(self, isi: str, **meta) -> skema.Episode:
        # K10: semua episode tersimpan verbatim — termasuk tier S — kredensial diredaksi SEBELUM tulis.
        # Ini satu-satunya jalur tulis episode (CLI, API, MCP semua lewat sini).
        r_isi = redaksi(isi)
        r_ringkas = redaksi(meta.get("ringkas", ""))
        meta["ringkas"] = r_ringkas.teks
        meta["diredaksi"] = sorted(set(r_isi.jenis) | set(r_ringkas.jenis))
        tier_naik, _alasan = tandai_tier(r_isi.teks + "\n" + r_ringkas.teks, meta.get("tier", "I"))
        meta["tier"] = "S" if (tier_naik == "S" or meta.get("tier") == "S") else meta.get("tier", "I")
        id_ = meta.pop("id", None) or skema.id_episode()
        ep = skema.Episode(id=id_, waktu=meta.pop("waktu", None) or skema.sekarang(), **meta)
        # Urutan ditentukan kontrak, bukan kemudahan. Baris episode yang sudah ter-commit WAJIB
        # punya blob verbatim di ujung `isi_ref` (K10) — jadi blob harus ada lebih dulu; baris
        # tanpa blob berarti bukti hilang. Sebaliknya blob tanpa baris hanyalah sampah yang tidak
        # dirujuk siapa pun, dan itu yang harus digulung balik.
        #
        # Karena itu: semat DULU (satu-satunya langkah yang memanggil dunia luar dan paling sering
        # gagal — Ollama mati = gagal di sini, sebelum ada apa pun ditulis), baru tulis blob, baru
        # baris. Kalau penulisan baris tetap gagal, blob dihapus supaya tidak jadi yatim.
        vek = self._hitung_vektor("episode", ep)
        ep.isi_ref = self.simpan_dingin(ep.id, {"id": ep.id, "waktu": ep.waktu, "isi": r_isi.teks, "meta": skema.ke_dict(ep)})
        try:
            # vektor dari ringkas saja; isi verbatim hidup di penyimpanan dingin
            self._upsert("episode", ep, vektor_siap=vek)
        except BaseException:
            self._hapus_dingin(ep.isi_ref)
            raise
        return ep

    def episode(self, id_: str) -> skema.Episode | None:
        b = self.db.execute("SELECT * FROM episode WHERE id=?", (id_,)).fetchone()
        return self._dari_baris("episode", b) if b else None

    def episode_aktif(self, tier: Iterable[str] = ("P", "I"), bobot_min: int = 0) -> list[skema.Episode]:
        t = list(tier)
        q = f"SELECT * FROM episode WHERE status='aktif' AND tier IN ({','.join('?' for _ in t)}) AND bobot>=? ORDER BY waktu"
        return self._daftar("episode", self.db.execute(q, [*t, bobot_min]))

    def episode_semua(self, status: str | None = None) -> list[skema.Episode]:
        if status:
            rows = self.db.execute("SELECT * FROM episode WHERE status=? ORDER BY waktu", (status,))
        else:
            rows = self.db.execute("SELECT * FROM episode ORDER BY waktu")
        return self._daftar("episode", rows)

    # ---- pelajaran / prosedur / norma / instrumen -------------------------
    def simpan_pelajaran(self, p: skema.Pelajaran):
        self._upsert("pelajaran", p)

    def pelajaran(self, id_: str) -> skema.Pelajaran | None:
        b = self.db.execute("SELECT * FROM pelajaran WHERE id=?", (id_,)).fetchone()
        return self._dari_baris("pelajaran", b) if b else None

    def pelajaran_semua(self, status: Iterable[str] | None = None) -> list[skema.Pelajaran]:
        if status:
            s = list(status)
            rows = self.db.execute(f"SELECT * FROM pelajaran WHERE status IN ({','.join('?' for _ in s)})", s)
        else:
            rows = self.db.execute("SELECT * FROM pelajaran")
        return self._daftar("pelajaran", rows)

    def simpan_prosedur(self, p: skema.Prosedur):
        self._upsert("prosedur", p)

    def prosedur(self, id_: str) -> skema.Prosedur | None:
        b = self.db.execute("SELECT * FROM prosedur WHERE id=?", (id_,)).fetchone()
        return self._dari_baris("prosedur", b) if b else None

    def prosedur_semua(self, status: Iterable[str] | None = None) -> list[skema.Prosedur]:
        if status:
            s = list(status)
            rows = self.db.execute(f"SELECT * FROM prosedur WHERE status IN ({','.join('?' for _ in s)})", s)
        else:
            rows = self.db.execute("SELECT * FROM prosedur")
        return self._daftar("prosedur", rows)

    def simpan_norma(self, n: skema.Norma):
        self._upsert("norma", n)

    def norma(self, id_: str) -> skema.Norma | None:
        b = self.db.execute("SELECT * FROM norma WHERE id=?", (id_,)).fetchone()
        return self._dari_baris("norma", b) if b else None

    def norma_semua(self) -> list[skema.Norma]:
        return self._daftar("norma", self.db.execute("SELECT * FROM norma"))

    def simpan_instrumen(self, i: skema.Instrumen):
        self._upsert("instrumen", i, semat=False)

    def instrumen_semua(self) -> list[skema.Instrumen]:
        return [self._dari_baris("instrumen", b) for b in self.db.execute("SELECT * FROM instrumen")]

    # ---- state machine -----------------------------------------------------
    def ubah_status(self, jenis: str, id_: str, ke: str, oleh: str = "mesin", alasan: str = ""):
        ambil = {"episode": self.episode, "pelajaran": self.pelajaran, "prosedur": self.prosedur, "norma": self.norma}[jenis]
        obj = ambil(id_)
        if obj is None:
            raise KeyError(f"{jenis} {id_} tidak ada")
        skema.periksa_transisi(jenis, obj.status, ke, oleh)
        with self._kunci:
            self.db.execute(f"UPDATE {jenis} SET status=? WHERE id=?", (ke, id_))
            if jenis in ("pelajaran", "prosedur") and oleh == "manusia":
                self.db.execute(f"UPDATE {jenis} SET ditinjau_manusia=1 WHERE id=?", (id_,))
            self.db.execute("INSERT INTO riwayat_status(waktu,jenis,item_id,dari,ke,oleh,alasan) VALUES(?,?,?,?,?,?,?)",
                            (skema.sekarang(), jenis, id_, obj.status, ke, oleh, alasan))
            self.db.commit()

    def riwayat(self, jenis: str, id_: str) -> list[dict]:
        return [dict(b) for b in self.db.execute(
            "SELECT * FROM riwayat_status WHERE jenis=? AND item_id=? ORDER BY id", (jenis, id_))]

    # ---- panggilan & metrik -----------------------------------------------
    def catat_panggilan(self, sesi: str, lingkup: str, query: str, jumlah: int, token: int, jenis: str):
        with self._kunci:
            self.db.execute("INSERT INTO panggilan_ingat(waktu,sesi,lingkup,query,jumlah_item,token_dipakai,jenis) VALUES(?,?,?,?,?,?,?)",
                            (skema.sekarang(), sesi, lingkup, query[:300], jumlah, token, jenis))
            self.db.commit()

    def ringkasan_metrik(self) -> dict:
        r = {}
        r["episode_aktif"] = self.db.execute("SELECT COUNT(*) FROM episode WHERE status='aktif'").fetchone()[0]
        r["episode_didinginkan"] = self.db.execute("SELECT COUNT(*) FROM episode WHERE status='didinginkan'").fetchone()[0]
        for st in ("hipotesis", "usulan", "aturan", "dipersempit", "ditarik"):
            r[f"pelajaran_{st}"] = self.db.execute("SELECT COUNT(*) FROM pelajaran WHERE status=?", (st,)).fetchone()[0]
        for st in ("draf", "teruji", "aktif", "dipersempit", "ditarik"):
            r[f"prosedur_{st}"] = self.db.execute("SELECT COUNT(*) FROM prosedur WHERE status=?", (st,)).fetchone()[0]
        r["norma"] = self.db.execute("SELECT COUNT(*) FROM norma").fetchone()[0]
        r["tinjau_ulang"] = (self.db.execute("SELECT COUNT(*) FROM pelajaran WHERE tinjau_ulang=1").fetchone()[0]
                             + self.db.execute("SELECT COUNT(*) FROM prosedur WHERE tinjau_ulang=1").fetchone()[0])
        b = self.db.execute("SELECT sesi, COUNT(*) c, SUM(token_dipakai) t FROM panggilan_ingat GROUP BY sesi ORDER BY MAX(id) DESC LIMIT 20").fetchall()
        r["panggilan_per_sesi"] = [{"sesi": x["sesi"], "panggilan": x["c"], "token": x["t"]} for x in b]
        r["metrik_terakhir"] = [dict(x) for x in self.db.execute("SELECT waktu,nama,nilai,konteks FROM metrik ORDER BY id DESC LIMIT 30")]
        r.update(self.encoding_failure())
        return r

    #: Bab 11 — ambang alarm "sesi tanpa episode" (Schacter: absentmindedness).
    AMBANG_SESI_KOSONG = 3

    def encoding_failure(self) -> dict:
        """Bab 11: sesi yang berakhir tanpa episode, plus alarm bila terjadi berturut-turut.

        Deret dihitung dari urutan AKHIR SESI — `sesi_tanpa_episode` (gagal) berselang-seling
        dengan `sesi_dengan_episode` (berhasil). Satu sesi berisi memutus deret; itulah yang
        membedakan "hook mati" dari "kebetulan ada beberapa sesi sepi".
        """
        total = self.db.execute("SELECT COUNT(*) FROM metrik WHERE nama='sesi_tanpa_episode'").fetchone()[0]
        baris = self.db.execute(
            "SELECT nama FROM metrik WHERE nama IN ('sesi_tanpa_episode','sesi_dengan_episode') "
            "ORDER BY id DESC LIMIT 50").fetchall()
        berturut = 0
        for x in baris:
            if x["nama"] != "sesi_tanpa_episode":
                break
            berturut += 1
        alarm = []
        if berturut >= self.AMBANG_SESI_KOSONG:
            alarm.append({"metrik": "sesi_tanpa_episode", "nilai": berturut, "ambang": self.AMBANG_SESI_KOSONG,
                          "pesan": f"{berturut} sesi berturut berakhir tanpa episode — "
                                   "hook tidak jalan atau cakupan tangkap bocor"})
        return {"sesi_tanpa_episode": total, "sesi_tanpa_episode_berturut": berturut, "alarm": alarm}
