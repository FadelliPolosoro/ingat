---
paths: ["src/tangkap/**", "src/simpan/**", "src/sematkan/**"]
---
# Aturan keamanan

- Redaksi kredensial berjalan **sebelum** episode ditulis; tidak ada jalur tulis yang melewatinya.
  Pola ada di `src/tangkap/redaksi.ts`; tambahkan pola baru dengan uji di `uji/redaksi.test.ts`.
- Nilai yang diredaksi diganti penanda `[REDAKSI:<jenis>]`; jumlah dan jenisnya dicatat di
  kolom `diredaksi`, bukan nilainya.
- Data pribadi (NIK, NPWP) **tidak** diredaksi (K10), tetapi episode ditandai `tier: S` oleh
  `src/tangkap/tier.ts`. Tier S: tidak keluar mesin, tidak muncul di `ingat()` tanpa `sertakan_S: true`.
- **Tier S ke LLM (K28, spek 9.1).** Default tetap TIDAK. Satu-satunya pengecualian: model **lokal**,
  di jalur `konsolidasi` saja, dan hanya bila keempat rem `rem_tier_s` terpasang sekaligus
  (`ingat/rem.py`). Desainnya **gagal-tertutup** — satu rem hilang, tier S tertutup lagi.
  Yang tidak boleh dilonggarkan tanpa keputusan baru: lokalitas diverifikasi dari `base_url`
  (bukan dari nama penyedia); P11 diperiksa pada **keluaran** model; jalur `/tanya` tetap menolak
  tier S; dan heuristik tier S tidak pernah menyalin `ringkas` episode ke pelajaran (vault = repo git).
  Menambah/melonggarkan rem = tambah uji di `uji/uji_rem_tier_s.py`.
- **Mode relay (K30, `ingat/relay.py`).** Instans dengan `relay.aktif` adalah pintu masuk BACA-SAJA
  tier P/I; store otoritatif ada di laptop dan tier S tidak pernah keluar dari sana. Jaminannya
  bersandar pada **tidak adanya jalur tulis sama sekali**, bukan pada penyaringan tier di relay —
  jangan menambah endpoint atau tool tulis yang lolos saat `relay.aktif`. Menambah endpoint POST
  yang mengubah keadaan = daftarkan di `relay.JALUR_TULIS` + uji di `uji/uji_relay.py`.
- **Pelajaran/prosedur `tier_maks:S` ditahan di laptop (K30, `ingat/obsidian.py`).** Dua lapis:
  penampungan fisik di `*/_tier-s/` (di-gitignore vault, tak di-push) + backstop
  `Vault.sinkron(lewati_tier_s=True)` yang dipakai relay lewat `Aplikasi.sinkron_vault()`. Jangan
  sinkron di relay tanpa lewat `sinkron_vault()`, dan jangan menulis item tier_maks:S ke folder
  selain `_tier-s/`. Uji: `uji/uji_filter_tier_s.py`.
- Berkas SQLite dibuat dengan izin 0600. Jangan pernah menulis kunci enkripsi ke repo atau
  menurunkannya dengan satu SHA-256 tanpa KDF.
- Adapter embedding hanya boleh menghubungi host yang dikonfigurasi eksplisit; default
  `http://127.0.0.1:11434`. Tidak ada fallback diam-diam ke API eksternal.
- Identitas model embedding (nama + dimensi) dicatat per koleksi; ketidakcocokan = error,
  bukan peringatan.
