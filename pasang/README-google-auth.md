# Google Auth untuk dashboard `ingat`

Ini bukan langkah yang bisa dikerjakan orang lain atas namamu — Google mengharuskan pembuatan
"OAuth Client ID" dilakukan lewat akun Google-mu sendiri, di browser yang sedang login sebagai kamu.

## Prasyarat: domain dengan HTTPS

Google **menolak** redirect URI `http://` kecuali `localhost`. `ingat` harus bisa diakses lewat
`https://<domain-kamu>/` sebelum langkah di bawah bisa selesai. Dua jalur:

- **Domain milikmu sendiri** (garnivo.id / lenteradigital.org / caktimedia.co.id, dll.) — tambah
  subdomain, mis. `memori.caktimedia.co.id`, A record → `187.52.125.35`. Butuh menunggu propagasi DNS
  (biasanya menit–jam).
- **sslip.io — instan, tanpa domain, tanpa konfigurasi apa pun**: `187-52-125-35.sslip.io` (ganti titik
  IP jadi strip) otomatis mengarah ke IP itu lewat DNS publik. Caddy bisa langsung minta sertifikat
  Let's Encrypt untuknya. Cocok untuk mulai hari ini; pindah ke domain sendiri kapan saja tanpa ubah kode.

Pilih salah satu, catat sebagai `<DOMAIN>` untuk langkah selanjutnya.

## Langkah di Google Cloud Console

1. Buka **console.cloud.google.com** → buat project baru (atau pakai yang sudah ada) → beri nama
   bebas, mis. "ingat-memori".
2. Menu kiri → **APIs & Services → OAuth consent screen**.
   - User Type: **External** (kecuali kamu punya Google Workspace dan mau batasi ke domain kantor — pilih Internal).
   - Isi nama app ("ingat"), email dukungan (emailmu sendiri), simpan.
   - Scopes: lewati saja (default sudah cukup — kita cuma pakai `openid`+`email`).
   - Test users (kalau consent screen belum "Published"): tambahkan email Google-mu sendiri di sini,
     kalau tidak Google akan menolak login dengan pesan "app belum diverifikasi".
3. Menu kiri → **APIs & Services → Credentials → + Create Credentials → OAuth client ID**.
   - Application type: **Web application**.
   - Name: bebas, mis. "ingat-dashboard".
   - **Authorized redirect URIs** → Add URI → isi PERSIS:
     ```
     https://<DOMAIN>/auth/google/callback
     ```
     Tanpa garis miring di akhir, harus `https`, harus sama persis dengan yang nanti diisi di
     `konfigurasi.json` → `auth.redirect_uri`. Beda satu karakter pun ditolak Google.
   - Create. Muncul **Client ID** dan **Client Secret** — salin keduanya.

## Isi ke `ingat`

Di `.env` (VPS):
```
GOOGLE_CLIENT_ID=<tempel Client ID>
GOOGLE_CLIENT_SECRET=<tempel Client Secret>
INGAT_SESI_RAHASIA=<buat baru: python3 -m ingat token>
```

Di `konfigurasi.json`:
```json
"auth": {
  "allowed_emails": ["emailmu@gmail.com"],
  "redirect_uri": "https://<DOMAIN>/auth/google/callback"
}
```

`allowed_emails` **wajib diisi** — tanpa ini, siapa pun dengan akun Google akan ditolak (allowlist
kosong = tidak ada yang diizinkan, bukan semua diizinkan; lihat `ingat/auth_google.py`).

## Uji

```
curl -i https://<DOMAIN>/auth/google/mulai
```
Harus `302` mengarah ke `accounts.google.com`. Kalau `501`, `GOOGLE_CLIENT_ID` belum terbaca (cek `.env`
sudah dimuat container — `docker compose restart ingat` setelah mengubah `.env`).

Lalu buka `https://<DOMAIN>/dashboard` di browser sungguhan, klik **Masuk dengan Google**.

## Konsekuensi keamanan yang perlu kamu tahu

- Sesi berupa cookie ber-HMAC (`INGAT_SESI_RAHASIA` menandatanganinya) — **bukan** JWT tervalidasi
  penuh dari Google, hanya email yang sudah diverifikasi Google saat login lalu ditandatangani
  server sendiri. Kalau `INGAT_SESI_RAHASIA` bocor, siapa pun bisa memalsukan sesi — perlakukan
  sama seperti `INGAT_TOKEN`.
- Verifikasi id_token lewat endpoint `tokeninfo` Google (bukan verifikasi JWKS/tanda tangan mandiri)
  — pilihan sadar demi tetap tanpa dependensi eksternal. Cukup untuk skala personal; endpoint itu
  sendiri dibatasi laju oleh Google.
- Cookie sesi berumur 7 hari, `HttpOnly; Secure; SameSite=Lax` — tidak bisa dibaca JavaScript pihak
  ketiga, tidak terkirim ke situs lain.
