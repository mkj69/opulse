#!/usr/bin/env bash
set -euo pipefail

# Set MODEL_PATH, TRAIN_PARQUET, and VAL_PARQUET before running.
: "${MODEL_PATH:?set MODEL_PATH to a local model directory}"
: "${TRAIN_PARQUET:?set TRAIN_PARQUET to the training parquet file}"
: "${VAL_PARQUET:?set VAL_PARQUET to the validation parquet file}"

example_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

python -m verl.trainer.main_ppo \
  data.train_files="${TRAIN_PARQUET}" \
  data.val_files="${VAL_PARQUET}" \
  actor_rollout_ref.model.path="${MODEL_PATH}" \
  reward.custom_reward_function.path="${example_dir}/reward.py" \
  reward.custom_reward_function.name=compute_score \
  "${@}"
