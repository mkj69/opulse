# Quickstart

These five commands grow operators, sample expressions, make hole tasks, and check the records. `tools/docs_examples.py` regenerates the displayed output. Terms such as [atom, operator, layer, interpreter, and NaN](../glossary.md) are defined in the glossary.

## 1. Grow an operator set

```bash
opulse operators --out outputs/operators.jsonl --layers 10 6 4 --seed 7
```

The starting set holds the base operations (`+ - * / %`, negation, `@ # $ &`). Ten operators are
added on layer 0, six on layer 1 and four on layer 2. Some of them:

--8<-- "docs/snippets/operators.md"

Each operator is one JSON line:

--8<-- "docs/snippets/operator_record.md"

## 2. Evaluate

Values and base-operation counts of the recursive operator above, computed by the reference
interpreter:

--8<-- "docs/snippets/evaluate.md"

## 3. Sample expressions with step-by-step solutions

```bash
opulse expressions --operators outputs/operators.jsonl --out outputs/expressions.jsonl \
                   --count 40 --seed 3 --cot en --keep-undefined
```

--8<-- "docs/snippets/expression_record.md"

After writing the file, the command prints the most frequent answers, their share, the NaN share
and a depth histogram. A warning appears when two answers account for more than 30% of at least
ten defined answers. Add `--max-answer-share 0.2` to limit how often one answer appears, or run
`opulse audit-data outputs/expressions.jsonl --out outputs/data-audit.json` for the full report.
`opulse bench build` prints the same short summary and also accepts `--max-answer-share`.
The default sampling remains unchanged so existing seeds reproduce the same records.
For the command above, the summary is:

```text
Data summary (40 records): top answers 0: 11, -4: 4, 1: 3, 2: 2, 3: 2; most common 30.6%; NaN 10.0%.
Depth histogram: 2: 2, 3: 2, 4: 36.
Warning: the two most common answers make up 41.7% of defined answers. Use --max-answer-share 0.2 to spread answers; inspect more with opulse audit-data.
```

The `cot` field of the same record:

--8<-- "docs/snippets/cot.md"

## 4. Make fill-in-the-blank problems

```bash
opulse holes --operators outputs/operators.jsonl --out outputs/holes.jsonl --count 100 --unique-only
```

--8<-- "docs/snippets/holes_unique.md"

## 5. Check everything

```bash
opulse verify --operators outputs/operators.jsonl --expressions outputs/expressions.jsonl
opulse analyze --operators outputs/operators.jsonl --out outputs/operators.analyzed.jsonl
```

`verify` compares every operator and every stored answer with the reference interpreter;
`analyze` adds the [SMT-LIB export](../guide/smt.md), branch reachability and
[algebraic properties](../guide/properties.md) to each operator.

## Next steps

* [Operators and definitions](../guide/definitions.md): what a definition means.
* [Configuration reference](../reference/configuration.md): every setting.
* [Command line reference](../reference/cli.md): every option.
