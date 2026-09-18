# SPDX-License-Identifier: Apache-2.0
"""Data untuk dashboard visual (Papan Bukti). Bukan wikilink generik ala aplikasi catatan — edge dihitung
dari relasi struktural yang benar-benar ada di skema Bab 6: bukti yang sama, norma yang saling
menggantikan, instrumen yang melahirkan pelajaran. Tanpa dependensi eksternal (SVG + JS tangan sendiri
di sisi klien, lihat static/dashboard.html)."""
from __future__ import annotations

from .aplikasi import Aplikasi


def _potong(teks: str | None, n: int = 220) -> str:
    if not teks:
        return ""
    return teks if len(teks) <= n else teks[: n - 1].rstrip() + "…"


def bangun_graf(app: Aplikasi, lingkup: str | None = None) -> dict:
    pelajaran = app.store.pelajaran_semua()
    prosedur = app.store.prosedur_semua()
    norma = app.store.norma_semua()
    instrumen = app.store.instrumen_semua()

    if lingkup:
        pelajaran = [p for p in pelajaran if p.lingkup == lingkup or p.lingkup == "global"]
        prosedur = [p for p in prosedur if p.lingkup == lingkup or p.lingkup == "global"]

    nodes: list[dict] = []
    for p in pelajaran:
        nodes.append({
            "id": p.id, "jenis": "pelajaran", "label": _potong(p.pelajaran, 60), "status": p.status,
            "lingkup": p.lingkup, "keyakinan": round(p.keyakinan, 2),
            "detail": f"{p.pelajaran}\n\nPemicu: {p.pemicu}\nTindakan: {p.tindakan}",
            "meta": f"{p.status} · keyakinan {p.keyakinan:.2f} · {len(p.bukti)} bukti · {p.lingkup}",
        })
    for p in prosedur:
        nodes.append({
            "id": p.id, "jenis": "prosedur", "label": _potong(p.prosedur, 60), "status": p.status,
            "lingkup": p.lingkup, "keyakinan": round(p.tingkat_berhasil, 2),
            "detail": f"{p.prosedur}\n\nDipicu tugas: {p.tugas_pemicu}\n\nLangkah:\n" + "\n".join(f"- {l}" for l in p.langkah),
            "meta": f"{p.status} · berhasil {p.tingkat_berhasil:.0%} · {p.lingkup}",
        })
    for n in norma:
        nodes.append({
            "id": n.id, "jenis": "norma", "label": _potong(n.norma, 60), "status": n.status,
            "lingkup": "global", "keyakinan": 1.0 if n.otoritatif else 0.5,
            "detail": f"{n.norma}\n{n.judul or ''}\n\nAlasan: {n.alasan or '(belum diisi)'}\n\nPeralihan: {n.peralihan or '(belum diisi)'}",
            "meta": f"{n.status} · berlaku sejak {n.berlaku_sejak or '?'} · {n.jenis}",
        })
    for i in instrumen:
        nodes.append({
            "id": i.id, "jenis": "instrumen", "label": _potong(i.nama, 60), "status": "aktif",
            "lingkup": "global", "keyakinan": 1.0,
            "detail": f"{i.nama}\n\nCakupan: {i.cakupan or '(belum diisi)'}\nDipasang: {i.dipasang_sejak or '?'}",
            "meta": f"instrumen · dipasang {i.dipasang_sejak or '?'}",
        })

    id_ada = {n["id"] for n in nodes}
    edges: list[dict] = []

    # norma yang saling menggantikan — arah historis, bukan bukti
    for n in norma:
        for lama in n.mengganti:
            if lama in id_ada:
                edges.append({"a": n.id, "b": lama, "jenis": "mengganti"})

    # pelajaran/prosedur berbagi episode bukti yang sama -> benang investigasi
    berbukti = [(p.id, set(p.bukti)) for p in pelajaran if p.bukti] + [(p.id, set(p.bukti)) for p in prosedur if p.bukti]
    for i in range(len(berbukti)):
        for j in range(i + 1, len(berbukti)):
            id_a, bukti_a = berbukti[i]
            id_b, bukti_b = berbukti[j]
            if bukti_a & bukti_b:
                edges.append({"a": id_a, "b": id_b, "jenis": "bukti-bersama"})

    # instrumen -> pelajaran yang lahir darinya
    for p in pelajaran:
        for ins_id in p.instrumen_saat_dibuat:
            if ins_id in id_ada:
                edges.append({"a": ins_id, "b": p.id, "jenis": "instrumen"})

    return {"nodes": nodes, "edges": edges}
