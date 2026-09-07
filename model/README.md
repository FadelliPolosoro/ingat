# Model embedding `ingat-e5-base`

Sumber bobot: `intfloat/multilingual-e5-base` (Hugging Face, lisensi MIT), 768 dimensi,
jendela 512 token. Tidak ada di pustaka resmi Ollama, jadi dikonversi sendiri (K9) supaya
provenance bersih dan bisa diulang siapa pun.

```
bash model/bangun-gguf.sh
ollama create ingat-e5-base -f model/Modelfile
ollama show ingat-e5-base
```

Catatan pemakaian yang ditegakkan adapter (`src/sematkan/ollama.ts`):
- Keluarga e5 dilatih dengan prefiks `query: ` / `passage: `; adapter menambahkannya otomatis.
- Teks dipotong ke 1.500 karakter sebelum dikirim (jendela 512 token).
- Identitas model (nama + dimensi) dicatat per koleksi; ketidakcocokan = error.

sha256 GGUF hasil konversi dicatat di `KEPUTUSAN.md` (K9) setelah dibangun pertama kali.
Berkas `.gguf` dan folder `hf/` tidak masuk git (`.gitignore`).
