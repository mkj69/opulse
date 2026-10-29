```bash
python tools/docs_evidence.py operators --out outputs/ev/seed1.jsonl --sizes 20 20 --seed 1 --check-variety > /dev/null
opulse operators --out outputs/ev/plain.jsonl --layers 20 20 --seed 1 --check-variety --proportions 1 0 0
opulse expressions --operators outputs/ev/plain.jsonl --out outputs/ev/plain_corpus.jsonl --count 2000 --seed 0
opulse expressions --operators outputs/ev/seed1.jsonl --out outputs/ev/full_corpus.jsonl --count 2000 --seed 0
python - <<'EOF'
import json
from collections import Counter
from pathlib import Path
from tools.docs_evidence import display
for ops, corpus in [("plain", "plain_corpus"), ("seed1", "full_corpus")]:
    kinds = Counter(json.loads(l)["definition_type"] for l in open(f"outputs/ev/{ops}.jsonl"))
    rows = [json.loads(l) for l in open(f"outputs/ev/{corpus}.jsonl")]
    mean = lambda k: sum(r[k] for r in rows) / len(rows)
    print(f"{corpus:<13} operators {dict((k, v) for k, v in kinds.items() if k)}")
    print(f"{'':<13} records {len(rows)}, mean operation_count {mean('operation_count'):.2f}, "
          f"mean expansion {mean('expansion'):.1f}")
    first = rows[0]
    sample = {key: first[key] for key in
                                 ("id", "expression_plain", "result", "defined_operators",
                                  "operation_count", "expansion")}
    sample["expression_plain"] = display(sample["expression_plain"], Path(f"outputs/ev/{ops}.jsonl"))
    print("  record:", json.dumps(sample, ensure_ascii=False))
EOF
```

Output:

```text
{
  "accepted": {
    "simple_definition": 39,
    "recursive_definition": 1
  },
  "rejected": {
    "unused parameter ['a']": 27,
    "unused parameter ['b']": 21,
    "defined on too few inputs": 11,
    "nearly constant": 8,
    "degenerate subexpression": 8,
    "single call of the same arity": 7,
    "undefined on all samples": 4,
    "duplicate body": 3,
    "unused parameter ['a', 'b']": 3,
    "mostly returns an input": 1
  },
  "layers": {
    "0": 20,
    "1": 20
  }
}
plain_corpus  operators {'simple_definition': 39, 'recursive_definition': 1}
              records 2000, mean operation_count 3.98, mean expansion 156.4
  record: {"id": 0, "expression_plain": "((50 △₃ 30) @) △₇", "result": -64, "defined_operators": ["1ibre2EmV1", "cgBAWt31qB"], "operation_count": 3, "expansion": 329}
full_corpus   operators {'simple_definition': 19, 'branch_definition': 17, 'recursive_definition': 4}
              records 2000, mean operation_count 4.14, mean expansion 67.8
  record: {"id": 0, "expression_plain": "((37 □₂ 16) ▲₉ (32 % 18)) ▲₁", "result": 0, "defined_operators": ["Etel4MU8Fq", "Q2frrj4r4t", "bJ2S87tCQG"], "operation_count": 4, "expansion": 149}
```

*Wall time of this block on the documentation machine: 7 s.*
