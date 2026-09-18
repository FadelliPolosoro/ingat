# Spek Aplikasi Desktop — Panel Kendali `ingat` — K29

| | |
|---|---|
| **Status** | RANGKUMAN KEPUTUSAN (bukan spek penuh). Ditulis 2026-09-13 dari keputusan sesi lain. Desain rinci **belum ditulis**. |
| **Keputusan** | K29 (`KEPUTUSAN.md`) |
| **Pemilik keputusan** | Tuan Muda |

> Dokumen ini merekam apa yang **diputuskan**, bukan cara membangunnya. Titik yang belum
> dispesifikasikan ditandai `[BELUM DISPESIFIKASIKAN]`.

## 1. Sikap dasar

Aplikasi desktop = **PANEL KENDALI**, **bukan tiruan aplikasi catatan**. Yang butuh pengalaman aplikasi catatan
(graph, editing catatan) didelegasikan ke aplikasi catatan asli lewat tombol "buka catatan".

## 2. Prioritas fungsi (berurutan)

1. **Konsolidasi + jawab** — jalankan/lihat loop konsolidasi dan dapatkan jawaban.
2. **Status** — keadaan sistem sekilas.
3. **Buka catatan** — lompat ke vault, bukan meniru tampilannya.
4. **Tempel cepat** — masukkan potongan ke sistem dengan cepat.

`[BELUM DISPESIFIKASIKAN untuk tiap fungsi: layar, aksi persis, endpoint yang dipakai]`

## 3. Wajib — pengukuran pemakaian

- **Penanda pengukuran pemakaian di TIAP tombol** — hitung/rekam berapa kali dipakai.
- **Ditinjau bersama tiap 2 minggu** — dasar memutuskan fitur mana dipertahankan/dibuang.
- `[BELUM DISPESIFIKASIKAN: apa yang direkam (klik saja? durasi? hasil?), di mana disimpan
  (lokal? server mode-jauh?), format tinjauan 2-mingguan]`

## 4. Belum dispesifikasikan (daftar kerja)

- Kerangka teknis (Electron/Tauri/lainnya), OS target.
- Kontrak ke server `ingat` (REST/MCP yang sudah ada).
- Layout tiap prioritas fungsi.
- Skema data penanda pengukuran.

## 5. Kaitan dengan kode yang sudah ada — CATATAN (bukan bentrok keras)

- **Selaras** dengan commit "Mode jauh: hook menulis ke server" — desktop app cocok jadi
  **klien tipis** ke server `ingat`, sejalan dengan tujuan "perangkat boleh dibuang".
- **Divergensi arah dari K23** (Dashboard web "Papan Bukti"): K23 sengaja dibuat
  "ala aplikasi catatan" dengan graph view force-directed. K29 justru **menjauh** dari meniru aplikasi catatan.
  Artefak berbeda (web dashboard vs desktop app), jadi tidak bentrok langsung — tapi arah desain
  berbeda; dicatat untuk ditinjau apakah keduanya konsisten atau dashboard web perlu disesuaikan.
