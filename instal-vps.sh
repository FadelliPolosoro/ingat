#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# instal-vps.sh — pasang ingat dari nol di VPS Ubuntu 24.04 LTS bersih.
# Jalankan SEBAGAI ROOT (atau lewat sudo) di VPS itu sendiri — bukan dari mesin lain.
#   ssh root@187.52.125.35
#   bash instal-vps.sh
#
# Skrip ini AMAN dijalankan berulang (idempoten) — langkah yang sudah selesai dilewati.
set -euo pipefail

biru() { printf '\033[1;34m%s\033[0m\n' "$1"; }
warn() { printf '\033[1;33m%s\033[0m\n' "$1"; }

if [ "$(id -u)" -ne 0 ]; then
  echo "Jalankan sebagai root: sudo bash instal-vps.sh" >&2
  exit 1
fi

biru "== 1/6 Paket dasar =="
apt update -qq
apt install -y -qq docker.io docker-compose-plugin caddy unzip curl ca-certificates >/dev/null
systemctl enable --now docker >/dev/null 2>&1 || true
# `unzip` dipakai di langkah 3 — kalau paketnya gagal terpasang, gagal sekarang dengan pesan jelas,
# jangan di tengah pembongkaran arsip.
command -v unzip >/dev/null || { echo "unzip gagal terpasang — 'apt install unzip' manual dulu" >&2; exit 1; }

biru "== 2/6 Penyemat semantik: DILEWATI di pemasangan dasar =="
# Sebelumnya langkah ini memasang Ollama di HOST lalu menyetel konfigurasi ke
# http://host.docker.internal:11434. Itu tidak pernah bisa bekerja di Docker Linux:
#   - `host.docker.internal` tidak resolve dari container tanpa `extra_hosts`, DAN
#   - Ollama di host hanya mendengar 127.0.0.1, jadi sambungannya ditolak walau namanya resolve.
# Kombinasi itu berbahaya karena diam: penyemat gagal -> tambah_episode menggulung balik ->
# NOL episode tercatat, padahal pemasangannya kelihatan sukses.
# Ollama sekarang jadi service compose opsional (profile `semantik`, tanpa port ke host).
# Pemasangan dasar memakai penyemat `lokal` yang tidak butuh model sama sekali.
echo "penyemat 'lokal' dipakai (tanpa model). Untuk pencarian semantik, lihat model/README.md"

biru "== 3/6 Cari ingat.zip =="
ZIP=""
for kandidat in /root/ingat.zip /root/*/ingat.zip ./ingat.zip; do
  if [ -f "$kandidat" ]; then ZIP="$kandidat"; break; fi
done
if [ -z "$ZIP" ]; then
  echo "ingat.zip tidak ditemukan di /root. Transfer dulu dari laptopmu:" >&2
  echo "  (di PowerShell laptop)  scp ingat.zip root@187.52.125.35:/root/" >&2
  exit 1
fi
echo "ditemukan: $ZIP"
mkdir -p /opt/ingat
unzip -oq "$ZIP" -d /opt/ingat-tmp
# ingat.zip berisi folder ingat/ di dalamnya
if [ -d /opt/ingat-tmp/ingat ]; then
  cp -rn /opt/ingat-tmp/ingat/. /opt/ingat/ 2>/dev/null || true
  cp -rf /opt/ingat-tmp/ingat/. /opt/ingat/
else
  cp -rf /opt/ingat-tmp/. /opt/ingat/
fi
rm -rf /opt/ingat-tmp
cd /opt/ingat

biru "== 4/6 Konfigurasi (.env dan konfigurasi.json) =="
if [ ! -f .env ]; then
  cp .env.contoh .env
  TOKEN=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
  sed -i "s#^INGAT_TOKEN=.*#INGAT_TOKEN=${TOKEN}#" .env
  echo "INGAT_TOKEN dibuat otomatis: ${TOKEN}"
  echo "  (dicatat ke /root/ingat-token-RAHASIA.txt sekali ini saja — simpan lalu hapus berkas itu)"
  echo "$TOKEN" > /root/ingat-token-RAHASIA.txt
else
  echo ".env sudah ada, dilewati (hapus manual kalau mau dibuat ulang)"
fi

if [ ! -f konfigurasi.json ]; then
  cp konfigurasi.contoh.json konfigurasi.json
  python3 - << 'PYEOF'
import json
d = json.load(open("konfigurasi.json"))
# Penyemat `lokal` (bawaan contoh) TIDAK butuh model apa pun dan tidak pernah gagal karena
# jaringan. Pemasangan dasar sengaja berhenti di sini. Beralih ke penyemat semantik adalah
# langkah terpisah yang WAJIB diikuti reindex (512-dim -> 768-dim) — lihat model/README.md.
d.setdefault("embedding", {"jenis": "lokal"})
d["server"]["proxy_tepercaya"] = True   # di belakang Caddy (langkah manual 2 di bawah)
json.dump(d, open("konfigurasi.json", "w"), indent=2, ensure_ascii=False)
PYEOF
  echo "konfigurasi.json dibuat dari contoh — ISI MANUAL: auth.allowed_emails, auth.redirect_uri (lihat pasang/README-google-auth.md)"
else
  echo "konfigurasi.json sudah ada, dilewati"
fi
mkdir -p vault/pelajaran/_usulan vault/prosedur/_usulan vault/norma
# Container jalan sebagai uid 10001 (non-root, lihat Dockerfile). Folder yang baru dibuat root di
# sini akan ditolak saat Vault() membuat subfoldernya sendiri:
#   PermissionError: [Errno 13] Permission denied: '/vault/norma/_konsolidasi'
chown -R 10001:10001 vault

biru "== 5/6 Model embedding: TIDAK dibangun di sini =="
# bangun-gguf.sh meng-clone llama.cpp, memasang torch, mengunduh model ~1,1 GB, lalu
# mengonversinya. Di VPS kecil (1 vCPU, 4 GB, tanpa swap) langkah itu lambat dan bisa kena OOM —
# dan tidak ada alasan mengerjakannya di sini: hasilnya berkas .gguf yang bisa dibangun di mesin
# mana pun lalu dikirim. Lihat model/README.md.
echo "dilewati — bangun .gguf di mesin yang lega, lalu kirim (model/README.md)"

biru "== 6/6 Jalankan =="
docker compose up -d --build

echo
biru "== Selesai =="
echo "Status:   docker compose ps"
echo "Log:      docker compose logs -f ingat"
echo "Cek:      curl http://127.0.0.1:8765/sehat"
echo
warn "LANGKAH MANUAL YANG TERSISA (tidak bisa diotomasi dari sini):"
echo "  1. Arahkan domain/subdomain ke IP VPS ini (atau pakai sslip.io — lihat pasang/README-google-auth.md)"
echo "  2. Edit /etc/caddy/Caddyfile (contoh: /opt/ingat/Caddyfile.contoh), lalu: systemctl reload caddy"
echo "  3a. Google Auth (opsional): OAuth Client ID di Google Cloud Console — pasang/README-google-auth.md"
echo "  3b. Verifikasi dua langkah MANDIRI, tanpa Google (opsional, K26) — TIGA hal, jangan dipotong:"
echo "        docker compose run --rm -T ingat python3 -m ingat totp-atur < /dev/null"
echo "      Scan/tempel rahasianya ke aplikasi authenticator, lalu tulis SENDIRI ke .env di host ini."
echo "      JANGAN pakai --tulis-env: .env ada di host dan tidak dimount ke container, jadi bendera"
echo "      itu tidak akan menemukannya. Tambahkan DUA baris, bukan satu:"
echo "        INGAT_TOTP_RAHASIA=<rahasia dari perintah di atas>"
echo "        INGAT_SESI_RAHASIA=\$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
echo "      Tanpa INGAT_SESI_RAHASIA container GAGAL START BERULANG — TOTP butuh kunci cookie sesi."
echo "      Terakhir:  docker compose up -d    <-- BUKAN 'restart'; restart tidak membaca ulang .env"
echo "  4. Isi auth.allowed_emails + auth.redirect_uri di konfigurasi.json (kalau pakai Google Auth), lalu: docker compose restart ingat"
echo "  5. Kalau mau connector Claude Code / claude.ai / ekstensi browser: python3 -m ingat pasang (di LAPTOP, bukan VPS ini)"
