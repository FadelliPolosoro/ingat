# Ekstensi Chrome — tangkap percakapan AI

Menangkap percakapanmu di ChatGPT/Claude/Gemini/DeepSeek/Kimi/Perplexity jadi episode `ingat`, tanpa mengubah
apa pun di halaman itu sendiri. Data hanya dikirim ke **server ingat milikmu sendiri** (`/episode`,
endpoint yang sama dipakai hook Claude Code) — tidak pernah ke server pihak ketiga.

## Yang harus kamu tahu SEBELUM memasang

1. **Ini bukan produk resmi Chrome Web Store.** Kamu memasangnya manual ("unpacked") — lihat langkah di
   bawah. Karena itu, tidak ada proses review keamanan pihak ketiga; kodenya ada di folder ini, baca sendiri.
2. **Selektor untuk Claude.ai, Gemini, DeepSeek, Kimi, Perplexity SENGAJA DIKOSONGKAN.** Struktur halaman
   situs-situs itu berubah dari waktu ke waktu dan belum diverifikasi langsung di masing-masing situs —
   jadi dibiarkan kosong daripada menebak. ChatGPT diisi satu pola yang secara umum relatif stabil
   (`data-message-author-role`), tapi **itu pun bisa berubah kapan saja tanpa pemberitahuan** —
   verifikasi sendiri, jangan percaya begitu saja.
3. **Cara mengisi 4 situs yang kosong**: buka Opsi ekstensi → klik "Pilih balon pengguna" pada situs itu →
   di tab situs itu, klik satu balon pesanmu → ulangi untuk "Pilih balon AI". Selektor tersimpan otomatis.
   Ini lebih tahan lama daripada selektor tebakan: kalau situsnya di-*redesign*, kamu cukup memilih ulang.
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
- Tidak login, tidak mengklik tombol kirim, tidak melewati proteksi apa pun. Murni membaca DOM.
- Tidak mengirim data ke mana pun selain host yang kamu isi sendiri di Opsi.
