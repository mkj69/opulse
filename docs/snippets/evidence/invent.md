```bash
python tools/docs_evidence.py operators --out outputs/ev/seed1.jsonl --sizes 20 20 --seed 1 --check-variety > /dev/null
opulse expressions --operators outputs/ev/seed1.jsonl --out outputs/ev/unfold_all.jsonl --count 500 --seed 0 --cot en
opulse expressions --operators outputs/ev/seed1.jsonl --out outputs/ev/layer0_known.jsonl --count 500 --seed 0 --cot en \
                   --cot-known-layers 1
python - <<'EOF'
import json
from pathlib import Path
from tools.docs_evidence import display
corpora = {}
for name in ["unfold_all", "layer0_known"]:
    rows = corpora[name] = [json.loads(l) for l in open(f"outputs/ev/{name}.jsonl")]
    lines = [r["cot"].count("\n\nIn ") for r in rows]
    print(f"{name:<13} records {len(rows)}, mean trace paragraphs {sum(lines) / len(lines):.1f}")
pairs = zip(corpora["unfold_all"], corpora["layer0_known"])
print("same expression and value:", sum(a["expression"] == b["expression"] and a["result"] == b["result"]
                                        for a, b in pairs), "of", len(rows))
r = corpora["unfold_all"][0]
show = lambda s: display(s, Path("outputs/ev/seed1.jsonl"))
print("expression       ", show(r["expression_plain"]), "=", r["result"])
symbol = {o["func_id"]: o["symbol"] for o in map(json.loads, open("outputs/ev/seed1.jsonl"))}
print("defined_operators   ", [show(symbol[f]) for f in r["defined_operators"]])
print("dependent_operators ", len(r["dependent_operators"]), "operators and atoms below them")
print("steps (op, in, out) ", [(show(s["symbol"]), s["inputs"], s["output"]) for s in r["steps"]])
EOF
```

Output:

```text
unfold_all    records 500, mean trace paragraphs 79.3
layer0_known  records 500, mean trace paragraphs 28.9
same expression and value: 500 of 500
expression        ((37 □₂ 16) ▲₉ (32 % 18)) ▲₁ = 0
defined_operators    ['▲₁', '▲₉', '□₂']
dependent_operators  25 operators and atoms below them
steps (op, in, out)  [('□₂', [37, 16], -752), ('%', [32, 18], 14), ('▲₉', [-752, 14], -33), ('▲₁', [-33], 0)]
```

*Wall time of this block on the documentation machine: 11 s.*
