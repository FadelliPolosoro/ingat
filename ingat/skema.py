# SPDX-License-Identifier: Apache-2.0
"""Skema empat jenis pengetahuan dan state machine (Bab 4–6 spek).

Semua transisi status lewat `periksa_transisi()`; transisi yang hanya boleh
dilakukan manusia ditolak bila `oleh == "mesin"`.
"""
from __future__ import annotations

import datetime as dt
import secrets
from dataclasses import dataclass, field, asdict
from typing import Any

JENIS = ("episode", "pelajaran", "prosedur", "norma")
TIER = ("P", "I", "S")
JENIS_KEJADIAN = ("koreksi", "kegagalan", "pola", "sukses")

# Bab 7.2 — bobot per jenis kejadian dan ambang hipotesis -> usulan
BOBOT = {"koreksi": 5, "kegagalan": 3, "pola": 2, "sukses": 1}
AMBANG_USULAN = 5
HARI_TINJAU_DEFAULT = 90
HARI_TINJAU_MAKS = 365

# Bab 5 — transisi yang diizinkan
TRANSISI: dict[str, dict[str, set[str]]] = {
    "episode": {
        "aktif": {"didinginkan"},
        "didinginkan": {"diarsipkan"},
        "diarsipkan": set(),
    },
    "pelajaran": {
        "hipotesis": {"usulan", "ditarik"},
        "usulan": {"aturan", "ditarik"},
        "aturan": {"dipersempit", "ditarik"},
        "dipersempit": {"aturan", "ditarik"},
        "ditarik": set(),
    },
    "prosedur": {
        "draf": {"teruji", "ditarik"},
        "teruji": {"aktif", "ditarik"},
        "aktif": {"dipersempit", "ditarik"},
        "dipersempit": {"aktif", "ditarik"},
        "ditarik": set(),
    },
    "norma": {
        "berlaku": {"dicabut", "dibatalkan"},
        "dicabut": set(),
        "dibatalkan": set(),
    },
}

# Transisi yang HANYA boleh dilakukan manusia (P5, P10, R6)
HANYA_MANUSIA = {
    ("pelajaran", "usulan", "aturan"),
    ("pelajaran", "dipersempit", "aturan"),
    ("prosedur", "teruji", "aktif"),
    ("prosedur", "dipersempit", "aktif"),
    ("norma", "berlaku", "dicabut"),      # norma bersumber otoritas; perubahan statusnya keputusan manusia (Bab 5.2)
    ("norma", "berlaku", "dibatalkan"),
}

STATUS_AWAL = {"episode": "aktif", "pelajaran": "hipotesis", "prosedur": "draf", "norma": "berlaku"}


class TransisiTerlarang(Exception):
    pass


def periksa_transisi(jenis: str, dari: str, ke: str, oleh: str = "mesin") -> None:
    if jenis not in TRANSISI:
        raise TransisiTerlarang(f"jenis tidak dikenal: {jenis}")
    if dari not in TRANSISI[jenis]:
        raise TransisiTerlarang(f"status awal tidak dikenal untuk {jenis}: {dari}")
    if ke not in TRANSISI[jenis][dari]:
        raise TransisiTerlarang(f"{jenis}: {dari} -> {ke} tidak diizinkan")
    if (jenis, dari, ke) in HANYA_MANUSIA and oleh != "manusia":
        raise TransisiTerlarang(f"{jenis}: {dari} -> {ke} hanya boleh oleh manusia")


def sekarang() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def hari_ini() -> str:
    return dt.date.today().isoformat()


def tambah_hari(tanggal_iso: str, hari: int) -> str:
    return (dt.date.fromisoformat(tanggal_iso[:10]) + dt.timedelta(days=hari)).isoformat()


def id_baru(awalan: str) -> str:
    return f"{awalan}-{secrets.token_hex(3)}"


def id_episode() -> str:
    stempel = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"ep-{stempel}-{secrets.token_hex(2)}"


# ---- lingkup (P9) --------------------------------------------------------

def lingkup_valid(lingkup: str) -> bool:
    if lingkup == "global":
        return True
    return bool(lingkup) and ":" in lingkup and lingkup.split(":", 1)[0] in ("proyek", "peran")


def lingkup_memuat(lingkup_item: str, lingkup_sesi: str) -> bool:
    """Item `global` menyala di mana pun; selain itu harus persis sama."""
    return lingkup_item == "global" or lingkup_item == lingkup_sesi


def tier_tertinggi(daftar: list[str]) -> str:
    urut = {"P": 0, "I": 1, "S": 2}
    return max(daftar, key=lambda t: urut.get(t, 0)) if daftar else "P"


def hitung_token(teks: str) -> int:
    """Perkiraan kasar (~4 karakter/token). Cukup untuk anggaran, bukan untuk tagihan."""
    return max(1, len(teks) // 4)


# ---- record --------------------------------------------------------------

@dataclass
class Episode:
    id: str
    waktu: str
    sumber: str
    tier: str
    lingkup: str
    jenis_kejadian: str
    ringkas: str
    instrumen: list[str] = field(default_factory=list)
    bobot: int = 1
    status: str = "aktif"
    isi_ref: str = ""
    langkah: list[str] = field(default_factory=list)
    sesi: str = ""
    diredaksi: list[str] = field(default_factory=list)  # K10: jenis kredensial yang diredaksi, bukan nilainya

    def __post_init__(self):
        if self.tier not in TIER:
            raise ValueError(f"tier tidak dikenal: {self.tier}")
        if self.jenis_kejadian not in JENIS_KEJADIAN:
            raise ValueError(f"jenis_kejadian tidak dikenal: {self.jenis_kejadian}")
        if not lingkup_valid(self.lingkup):
            raise ValueError(f"lingkup tidak valid: {self.lingkup}")
        self.bobot = BOBOT[self.jenis_kejadian]


@dataclass
class Pelajaran:
    id: str
    pelajaran: str
    pemicu: str
    tindakan: str
    lingkup: str
    status: str = "hipotesis"
    keyakinan: float = 0.5
    bukti: list[str] = field(default_factory=list)
    kontra: list[str] = field(default_factory=list)
    instrumen_saat_dibuat: list[str] = field(default_factory=list)
    berlaku_untuk: dict[str, str] = field(default_factory=dict)
    tinjau_setelah: str = ""
    dibuat: str = ""
    terakhir_dikonfirmasi: str = ""
    tinjau_ulang: bool = False
    ditinjau_manusia: bool = False
    veto_manusia: str | None = None
    tier_maks: str = "P"
    sintesis: str = "llm"           # llm | heuristik | manusia
    usulan_perluasan_lingkup: str | None = None
    catatan: str = ""

    def __post_init__(self):
        if not lingkup_valid(self.lingkup):
            raise ValueError(f"lingkup tidak valid: {self.lingkup}")
        if not self.dibuat:
            self.dibuat = hari_ini()
        if not self.terakhir_dikonfirmasi:
            self.terakhir_dikonfirmasi = self.dibuat
        if not self.tinjau_setelah:
            self.tinjau_setelah = tambah_hari(self.dibuat, HARI_TINJAU_DEFAULT)

    def teks_embedding(self) -> str:
        return f"{self.pelajaran}\n{self.pemicu}\n{self.tindakan}"


@dataclass
class Prosedur:
    id: str
    prosedur: str
    tugas_pemicu: str
    langkah: list[str]
    lingkup: str
    bentuk: str = "teks"            # teks | skrip:<path> | hook:<path> | skill:<nama>
    status: str = "draf"
    eksekusi_total: int = 0
    eksekusi_berhasil: int = 0
    gagal_beruntun: int = 0
    bukti: list[str] = field(default_factory=list)
    berlaku_untuk: dict[str, str] = field(default_factory=dict)
    tinjau_setelah: str = ""
    uji: str = ""
    ditinjau_manusia: bool = False
    veto_manusia: str | None = None
    tinjau_ulang: bool = False
    dibuat: str = ""
    tier_maks: str = "P"
    catatan: str = ""

    def __post_init__(self):
        if not lingkup_valid(self.lingkup):
            raise ValueError(f"lingkup tidak valid: {self.lingkup}")
        if not self.dibuat:
            self.dibuat = hari_ini()
        if not self.tinjau_setelah:
            self.tinjau_setelah = tambah_hari(self.dibuat, HARI_TINJAU_DEFAULT)

    @property
    def tingkat_berhasil(self) -> float:
        return self.eksekusi_berhasil / self.eksekusi_total if self.eksekusi_total else 1.0

    def teks_embedding(self) -> str:
        return f"{self.prosedur}\n{self.tugas_pemicu}"


@dataclass
class Norma:
    id: str
    norma: str
    judul: str = ""
    jenis: str = "perpres"
    otoritatif: bool = True
    berlaku_sejak: str | None = None
    berlaku_sampai: str | None = None      # diturunkan dari dicabut_oleh saat sinkron
    dicabut_oleh: str | None = None
    dibatalkan_oleh: str | None = None
    mengganti: list[str] = field(default_factory=list)
    alasan: str = ""
    peralihan: str = ""
    sumber_dokumen: str = ""
    status: str = "berlaku"
    # tampilan konsolidasi (6.4)
    disusun_dari: list[str] = field(default_factory=list)
    disusun_pada: str | None = None
    disusun_oleh: str | None = None
    berlaku_untuk_tanggal: str | None = None
    catatan: str = ""
    isi: str = ""

    def teks_embedding(self) -> str:
        return f"{self.norma}\n{self.judul}\n{self.alasan}\n{self.isi[:2000]}"

    def berlaku_pada(self, tanggal: str) -> bool:
        if self.status == "dibatalkan":
            return False
        if not self.otoritatif:
            return self.berlaku_untuk_tanggal == tanggal
        if not self.berlaku_sejak or self.berlaku_sejak > tanggal:
            return False
        if self.berlaku_sampai and tanggal >= self.berlaku_sampai:
            return False
        return True


@dataclass
class Instrumen:
    id: str
    nama: str
    dipasang_sejak: str | None = None
    cakupan: str = ""
    titik_buta_diketahui: list[str] = field(default_factory=list)


def ke_dict(obj: Any) -> dict:
    return asdict(obj)
