# SPDX-License-Identifier: Apache-2.0
"""Perakit komponen dari konfigurasi (dipakai oleh API, MCP, dan CLI)."""
from __future__ import annotations

import json
import os

from . import penyedia as mod_penyedia
from .gate import Gate
from .gateway import Gateway
from .konsolidasi import Konsolidator
from .obsidian import Vault
from .simpan import Store
from .vektor import PenyematLokal, PenyematHTTP, PenyematOllama

KONFIG_DEFAULT = {
    "dir_data": "./data",
    "vault": "./vault",
    "embedding": {"jenis": "lokal"},
    "gateway": {"anggaran_tarik": 600, "maks_item": 5, "anggaran_peta": 300, "anggaran_aturan": 1500, "rasio_maks": 0.15},
    "gate": {"P": [], "I": [], "S": []},
    "penyedia": {},
    "auth": {"allowed_emails": [], "redirect_uri": ""},
    "server": {"host": "127.0.0.1", "port": 8765, "proxy_tepercaya": False, "batas_body": 1_048_576,
               "timeout_detik": 30, "laju_per_menit": 120},
}


def muat_konfig(path: str | None = None) -> dict:
    path = path or os.environ.get("INGAT_KONFIG", "konfigurasi.json")
    k = json.loads(json.dumps(KONFIG_DEFAULT))
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            pengguna = json.load(f)
        for a, b in pengguna.items():
            if isinstance(b, dict) and isinstance(k.get(a), dict):
                k[a].update(b)
            else:
                k[a] = b
    # env menimpa lokasi
    k["dir_data"] = os.environ.get("INGAT_DIR_DATA", k["dir_data"])
    k["vault"] = os.environ.get("INGAT_VAULT", k["vault"])
    return k


class Aplikasi:
    def __init__(self, konfig: dict, bangun_ulang_vektor: bool = False):
        """`bangun_ulang_vektor`: satu-satunya jalan sah keluar dari IdentitasEmbedderTidakCocok
        (K8/K9) — ganti model embedding = semat ulang semua item. Dipakai perintah
        `ingat bangun-ulang-vektor`; jangan dinyalakan sebagai kebiasaan."""
        self.konfig = konfig
        e = konfig.get("embedding", {})
        if e.get("jenis") == "http":
            kunci = os.environ.get(e.get("env", "EMBEDDING_API_KEY"), "")
            self.penyemat = PenyematHTTP(e["base_url"], kunci, e["model"])
        elif e.get("jenis") == "ollama":  # K5/K8/K9: model dibangun sendiri, lihat model/README.md
            self.penyemat = PenyematOllama(e.get("host", "http://127.0.0.1:11434"), e.get("model", "ingat-e5-base"),
                                           int(e.get("dim", 768)), bool(e.get("prefiks", True)))
        else:
            self.penyemat = PenyematLokal(int(e.get("dim", 512)))
        os.makedirs(konfig["dir_data"], exist_ok=True)
        self.store = Store(konfig["dir_data"], self.penyemat, bangun_ulang_vektor=bangun_ulang_vektor)
        self.vault = Vault(konfig["vault"]) if konfig.get("vault") else None
        self.gate = Gate(konfig.get("gate"))
        self.penyedia = mod_penyedia.bangun_penyedia(konfig.get("penyedia"))
        self.gateway = Gateway(self.store, konfig.get("gateway"))
        self.konsolidator = Konsolidator(self.store, self.gate, self.penyedia, self.vault, konfig.get("konsolidasi"))

    # ---- /tanya: konektor keluar dengan memori disuntik --------------------
    def tanya(self, penyedia_id: str, pesan: str, lingkup: str, tier: str = "P", tugas: str | None = None,
              lingkungan: dict | None = None, sesi: str = "", catat: bool = True, ukuran_context: int = 128_000) -> dict:
        if penyedia_id not in self.penyedia:
            raise KeyError(f"penyedia '{penyedia_id}' tidak aktif/terkonfigurasi; tersedia: {sorted(self.penyedia)}")
        self.gate.wajib(penyedia_id, tier)
        startup = self.gateway.muat_startup(lingkup, tugas, lingkungan, sesi)
        tarik = self.gateway.ingat(pesan, lingkup, tugas=tugas, lingkungan=lingkungan, sesi=sesi)
        blok = ["Kamu bekerja dengan sistem memori 'ingat'. Patuhi aturan berikut:",
                "- Item berbendera 'belum_ditinjau' adalah pola yang belum disetujui manusia: boleh dipakai, wajib disebut sebagai belum ditinjau.",
                "- Item 'versi_berbeda' mungkin tidak berlaku untuk lingkungan sekarang.",
                "- Peringatan 'pernah_ditarik' berarti keyakinan lama yang terbukti salah — jangan dipakai.",
                "- Norma berlaku per tanggal peristiwa; asumsi tanggal tercantum.",
                "", "## L-peta", *startup["peta"], "", "## L-aturan", *startup["aturan"],
                "", "## L-tarik", *[i["teks"] for i in tarik["item"]]]
        if tarik["peringatan"]:
            blok += ["", "## Peringatan", *[p["teks"] for p in tarik["peringatan"]]]
        if tarik["asumsi"]:
            blok += ["", "## Asumsi", *tarik["asumsi"]]
        sistem = "\n".join(blok)
        token_memori = startup["token"]["total"] + tarik["token"]
        rasio = self.gateway.rasio_konteks(token_memori, ukuran_context)
        jawaban = self.penyedia[penyedia_id].tanya(sistem, pesan)
        episode_id = None
        if catat and tier != "S":
            ep = self.store.tambah_episode(
                f"[pengguna]\n{pesan}\n\n[{penyedia_id}]\n{jawaban}",
                sumber=f"tanya:{penyedia_id}", tier=tier, lingkup=lingkup, jenis_kejadian="sukses",
                ringkas=pesan[:200], sesi=sesi, instrumen=[f"llm:{penyedia_id}"])
            episode_id = ep.id
        return {"jawaban": jawaban, "penyedia": penyedia_id, "memori": {"peta": startup["peta"], "aturan": startup["aturan"],
                "tarik": tarik["item"], "pointer": tarik["pointer"] + startup["pointer"]},
                "bendera": tarik["bendera"], "peringatan": tarik["peringatan"], "asumsi": tarik["asumsi"],
                "token_memori": token_memori, "rasio_konteks": rasio, "episode": episode_id}
