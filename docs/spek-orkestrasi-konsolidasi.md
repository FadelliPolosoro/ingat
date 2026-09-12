# Spek Orkestrasi & Konsolidasi Model-ke-Model — K28

| | |
|---|---|
| **Status** | **TERBANGUN sebagian** (13 Sep 2026). Empat rem + P11 sudah jalan dan teruji (`ingat/rem.py`, 29 uji). Pilihan runtime model lokal masih terbuka. |
| **Keputusan** | K28 (`KEPUTUSAN.md`) |
| **Induk** | `docs/spek-arsitektur-memori.md` Bab 2 (P11) & 9.1 (empat rem) + `docs/spek-ai-hybrid.md` **[BELUM ADA DI REPO — VERIFIKASI]** |
| **Pemilik keputusan** | Tuan Muda |

## 1. Prinsip P11 — "abstraksi bukan penyamaran" — TERBANGUN

Masuk daftar prinsip spek arsitektur Bab 2 (sebelumnya berhenti di P10).

- **Inti:** apa pun yang lahir dari data tier tinggi harus naik ke tingkat abstraksi yang bisa
  ditransfer (P8), bukan sekadar ditutupi. Menyalin kalimat sumber lalu menghapus angkanya adalah
  **penyamaran**, dan ditolak.
- **Ditegakkan pada keluaran, bukan masukan.** Ini titik desain terpenting K28: model lokal memang
  boleh *melihat* tier S — ia tidak keluar mesin, itulah dasar pelonggarannya. Yang dijaga adalah apa
  yang ia *hasilkan*.
- **Uji operasional** (`periksa_abstraksi`, jawaban atas "sudah cukup abstrak?"), keluaran gugur bila:
  1. memuat pola tier S (`POLA_TIER_S`: NIK, NPWP, rekening, kata kunci payroll/pajak);
  2. memuat deret ≥8 digit — identitas konkret;
  3. menyalin ≥5 kata berurutan dari sumber (`AMBANG_RUN_KATA`) — ini yang menangkap penyamaran.
- Keluaran yang gugur **dibuang**, bukan disimpan; kejadiannya dicatat ke metrik
  `rem_tier_s_abstraksi_ditolak`.

## 2. Model lokal untuk tier S

- **Pilihan:** Qwen3 **4B**; turun ke **1.7B** bila VPS berat (1 vCPU/4 GB — lihat catatan K9).
- **Sifat:** lokal, **tidak keluar mesin** — dasar mengapa tier S boleh menyentuhnya.
- **Lokalitas diverifikasi dari alamat, bukan nama** (`alamat_lokal`): loopback, RFC1918, label tunggal
  (`http://ollama:11434` — DNS Docker), atau sufiks `.local`/`.internal`. Penyedia bernama "lokal"
  yang `base_url`-nya cloud **ditolak** — kalau tidak, rem 1 bisa dilewati hanya dengan menamai ulang.
- `[BELUM DISPESIFIKASIKAN: runtime (Ollama vs vLLM vs llama.cpp), kuantisasi, sumber bobot/GGUF,
  Modelfile, cara dijalankan di compose — samakan gaya dengan K9]` — **status: PARKIR** atas
  permintaan Tuan Muda.

## 3. Empat rem wajib — TERBANGUN (`ingat/rem.py`)

Rinciannya di spek arsitektur **9.1**. Ringkas:

| # | Rem | Konfigurasi | Gagal-tertutup bila |
|---|---|---|---|
| 1 | Gate P/I/S + lokalitas | `rem_tier_s.penyedia` | tak terdaftar / tak terkonfigurasi / bukan alamat lokal |
| 2 | Abstraksi P11 | — (tidak bisa dimatikan) | keluaran gugur uji Bab 1 |
| 3 | Anggaran token harian | `rem_tier_s.anggaran_token_harian` | ≤ 0, atau kuota hari itu habis |
| 4 | Manusia penjaga akhir | `rem_tier_s.aktif`, `rem_tier_s.penjaga` | sakelar mati / penjaga kosong |

Rem 4 punya sisi kedua yang tidak bisa dimatikan lewat konfigurasi: pelajaran ber-`tier_maks: S`
**tidak pernah** naik status otomatis, berapa pun bobot buktinya — manusia yang menilai.

**Anggaran dicatat begitu model dipanggil**, termasuk saat keluarannya kemudian gugur P11. Alasannya:
biaya sudah terjadi; kalau hanya yang lolos yang dihitung, keluaran buruk jadi gratis dan rem 3 bisa
dikuras tanpa batas.

## 4. Ruang lingkup yang sengaja dipertahankan sempit

- Pelonggaran **hanya** untuk `jalur="konsolidasi"`. `Aplikasi.tanya` (`/tanya`) dan endpoint
  `/penyedia` tetap menolak tier S selamanya.
- `gate.S` di konfigurasi **diabaikan** — supaya konfigurasi gaya lama tidak jadi pintu belakang.
- Heuristik tier S **tidak menyalin** `ringkas` episode (vault = repo git, K7). Bila sintesis gagal
  atau gugur P11, pelajarannya ditulis manusia — sejalan Bab 9.

## 5. Klien yang terhubung

Per 13 Sep 2026: **Claude, Claude Desktop, ChatGPT, ChatGPT Desktop, Gemini, Perplexity.**

Keenamnya bermodel cloud, jadi **tidak satu pun boleh menerima tier S**. Rem 1 menutup mereka lewat
uji lokalitas `base_url` — bukan lewat daftar nama — supaya klien baru yang ditambahkan nanti tidak
otomatis lolos. Jalur masuk mereka (ekstensi browser K18/K20/K22, connector MCP K19) tidak berubah.

## 6. Sisa kerja

- Runtime model lokal (Bab 2) — **PARKIR**.
- `docs/spek-ai-hybrid.md` tidak ada di repo padahal jadi induk definisi gate P/I/S — celah lama.
- Kalibrasi angka: `AMBANG_RUN_KATA = 5` dan ambang 8 digit dipilih dari contoh nyata, belum diuji
  terhadap korpus pelajaran sungguhan. Tinjau setelah dua minggu metrik
  (`rem_tier_s_abstraksi_ditolak` vs total sintesis tier S).
