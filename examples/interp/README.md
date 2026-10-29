# Run an exact value probe

Use a Python environment with Opulse, nnsight, torch, and transformers. The model must already be in the local Hugging Face cache.

```bash
opulse operators --out ops.jsonl --layers 12 8 4 --seed 15
opulse bench build --operators ops.jsonl --out tasks.jsonl --count 200 --family compute --max-depth 2 --max-abs-value 500 --seed 15
opulse interp collect --model Qwen/Qwen2.5-0.5B --tasks tasks.jsonl --operators ops.jsonl --layers 0,12,23 --device cpu --out states
opulse interp probe --activations states --bins=-10,0,10 --out probe.json
opulse interp patch --model Qwen/Qwen2.5-0.5B --tasks tasks.jsonl --operators ops.jsonl --layers 0,12,23 --device cpu --max-pairs 2 --out patches
```

The first two commands generate definitions and 200 compute tasks with exact answers. The remaining commands save residual vectors, fit probes with an operator split, and compare two patched pairs with interpreter predictions. The probe report is in `probe.json`; patch records and their grouped fractions are in `patches/`.
