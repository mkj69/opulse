```bash
python tools/docs_evidence.py operators --out outputs/ev/seed1.jsonl --sizes 20 20 --seed 1 --check-variety > /dev/null
opulse expressions --operators outputs/ev/seed1.jsonl --out outputs/ev/uniform.jsonl --count=2000 --seed 0
opulse expressions --operators outputs/ev/seed1.jsonl --out outputs/ev/zipf.jsonl --count=2000 --seed 0 --operator-frequency zipf:1.5
for f in uniform zipf; do
  echo "== $f"
  opulse audit-data outputs/ev/$f.jsonl --out outputs/ev/audit_$f.json --operators outputs/ev/seed1.jsonl \
    | grep -E "^(applications|expression_depth|highest_layer|operation_count):|Gini"
done
```

Output:

```text
== uniform
applications: n=2000, min=1, median=4.0, p90=6.0, max=7.
expression_depth: n=2000, min=2, median=4.0, p90=4.0, max=4.
highest_layer: n=2000, min=0, median=1.0, p90=1.0, max=1.
operation_count: n=2000, min=1, median=4.0, p90=6.0, max=7.
Defined operators used: 40/40; usage Gini: 0.112.
== zipf
applications: n=2000, min=1, median=4.0, p90=6.0, max=7.
expression_depth: n=2000, min=2, median=4.0, p90=4.0, max=4.
highest_layer: n=2000, min=0, median=1.0, p90=1.0, max=1.
operation_count: n=2000, min=1, median=4.0, p90=6.0, max=7.
Defined operators used: 40/40; usage Gini: 0.658.
```

*Wall time of this block on the documentation machine: 4 s.*
