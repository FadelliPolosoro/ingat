# SPDX-License-Identifier: Apache-2.0
"""REST API — konektor masuk (ChatGPT Actions, Perplexity, skrip, dashboard).

Keamanan (mengikuti temuan audit fp-dashboard):
- INGAT_TOKEN wajib dari environment; tanpa itu server MENOLAK start (tidak ada fallback).
- X-Forwarded-For hanya dipercaya bila server.proxy_tepercaya = true (di belakang Caddy).
- Timeout socket, batas ukuran body, rate limit sederhana per IP.
- Tidak ada endpoint tanpa autentikasi kecuali /sehat (tanpa data).
"""
from __future__ import annotations

import hmac
import json
import os
import re
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from . import __version__, __penulis__, skema
from .aplikasi import Aplikasi
from .gate import GateDitolak
from .relay import jalur_tulis as relay_jalur_tulis, tolak as relay_tolak
from .penyedia import PenyediaGagal, daftar_preset
from .mcp_http import tangani_http as _mcp_http, ambil_token_dari_path, token_cocok
from .dashboard import bangun_graf
from .auth_google import (
    url_masuk, tukar_kode, verifikasi_id_token, email_diizinkan,
    buat_sesi, baca_sesi, ambil_cookie, AuthGagal,
)
from .auth_totp import verifikasi_kode as totp_verifikasi_kode

_LAJU: dict[str, list[float]] = {}
_LAJU_KUNCI = threading.Lock()
# Pembatas laju KHUSUS TOTP — ruang kode 6-digit jauh lebih kecil dari token 32-byte, jadi jauh lebih
# ketat: 5 percobaan / 5 menit per IP, terlepas dari batas laju umum di atas (K26).
_LAJU_TOTP: dict[str, list[float]] = {}
_LAJU_TOTP_KUNCI = threading.Lock()
_TOTP_MAKS_PERCOBAAN = 5
_TOTP_JENDELA_DETIK = 300
_POLA_TOKEN_PATH = re.compile(r"(/mcp)/[^\s\"?#]+")


def _openapi(host: str) -> dict:
    def op(ringkas, badan=None, respons="object"):
        o = {"summary": ringkas, "security": [{"bearer": []}], "responses": {"200": {"description": "OK"}}}
        if badan:
            o["requestBody"] = {"required": True, "content": {"application/json": {"schema": {"type": "object", "properties": badan}}}}
        return o
    S = {"type": "string"}
    return {
        "openapi": "3.1.0",
        "info": {"title": "ingat — Sistem Memori Agent", "version": __version__, "description": f"Dibuat oleh {__penulis__}. Implementasi docs/spek-arsitektur-memori.md"},
        "servers": [{"url": host}],
        "components": {"securitySchemes": {"bearer": {"type": "http", "scheme": "bearer"}}},
        "paths": {
            "/sehat": {"get": {"summary": "Status layanan", "responses": {"200": {"description": "OK"}}}},
            "/episode": {"post": op("Catat episode (L0). `id` opsional: kirim id deterministik untuk meng-upsert episode yang sama (dipakai hook Stop).", {"isi": S, "id": S, "sumber": S, "tier": S, "lingkup": S, "jenis_kejadian": S, "ringkas": S, "instrumen": {"type": "array", "items": S}, "langkah": {"type": "array", "items": S}, "sesi": S})},
            "/ingat": {"post": op("L-tarik: ambil memori berperingkat", {"query": S, "lingkup": S, "jenis": S, "tanggal_peristiwa": S, "tugas": S, "lingkungan": {"type": "object"}, "anggaran_token": {"type": "integer"}, "sesi": S})},
            "/startup": {"post": op("L-peta + L-aturan", {"lingkup": S, "tugas": S, "lingkungan": {"type": "object"}, "sesi": S})},
            "/bukti/{id}": {"get": {"summary": "L-bukti: isi verbatim satu episode", "security": [{"bearer": []}], "parameters": [{"name": "id", "in": "path", "required": True, "schema": S}], "responses": {"200": {"description": "OK"}}}},
            "/tanya": {"post": op("Tanya penyedia LLM dengan memori disuntik", {"penyedia": S, "pesan": S, "lingkup": S, "tier": S, "tugas": S, "lingkungan": {"type": "object"}, "sesi": S})},
            "/konsolidasi": {"post": op("Jalankan job konsolidasi", {"jalur": S})},
            "/sinkron": {"post": op("Sinkron vault Obsidian -> store")},
            "/instrumen": {"post": op("Daftarkan instrumen baru (7.4)", {"id": S, "nama": S, "dipasang_sejak": S, "cakupan": S, "titik_buta_diketahui": {"type": "array", "items": S}})},
            "/prosedur/{id}/eksekusi": {"post": {"summary": "Catat hasil eksekusi prosedur", "security": [{"bearer": []}], "parameters": [{"name": "id", "in": "path", "required": True, "schema": S}], "requestBody": {"content": {"application/json": {"schema": {"type": "object", "properties": {"berhasil": {"type": "boolean"}}}}}}, "responses": {"200": {"description": "OK"}}}},
            "/metrik": {"get": op("Ringkasan metrik (Bab 11)"),
                        "post": op("Catat satu metrik (dipakai hook mode jauh)", {"nama": S, "nilai": {"type": "number"}, "konteks": {"type": "object"}})},
            "/penyedia": {"get": op("Daftar penyedia aktif + preset")},
        },
    }


def buat_handler(app: Aplikasi, token: str, konfig_server: dict, google: dict | None = None,
                 totp_rahasia: str = "", sesi_rahasia: str = ""):
    proxy_tepercaya = bool(konfig_server.get("proxy_tepercaya"))
    batas_body = int(konfig_server.get("batas_body", 1_048_576))
    laju_per_menit = int(konfig_server.get("laju_per_menit", 120))
    google = google or {}
    sesi_rahasia = sesi_rahasia or google.get("sesi_rahasia", "")
    auth_konfig = app.konfig.get("auth", {})

    class Handler(BaseHTTPRequestHandler):
        server_version = f"ingat/{__version__}"
        timeout = int(konfig_server.get("timeout_detik", 30))
        #: Sudahkah badan permintaan dibaca/dikuras? Dipakai `_kuras_badan` agar tiap cabang
        #: jawaban — termasuk cabang galat yang keluar lebih awal — menutup soket dengan tertib.
        _badan_dibaca = False

        def log_message(self, fmt, *args):
            # /mcp/<token>: token ada literal di path — REDAKSI sebelum masuk log (K10, prinsip yang sama).
            baris = _POLA_TOKEN_PATH.sub(r"\1/[REDAKSI]", fmt % args)
            print(f"[ingat] {self.address_string()} {baris}")

        # ---- util ----
        def _ip(self) -> str:
            if proxy_tepercaya:
                xff = self.headers.get("X-Forwarded-For", "")
                if xff:
                    return xff.split(",")[-1].strip()  # entri TERAKHIR = yang ditulis proxy kita
            return self.client_address[0]

        def _kuras_badan(self):
            """Baca-buang badan permintaan yang belum sempat dibaca, sebelum menjawab.

            Menutup soket sementara masih ada byte menunggu di buffer terima membuat Windows
            mengirim RST alih-alih FIN; klien lalu kena WSAECONNABORTED (10053) saat membaca
            respons yang sebenarnya SUDAH lengkap terkirim. Terukur pada jalur 401: 6 dari 300
            POST berbadan, sementara jalur 200 yang badannya dibaca bersih 0 dari 300.

            Ini bukan kosmetik uji — klien nyata yang ditolak 401/429 kehilangan pesan galatnya
            dan hanya melihat koneksi putus.

            Badan raksasa (penolakan 413) tidak dikuras seluruhnya; koneksi ditutup terus terang
            supaya penolakan tidak berubah jadi jalur membaca sebanyak apa pun yang dikirim.
            """
            if self._badan_dibaca:
                return
            self._badan_dibaca = True
            sisa = min(int(self.headers.get("Content-Length") or 0), batas_body)
            while sisa > 0:
                potong = self.rfile.read(min(sisa, 65536))
                if not potong:
                    break
                sisa -= len(potong)
            if int(self.headers.get("Content-Length") or 0) > batas_body:
                self.close_connection = True

        def _kirim(self, kode: int, data):
            self._kuras_badan()
            badan = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(kode)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(badan)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(badan)

        def _auth(self) -> bool:
            h = self.headers.get("Authorization", "")
            if h.startswith("Bearer ") and hmac.compare_digest(h[7:].strip(), token):
                return True
            return self._email_sesi() is not None

        def _email_sesi(self) -> str | None:
            if not sesi_rahasia:
                return None
            nilai = ambil_cookie(self.headers.get("Cookie", ""), "ingat_sesi")
            if not nilai:
                return None
            return baca_sesi(nilai, sesi_rahasia)

        def _laju_totp_ok(self) -> bool:
            ip = self._ip()
            kini = time.time()
            with _LAJU_TOTP_KUNCI:
                daftar = [t for t in _LAJU_TOTP.get(ip, []) if kini - t < _TOTP_JENDELA_DETIK]
                if len(daftar) >= _TOTP_MAKS_PERCOBAAN:
                    _LAJU_TOTP[ip] = daftar
                    return False
                daftar.append(kini)
                _LAJU_TOTP[ip] = daftar
            return True

        def _laju_ok(self) -> bool:
            ip = self._ip()
            kini = time.time()
            with _LAJU_KUNCI:
                daftar = [t for t in _LAJU.get(ip, []) if kini - t < 60]
                if len(daftar) >= laju_per_menit:
                    _LAJU[ip] = daftar
                    return False
                daftar.append(kini)
                _LAJU[ip] = daftar
            return True

        def _badan(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            if n > batas_body:
                raise ValueError(f"body melebihi {batas_body} byte")
            if n == 0:
                self._badan_dibaca = True
                return {}
            self._badan_dibaca = True
            mentah = self.rfile.read(n)
            data = json.loads(mentah.decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError("body harus objek JSON")
            return data

        def _jaga(self) -> bool:
            if not self._laju_ok():
                self._kirim(429, {"galat": "terlalu banyak permintaan"})
                return False
            if not self._auth():
                self._kirim(401, {"galat": "token tidak valid"})
                return False
            return True

        # ---- routes ----
        def do_GET(self):
            if self._adalah_mcp():
                return self._layani_mcp("GET")
            path = urlparse(self.path).path

            if path == "/auth/google/mulai":
                if not google.get("client_id"):
                    return self._kirim(501, {"galat": "Google Auth belum dikonfigurasi (GOOGLE_CLIENT_ID kosong)"})
                if not auth_konfig.get("redirect_uri"):
                    return self._kirim(501, {"galat": "auth.redirect_uri belum diisi di konfigurasi.json"})
                state = secrets.token_urlsafe(24)
                self.send_response(302)
                self.send_header("Location", url_masuk(google["client_id"], auth_konfig["redirect_uri"], state))
                self.send_header("Set-Cookie", f"ingat_state={state}; Path=/auth/google/; Max-Age=600; "
                                                f"HttpOnly; Secure; SameSite=Lax")
                self.end_headers()
                return

            if path == "/auth/google/callback":
                qs = parse_qs(urlparse(self.path).query)
                kode = (qs.get("code") or [None])[0]
                state_diberi = (qs.get("state") or [None])[0]
                state_tersimpan = ambil_cookie(self.headers.get("Cookie", ""), "ingat_state")
                if not kode or not state_diberi or not state_tersimpan or not hmac.compare_digest(state_diberi, state_tersimpan):
                    return self._kirim(400, {"galat": "state tidak cocok (CSRF) atau kode hilang — coba masuk lagi"})
                try:
                    hasil = tukar_kode(google["client_id"], google["client_secret"], kode, auth_konfig["redirect_uri"])
                    email = verifikasi_id_token(hasil["id_token"], google["client_id"])
                except AuthGagal as e:
                    return self._kirim(401, {"galat": str(e)})
                except KeyError:
                    return self._kirim(502, {"galat": "respons Google tidak memuat id_token"})
                if not email_diizinkan(email, auth_konfig.get("allowed_emails", [])):
                    return self._kirim(403, {"galat": f"{email} tidak ada di auth.allowed_emails (konfigurasi.json)"})
                sesi = buat_sesi(email, google["sesi_rahasia"])
                self.send_response(302)
                self.send_header("Location", "/dashboard")
                self.send_header("Set-Cookie", f"ingat_sesi={sesi}; Path=/; Max-Age={7*24*3600}; "
                                                f"HttpOnly; Secure; SameSite=Lax")
                self.send_header("Set-Cookie", "ingat_state=; Path=/auth/google/; Max-Age=0")
                self.end_headers()
                return

            if path == "/auth/keluar":
                self.send_response(302)
                self.send_header("Location", "/dashboard")
                self.send_header("Set-Cookie", "ingat_sesi=; Path=/; Max-Age=0")
                self.end_headers()
                return

            if path == "/auth/sesi":
                email = self._email_sesi()
                return self._kirim(200, {"masuk": bool(email), "email": email})

            if path == "/dashboard" or path == "/dashboard/":
                # Halaman publik (tanpa token) — hanya markup/JS statis, tidak ada data. Data (di bawah,
                # /dashboard/data) tetap butuh Bearer, dimasukkan pengguna sendiri lewat kotak di halaman.
                import os as _os
                jalur = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "static", "dashboard.html")
                try:
                    with open(jalur, "rb") as f:
                        isi = f.read()
                except FileNotFoundError:
                    return self._kirim(404, {"galat": "static/dashboard.html tidak ditemukan"})
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(isi)))
                self.end_headers()
                self.wfile.write(isi)
                return
            if path == "/sehat":
                return self._kirim(200, {"ok": True, "layanan": "ingat", "versi": __version__, "penulis": __penulis__})
            if path == "/openapi.json":
                skema_host = f"{'https' if proxy_tepercaya else 'http'}://{self.headers.get('Host', 'localhost')}"
                return self._kirim(200, _openapi(skema_host))
            if not self._jaga():
                return
            try:
                if path == "/metrik":
                    return self._kirim(200, app.store.ringkasan_metrik())
                if path == "/penyedia":
                    return self._kirim(200, {"aktif": sorted(app.penyedia), "gate": app.gate.izin_tier, "preset": daftar_preset()})
                if path.startswith("/bukti/"):
                    return self._kirim(200, app.gateway.buka_bukti(path[len("/bukti/"):], sesi=self.headers.get("X-Sesi", "")))
                if path == "/usulan":
                    return self._kirim(200, app.vault.daftar_usulan() if app.vault else {})
                return self._kirim(404, {"galat": "tidak ada"})
            except KeyError as e:
                return self._kirim(404, {"galat": str(e)})
            except Exception as e:
                return self._kirim(500, {"galat": f"{type(e).__name__}: {e}"})

        # ---- MCP Streamable HTTP (/mcp atau /mcp/<token>) ------------------------
        def _adalah_mcp(self) -> bool:
            p = urlparse(self.path).path
            return p == "/mcp" or p.startswith("/mcp/")

        def _layani_mcp(self, metode: str):
            path = urlparse(self.path).path
            if not self._laju_ok():
                return self._kirim(429, {"galat": "terlalu banyak permintaan"})
            h = self.headers.get("Authorization", "")
            bearer = h[7:].strip() if h.startswith("Bearer ") else None
            di_path = ambil_token_dari_path(path)
            if not (token_cocok(bearer, token) or token_cocok(di_path, token)):
                # 401 TANPA WWW-Authenticate ke metadata OAuth: kita tidak menawarkan OAuth (lihat mcp_http.py)
                return self._kirim(401, {"galat": "token tidak valid: pakai Authorization: Bearer <token> atau /mcp/<token>"})
            badan = None
            if metode == "POST":
                n = int(self.headers.get("Content-Length", "0") or 0)
                if n > batas_body:
                    return self._kirim(413, {"galat": "badan terlalu besar"})
                self._badan_dibaca = True
                badan = self.rfile.read(n) if n else b""
            try:
                status, hdr, isi = _mcp_http(app, metode, badan, self.headers.get("Mcp-Session-Id"))
            except Exception as e:
                return self._kirim(500, {"galat": f"{type(e).__name__}: {e}"})
            self.send_response(status)
            for k, v in hdr.items():
                self.send_header(k, v)
            if isi is None:
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            data = json.dumps(isi, ensure_ascii=False).encode()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if metode != "HEAD":
                self.wfile.write(data)

        def do_HEAD(self):
            if self._adalah_mcp():
                return self._layani_mcp("HEAD")
            self.send_response(404); self.send_header("Content-Length", "0"); self.end_headers()

        def do_DELETE(self):
            if self._adalah_mcp():
                return self._layani_mcp("DELETE")
            self._kirim(404, {"galat": "tidak ada"})

        def do_POST(self):
            if self._adalah_mcp():
                return self._layani_mcp("POST")
            path = urlparse(self.path).path

            if path == "/auth/totp/masuk":
                if not totp_rahasia:
                    return self._kirim(501, {"galat": "TOTP belum dikonfigurasi (INGAT_TOTP_RAHASIA kosong). "
                                                       "Atur: python3 -m ingat totp-atur"})
                if not self._laju_totp_ok():
                    return self._kirim(429, {"galat": "terlalu banyak percobaan — coba lagi dalam beberapa menit"})
                try:
                    b = self._badan()
                except ValueError as e:
                    return self._kirim(400, {"galat": str(e)})
                if not totp_verifikasi_kode(totp_rahasia, str(b.get("kode", ""))):
                    return self._kirim(401, {"galat": "kode salah atau kedaluwarsa"})
                if not sesi_rahasia:
                    return self._kirim(501, {"galat": "INGAT_SESI_RAHASIA belum diatur"})
                sesi = buat_sesi("totp:pemilik", sesi_rahasia)
                badan = json.dumps({"masuk": True}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(badan)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Set-Cookie", f"ingat_sesi={sesi}; Path=/; Max-Age={7*24*3600}; "
                                                f"HttpOnly; Secure; SameSite=Lax")
                self.end_headers()
                self.wfile.write(badan)
                return

            if not self._jaga():
                return
            try:
                b = self._badan()
                sesi = b.pop("sesi", None) or self.headers.get("X-Sesi", "")
                # K30: di relay tidak ada tulis yang mendarat — jadi tier S tidak pernah bisa tiba.
                if app.relay and relay_jalur_tulis(path):
                    raise relay_tolak(f"POST {path}")
                if path == "/episode":
                    # `id` ikut diteruskan: hook Stop memakai id deterministik (`ep-sesi-<sesi>`) supaya
                    # satu sesi menghasilkan SATU episode yang di-upsert, bukan satu episode tiap Stop.
                    # Tanpa ini klien jauh (ingat/jauh.py) kehilangan sifat anti-banjir itu.
                    ep = app.store.tambah_episode(b.pop("isi", ""), sesi=sesi, **{k: b[k] for k in ("id", "sumber", "tier", "lingkup", "jenis_kejadian", "ringkas", "instrumen", "langkah") if k in b})
                    return self._kirim(201, {"id": ep.id, "bobot": ep.bobot, "isi_ref": ep.isi_ref})
                if path == "/metrik":
                    # Pasangan tulis dari GET /metrik. Dipakai klien jauh untuk `sesi_tanpa_episode` /
                    # `sesi_dengan_episode`; tanpa endpoint ini alarm Bab 11 mati diam-diam begitu
                    # hook dipindah ke mode jauh.
                    app.store.catat_metrik(str(b.get("nama", "")), float(b.get("nilai", 1)), **(b.get("konteks") or {}))
                    return self._kirim(200, {"ok": True})
                if path == "/ingat":
                    return self._kirim(200, app.gateway.ingat(sesi=sesi, **{k: b[k] for k in ("query", "lingkup", "jenis", "tanggal_peristiwa", "tugas", "lingkungan", "anggaran_token") if k in b}))
                if path == "/startup":
                    return self._kirim(200, app.gateway.muat_startup(sesi=sesi, **{k: b[k] for k in ("lingkup", "tugas", "lingkungan") if k in b}))
                if path == "/tanya":
                    return self._kirim(200, app.tanya(b["penyedia"], b["pesan"], b["lingkup"], b.get("tier", "P"), b.get("tugas"), b.get("lingkungan"), sesi))
                if path == "/konsolidasi":
                    hasil = app.konsolidator.jalankan(b.get("jalur", "batch"))
                    hasil["kedaluwarsa"] = app.konsolidator.kedaluwarsa()
                    return self._kirim(200, hasil)
                if path == "/sinkron":
                    return self._kirim(200, app.sinkron_vault())
                if path == "/dashboard/data":
                    return self._kirim(200, bangun_graf(app, b.get("lingkup")))
                if path == "/instrumen":
                    ins = skema.Instrumen(**{k: b[k] for k in ("id", "nama", "dipasang_sejak", "cakupan", "titik_buta_diketahui") if k in b})
                    return self._kirim(200, app.konsolidator.instrumen_baru(ins))
                if path.startswith("/prosedur/") and path.endswith("/eksekusi"):
                    pid = path[len("/prosedur/"):-len("/eksekusi")]
                    return self._kirim(200, app.konsolidator.catat_eksekusi_prosedur(pid, bool(b.get("berhasil"))))
                return self._kirim(404, {"galat": "tidak ada"})
            except (KeyError, ValueError, skema.TransisiTerlarang) as e:
                return self._kirim(400, {"galat": f"{type(e).__name__}: {e}"})
            except (GateDitolak, PermissionError) as e:
                return self._kirim(403, {"galat": str(e)})
            except PenyediaGagal as e:
                return self._kirim(502, {"galat": str(e)})
            except Exception as e:
                return self._kirim(500, {"galat": f"{type(e).__name__}: {e}"})

    return Handler


def jalankan_server(app: Aplikasi):
    token = os.environ.get("INGAT_TOKEN", "")
    if len(token) < 24:
        raise SystemExit("INGAT_TOKEN wajib diset di environment (>= 24 karakter). Tidak ada nilai bawaan — sengaja.")
    _google = {
        "client_id": os.environ.get("GOOGLE_CLIENT_ID", ""),
        "client_secret": os.environ.get("GOOGLE_CLIENT_SECRET", ""),
        "sesi_rahasia": os.environ.get("INGAT_SESI_RAHASIA", ""),
    }
    _totp_rahasia = os.environ.get("INGAT_TOTP_RAHASIA", "")
    if (_google["client_id"] or _totp_rahasia) and len(_google["sesi_rahasia"]) < 24:
        raise SystemExit("GOOGLE_CLIENT_ID atau INGAT_TOTP_RAHASIA diset tapi INGAT_SESI_RAHASIA belum "
                          "(>= 24 karakter). Buat: python3 -m ingat token")
    ks = app.konfig.get("server", {})
    host, port = ks.get("host", "127.0.0.1"), int(ks.get("port", 8765))
    server = ThreadingHTTPServer((host, port), buat_handler(app, token, ks, _google, _totp_rahasia, _google["sesi_rahasia"]))
    server.daemon_threads = True
    print(f"[ingat] v{__version__} · {__penulis__} · http://{host}:{port} · vault={app.konfig.get('vault')} · "
          f"penyedia={sorted(app.penyedia)} · google_auth={'aktif' if _google['client_id'] else 'mati'} · "
          f"totp={'aktif' if _totp_rahasia else 'mati'}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
