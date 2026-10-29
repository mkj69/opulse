# Pretraining on Opulse corpora

Opulse can turn expression records and benchmark tasks into text documents for causal language model training. Each output line is a JSON object with one `text` string. The tokenizer stores each known operator symbol as one token by default, including a complete symbol such as `◆₁`. It also stores atoms, numeral markers, configured digits, syntax, spaces, newlines, and four special tokens. UTF8 byte tokens cover other text, including English and Chinese descriptions.

## Build a corpus and tokenizer

The following commands create expressions, convert them to text documents, and build a tokenizer that checks every exported document for an exact round trip.

```bash
opulse operators --out outputs/operators.jsonl --layers 20 10
opulse expressions --operators outputs/operators.jsonl --out outputs/expressions.jsonl --count 10000 --cot en
opulse export megatron --input outputs/expressions.jsonl --out outputs/pretrain.jsonl
opulse export tokenizer --operators outputs/operators.jsonl --corpus outputs/pretrain.jsonl --out outputs/tokenizer
```

For expression records, `export megatron` uses the existing `text` field, which contains the expression and its checked result. The next command includes the narrated reduction in each document.

```bash
opulse export megatron --input outputs/expressions.jsonl --fields text cot --out outputs/pretrain_cot.jsonl
```

For benchmark tasks, the exporter joins `prompt` and `answer_text`. Use `--fields` to select strings that are present in every input record.

The next command includes the complete pseudo names used by `opulse bench build --naming pseudo` as operator tokens.

```bash
opulse export tokenizer --operators outputs/operators.jsonl --out outputs/tokenizer_pseudo --naming pseudo
```

The next command stores each operator character separately and gives complete decimal numbers through 100 their own tokens. Without `--number-bound`, numbers are sequences of digit tokens.

```bash
opulse export tokenizer --operators outputs/operators.jsonl --out outputs/tokenizer_chars --operator-mode character --number-bound 100
```

To keep token IDs across curriculum stages, extend the earlier directory. Existing IDs stay fixed, and newly seen operators are appended.

```bash
opulse operators --out outputs/larger_operators.jsonl --layers 24 12 --seed 1
opulse export tokenizer --operators outputs/larger_operators.jsonl --out outputs/tokenizer_larger --extend-from outputs/tokenizer
```

Install `tokenizers` to build the tokenizer. Loading it with Transformers also requires `transformers`. Both `tokenizer.json` and `tokenizer_config.json` are written in the output directory.

## Megatron LM

Megatron's [preprocessing script](https://github.com/NVIDIA/Megatron-LM/blob/main/tools/preprocess_data.py) reads the `text` field and writes indexed data. Its [tokenizer wrapper](https://github.com/NVIDIA/Megatron-LM/blob/main/megatron/core/tokenizers/text/libraries/huggingface_tokenizer.py) loads the tokenizer directory through Hugging Face AutoTokenizer. Set `MEGATRON_PATH` to a checkout and run these commands from the Opulse repository.

```bash
export MEGATRON_PATH=/path/to/Megatron-LM
mkdir -p outputs/megatron
bash examples/pretrain/megatron/prepare.sh outputs/pretrain.jsonl outputs/tokenizer outputs/megatron/opulse
bash examples/pretrain/megatron/pretrain_gpt_small.sh outputs/megatron/opulse_text_document outputs/tokenizer outputs/megatron/checkpoints
```

The preparation script appends `<eos>` to each document and writes `opulse_text_document.bin` and `opulse_text_document.idx`. The training script uses six transformer layers and the local tokenizer. Megatron requires a suitable accelerator and its own dependencies; this example has no CPU smoke path.

## Transformers on CPU

The following command runs three CPU steps with a tiny GPT2 model and saves a local checkpoint. The script also accepts `--architecture llama`; without `--smoke`, its default model has six layers.

```bash
python examples/pretrain/hf/train_from_scratch.py --corpus outputs/pretrain.jsonl --tokenizer outputs/tokenizer --out outputs/hf_smoke --smoke
```

Install `torch` and `transformers` for this script. It constructs model weights from a new configuration and reads the same `text` JSONL as the Megatron path.
