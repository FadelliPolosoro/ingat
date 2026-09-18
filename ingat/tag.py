# SPDX-License-Identifier: Apache-2.0
"""Tag otomatis per episode (19 Sep 2026).

Tabel sidecar `tag_episode` menyimpan 1-4 tag per episode tanpa mengubah data asli.
Otak baku: `tag_heuristik` (deterministik, tanpa LLM). Pattern mengikuti `judul_memori.py`.
"""
from __future__ import annotations

from . import skema

SKEMA_TAG = """
CREATE TABLE IF NOT EXISTS tag_episode (
  item_id TEXT NOT NULL,
  tag     TEXT NOT NULL,
  sumber  TEXT NOT NULL DEFAULT 'heuristik',
  waktu   TEXT NOT NULL,
  PRIMARY KEY (item_id, tag)
);
CREATE INDEX IF NOT EXISTS ix_tag_episode_tag ON tag_episode(tag);
"""

_PETA_PLATFORM = {
    "browser:gemini.google.com": "gemini",
    "browser:chatgpt.com": "chatgpt",
    "browser:chat.openai.com": "chatgpt",
    "browser:claude.ai": "claude-ai",
    "browser:www.perplexity.ai": "perplexity",
    "browser:perplexity.ai": "perplexity",
    "mcp": "claude-desktop",
    "claude-code": "claude-code",
    "claude-code-histori": "claude-code",
    "panel": "panel",
}

_PETA_KATA = {
    "deploy": "deploy", "server": "server", "vps": "server",
    "bug": "debug", "error": "debug", "gagal": "debug",
    "security": "keamanan", "enkripsi": "keamanan", "sandi": "keamanan",
    "api": "api", "endpoint": "api",
    "database": "database", "sql": "database", "sqlite": "database",
    "ui": "ui", "panel": "ui", "dashboard": "ui", "css": "ui",
    "test": "pengujian", "uji": "pengujian",
    "config": "konfigurasi", "konfig": "konfigurasi", "setup": "konfigurasi",
}


def _pastikan_tabel(store):
    store.db.executescript(SKEMA_TAG)
    store.db.commit()


def tag_heuristik(ep, judul: str = "") -> list[str]:
    """Beri 1-4 tag otomatis berdasarkan field episode. Tanpa LLM, deterministik."""
    tags = []

    sumber = getattr(ep, "sumber", "") or ""
    if sumber in _PETA_PLATFORM:
        tags.append(_PETA_PLATFORM[sumber])
    elif sumber.startswith("browser:"):
        tags.append("web")

    jenis = getattr(ep, "jenis_kejadian", "") or ""
    if jenis in ("gagal", "debug"):
        tags.append("debug")
    elif jenis == "keputusan":
        tags.append("keputusan")
    elif jenis == "prosedur-dijalankan":
        tags.append("prosedur")
    elif jenis == "hipotesis":
        tags.append("riset")

    tier = getattr(ep, "tier", "") or ""
    if tier == "S":
        tags.append("rahasia")

    teks = ((getattr(ep, "ringkas", "") or "") + " " + judul).lower()
    for kata, tag in _PETA_KATA.items():
        if kata in teks and tag not in tags:
            tags.append(tag)
            if len(tags) >= 4:
                break

    return tags[:4]


def tandai(store, otak_fn=tag_heuristik, otak: str = "heuristik", batas: int | None = None) -> dict:
    """Beri tag ke semua episode yang belum punya. Return {diproses, ditulis}."""
    _pastikan_tabel(store)
    from . import judul_memori as JM
    eps = store.episode_semua()
    if batas:
        eps = eps[:batas]
    judul_map = JM.semua_judul(store)
    sudah = set(r["item_id"] for r in store.db.execute("SELECT DISTINCT item_id FROM tag_episode"))
    waktu = skema.sekarang()
    ditulis = 0
    for ep in eps:
        if ep.id in sudah:
            continue
        judul = judul_map.get(ep.id, "")
        tags = otak_fn(ep, judul)
        for t in tags:
            store.db.execute(
                "INSERT OR IGNORE INTO tag_episode(item_id,tag,sumber,waktu) VALUES(?,?,?,?)",
                (ep.id, t, otak, waktu),
            )
        if tags:
            ditulis += 1
    store.db.commit()
    return {"diproses": len(eps), "ditulis": ditulis}


def tag_untuk(store, item_id: str) -> list[str]:
    """Ambil semua tag untuk satu episode."""
    _pastikan_tabel(store)
    return [r["tag"] for r in store.db.execute(
        "SELECT tag FROM tag_episode WHERE item_id=? ORDER BY tag", (item_id,))]


def set_tag(store, item_id: str, tags: list[str], sumber: str = "manusia") -> None:
    """Timpa tag satu episode (mis. edit manual)."""
    _pastikan_tabel(store)
    waktu = skema.sekarang()
    store.db.execute("DELETE FROM tag_episode WHERE item_id=?", (item_id,))
    for t in tags:
        t = t.strip()
        if t:
            store.db.execute(
                "INSERT OR IGNORE INTO tag_episode(item_id,tag,sumber,waktu) VALUES(?,?,?,?)",
                (item_id, t, sumber, waktu),
            )
    store.db.commit()


def hapus_tag(store, item_id: str) -> None:
    """Hapus semua tag satu episode."""
    _pastikan_tabel(store)
    store.db.execute("DELETE FROM tag_episode WHERE item_id=?", (item_id,))
    store.db.commit()


def semua_tag(store) -> dict[str, list[str]]:
    """Kembalikan {item_id: [tag, ...]} untuk semua episode ber-tag."""
    _pastikan_tabel(store)
    hasil: dict[str, list[str]] = {}
    for r in store.db.execute("SELECT item_id, tag FROM tag_episode ORDER BY item_id, tag"):
        hasil.setdefault(r["item_id"], []).append(r["tag"])
    return hasil


def daftar_tag_unik(store) -> list[dict]:
    """Kembalikan daftar tag unik + jumlah episode per tag, urut terbanyak."""
    _pastikan_tabel(store)
    return [{"tag": r["tag"], "jumlah": r["n"]} for r in store.db.execute(
        "SELECT tag, COUNT(DISTINCT item_id) AS n FROM tag_episode GROUP BY tag ORDER BY n DESC, tag")]


def episode_dengan_tag(store, tag: str) -> list[str]:
    """Kembalikan list item_id yang punya tag tertentu."""
    _pastikan_tabel(store)
    return [r["item_id"] for r in store.db.execute(
        "SELECT item_id FROM tag_episode WHERE tag=?", (tag,))]
