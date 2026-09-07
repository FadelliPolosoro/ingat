# Custom Connector claude.ai (MCP Streamable HTTP)

Memasang `ingat` sebagai connector di claude.ai — sejajar dengan GitHits/Zernio di menu Connectors
(itulah yang kamu tunjukkan di tangkapan layar). Server: `ingat/mcp_http.py`, dipasang di `/mcp` pada
server REST yang sama (`ingat serve`). Empat tool yang sama seperti Claude Code: `ingat`, `muat_startup`,
`buka_bukti`, `catat_episode`.

## Yang BELUM ada — baca ini dulu

Tidak ada OAuth 2.1 / Dynamic Client Registration. Autentikasi cuma satu token statis (`INGAT_TOKEN`),
dikirim lewat **URL rahasia** (`https://.../mcp/<token>`) atau header `Authorization: Bearer`.

Kenapa bukan OAuth: OAuth butuh authorization server terpisah (client registration, PKCE, penyimpanan
kode/refresh token) — beban yang tidak sepadan untuk satu pengguna satu server. Konsekuensinya: **URL
dengan token di dalamnya adalah kata sandi**. Jangan tempel di chat, jangan commit ke git, jangan
screenshot. Kalau bocor: ganti `INGAT_TOKEN` di `.env`, restart server, pasang ulang connector-nya.

Beberapa laporan publik (dicek Sep 2026) menunjukkan risiko ini spesifik ke akun **Team/Enterprise
yang di-manage organisasi** — connector ditambahkan lewat *Organization settings*, dan sebagian konfigurasi
di sana mengasumsikan OAuth. **Untuk akun pribadi (Free/Pro/Max)** — connector ditambahkan langsung lewat
*Settings → Connectors* milikmu sendiri, tanpa admin, tanpa lapisan itu — risiko ini tidak relevan.
Tangkapan layar yang kamu tunjukkan sebelumnya (menu Connectors dengan GitHits/Zernio dkk.) memang UI akun
pribadi, jadi jalur token-di-URL/Bearer di bawah ini seharusnya berlaku langsung tanpa hambatan OAuth.

## Langkah

1. Pastikan server jalan dan bisa dicapai lewat HTTPS (Caddy — lihat `Caddyfile.contoh`, sudah
   ditambah blok yang mematikan access log khusus untuk `/mcp` supaya token tidak tersimpan di disk Caddy).
2. **Verifikasi dulu dengan curl** sebelum ke claude.ai — supaya kalau connector gagal, kamu tahu itu
   bukan salah server:
   ```
   curl -i -X POST https://memori.contoh-domain.id/mcp/<INGAT_TOKEN> \\
     -H 'content-type: application/json' \\
     -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"curl"}}}'
   ```
   Harus 200, `result.serverInfo.name == "ingat"`, dan header `Mcp-Session-Id` ada.
3. claude.ai → **Settings → Connectors → Add connector → Remote**.
4. **Name**: `ingat` (huruf kecil/angka/strip saja). **URL**: `https://memori.contoh-domain.id/mcp/<INGAT_TOKEN>`.
5. **Advanced settings** → Transport: **Streamable HTTP** (bukan SSE — server ini tidak menawarkan SSE,
   lihat `mcp_http.py`: GET mengembalikan 405 dengan sengaja).
6. Simpan. Kalau connector tampil "Connected" dengan 4 tool terdaftar, buka percakapan baru, aktifkan
   dari menu `+` → Connectors, coba: *"pakai tool ingat, cari 'tool kosong bukan berarti tidak ada'
   di lingkup global"*.

## Kalau gagal

- **"Connection issue" instan, tanpa log apa pun muncul di server** → curl langkah 2 dulu; kalau curl
  sukses tapi claude.ai tetap gagal, ini kemungkinan besar soal OAuth yang disebut di atas, bukan server.
- **Token di URL terasa berisiko** → pakai jalur Bearer lewat Advanced settings → Headers (kalau akunmu
  menyediakan opsi ini; disebut di dokumentasi resmi sebagai fitur beta yang tidak semua akun punya).
- **Perlu diagnosis lebih lanjut** → `python3 -m ingat --konfig ... metrik` untuk lihat apakah permintaan
  memang sampai ke server sama sekali.
