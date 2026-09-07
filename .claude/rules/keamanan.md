---
paths: ["src/tangkap/**", "src/simpan/**", "src/sematkan/**"]
---
# Aturan keamanan

- Redaksi kredensial berjalan **sebelum** episode ditulis; tidak ada jalur tulis yang melewatinya.
  Pola ada di `src/tangkap/redaksi.ts`; tambahkan pola baru dengan uji di `uji/redaksi.test.ts`.
- Nilai yang diredaksi diganti penanda `[REDAKSI:<jenis>]`; jumlah dan jenisnya dicatat di
  kolom `diredaksi`, bukan nilainya.
- Data pribadi (NIK, NPWP) **tidak** diredaksi (K10), tetapi episode ditandai `tier: S` oleh
  `src/tangkap/tier.ts`. Tier S: tidak ke LLM, tidak keluar mesin, tidak muncul di `ingat()`
  tanpa `sertakan_S: true`.
- Berkas SQLite dibuat dengan izin 0600. Jangan pernah menulis kunci enkripsi ke repo atau
  menurunkannya dengan satu SHA-256 tanpa KDF.
- Adapter embedding hanya boleh menghubungi host yang dikonfigurasi eksplisit; default
  `http://127.0.0.1:11434`. Tidak ada fallback diam-diam ke API eksternal.
- Identitas model embedding (nama + dimensi) dicatat per koleksi; ketidakcocokan = error,
  bukan peringatan.
