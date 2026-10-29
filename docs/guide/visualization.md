# Reports and tools

<div class="op-lead" markdown>
A dataset of thousands of operators is hard to inspect from JSON lines, and a configuration file is easy to get wrong.
</div>

## HTML report

`opulse viz` writes a single self-contained HTML file: the dependency graph laid out by layer (click
a node for its definition, dependencies and dependents), per-layer statistics, and, with
`--expressions`, result distributions, operator usage and a sample browser.

```bash
opulse operators --out outputs/operators.jsonl --layers 2 1
opulse expressions --operators outputs/operators.jsonl --out outputs/expressions.jsonl --count 3
opulse viz --operators outputs/operators.jsonl --expressions outputs/expressions.jsonl --out outputs/report
```

The report for the quickstart data (open it [full screen](../assets/report/index.html)):

<iframe src="../../assets/report/index.html" style="width:100%;height:720px;border:1px solid var(--md-default-fg-color--lightest);border-radius:8px"></iframe>

## Configuration wizard

`opulse wizard` asks for every setting with its default filled in, validates the answers with the
same settings classes the generator uses, and writes a YAML configuration. `--dry-run` grows two
small layers with it and prints sample definitions and expressions.

```bash
# run
mkdir -p outputs
cat > outputs/answers.json <<'JSON'
{}
JSON
opulse wizard --out outputs/mine.yaml --answers outputs/answers.json --dry-run
opulse wizard --out outputs/mine.yaml --answers outputs/answers.json
```

## Cost fitting

`opulse complexity` measures `base_ops` of every operator on inputs spanning six orders of magnitude
in both signs, plus one input per branch found by z3, and fits candidate cost models (constant,
logarithmic, linear, n log n, quadratic, and their two-argument forms) by least squares, choosing by
BIC. The fit describes measured costs, not a worst-case bound; R² shows how well it fits.

--8<-- "docs/snippets/complexity.md"
