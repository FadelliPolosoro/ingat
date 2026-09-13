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

_HTML = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "pantau.html")


def snapshot(app: Aplikasi) -> dict:
    """Ringkasan yang dikirim ke halaman. Hanya metrik agregat + konteks non-rahasia."""
    e = app.konfig.get("embedding", {}) or {}
    return {
        "versi": __version__,
        "mode": "relay (baca-saja)" if app.relay else "otoritatif",
        "embedding": {"jenis": e.get("jenis"), "model": e.get("model"), "dim": e.get("dim")},
        "dir_data": app.konfig.get("dir_data"),
        "metrik": app.store.ringkasan_metrik(),
    }


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

        def do_GET(self):
            if self.path == "/data":
                isi = json.dumps(snapshot(app), ensure_ascii=False).encode("utf-8")
                return self._kirim(200, "application/json; charset=utf-8", isi)
            if self.path in ("/", "/pantau", "/pantau/"):
                try:
                    with open(_HTML, "rb") as f:
                        return self._kirim(200, "text/html; charset=utf-8", f.read())
                except FileNotFoundError:
                    return self._kirim(404, "application/json; charset=utf-8",
                                       b'{"galat": "static/pantau.html tidak ditemukan"}')
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
