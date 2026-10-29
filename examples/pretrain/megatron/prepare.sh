#!/usr/bin/env bash
set -euo pipefail

: "${MEGATRON_PATH:?Set MEGATRON_PATH to a Megatron-LM checkout}"
if [ "$#" -ne 3 ]; then
  echo "Usage: prepare.sh CORPUS_JSONL TOKENIZER_DIR OUTPUT_PREFIX" >&2
  exit 2
fi

python "${MEGATRON_PATH}/tools/preprocess_data.py" \
  --input "$1" \
  --json-keys text \
  --output-prefix "$3" \
  --tokenizer-type HuggingFaceTokenizer \
  --tokenizer-model "$2" \
  --workers "${WORKERS:-4}" \
  --append-eod
