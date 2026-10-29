# Hugging Face dataset export

`opulse export hf` packages generated operator, expression, and benchmark JSONL files in a local
directory that `datasets.load_dataset` can read. The command writes JSONL data and a dataset card.
It does not publish the directory.

## Inputs and splits

Generate separate operator sets for train and test with different seeds. Generate expressions
and benchmark tasks against the operator set assigned to each split. The export checks the
structural and behavioural fingerprints used by `opulse bench leakage`. It stops if generated
concepts or generated operator identifiers occur in both sets. Each expression and task must
carry provenance for its assigned operator set.

Supply at least one benchmark task family in both splits. Files may contain several families.
The available families are `compute`, `hole`, and `contrast`. `compute` tasks may use `free` or
`steps`; the other families use `free`.

```bash
opulse operators --out train_ops.jsonl --layers 10 6 --seed 11
cat > generation.sh <<'SH'
opulse operators --out train_ops.jsonl --layers 10 6 --seed 11
opulse operators --out test_ops.jsonl --layers 10 6 --seed 22
opulse expressions --operators train_ops.jsonl --out train_expr.jsonl --count 10
opulse expressions --operators test_ops.jsonl --out test_expr.jsonl --count 10
opulse bench build --operators train_ops.jsonl --out train_compute_free.jsonl --count 10
opulse bench build --operators test_ops.jsonl --out test_compute_free.jsonl --count 10
SH
bash generation.sh
rm -rf hf_dataset
opulse export hf \
  --train-operators train_ops.jsonl --test-operators test_ops.jsonl \
  --train-expressions train_expr.jsonl --test-expressions test_expr.jsonl \
  --train-tasks train_compute_free.jsonl --test-tasks test_compute_free.jsonl \
  --train-seed 11 --test-seed 22 \
  --generation-command "$(cat generation.sh)" --out hf_dataset
```

This small example packages compute tasks in both splits and records the input generation
commands from `generation.sh` in the dataset card. Generate other task families the same way
before adding their files to the export command.

The standalone entry point accepts the same options:

```bash
PYTHONPATH=src python tools/hf_export.py --help
```

This example prints the standalone export options.

## Load the directory

The card defines `operators`, `expressions`, and one config for each supplied task family.
Each config has `train` and `test` splits.

```python
from datasets import load_dataset

tasks = load_dataset("hf_dataset", "compute")
print(tasks["train"][0]["prompt"])
```

This example loads the compute tasks and prints the first training prompt.

The YAML header declares each feature and its type. Common fields are separate columns.
`record_json` preserves the complete original Opulse record, including expression steps and
benchmark metadata. Fields ending in `_json` contain JSON text. The `cot` column contains a
narrated derivation when the input expression was generated with `--cot en` or `--cot zh`.
The `format` column distinguishes compute tasks that request steps from tasks that request a
final answer.

The card records the supplied generation command, seeds, row counts, task formats, and leakage
report. The card and its metadata give the license `cc-by-4.0`, the license of Opulse data. Set
`--license` to another identifier when another license applies, or to `unknown` to state that no
license was specified.
