# SPDX-License-Identifier: Apache-2.0
"""Autentikasi Google OAuth2 untuk dashboard visual (K25). Stdlib saja — tanpa pustaka OAuth/JWT eksternal,
konsisten dengan etos nol-dependensi proyek ini.

Alur (Authorization Code):
  1. /auth/google/mulai   -> redirect ke Google, `state` acak disimpan di cookie sementara (anti-CSRF)
  2. Google -> /auth/google/callback?code=...&state=...
  3. tukar_kode()         -> POST ke Google, dapat id_token
  4. verifikasi_id_token() -> validasi lewat endpoint tokeninfo Google (audience + email_verified),
     TANPA mengimplementasikan verifikasi tanda tangan JWT/JWKS sendiri — trade-off sengaja untuk
     tetap stdlib-only; cukup untuk skala personal, bukan untuk beban tinggi (endpoint ini dibatasi
     laju oleh Google sendiri).
  5. Email dicocokkan ke allowlist (konfigurasi.json -> auth.allowed_emails). TANPA allowlist,
     SIAPA PUN dengan akun Google bisa masuk — allowlist adalah batas otorisasi sesungguhnya, bukan OAuth-nya.
  6. buat_sesi() -> cookie ber-HMAC (email + kadaluwarsa + tanda), stateless — tidak ada tabel sesi
     di server, jadi tidak ada yang perlu dibersihkan/dibocorkan dari sisi penyimpanan.

Google mewajibkan HTTPS untuk redirect_uri (kecuali localhost) — lihat pasang/README-google-auth.md.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"


class AuthGagal(Exception):
    pass


def url_masuk(client_id: str, redirect_uri: str, state: str) -> str:
    q = urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email",
        "state": state,
        "prompt": "select_account",
    })
    return f"{GOOGLE_AUTH_URL}?{q}"


def tukar_kode(client_id: str, client_secret: str, code: str, redirect_uri: str, timeout: int = 15,
               pembuka=None) -> dict:
    pembuka = pembuka or urllib.request.urlopen
    data = urllib.parse.urlencode({
        "code": code, "client_id": client_id, "client_secret": client_secret,
        "redirect_uri": redirect_uri, "grant_type": "authorization_code",
    }).encode()
    req = urllib.request.Request(GOOGLE_TOKEN_URL, data=data, method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with pembuka(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise AuthGagal(f"tukar kode gagal: HTTP {e.code} — {e.read().decode(errors='replace')[:300]}") from e
    except urllib.error.URLError as e:
        raise AuthGagal(f"tidak bisa menghubungi Google: {e.reason}") from e


def verifikasi_id_token(id_token: str, client_id: str, timeout: int = 15, pembuka=None) -> str:
    """Kembalikan email terverifikasi, atau lempar AuthGagal."""
    pembuka = pembuka or urllib.request.urlopen
    q = urllib.parse.urlencode({"id_token": id_token})
    req = urllib.request.Request(f"{GOOGLE_TOKENINFO_URL}?{q}")
    try:
        with pembuka(req, timeout=timeout) as r:
            info = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise AuthGagal(f"verifikasi token gagal: HTTP {e.code}") from e
    except urllib.error.URLError as e:
        raise AuthGagal(f"tidak bisa menghubungi Google: {e.reason}") from e
    if info.get("aud") != client_id:
        raise AuthGagal("audience token tidak cocok dengan GOOGLE_CLIENT_ID")
    if str(info.get("email_verified")).lower() != "true":
        raise AuthGagal("email belum diverifikasi Google")
    email = info.get("email")
    if not email:
        raise AuthGagal("token tidak memuat email")
    return email


def email_diizinkan(email: str, allowlist: list[str]) -> bool:
    return email.strip().lower() in {a.strip().lower() for a in allowlist}


# ---- sesi: cookie ber-HMAC, stateless (tidak ada tabel sesi di server) --------
def buat_sesi(email: str, rahasia: str, umur_detik: int = 7 * 24 * 3600) -> str:
    kadaluwarsa = int(time.time()) + umur_detik
    payload = f"{email}|{kadaluwarsa}"
    tanda = hmac.new(rahasia.encode(), payload.encode(), hashlib.sha256).hexdigest()
    mentah = f"{payload}|{tanda}".encode()
    return base64.urlsafe_b64encode(mentah).decode()


def baca_sesi(nilai_cookie: str, rahasia: str) -> str | None:
    """Kembalikan email bila cookie valid & belum kadaluwarsa; None bila tidak (diam-diam, bukan galat)."""
    try:
        mentah = base64.urlsafe_b64decode(nilai_cookie.encode()).decode()
        email, kadaluwarsa_s, tanda = mentah.rsplit("|", 2)
        kadaluwarsa = int(kadaluwarsa_s)
    except Exception:
        return None
    payload = f"{email}|{kadaluwarsa}"
    tanda_benar = hmac.new(rahasia.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(tanda, tanda_benar):
        return None
    if kadaluwarsa < int(time.time()):
        return None
    return email


def ambil_cookie(header_cookie: str, nama: str) -> str | None:
    """Parser cookie minimal (stdlib http.cookies bisa dipakai, tapi ini cukup dan tanpa efek samping)."""
    for bagian in (header_cookie or "").split(";"):
        if "=" not in bagian:
            continue
        k, _, v = bagian.strip().partition("=")
        if k == nama:
            return v
    return None
