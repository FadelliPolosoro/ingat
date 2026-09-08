# Model embedding `ingat-e5-base`

Sumber bobot: `intfloat/multilingual-e5-base` (Hugging Face, lisensi MIT), 768 dimensi,
jendela 512 token. Tidak ada di pustaka resmi Ollama, jadi dikonversi sendiri (K9) supaya
provenance bersih dan bisa diulang siapa pun.

Penyemat semantik **opsional**. Pemasangan dasar memakai penyemat `lokal` (512-dim, tanpa model,
tanpa jaringan). Berkas ini untuk saat kamu memutuskan pindah ke penyemat semantik.

---

## Bangun di mesin yang lega, JANGAN di VPS kecil

`bangun-gguf.sh` meng-clone llama.cpp, memasang `torch` (~2,5 GB), mengunduh bobot ~1,1 GB, lalu
mengonversinya. Di VPS 1 vCPU / 4 GB tanpa swap itu lambat dan bisa kena OOM — dan sama sekali
tidak perlu dikerjakan di sana: **hasilnya satu berkas `.gguf` yang bisa dibangun di mana saja
lalu dikirim.**

Pakai venv supaya `torch` tidak masuk ke Python yang menjalankan hook:

```bash
python -m venv /tmp/venv-gguf
/tmp/venv-gguf/bin/python -m pip install -r model/llama.cpp/requirements/requirements-convert_hf_to_gguf.txt "huggingface_hub[cli]"
bash model/bangun-gguf.sh          # menghasilkan model/multilingual-e5-base-f16.gguf
```

Catat `sha256` hasil konversi ke `KEPUTUSAN.md` (K9) sebagai identitas model.
Berkas `.gguf` dan folder `hf/` tidak masuk git (`.gitignore`).

## Jalankan di server: Ollama sebagai service compose, bukan di host

```bash
docker compose --profile semantik up -d          # menjalankan container `ingat-ollama`
docker cp model/multilingual-e5-base-f16.gguf ingat-ollama:/tmp/
docker cp model/Modelfile.container ingat-ollama:/tmp/Modelfile
docker compose exec ollama ollama create ingat-e5-base -f /tmp/Modelfile
docker compose exec ollama ollama list
```

**Kenapa container, bukan Ollama di host.** Versi lama `instal-vps.sh` memasang Ollama di host lalu
menyetel `"host": "http://host.docker.internal:11434"`. Itu tidak pernah bisa bekerja di Docker
Linux, karena dua sebab yang menumpuk:

1. `host.docker.internal` tidak resolve dari container tanpa `extra_hosts: host-gateway`.
2. Meski namanya resolve, Ollama di host hanya mendengar `127.0.0.1` — sambungan dari container
   tetap ditolak. Menyuruhnya mendengar `0.0.0.0` berarti memaparkan Ollama ke internet pada VPS
   yang tidak punya firewall.

Kombinasi itu berbahaya justru karena **diam**: penyemat gagal → `tambah_episode` menggulung balik
(lihat K10) → **nol episode tercatat**, padahal pemasangannya kelihatan sukses. Sebagai service di
jaringan compose, Ollama dicapai lewat DNS Docker (`http://ollama:11434`), tanpa satu pun port ke
host, dan konfigurasinya identik di Linux/macOS/Windows.

## Beralih ke penyemat semantik = WAJIB reindex

`lokal` 512-dim dan `ingat-e5-base` 768-dim punya identitas embedder berbeda; membuka store dengan
penyemat lain melempar `IdentitasEmbedderTidakCocok`. Itu disengaja, bukan kerusakan.

```bash
# 1. ubah blok embedding di konfigurasi.json
#    {"jenis":"ollama","host":"http://ollama:11434","model":"ingat-e5-base","dim":768,"prefiks":true}
# 2. reindex — tanpa ini semua perintah lain gagal
docker compose run --rm ingat python3 -m ingat bangun-ulang-vektor
docker compose restart ingat
```

Yang disemat ulang **hanya vektor**. Isi verbatim di penyimpanan dingin tidak disentuh (K10), jadi
tidak ada bukti yang hilang.

## Catatan pemakaian yang ditegakkan adapter

(`ingat/vektor.py` di rujukan Python; `src/sematkan/ollama.ts` di port TS)

- Keluarga e5 dilatih dengan prefiks `query: ` / `passage: `; adapter menambahkannya otomatis.
- Teks dipotong ke 1.500 karakter sebelum dikirim (jendela 512 token).
- Identitas model (nama + dimensi) dicatat per koleksi; ketidakcocokan = error, bukan diam-diam
  menghasilkan vektor yang tidak sebanding.
