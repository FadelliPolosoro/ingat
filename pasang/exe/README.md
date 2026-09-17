# ingat panel — build .exe (Windows)

Aplikasi desktop `ingat panel` dibungkus jadi satu `.exe` dengan PyInstaller.
Titik masuk: [`ingat-panel.py`](ingat-panel.py) (memanggil `ingat.panel.jalankan`
dengan konfig `~/.ingat/konfigurasi.json` bila ada).

## Prasyarat (sekali)

```bash
python -m pip install pyinstaller
```

PyInstaller hanya alat build — TIDAK menjadi dependency runtime (panel tetap stdlib-only).

## Build

Dari root repo (`Memori/`):

```bash
python -m PyInstaller --noconfirm --onefile --windowed --name ingat-panel \
  --collect-submodules ingat \
  --add-data "static;static" \
  --add-data "pasang/browser-extension;pasang/browser-extension" \
  --add-data "pasang/mcpb;pasang/mcpb" \
  --paths . \
  pasang/exe/ingat-panel.py
```

Hasil: `dist/ingat-panel.exe` (~13 MB).

- `--collect-submodules ingat` — tangkap import lazy (`api`, `pantau`, `tanya`, `konsolidasi` di-import di dalam fungsi).
- `--add-data …` — `static/` (dashboard+monitor), folder ekstensi & MCPB (dipakai tombol "Siapkan" di jendela Koneksi AI). Path dihitung dari `_MEIPASS` (lihat `panel._basis_sumberdaya`).
- `--paths .` — supaya PyInstaller menemukan paket `ingat` saat menganalisis launcher.

## Verifikasi

```bash
# jalankan, cek proses hidup + server in-process merespons
# 8765 → 401 (server hidup, butuh auth) · 8790 → 200 (monitor)
```

## Catatan portable (device baru)

- **`INGAT_TOKEN` (env) wajib** agar server 8765 (API + koneksi AI) start. Tanpa itu
  GUI + monitor 8790 tetap jalan, tapi ekstensi/klien tak bisa otentikasi → koneksi AI mati.
- **Ollama** (embedder `ingat-e5-base`) harus terpasang terpisah untuk konsolidasi & retrieval.
- Store & vault dibaca dari `~/.ingat/` — bawa lewat backup/restore (Fase 1).
