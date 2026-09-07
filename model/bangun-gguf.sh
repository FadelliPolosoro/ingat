#!/usr/bin/env bash
# Konversi intfloat/multilingual-e5-base (MIT) ke GGUF f16 secara lokal, lalu daftarkan ke Ollama.
# Dependensi BUILD-TIME (bukan runtime ingat): git, python3, pip, huggingface-cli.
# Arsitektur XLM-RoBERTa didukung llama.cpp sejak Agustus 2024.
set -euo pipefail
cd "$(dirname "$0")"

MODEL_HF="intfloat/multilingual-e5-base"
OUT="multilingual-e5-base-f16.gguf"

if [ ! -d llama.cpp ]; then
  git clone --depth 1 https://github.com/ggml-org/llama.cpp.git
fi
python3 -m pip install --user -r llama.cpp/requirements/requirements-convert_hf_to_gguf.txt
python3 -m pip install --user -U "huggingface_hub[cli]"

if [ ! -d hf ]; then
  huggingface-cli download "$MODEL_HF" --local-dir hf
fi

python3 llama.cpp/convert_hf_to_gguf.py hf --outtype f16 --outfile "$OUT"
sha256sum "$OUT" | tee "$OUT.sha256"

echo
echo "Selesai. Daftarkan ke Ollama:"
echo "  ollama create ingat-e5-base -f Modelfile"
echo "Catat isi $OUT.sha256 ke KEPUTUSAN.md (K9) sebagai identitas model."
