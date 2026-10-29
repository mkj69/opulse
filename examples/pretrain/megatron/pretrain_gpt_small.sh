#!/usr/bin/env bash
set -euo pipefail

: "${MEGATRON_PATH:?Set MEGATRON_PATH to a Megatron-LM checkout}"
if [ "$#" -ne 3 ]; then
  echo "Usage: pretrain_gpt_small.sh DATA_PREFIX TOKENIZER_DIR CHECKPOINT_DIR" >&2
  exit 2
fi

torchrun --standalone --nproc_per_node="${NPROC_PER_NODE:-1}" \
  "${MEGATRON_PATH}/pretrain_gpt.py" \
  --num-layers 6 \
  --hidden-size 384 \
  --ffn-hidden-size 1536 \
  --num-attention-heads 6 \
  --seq-length 512 \
  --max-position-embeddings 512 \
  --micro-batch-size 2 \
  --global-batch-size 16 \
  --train-iters "${TRAIN_ITERS:-1000}" \
  --lr 0.0003 \
  --min-lr 0.00003 \
  --lr-decay-style cosine \
  --lr-decay-iters "${TRAIN_ITERS:-1000}" \
  --lr-warmup-fraction 0.01 \
  --weight-decay 0.1 \
  --clip-grad 1.0 \
  --tensor-model-parallel-size 1 \
  --pipeline-model-parallel-size 1 \
  --tokenizer-type HuggingFaceTokenizer \
  --tokenizer-model "$2" \
  --data-path "$1" \
  --split 98,2,0 \
  --save "$3" \
  --save-interval 500 \
  --eval-interval 200 \
  --eval-iters 10 \
  --log-interval 10
