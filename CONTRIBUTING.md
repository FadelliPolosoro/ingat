# Berkontribusi ke `ingat`

Terima kasih. Tiga aturan pendek, lalu alur kerja.

1. **Lisensi masuk = lisensi keluar.** Semua kontribusi di bawah Apache-2.0. Tidak ada CLA.
   Setiap commit wajib `Signed-off-by` (`git commit -s`) — lihat `DCO.md`.
2. **Kontrak dulu, kode kemudian.** Perubahan pada `skema/ingat.sql`, format frontmatter,
   atau skema tool MCP adalah perubahan kontrak: butuh entri di `docs/` dan versi bump,
   karena port lain bergantung padanya.
3. **Tidak ada dependensi runtime baru tanpa diskusi.** Yang diizinkan: lisensi MIT,
   Apache-2.0, BSD, ISC, 0BSD, CC0, PostgreSQL. Yang dilarang: SSPL, BSL, dan semua
   "source-available". Dependensi dev boleh, tetap dengan lisensi permisif.

## Alur kerja

- Buka issue dulu untuk perubahan non-trivial; untuk perbaikan kecil, langsung PR.
- Tulis uji sebelum kode (`uji/*.test.ts`); `npm test` harus hijau.
- Kode di `src/inti/` tidak boleh melakukan I/O.
- Bahasa identifier dan komentar: Bahasa Indonesia; istilah teknis boleh Inggris.
- Jangan klaim "selesai" di PR sebelum uji hijau dan (bila menyentuh berkas) keberadaan
  berkas diverifikasi.

## Keamanan

Laporkan kerentanan lewat kanal privat (alamat ditetapkan saat repo dibuka), bukan issue publik.
