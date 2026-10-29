```bash
opulse operators --out outputs/ev/seed1.jsonl --layers 20 20 --seed 1 --check-variety > /dev/null
opulse operators --out outputs/ev/seed2.jsonl --layers 20 20 --seed 2 --check-variety > /dev/null
opulse bench leakage --train-operators outputs/ev/seed1.jsonl --test-operators outputs/ev/seed2.jsonl
python - <<'EOF'
import json
from pathlib import Path
from tools.docs_evidence import display
defs = lambda p: {json.loads(l)["definition"] for l in open(p)} - {None}
a, b = defs("outputs/ev/seed1.jsonl"), defs("outputs/ev/seed2.jsonl")
print(len(a), "new definitions from seed 1,", len(b), "from seed 2,", len(a & b), "identical")
for name, d, path, offset in (("seed 1", a, "outputs/ev/seed1.jsonl", 0),
                              ("seed 2", b, "outputs/ev/seed2.jsonl", 40)):
    examples = [display(s, Path(path), offset) for s in sorted(d, key=lambda item: (len(item), item))[:2]]
    print(name, "shortest:", *examples, sep="\n  ")
EOF
```

Output:

```text
{
  "test_operators": 40,
  "structural": {
    "shared": 0,
    "examples": []
  },
  "behavioural": {
    "shared": 0,
    "candidates": 0,
    "examples": []
  },
  "shared_func_ids": 0,
  "shared_symbols": 1
}
40 new definitions from seed 1, 40 from seed 2, 0 identical
seed 1
  shortest:
  ■₄ a = { 56 * a }
  △₂ a = { - (a ▲₈) }
seed 2
  shortest:
  ◆₅ a = { a ◆₂ a }
  a ▼₄ = { # (4 + a) }
```

*Wall time of this block on the documentation machine: 22 s.*
