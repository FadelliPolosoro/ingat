# ingat — instruksi untuk agent coding (Claude Code, dan agent lain yang membaca AGENTS.md)

Proyek: sistem memori agent yang bisa diperiksa manusia. **Implementasi rujukan: Python 3.11+ stdlib-only**
(`ingat/`). **Port TypeScript** (`port/typescript/`) memegang inti + kontrak, gateway belum.
Produk sebenarnya adalah **kontrak**: `skema/ingat.sql`, format frontmatter, protokol tool MCP.
Apache-2.0, privat sampai pemilik menyatakan siap. Pemilik: Tuan Muda (Fadelli Polosoro).

## Baca dulu
- `KEPUTUSAN.md` — keputusan terkunci K1–K13 (+ revisi K3). Jangan membuka ulang tanpa diminta.
- `docs/spek-arsitektur-memori.md` — desain. Bab 5 (status), 6 (skema), 8 (anggaran), 12 (uji).
- `SELARAS.md` — selisih skema implementasi Python vs kontrak SQL, dan urutan penyelarasannya.
- `docs/spek-arsitektur-memori.md` Lampiran E — landasan kognitif: kalau ragu *mengapa* sebuah aturan ada, cari di sana dulu.
- `.claude/rules/*.md` — aturan bertaraf: kontrak, keamanan, uji, gaya-kode, lisensi.

## Perintah

**Nama penafsir Python berbeda per OS.** Linux/macOS: `python3`. Windows: `python` atau `py -3` —
installer python.org **tidak** memasang `python3.exe`, dan nama itu jatuh ke stub Microsoft Store yang
keluar dengan kode bukan-nol. Di bawah ditulis `<py>`; ganti sekali sesuai OS.

**Shell.** Perintah di bawah dijaga tetap satu baris tanpa `&&`, karena `&&` bukan pemisah pernyataan
di Windows PowerShell 5.1 (parse error, bukan galat runtime). Untuk npm pakai `--prefix`, bukan `cd`.

- `<py> -m unittest discover -s uji -p "uji_*.py" -t .` — suite Python (152 uji, harus OK).
- `npm test --prefix port/typescript` — suite port TS (type-stripping Node 22, **tanpa** `npm install`).
- `npm install --prefix port/typescript` sekali, lalu `npm run build --prefix port/typescript` — type-check
  penuh `tsc` (strict + `noUncheckedIndexedAccess`). Hanya ini yang butuh install; `npm test` tidak, dan
  type-stripping **tidak** memeriksa tipe — suite hijau bukan bukti tipe lolos.
- `npm run cek-lisensi --prefix port/typescript` — pagar `.claude/rules/lisensi.md` atas dependensi dev.
- `<py> -m ingat --konfig konfigurasi.json <perintah>` — CLI (lihat `ingat/cli.py`).
- `… tanya` lalu `… jawab --berkas <path>` — konsolidasi berpandu pertanyaan (v0.5, `ingat/tanya.py`): mesin bertanya dari data, manusia menjawab di blok ```jawab```, jawaban diterapkan ke vault lalu disinkronkan.
- Model embedding: `model/README.md` (Ollama, dibangun sendiri; konfigurasi `embedding.jenis = "ollama"`).
- Hook Claude Code: `<py> -m ingat pasang [--tulis]`; handler `ingat/tangkap.py` (selalu exit 0; galat ke `<dir_data>/tangkap.log`).
  Catatan Windows: templat `pasang/settings.hooks.json` memaku `python3 -m ingat.tangkap …` di keenam
  hook. Di Windows semuanya akan diam-diam gagal — dan karena handler memang dirancang selalu exit 0,
  kegagalan itu tidak kelihatan sama sekali. Belum diperbaiki; butuh keputusan pemilik soal bentuknya.
- Deploy VPS: `docker compose up -d --build` (non-root, read-only; lihat `docker-compose.yml`).

## Cara kerja di repo ini
- Irisan vertikal tipis: satu uji putar-ulang hijau, baru tebalkan. Papan status: `uji/putar-ulang/README.md`.
- Uji ditulis sebelum kode. Uji `todo`/`skip` wajib menyebut nama tiket — bukan placeholder.
- **Jawaban tanya menulis ke VAULT, bukan ke store** (P5): `Penanya._terapkan` hanya menyunting berkas markdown; `Vault.sinkron` yang menegakkan state machine. Jangan tambah jalur pintas ke store.
- **Titik tulis episode tunggal**: `Store.tambah_episode` (`ingat/simpan.py`). Redaksi kredensial dan
  penanda tier hidup di sana. Jangan buat jalur tulis lain.
- **K10**: semua episode tersimpan verbatim termasuk tier S; kredensial diredaksi sebelum tulis; tier S
  tidak ke LLM (`Gate`), tidak keluar mesin, tidak muncul di `ingat()`/`buka_bukti()` tanpa `sertakan_S=True`.
- Ganti model embedding = `Store(..., bangun_ulang_vektor=True)`; tanpa itu Store menolak dibuka (`IdentitasEmbedderTidakCocok`).
- Semua perubahan status lewat `Store.ubah_status()`; state machine di `ingat/skema.py` dikunci ke
  `skema/ingat.sql` oleh `uji/uji_kontrak.py`. Ubah salah satu = ubah keduanya + port TS.
- Frontmatter = subset YAML (satu kunci per baris; nilai skalar atau JSON flow). PyYAML opsional.
- SQL portabel di kontrak; pragma hanya di `simpan.py`. Selisih skema Python vs kontrak → `SELARAS.md`.
- Klaim "selesai" hanya setelah kedua suite hijau, `tsc` lolos bila TS disentuh, dan berkas terbukti ada di disk.
  Uji `skipped` dihitung sebagai utang, bukan lulus — uji interop Python↔TS pernah dilewati diam-diam berbulan-bulan.
- Bahasa: identifier, komentar, pesan commit Bahasa Indonesia; istilah teknis Inggris boleh.
- Tanpa dependensi runtime (Python stdlib; TS `node:sqlite`). PyYAML opsional saja.
