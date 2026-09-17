# SPDX-License-Identifier: Apache-2.0
"""C — rekonsiliasi store ↔ vault.

Mendeteksi dan memperbaiki tiga jenis divergensi:
1. Vault hilang: pelajaran/prosedur ada di store tapi tidak punya .md di vault.
2. Vault yatim: .md ada di vault tapi tidak ada di store.
3. Bukti korup: field bukti/kontra berisi karakter individual (bukan episode ID).

Penyebab bukti korup: saat konsolidasi menggabungkan bukti, `set(string_json)` diiterasi
per-karakter alih-alih `set(list)`. Perbaikan: buang entri yang bukan ID episode valid.
"""
from __future__ import annotations

import glob
import json
import os
import re

from . import frontmatter, skema
from .simpan import Store

_POLA_EP = re.compile(r"^ep-")


def _id_dari_vault(vault_path: str, jenis: str) -> dict[str, str]:
    """Kembalikan {id: path} dari semua .md di folder vault jenis ini."""
    hasil = {}
    for sub in ("", "_usulan", "_tier-s"):
        folder = os.path.join(vault_path, jenis, sub) if sub else os.path.join(vault_path, jenis)
        if not os.path.isdir(folder):
            continue
        for path in glob.glob(os.path.join(folder, "*.md")):
            nama = os.path.splitext(os.path.basename(path))[0]
            if nama.startswith(("pl-", "pr-", "nr-")):
                hasil[nama] = path
    return hasil


def _bukti_korup(daftar: list) -> list:
    """Kembalikan entri yang bukan episode ID valid (sampah dari iterasi karakter)."""
    return [x for x in daftar if not isinstance(x, str) or not _POLA_EP.match(x)]


def _bersihkan_bukti(daftar: list) -> list:
    """Buang entri sampah, pertahankan hanya ID episode valid, hilangkan duplikat."""
    bersih = []
    sudah = set()
    for x in daftar:
        if isinstance(x, str) and _POLA_EP.match(x) and x not in sudah:
            bersih.append(x)
            sudah.add(x)
    return bersih


def periksa(store: Store, vault_path: str | None) -> dict:
    """Periksa divergensi store ↔ vault. Tidak mengubah apa pun."""
    lap = {
        "vault_hilang": [],
        "vault_yatim": [],
        "bukti_korup": [],
        "ringkasan": {},
    }

    semua_pl = store.pelajaran_semua()
    semua_pr = store.prosedur_semua()

    for p in semua_pl:
        sampah = _bukti_korup(p.bukti or [])
        if sampah:
            lap["bukti_korup"].append({
                "id": p.id, "jenis": "pelajaran",
                "sampah": len(sampah), "bersih": len(p.bukti) - len(sampah),
            })
        kontra_sampah = _bukti_korup(p.kontra or [])
        if kontra_sampah:
            lap["bukti_korup"].append({
                "id": p.id, "jenis": "pelajaran", "field": "kontra",
                "sampah": len(kontra_sampah), "bersih": len(p.kontra) - len(kontra_sampah),
            })

    if vault_path and os.path.isdir(vault_path):
        id_vault_pl = _id_dari_vault(vault_path, "pelajaran")
        id_vault_pr = _id_dari_vault(vault_path, "prosedur")
        id_store_pl = {p.id for p in semua_pl}
        id_store_pr = {p.id for p in semua_pr}

        for p in semua_pl:
            if p.id not in id_vault_pl and p.status in ("usulan", "aturan"):
                lap["vault_hilang"].append({"id": p.id, "jenis": "pelajaran", "status": p.status})
        for p in semua_pr:
            if p.id not in id_vault_pr and p.status in ("draf", "teruji", "aktif"):
                lap["vault_hilang"].append({"id": p.id, "jenis": "prosedur", "status": p.status})

        for id_, path in id_vault_pl.items():
            if id_ not in id_store_pl:
                lap["vault_yatim"].append({"id": id_, "jenis": "pelajaran", "path": path})
        for id_, path in id_vault_pr.items():
            if id_ not in id_store_pr:
                lap["vault_yatim"].append({"id": id_, "jenis": "prosedur", "path": path})

    lap["ringkasan"] = {
        "pelajaran_store": len(semua_pl),
        "prosedur_store": len(semua_pr),
        "vault_hilang": len(lap["vault_hilang"]),
        "vault_yatim": len(lap["vault_yatim"]),
        "bukti_korup": len(lap["bukti_korup"]),
    }
    return lap


def perbaiki(store: Store, vault_path: str | None = None, vault=None) -> dict:
    """Perbaiki divergensi. Kembalikan laporan perubahan.

    `vault` = objek Vault (obsidian.Vault) untuk menulis .md yang hilang.
    """
    lap = {"bukti_diperbaiki": [], "vault_ditulis": [], "galat": []}

    semua_pl = store.pelajaran_semua()
    for p in semua_pl:
        diubah = False
        bukti_baru = _bersihkan_bukti(p.bukti or [])
        if len(bukti_baru) != len(p.bukti or []):
            sampah = len(p.bukti or []) - len(bukti_baru)
            store.db.execute("UPDATE pelajaran SET bukti=? WHERE id=?",
                             (json.dumps(bukti_baru), p.id))
            diubah = True
            lap["bukti_diperbaiki"].append({
                "id": p.id, "field": "bukti",
                "sebelum": len(p.bukti or []), "sesudah": len(bukti_baru),
                "dibuang": sampah,
            })
        kontra_baru = _bersihkan_bukti(p.kontra or [])
        if len(kontra_baru) != len(p.kontra or []):
            sampah = len(p.kontra or []) - len(kontra_baru)
            store.db.execute("UPDATE pelajaran SET kontra=? WHERE id=?",
                             (json.dumps(kontra_baru), p.id))
            diubah = True
            lap["bukti_diperbaiki"].append({
                "id": p.id, "field": "kontra",
                "sebelum": len(p.kontra or []), "sesudah": len(kontra_baru),
                "dibuang": sampah,
            })
        if diubah:
            store.db.commit()

    if vault_path and vault:
        id_vault_pl = _id_dari_vault(vault_path, "pelajaran")
        for p in store.pelajaran_semua():
            if p.id not in id_vault_pl and p.status in ("usulan", "aturan"):
                try:
                    ringkas = []
                    for eid in (p.bukti or [])[:5]:
                        ep = store.episode(eid)
                        if ep:
                            ringkas.append(ep.ringkas or eid)
                        else:
                            ringkas.append(f"(episode {eid} tidak ditemukan)")
                    vault.tulis_usulan_pelajaran(p, ringkas)
                    lap["vault_ditulis"].append(p.id)
                except Exception as e:
                    lap["galat"].append(f"{p.id}: {e}")

        id_vault_pr = _id_dari_vault(vault_path, "prosedur")
        for p in store.prosedur_semua():
            if p.id not in id_vault_pr and p.status in ("draf", "teruji", "aktif"):
                try:
                    ringkas = []
                    vault.tulis_usulan_prosedur(p, ringkas)
                    lap["vault_ditulis"].append(p.id)
                except Exception as e:
                    lap["galat"].append(f"{p.id}: {e}")

    return lap
