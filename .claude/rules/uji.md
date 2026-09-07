---
paths: ["uji/**", "ingat/**", "port/typescript/**"]
---
# Aturan uji

- Python: `unittest` (stdlib). Berkas `uji/uji_*.py`. Store dibangun di `tempfile.mkdtemp`, dihapus di `tearDown`.
- TS: `node:test` + `node:assert/strict`. Berkas `port/typescript/uji/*.test.ts`.
- Uji tidak boleh butuh Ollama/LLM hidup: `PenyematLokal` (Python) / `PenyematPalsu` (TS); adapter jaringan
  diuji dengan pembuka/fetch yang disuntik.
- Uji putar-ulang U1..U9 (`uji/uji_putar_ulang.py`) adalah uji penerimaan; fixture bersama di
  `uji/putar-ulang/<U>/` dipakai kedua bahasa.
- `uji/uji_kontrak.py` dan `port/typescript/uji/status.test.ts` mengunci state machine ke `skema/ingat.sql`.
- Test yang belum bisa hijau: `test.todo` (TS) / `@unittest.skip("tiket …")` (Python) dengan nama tiket.
- Pesan assert Bahasa Indonesia, menyebut yang diharapkan dan yang didapat.
