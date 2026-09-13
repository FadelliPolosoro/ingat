# SPDX-License-Identifier: Apache-2.0
"""K30 — pindah episode antar mesin (ekspor/impor JSON portabel).

Kenapa ada: pelajaran/prosedur/norma pindah lewat vault git (K7), tapi **episode** hidup di store +
penyimpanan dingin, bukan di vault. Saat laptop jadi mesin otoritatif (K30), episode di VPS harus
turun ke laptop — kalau tidak, pointer `bukti` tiap pelajaran menggantung. Alat ini juga menjawab
tujuan lama K30: "perangkat boleh dibuang" butuh jalan memindah riwayat ke perangkat baru.

Dua sifat yang dijaga:
1. **`id` dan `waktu` dipertahankan** — `bukti` pelajaran menunjuk id episode; kalau id berubah,
   seluruh jejak bukti putus.
2. **Impor lewat `Store.tambah_episode` (titik tulis tunggal, AGENTS.md).** Konsekuensinya redaksi
   K10 berjalan ULANG saat impor — itu fitur, bukan beban: kalaupun ekspor memuat kredensial mentah,
   ia tetap diredaksi sebelum mendarat. Vektor dihitung ulang oleh embedder mesin TUJUAN, jadi impor
   tahan beda embedder (mis. e5-base VPS → embedder lain di laptop) tanpa vektor basi.

Ekspor TIDAK memuat kredensial (isi sudah diredaksi saat pertama ditulis). Tetap perlakukan berkas
ekspor sebagai sensitif: ia memuat episode tier S verbatim (K10).
"""
from __future__ import annotations

from . import skema
from .simpan import Store

VERSI_EKSPOR = 1


def _identitas(store: Store) -> dict:
    p = store.penyemat
    return {"nama": getattr(p, "nama", type(p).__name__), "dim": int(getattr(p, "dim", 0) or 0)}


def ekspor(store: Store) -> dict:
    """Seluruh episode + isi verbatim → dict JSON-serializable."""
    episode = []
    for ep in store.episode_semua():
        cold = store.buka_dingin(ep.isi_ref) if ep.isi_ref else {}
        episode.append({"meta": skema.ke_dict(ep), "isi": cold.get("isi", "")})
    return {"versi_ekspor": VERSI_EKSPOR, "waktu": skema.sekarang(),
            "embedder": _identitas(store), "jumlah": len(episode), "episode": episode}


# Field Episode yang diteruskan apa adanya ke tambah_episode. Sengaja TIDAK termasuk:
# bobot (diturunkan dari jenis_kejadian di __post_init__), isi_ref (ditulis internal),
# diredaksi (dihitung ulang oleh redaksi saat impor).
_FIELD_TERUS = ("sumber", "tier", "lingkup", "jenis_kejadian", "ringkas", "instrumen", "status", "langkah", "sesi")


def impor(store: Store, data: dict, lewati_ada: bool = True) -> dict:
    """Terapkan hasil ekspor ke `store`. Idempoten: episode ber-id yang sudah ada dilewati
    (kecuali `lewati_ada=False`, yang menimpa lewat upsert `tambah_episode`)."""
    versi = data.get("versi_ekspor")
    if versi != VERSI_EKSPOR:
        raise ValueError(f"versi ekspor '{versi}' tak dikenal (diharapkan {VERSI_EKSPOR})")
    laporan = {"diimpor": 0, "dilewati_sudah_ada": 0, "total": len(data.get("episode", [])),
               "embedder_sumber": data.get("embedder"), "embedder_tujuan": _identitas(store)}
    for e in data.get("episode", []):
        m = dict(e.get("meta") or {})
        id_ = m.get("id")
        if not id_:
            continue
        if lewati_ada and store.episode(id_) is not None:
            laporan["dilewati_sudah_ada"] += 1
            continue
        meta = {k: m[k] for k in _FIELD_TERUS if k in m}
        store.tambah_episode(e.get("isi", ""), id=id_, waktu=m.get("waktu"), **meta)
        laporan["diimpor"] += 1
    return laporan
