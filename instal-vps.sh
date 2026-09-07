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

biru "== 2/6 Ollama (embedding lokal) =="
if ! command -v ollama >/dev/null; then
  curl -fsSL https://ollama.com/install.sh | sh
else
  echo "sudah terpasang, dilewati"
fi
systemctl enable --now ollama >/dev/null 2>&1 || true

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
d["embedding"] = {"jenis": "ollama", "host": "http://host.docker.internal:11434",
                   "model": "ingat-e5-base", "dim": 768, "prefiks": True}
json.dump(d, open("konfigurasi.json", "w"), indent=2, ensure_ascii=False)
PYEOF
  echo "konfigurasi.json dibuat dari contoh — ISI MANUAL: auth.allowed_emails, auth.redirect_uri (lihat pasang/README-google-auth.md)"
else
  echo "konfigurasi.json sudah ada, dilewati"
fi
mkdir -p vault/pelajaran/_usulan vault/prosedur/_usulan vault/norma

biru "== 5/6 Model embedding =="
if ! ollama list 2>/dev/null | grep -q ingat-e5-base; then
  bash model/bangun-gguf.sh
  ollama create ingat-e5-base -f model/Modelfile
else
  echo "model ingat-e5-base sudah ada, dilewati"
fi

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
echo "  3b. Verifikasi dua langkah MANDIRI, tanpa Google (opsional, K26):"
echo "        docker compose run --rm ingat python3 -m ingat totp-atur --tulis-env"
echo "      lalu scan/tempel rahasia yang tampil ke aplikasi authenticator, docker compose restart ingat"
echo "  4. Isi auth.allowed_emails + auth.redirect_uri di konfigurasi.json (kalau pakai Google Auth), lalu: docker compose restart ingat"
echo "  5. Kalau mau connector Claude Code / claude.ai / ekstensi browser: python3 -m ingat pasang (di LAPTOP, bukan VPS ini)"
