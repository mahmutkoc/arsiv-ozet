#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
export ARSIV_LLAMA_SERVER="${ARSIV_LLAMA_SERVER:-$HOME/llama.cpp/build/bin/llama-server}"
export ARSIV_GPU_LAYERS=0
export ARSIV_SHARED=1
if [[ ! -x "$ARSIV_LLAMA_SERVER" ]]; then
  echo "llama-server bulunamadı: $ARSIV_LLAMA_SERVER" >&2
  exit 1
fi
if [[ ! -f .demo/password.txt ]]; then
  echo "Önce deploy/linux/password.py ile yeni sunucu şifresi oluşturun." >&2
  exit 1
fi
exec .venv/bin/python -m streamlit run app.py --server.address 127.0.0.1 --server.port 8503 --server.maxUploadSize 200 --browser.gatherUsageStats false
