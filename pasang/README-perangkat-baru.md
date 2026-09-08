# Pasang di perangkat baru (laptop / HP / tablet)

Sejak mode jauh ada (`ingat/jauh.py`), **memori tidak tinggal di perangkat**. Server yang menyimpan;
perangkat hanya klien yang boleh diganti, hilang, atau dihapus kapan saja. Berkas ini resep untuk
menyambungkan perangkat baru — tidak ada langkah migrasi data, karena tidak ada data yang perlu ikut.

Ganti `https://memori.contoh-domain.id` dengan host server-mu.

---

## A. Laptop / desktop baru (Claude Code)

Perangkat yang menjalankan Claude Code perlu tiga hal: paket terpasang, token, dan blok `jauh`.

```bash
# 1. paket (dari salinan repo)
pip install -e .

# 2. token — ambil dari server, jangan diketik ulang dan jangan lewat chat
ssh root@<ip-server> 'cat /root/ingat-token-RAHASIA.txt' > ~/.ingat/token
chmod 600 ~/.ingat/token          # Linux/macOS
```

**Windows:** `chmod` tidak berlaku di NTFS lewat Git Bash — berkasnya akan tetap 644 dan
terbaca akun lain. Kunci dengan ACL yang sungguhan:

```
icacls "%USERPROFILE%\.ingat\token" /inheritance:r /grant:r "%USERNAME%:(R,W)"
```

```bash
# 3. hook Claude Code
python -m ingat pasang --tulis
```

Lalu tambahkan blok `jauh` ke `~/.ingat/konfigurasi.json`:

```json
"jauh": {
  "host": "https://memori.contoh-domain.id",
  "timeout_detik": 5
}
```

Verifikasi — **jangan** memanggil hook manual, cukup periksa mode yang terbaca:

```bash
python -c "from ingat.aplikasi import muat_konfig; from ingat.tangkap import path_konfig; from ingat.jauh import bangun_aplikasi_jauh; a=bangun_aplikasi_jauh(muat_konfig(path_konfig())); print('JAUH ->', a.store.klien.host if a else 'LOKAL')"
```

Harus mencetak `JAUH -> https://…`. Kalau `LOKAL`, blok `jauh` belum terbaca.

Bukti sungguhan bahwa hook menulis ke server: jalankan satu perintah yang gagal, lalu hitung episode
di server sebelum dan sesudah. Jumlah di server naik, jumlah di store lokal perangkat tidak.

### Kalau server sedang mati

Tidak ada yang perlu dilakukan. Episode masuk `~/.ingat/data/spool.jsonl` dan dikirim ulang sendiri
pada panggilan berikutnya yang berhasil. Sesi Claude Code tetap jalan normal — hook tidak pernah
memblokir. Yang hilang sementara hanyalah konteks memori di awal sesi.

---

## B. HP / tablet — melihat dashboard

Buka `https://memori.contoh-domain.id/dashboard` di browser, tempel **Host** dan **Token**.
Keduanya disimpan di `localStorage` browser itu saja.

Layar sempit (≤ 820px) memakai tata letak satu kolom dengan tab **Registri / Catatan / Papan**;
menekan baris atau simpul otomatis membuka tab Catatan.

**Risiko yang harus disadari:** token tersimpan di browser perangkat itu. HP hilang = token ikut.
Kalau itu terjadi, rotasi token di server (`INGAT_TOKEN` di `.env`, lalu `docker compose up -d`) —
semua perangkat lain perlu dipasangi token baru. Untuk perangkat yang sering dibawa keluar,
nyalakan verifikasi dua langkah mandiri (K26, tanpa Google):

```bash
docker compose run --rm ingat python3 -m ingat totp-atur --tulis-env
docker compose restart ingat
```

## C. HP / tablet — Claude ikut menulis memori

Ini yang membuat percakapan di HP masuk ke memori yang sama, bukan menguap.

1. Uji dulu dari terminal mana pun — kalau ini gagal, masalahnya di server, bukan di claude.ai:
   ```bash
   curl -i -X POST https://memori.contoh-domain.id/mcp/<TOKEN> \
     -H 'content-type: application/json' \
     -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"curl"}}}'
   ```
   Harus 200, ada header `Mcp-Session-Id`, dan `result.serverInfo.name == "ingat"`.
2. claude.ai → **Settings → Connectors → Add connector → Remote**
3. **Name** `ingat`; **URL** `https://memori.contoh-domain.id/mcp/<TOKEN>`
4. **Advanced settings → Transport: Streamable HTTP** (bukan SSE — server ini sengaja menjawab 405 untuk GET)

Detail dan penanganan galat: `pasang/README-connector.md`.

> **URL itu memuat token, jadi ia setara kata sandi.** Jangan ditempel di percakapan, jangan
> di-screenshot, jangan masuk git.

---

## Perangkat lama yang dilepas

Tidak ada data yang perlu diselamatkan dari perangkat lama — semuanya sudah di server. Yang perlu:

1. Hapus `~/.ingat/token` (dan `~/.ingat/konfigurasi.json` bila perangkatnya berpindah tangan).
2. Kalau spool masih berisi (`~/.ingat/data/spool.jsonl` ada), sambungkan sekali lagi ke jaringan
   dan jalankan satu perintah apa pun supaya spool terkuras sebelum perangkat dilepas.
3. Kalau perangkatnya hilang, bukan dilepas baik-baik: rotasi `INGAT_TOKEN` di server.
