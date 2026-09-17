# Ekstensi Chrome — tangkap percakapan AI

Menangkap percakapanmu di ChatGPT/Claude/Gemini/DeepSeek/Kimi/Perplexity jadi episode `ingat`, tanpa mengubah
apa pun di halaman itu sendiri. Data hanya dikirim ke **server ingat milikmu sendiri** (`/episode`,
endpoint yang sama dipakai hook Claude Code) — tidak pernah ke server pihak ketiga.

## Yang harus kamu tahu SEBELUM memasang

1. **Ini bukan produk resmi Chrome Web Store.** Kamu memasangnya manual ("unpacked") — lihat langkah di
   bawah. Karena itu, tidak ada proses review keamanan pihak ketiga; kodenya ada di folder ini, baca sendiri.
2. **Claude.ai tidak memakai selektor sama sekali** — lihat bagian "Jalur API" di bawah. ChatGPT, Gemini,
   dan Perplexity memakai selektor yang sudah diverifikasi (13–14 Sep 2026), tapi **selektor bisa berubah
   kapan saja tanpa pemberitahuan** — ekstensi akan memberi tahu kalau selektornya mati, tidak diam saja.
   DeepSeek dan Kimi masih kosong.
3. **Cara mengisi situs yang kosong**: buka Opsi ekstensi → klik "Pilih balon pengguna" pada situs itu →
   di tab situs itu, klik satu balon pesanmu → ulangi untuk "Pilih balon AI". Selektor tersimpan otomatis.
   Ini lebih tahan lama daripada selektor tebakan: kalau situsnya di-*redesign*, kamu cukup memilih ulang.
   Satu kolom boleh berisi beberapa kandidat dipisah `||`; yang dipakai kandidat pertama yang cocok.
4. **Area abu-abu ketentuan layanan.** Kebanyakan chat app konsumen (ChatGPT, Claude.ai, dst.) melarang
   "automated access" dalam ToS mereka dalam bentuk umum. Ekstensi ini hanya **membaca DOM** halaman yang
   sudah kamu buka dan login sendiri (tidak login otomatis, tidak melewati CAPTCHA, tidak mengklik apa pun
   atas namamu) — mirip ekstensi pencatat/ekspor lain yang beredar luas. Ini bukan nasihat hukum; ini
   keputusanmu, dengan akun dan datamu sendiri.
5. **Fragil, bukan "pasang lalu lupa".** DOM situs berubah. Kalau suatu hari status di popup bilang
   "terkonfigurasi" tapi tidak ada episode baru masuk, buka Opsi → Diagnostik → cek "Galat tangkap terakhir",
   dan pilih ulang elemen bila perlu.

## Memasang (mode developer)

1. `chrome://extensions` → aktifkan **Developer mode** (kanan atas).
2. **Load unpacked** → pilih folder `pasang/browser-extension/` ini.
3. Klik ikon ekstensi → **Buka opsi**.
4. Isi **Host API** (biasanya `https://memori.contoh-domain.id` lewat Caddy, atau `http://127.0.0.1:8765`
   kalau server jalan di mesin yang sama) dan **Token** (nilai `INGAT_TOKEN` di `.env` server) → Simpan.
5. Untuk ChatGPT: coba dulu tanpa mengisi selektor manual (sudah ada bawaan). Untuk Claude/Gemini/DeepSeek/Kimi/Perplexity:
   ikuti langkah 3 di atas.

## Menemukan selektor tanpa menebak (`deteksi-selektor.js`)

Untuk situs yang selektornya kosong (DeepSeek/Kimi) atau yang selektornya patah, selain picker
ada alat bantu: buka situsnya (login, satu percakapan berisi pesanmu + jawaban AI), tekan F12 →
Console → tempel seluruh isi `deteksi-selektor.js`. Ia **mengukur** kandidat selektor terhadap DOM
nyata di halamanmu (bukan menebak), mencetak tabel cocok/berteks/contoh, merekomendasikan yang sehat,
lalu mencetak perintah `chrome.storage.sync.set(...)` siap-tempel (dijalankan di Console **halaman Opsi
ekstensi**, bukan di situs). Hanya membaca DOM. Kandidat awal: Gemini `user-query`/`model-response`/
`rich-textarea .ql-editor`; Perplexity `compose = [contenteditable="true"][role="textbox"]` (diverifikasi
di halaman guest 13 Sep 2026) — balon user/assistant-nya diverifikasi lewat skrip ini di sesi loginmu.

## Jalur API untuk Claude.ai (18 September 2026)

Untuk Claude.ai ekstensi **tidak membaca tampilan layar**. Ia memanggil API internal Claude memakai
sesi login yang sudah ada di browsermu:

```
GET /api/organizations/{orgId}/chat_conversations/{id}?tree=true&rendering_mode=messages&render_all_tools=true
```

`orgId` diambil dari cookie `lastActiveOrg` (kalau cookienya hilang, dari `/api/organizations`), `id` dari
URL halaman. Dua alasan ini lebih baik daripada selektor CSS:

1. **Kontrak datanya stabil** — selektor patah setiap Anthropic mengubah tata letak; bentuk JSON tidak.
2. **Lengkap** — DOM hanya merender sebagian percakapan panjang (virtualisasi), jadi episode hasil
   pembacaan layar bisa bolong tanpa kelihatan. API memberi percakapan utuh.

Kodenya di `pengambil-api.js`. Ia hanya **membaca** dan tidak pernah menulis ke halaman; yang mengirim
ke server `ingat` tetap `background.js` lewat `/episode` yang sama seperti situs lain.

**Kalau jalur API gagal** (belum login, endpoint berubah, format berubah, jaringan mati), ekstensi
**jatuh ke pembacaan DOM** dan **memberi tahu di tiga tempat sekaligus**: lencana merah `!` di ikon
ekstensi, satu baris merah di popup, dan satu bisikan kecil di pojok kanan bawah halaman (sekali per
jenis masalah per percakapan). Catatannya tersimpan di Opsi → Diagnostik. Gagal diam-diam adalah
kegagalan terburuk di sini: kamu akan mengira memorimu tersimpan padahal tidak.

**Perplexity**: tidak ada API internal yang bisa dipastikan seperti Claude. `pengambil-api.js` hanya
*mencoba* `/rest/thread/<slug>` **sekali per percakapan**; kalau tidak ada atau bentuknya tak dikenali,
ia diam-diam memakai jalur DOM — tanpa peringatan, karena untuk Perplexity jalur DOM memang jalur yang
sah. Yang tetap diperingatkan untuk semua situs: selektor sudah diisi tapi **tidak mengenali satu balon
pun** di halaman yang jelas berisi percakapan (dicek 15 detik setelah percakapan dibuka).

Karena jalur API mengembalikan seluruh percakapan setiap kali dipanggil, ekstensi menyimpan penanda
"sudah sampai pesan ke-berapa" di `chrome.storage.local` (bukan `sessionStorage`, yang mati bersama
tabnya) dan hanya mengirim selisihnya. Episode jalur API juga diberi `id` deterministik supaya
pengiriman ulang meng-*upsert*, bukan menumpuk salinan.

Uji tanpa browser: `node pasang/browser-extension/uji-pengambil-api.mjs` (35 periksaan).

## Cara kerja singkat

- Satu episode per **percakapan**, dikirim saat idle 90 detik atau tab ditutup/disembunyikan — bukan satu
  episode per pesan (pola sama dengan hook Claude Code: anti-banjir).
- Pesan yang diawali `/koreksi` atau `koreksi:` jadi episode `koreksi` bobot 5 — konvensi yang sama dengan
  Claude Code, supaya kebiasaanmu tetap satu, di platform mana pun.
- Kredensial dalam teks yang tertangkap diredaksi otomatis oleh server (K10) — ekstensi tidak melakukan
  redaksi sendiri, jadi jangan andalkan ekstensi untuk itu; server-lah yang menjamin.
- Kegagalan kirim (server mati/offline) masuk antrean lokal (`chrome.storage.local`), dicoba lagi tiap
  2 menit, dibuang setelah ~20 percobaan gagal.

## Suntik memori (fitur baru — 8 September 2026)

Tombol **🧠 Suntik memori** di popup ekstensi: sekali klik, ekstensi membaca draf yang sedang kamu
ketik (kalau ada), menariknya sebagai query ke server `ingat` lewat `/ingat` (atau `/startup` untuk
konteks awal bila kotak ketik masih kosong), lalu **menyisipkan** hasilnya ke kotak ketik — sebelum
teks yang sudah kamu tulis, bukan menimpanya.

**Jaminan keamanan yang ditegakkan di kode ini: TIDAK PERNAH menekan tombol kirim/submit.** Ekstensi
hanya menaruh teks di kotak ketik, persis seperti kamu menempel dari clipboard. Kamu yang memutuskan
kapan (atau apakah) mengirimnya — bisa diedit atau dihapus dulu.

Butuh selektor ketiga: **"kotak ketik"** (compose), diisi sama seperti user/AI lewat "Pilih elemen" di
halaman Opsi (klik area tempat kamu biasa mengetik). ChatGPT diberi tebakan awal (`#prompt-textarea`,
pola lama yang dipakai banyak alat sejenis) — verifikasi sendiri, situs lain kosong seperti biasa.

**Kenapa risikonya lebih rendah dari fitur tangkap (K18):** fitur ini tidak membaca/mengirim isi
percakapanmu ke mana pun tanpa kamu klik; dan karena tidak pernah submit, ia tidak "menjalankan aksi
otomatis" di situs itu — paling dekat dengan menempel teks manual. Tetap: teknik penyisipannya
(`execCommand`, event sintetis) bisa berhenti bekerja kalau editor situs berubah; kalau tombol
menunjukkan sukses tapi kotak ketik tidak berubah, berarti selektor compose perlu dipilih ulang.

## Suntik OTOMATIS saat percakapan baru — 8 September 2026

Ini yang membuat jawaban "apakah otomatis di mana pun saya mulai?" jadi **ya** untuk platform tanpa MCP juga.
Begitu kamu buka percakapan baru dan kotak ketiknya masih kosong (0 pesan pengguna, 0 pesan AI di halaman),
ekstensi menyuntik konteks awal (`/startup`) **sekali**, tanpa kamu klik apa pun — sejajar dengan hook
`SessionStart` di Claude Code.

Pengaman yang ditegakkan (dan diuji):
- **Hanya kotak yang benar-benar kosong.** Kalau kamu sudah mulai mengetik draf, tidak disentuh.
- **Hanya percakapan yang benar-benar baru.** Membuka-baca percakapan lama (yang sudah ada pesan) tidak
  memicu ini — supaya tidak mengacaukan halaman yang sedang kamu tinjau, bukan mulai.
- **Sekali per percakapan per tab** (ditandai lewat `sessionStorage`, bukan disimpan permanen).
- **Bisa dimatikan** — centang "Suntik otomatis" di Opsi kalau kamu tidak suka kotak terisi tanpa diminta.
- **Lewat jalur kode yang sama** dengan tombol manual (`suntikKe`) — jaminan tidak-pernah-submit ikut
  berlaku otomatis, bukan jalur kedua yang bisa diam-diam berbeda.

## Pengingat relevansi (badge) — 8 September 2026

Sambil kamu mengetik (jeda 1.5 detik, tidak lebih sering dari tiap 4 detik), ekstensi diam-diam
bertanya ke server: "ada memori relevan untuk ini?" Kalau skor relevansinya tinggi (≥0.30, sama dengan
ambang peringatan di server), muncul titik hijau di ikon ekstensi + satu baris di popup. **Ini hanya
pemberitahuan — tidak pernah menyisipkan apa pun sendiri.** Kamu tetap yang klik Suntik memori.

Ini bukan "AI belajar baru" — ia menumpang skor relevansi yang sama dipakai `/ingat`. Yang membuatnya
terasa makin pintar dari waktu ke waktu adalah pelajaran itu sendiri makin matang lewat siklus
tanya/jawab (lihat `ingat/tanya.py`) — bukan kode ekstensi ini yang berubah.

## Suntik lagi — menyicil anggaran token

Kalau hasil Suntik memori pertama masih menyisakan item relevan yang terpotong anggaran (server
membatasi token per tarikan, Bab 8 spek), tombol **➕ Suntik lagi** muncul menunjukkan berapa sisa.
Klik untuk menaikkan anggaran dan menarik lebih banyak — item yang sudah disisipkan tidak diulang
(dilacak per tab). Ini literally "cicilan": bukan sekali tarik semua, tapi bertahap sesuai kebutuhan.

**Batasnya:** pelacakan cicilan hidup di memori background script tab-per-tab — kalau Chrome mematikan
service worker ekstensi (wajar di Manifest V3 saat idle), riwayat cicilan tab itu reset dan "Suntik
lagi" mulai dari cicilan pertama lagi. Bukan bug tersembunyi — cukup diklik ulang, tidak ada yang rusak.

## Yang TIDAK dilakukan ekstensi ini

- **Tidak pernah menekan kirim/submit** — Suntik memori hanya menulis ke kotak ketik.
- Tidak menarik riwayat percakapan LAMA (sebelum ekstensi dipasang) — hanya menangkap yang terjadi
  SETELAH dipasang dan situsnya kamu buka. Untuk riwayat lama, itu Jalur A (impor dari ekspor resmi
  platform) — belum dibangun di sesi ini.
- Tidak login, tidak mengklik tombol kirim, tidak melewati proteksi apa pun. Murni membaca: DOM untuk
  sebagian besar situs, dan untuk Claude.ai API internal situs itu sendiri memakai sesi login yang sudah
  ada di browsermu — permintaan yang sama persis dengan yang dikirim halamannya sendiri saat kamu
  membuka percakapan itu.
- Tidak mengirim data ke mana pun selain host yang kamu isi sendiri di Opsi.
