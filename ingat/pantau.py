# SPDX-License-Identifier: Apache-2.0
"""`ingat pantau` — monitor visual store di laptop.

Berbeda dari `/dashboard` (Papan Bukti, graf relasi, lewat REST API ber-auth): ini pemantau
kesehatan store yang ringan — kartu metrik + rincian status + alarm, auto-refresh di browser.
Sengaja **localhost saja + baca-saja + tanpa auth**: server terpisah dari `api.py` yang teraudit,
tidak membuka endpoint tulis, tidak menyajikan rahasia (metrik tidak memuat isi episode/token).
Tanpa dependensi eksternal (HTML+JS tangan sendiri di `static/pantau.html`)."""
from __future__ import annotations

import http.server
import json
import os
import webbrowser

from . import __version__
from .aplikasi import Aplikasi

_STATIK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
_HTML = os.path.join(_STATIK, "pantau.html")
_GRAF = os.path.join(_STATIK, "graf.html")


def snapshot(app: Aplikasi) -> dict:
    """Ringkasan yang dikirim ke halaman. Hanya metrik agregat + konteks non-rahasia."""
    from .panel import hitungan_tinjau
    e = app.konfig.get("embedding", {}) or {}
    return {
        "versi": __version__,
        "mode": "relay (baca-saja)" if app.relay else "otoritatif",
        "embedding": {"jenis": e.get("jenis"), "model": e.get("model"), "dim": e.get("dim")},
        "dir_data": app.konfig.get("dir_data"),
        "metrik": app.store.ringkasan_metrik(),
        "tinjau": hitungan_tinjau(app.store),
    }


def graf(app: Aplikasi) -> dict:
    """Graf force-directed: node curated (pelajaran/prosedur/norma/instrumen) dari `bangun_graf`
    PLUS episode sebagai node kecil, dihubungkan ke pelajaran/prosedur yang memakainya sebagai bukti.
    Episode membuat graf padat (mirip graf catatan). Hanya label ringkas — bukan isi verbatim."""
    from .dashboard import bangun_graf
    g = bangun_graf(app)
    id_ep = set()
    for e in app.store.episode_semua():
        g["nodes"].append({"id": e.id, "jenis": "episode", "label": (e.ringkas or e.id)[:48],
                           "lingkup": e.lingkup, "meta": f"episode · {e.jenis_kejadian} · {e.lingkup}"})
        id_ep.add(e.id)
    for p in list(app.store.pelajaran_semua()) + list(app.store.prosedur_semua()):
        for b in (getattr(p, "bukti", None) or []):
            if b in id_ep:
                g["edges"].append({"a": p.id, "b": b, "jenis": "bukti"})
    return g


def hitungan_tinjau_snapshot(app: Aplikasi) -> dict:
    """Ringkasan item yang perlu ditinjau — untuk halaman monitor."""
    from .panel import hitungan_tinjau
    return hitungan_tinjau(app.store)


def timeline_data(app: Aplikasi) -> dict:
    """Episode dikelompokkan per hari, terbaru dulu. Maks 200 episode terbaru."""
    from . import judul_memori as JM
    from . import tag as TAG
    episodes = list(reversed(app.store.episode_semua()))[:200]
    judul_map = JM.semua_judul(app.store)
    tag_map = TAG.semua_tag(app.store)
    hari: dict[str, list] = {}
    for ep in episodes:
        tanggal = (getattr(ep, "waktu", "") or "")[:10]
        if not tanggal:
            continue
        item = {
            "id": ep.id,
            "waktu": getattr(ep, "waktu", ""),
            "judul": judul_map.get(ep.id, ""),
            "ringkas": (getattr(ep, "ringkas", "") or "")[:120],
            "sumber": getattr(ep, "sumber", ""),
            "tier": getattr(ep, "tier", ""),
            "jenis": getattr(ep, "jenis_kejadian", ""),
            "tag": tag_map.get(ep.id, []),
        }
        hari.setdefault(tanggal, []).append(item)
    return {"hari": [{"tanggal": k, "episode": v} for k, v in hari.items()]}


def _buat_handler(app: Aplikasi):
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):  # senyap: hindari bising + kebocoran path ke konsol (K10)
            pass

        def _kirim(self, kode: int, tipe: str, isi: bytes):
            self.send_response(kode)
            self.send_header("Content-Type", tipe)
            self.send_header("Content-Length", str(len(isi)))
            self.end_headers()
            self.wfile.write(isi)

        def _html(self, jalur: str, nama: str):
            try:
                with open(jalur, "rb") as f:
                    return self._kirim(200, "text/html; charset=utf-8", f.read())
            except FileNotFoundError:
                return self._kirim(404, "application/json; charset=utf-8",
                                   f'{{"galat": "static/{nama} tidak ditemukan"}}'.encode("utf-8"))

        def do_GET(self):
            if self.path == "/digest/data":
                from .digest import digest_7_hari
                isi = json.dumps(digest_7_hari(app), ensure_ascii=False).encode("utf-8")
                return self._kirim(200, "application/json; charset=utf-8", isi)
            if self.path.startswith("/digest/data/"):
                from .digest import digest_hari, digest_rentang
                from urllib.parse import urlparse, parse_qs
                parsed = urlparse(self.path)
                tgl = parsed.path.split("/")[-1]
                qs = parse_qs(parsed.query)
                if "sampai" in qs:
                    data = digest_rentang(app.store, tgl, qs["sampai"][0])
                else:
                    data = digest_hari(app.store, tgl)
                isi = json.dumps(data, ensure_ascii=False).encode("utf-8")
                return self._kirim(200, "application/json; charset=utf-8", isi)
            if self.path in ("/digest", "/digest/"):
                return self._html(os.path.join(_STATIK, "digest.html"), "digest.html")
            if self.path == "/data":
                isi = json.dumps(snapshot(app), ensure_ascii=False).encode("utf-8")
                return self._kirim(200, "application/json; charset=utf-8", isi)
            if self.path == "/tinjau":
                isi = json.dumps(hitungan_tinjau_snapshot(app), ensure_ascii=False).encode("utf-8")
                return self._kirim(200, "application/json; charset=utf-8", isi)
            if self.path == "/graf/data":
                isi = json.dumps(graf(app), ensure_ascii=False).encode("utf-8")
                return self._kirim(200, "application/json; charset=utf-8", isi)
            if self.path in ("/graf", "/graf/"):
                return self._html(_GRAF, "graf.html")
            if self.path == "/timeline/data":
                isi = json.dumps(timeline_data(app), ensure_ascii=False).encode("utf-8")
                return self._kirim(200, "application/json; charset=utf-8", isi)
            if self.path in ("/timeline", "/timeline/"):
                return self._html(os.path.join(_STATIK, "timeline.html"), "timeline.html")
            if self.path in ("/", "/pantau", "/pantau/"):
                return self._html(_HTML, "pantau.html")
            return self._kirim(404, "application/json; charset=utf-8", b'{"galat": "tidak ada"}')

    return Handler


def layani_pantau(app: Aplikasi, host: str = "127.0.0.1", port: int = 8790, buka: bool = True) -> int:
    if host not in ("127.0.0.1", "localhost", "::1"):
        # Pemantau ini tanpa auth — menolak bind ke alamat non-loopback adalah pengaman, bukan kenyamanan.
        print(f"[ingat pantau] DITOLAK: host '{host}' bukan loopback. Pemantau ini tanpa auth, "
              f"hanya boleh 127.0.0.1/localhost/::1.")
        return 2
    srv = http.server.ThreadingHTTPServer((host, port), _buat_handler(app))
    url = f"http://{host}:{port}/"
    print(f"[ingat pantau] {url}  (Ctrl+C untuk berhenti · localhost saja · baca-saja)")
    if buka:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[ingat pantau] berhenti")
    finally:
        srv.server_close()
    return 0
