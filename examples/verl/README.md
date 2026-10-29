# Opulse tasks in verl

This example matches [verl 0.9.1](https://pypi.org/project/verl/0.9.1/). Its [dataset reader](https://github.com/verl-project/verl/blob/v0.9.1/verl/utils/dataset/rl_dataset.py) accepts parquet files with chat messages in `prompt`. Its [reward manager](https://github.com/verl-project/verl/blob/v0.9.1/verl/workers/reward_manager/naive.py) passes `data_source`, `solution_str`, `reward_model.ground_truth`, and `extra_info` to the custom score function. The [reward config](https://github.com/verl-project/verl/blob/v0.9.1/verl/trainer/config/reward/reward.yaml) uses `reward.custom_reward_function.path` and `reward.custom_reward_function.name`.

Install Opulse and `pyarrow` in the Python environment used for preparation. Install Opulse in the verl environment too so reward workers can import it.

```bash
python -m pip install -e . pyarrow
```

This command installs the local Opulse package and the parquet writer.

Build task JSONL files with `opulse bench build`. Use separate operator sets for training and validation, and check their overlap with `opulse bench leakage` as described in the [benchmark guide](../../docs/guide/benchmark.md).

```bash
python -m opulse.cli.main bench build --operators train_ops.jsonl --out train_tasks.jsonl --count 300 --format steps
python -m opulse.cli.main bench build --operators val_ops.jsonl --out val_tasks.jsonl --count 100 --format steps
```

These commands create step tasks whose exact answers come from the Opulse interpreter.

Convert each task file to parquet. The `steps` mode gives half the reward for the final answer and half for valid single rewrites. The `progress` mode uses valid single rewrites divided by the length of the reference derivation. The `outcome` mode uses only the final answer and works with both task formats.

```bash
python examples/verl/prepare_data.py --tasks train_tasks.jsonl --out train.parquet --split train --reward-mode steps --operators train_ops.jsonl
python examples/verl/prepare_data.py --tasks val_tasks.jsonl --out val.parquet --split val --reward-mode steps --operators val_ops.jsonl
```

These commands write one verl record per task with `data_source`, `prompt`, `ability`, `reward_model`, and `extra_info`. Each record stores its reward mode and the absolute operator path needed to check step lines. Pass `--config` when the task set used a custom Opulse config; the same file must be available to reward workers.

The example script passes the parquet paths and custom reward function to verl. Set the model path and any training settings required by your verl installation before using it.

```bash
MODEL_PATH=/models/model TRAIN_PARQUET="$PWD/train.parquet" VAL_PARQUET="$PWD/val.parquet" \
  bash examples/verl/run.sh data.max_prompt_length=4096 data.max_response_length=1024
```

This command invokes `verl.trainer.main_ppo` with `reward.custom_reward_function.path` set to `examples/verl/reward.py` and `reward.custom_reward_function.name=compute_score`. The script forwards additional verl config keys supplied after its name.
