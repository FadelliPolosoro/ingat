# Spek Orkestrasi & Konsolidasi Model-ke-Model — K28

| | |
|---|---|
| **Status** | RANGKUMAN KEPUTUSAN (bukan spek penuh). Ditulis 2026-09-13 dari keputusan sesi lain. Arsitektur rinci **belum ditulis**. |
| **Keputusan** | K28 (`KEPUTUSAN.md`) |
| **Induk** | `docs/spek-arsitektur-memori.md` (gate P/I/S) + `docs/spek-ai-hybrid.md` **[BELUM ADA DI REPO — VERIFIKASI]** |
| **Pemilik keputusan** | Tuan Muda |

> Dokumen ini merekam apa yang **diputuskan**, bukan cara membangunnya. Titik yang belum
> dispesifikasikan ditandai `[BELUM DISPESIFIKASIKAN]`. Jangan dianggap final sebelum diisi.

## 1. Prinsip P11 — "abstraksi bukan penyamaran"

Ditambahkan ke daftar prinsip `docs/spek-arsitektur-memori.md` Bab 2 (saat ini baru P1–P10).

- **Inti:** data tier tinggi diangkat ke **tingkat abstraksi yang bisa ditransfer** sebelum
  dilihat model orkestrator — *bukan* sekadar diredaksi/disamarkan (mengganti nama dengan `XXX`).
  Abstraksi menghapus keterikatan pada identitas konkret sambil mempertahankan pola yang berguna;
  penyamaran hanya menutupi permukaan dan bocor lewat konteks.
- **Hubungan dengan P8** ("simpan tanpa mengikat konteks asal"): P11 adalah penerapan P8 pada
  jalur orkestrasi model-ke-model. `[BELUM DISPESIFIKASIKAN: kriteria uji "sudah cukup abstrak?"]`

## 2. Model lokal untuk tier S

- **Pilihan:** Qwen3 **4B**; turun ke **1.7B** bila VPS berat (1 vCPU/4 GB — lihat catatan K9).
- **Sifat:** lokal, **tidak keluar mesin** — inilah dasar mengapa tier S boleh menyentuhnya,
  berbeda dari penyedia cloud.
- `[BELUM DISPESIFIKASIKAN: runtime (Ollama vs vLLM vs llama.cpp), kuantisasi, sumber bobot/GGUF,
  Modelfile, cara dijalankan di compose — samakan gaya dengan K9]`

## 3. Empat rem wajib (pertahanan berlapis)

1. **Gate P/I/S** — tetap dipakai; lihat konflik di Bab 5.
2. **Abstraksi P11** — Bab 1.
3. **Anggaran token harian** — batas atas pemakaian orkestrasi per hari.
   `[BELUM DISPESIFIKASIKAN: angka, reset harian, perilaku saat habis]`
4. **Manusia penjaga akhir** — keputusan akhir tetap di tangan manusia.
   `[BELUM DISPESIFIKASIKAN: titik mana yang butuh persetujuan manusia]`

## 4. Belum dispesifikasikan (daftar kerja)

- Alur orkestrasi model-ke-model konkret (siapa memanggil siapa, untuk tugas apa).
- Definisi operasional P11 + uji keberterimaan abstraksi.
- Parameter anggaran harian & titik penjaga manusia.
- Perubahan kontrak/skema bila ada.

## 5. Konflik dengan kode — ARAH DIPUTUSKAN (implementasi tertunda)

**Arah diputuskan 2026-09-13:** Tuan Muda **setuju** gate tier-S dilonggarkan supaya model lokal
boleh memproses tier S (dijaga P11 + tiga rem lain). Ini membalik invarian yang saat ini di-*hardcode*
dan diuji. **Implementasi = tugas "bangun" terpisah, BELUM dikerjakan** — belum dijadwalkan.

- `ingat/gate.py` saat ini: `Gate.izin("S")` **selalu** mengembalikan `[]`; `wajib(…, "S")`
  **selalu** melempar `GateDitolak("tier S tidak pernah boleh dikirim ke penyedia inferensi (Bab 9)")`.
  Docstring: *"Tier S tidak pernah boleh — apa pun isi konfigurasi."*
- `docs/spek-arsitektur-memori.md` Bab 7.3 & Bab 9: job konsolidasi **melewati tier S**;
  tier S "Tidak pernah" dikonsolidasi oleh mesin.
- Preset `lokal` di `ingat/penyedia.py` (`qwen2.5:7b`) diperlakukan sebagai penyedia inferensi
  biasa → tier S diblokir darinya **juga**.
- **K28 melonggarkan invarian ini**: model lokal boleh melihat tier S (terabstraksi P11).
  Ini perubahan pada invarian keamanan terkuat sistem — perlu keputusan eksplisit + perubahan
  `gate.py`, Bab 9, dan mungkin `spek-ai-hybrid.md`. **Belum dikerjakan** (perintah: jangan bangun).
