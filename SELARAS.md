# Penyelarasan implementasi Python ↔ kontrak `skema/ingat.sql`

Status per 7 September 2026. **Tiket 1–4 selesai; Store Python kini menulis `versi_kontrak = '2'` dan setiap kolom kontrak ada di DB Python (`uji_migrasi_python.py::KontrakSubset`). Port TS terbukti membaca DB Python (`interop-python.test.ts`).** Tiket 1 — kolom-kolom Python yang layak sudah masuk kontrak; `uji/uji_migrasi.py` menjamin v1 + migrasi ≡ v2 segar. Implementasi Python (`ingat/simpan.py::_SKEMA_SQL`) lahir dari spek v0.2
sebelum kontrak SQL v1 ditulis. Keduanya sekarang **dikunci pada state machine yang sama**
(`uji/uji_kontrak.py`), tetapi skema tabelnya belum identik. Kontrak v1 adalah target; port lain
(TypeScript) membaca kontrak, jadi sampai penyelarasan selesai **port belum bisa membaca DB Python**.

## Selisih yang tercatat

| Area | Implementasi Python | Kontrak v1 | Arah penyelarasan |
|---|---|---|---|
| Vektor | tabel `vektor` + `identitas_embedder`, koleksi `isi`/`pemicu` | sama | Selaras ✔ (7 Sep) |
| Episode `isi` | selalu di penyimpanan dingin gzip (`isi_ref`), tidak ada kolom `isi` | `isi` nullable + `isi_ref` | Kontrak menerima pola Python: `isi` boleh NULL sejak lahir bila `isi_ref` terisi — **tidak perlu migrasi** |
| Episode kolom ekstra | `langkah`, `sesi` | ada (v2) | Selaras ✔ |
| Episode `diredaksi` | ada (K10, migrasi aditif) | ada | Selaras ✔ |
| `riwayat_status` | `id INTEGER PRIMARY KEY` | sama | Selaras ✔ (7 Sep) |
| `metrik`, `panggilan_ingat` | `id INTEGER PRIMARY KEY` | sama | Selaras ✔ (7 Sep) |
| Pelajaran kolom ekstra | `tier_maks`, `sintesis`, `usulan_perluasan_lingkup`, `catatan` | ada (v2) | Selaras ✔ |
| Prosedur keberhasilan | tiga penghitung + cache `tingkat_berhasil` dihitung saat tulis | sama | Selaras ✔ (7 Sep) |
| Norma kolom ekstra | `berlaku_sampai`, `disusun_pada`, `disusun_oleh`, `berlaku_untuk_tanggal`, `isi`, `catatan` | ada (v2) | Selaras ✔ |
| `transisi_status` | tabel diisi dari peta `skema.py` saat Store dibuka | tabel | Selaras ✔ — port membaca aturan yang sama dari SQL (`interop-python.test.ts`) |
| `instrumen.titik_buta_diketahui` | ada | ada (v2; v1 salah tulis `titik_buta`) | Selaras ✔ |
| Transisi pemulihan | `dipersempit → aturan/aktif` (manusia) | diadopsi ke kontrak v1 | Selaras ✔ |
| Norma dicabut/dibatalkan | sebelumnya boleh mesin | hanya manusia | Python dikunci ke manusia ✔ |
| Frontmatter | subset YAML + PyYAML opsional | subset YAML | Selaras ✔ |

## Urutan penyelarasan (tiket)

1. ~~**kontrak-v2**~~ — **selesai 7 Sep 2026**: `skema/ingat.sql` v2, `skema/migrasi/002-v1-ke-v2.sql`, `skema/versi/ingat-v1.sql`, port TS diperbarui (`Prosedur`, `Norma`, `normaBerlakuPada`).
2. ~~**python-migrasi-vektor**~~ — **selesai**: tabel `vektor` + `identitas_embedder`; migrasi memindahkan BLOB lama lalu `DROP COLUMN`; identitas per koleksi ditegakkan (`IdentitasEmbedderTidakCocok`, `bangun_ulang_vektor=True` untuk ganti model). **Dua koleksi** (R12): `pemicu` dan `isi`; gateway memakai skor maksimum keduanya.
3. ~~**python-riwayat-portabel**~~ — **selesai**: rebuild `riwayat_status`, `metrik`, `panggilan_ingat` ke `id INTEGER PRIMARY KEY`.
4. ~~**episode-tetap-aktif**~~ — **selesai 7 Sep 2026** (R8): `Konsolidator.dinginkan_tertunda()`; hanya episode baru yang mengubah pelajaran (tanpa penggelembungan keyakinan / kontra palsu); draf prosedur tidak duplikat. Uji: `uji/uji_r8_pendinginan.py`.
5. **port-baca-db-python** — **bagian baca selesai** (`port/typescript/uji/interop-python.test.ts`: versi, episode, transisi, vektor). Bagian gateway TS menyusul irisan 1 port.

`Store` kini menulis `meta.versi_kontrak = '2'` — klaim kesesuaian pertama yang jujur, dijaga oleh `KontrakSubset` (setiap kolom kontrak ada) dan uji interop TS. Kolom ekstra Python di luar kontrak: tidak ada lagi untuk tabel item; `episode.isi` selalu NULL (verbatim di `isi_ref`, diizinkan kontrak).
