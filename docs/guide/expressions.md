# Expressions and datasets

<div class="op-lead" markdown>
**What it is:** `opulse expressions` samples expressions over an operator set and evaluates them.

**You get:** a dataset whose every answer was recomputed before it was written.

**Use it when:** you need question and answer pairs.
</div>


`opulse expressions` samples expression trees over an operator set, evaluates them, and writes one
JSON record per expression.

```bash
opulse operators --out outputs/operators.jsonl --layers 2 1 --seed 1
opulse expressions --operators outputs/operators.jsonl --out outputs/expressions.jsonl --count 10000
```

## A record

--8<-- "docs/snippets/expression_record.md"

| Field | Meaning |
| --- | --- |
| `expression` | the expression with numeral-base markers (`⊺⇮9` is 9 written in base 10) |
| `expression_plain`, `expression_full_brackets` | decimal renderings, minimal and fully bracketed |
| `result`, `result_text` | the value, and the value written in `result_base` |
| `undefined` | `true` when the value is NaN (`result` is then `null`) |
| `expansion` | base operations executed when every operator is unfolded |
| `steps` | every operator application with inputs, output and `base_ops` |
| `defined_operators` | `func_id`s of the defined operators applied in the expression, one entry per application |
| `tree` | the expression tree (JSON) |

Undefined expressions are dropped unless `--keep-undefined` is given:

--8<-- "docs/snippets/expression_undefined.md"

## Verified on write

Before a record is written, an evaluator independent of the generation path recomputes its value and
counts with the reference interpreter. A disagreement stops the run, so a dataset never contains an
unchecked answer.

## Shaping the data

| Setting | Effect |
| --- | --- |
| `expressions.max_depth` | depth of the sampled trees |
| `expressions.type_weights` | how often binary, prefix, postfix applications and atoms appear |
| `expressions.random_numeral_base`, `numeral_base` | the base numbers are written in |
| `expressions.random_result_base`, `result_base` | the base results are written in |
| `--max-layer L` | only use operators up to layer L |
| `--cython-build-dir DIR` | compile operators with Cython for large runs |
| `--operator-frequency`, `--frequency-seed` | how often each defined operator is drawn (below) |
| `--max-answer-share 0.2` | cap the number of records with one answer at 20% of the requested count |

See the [configuration reference](../reference/configuration.md#expressions).
The command prints the top answers, NaN share and depth histogram after writing records. A warning
points to `--max-answer-share` when two answers dominate. The default leaves answer sampling
unchanged for seeded runs. The full `opulse audit-data` report includes more distribution checks.

### Operator frequency

By default every operator of a kind (binary, prefix, postfix) is drawn equally often.
`--operator-frequency zipf:ALPHA` gives the defined operators a long tail instead: within each
kind they are ranked in a random order set by `--frequency-seed`, and the operator of rank r is
drawn with weight proportional to r^-ALPHA, so a few concepts are frequent and most are rare.
Base operations keep their weight, and the defined operators of each kind keep their total
weight, so the expected number of defined operators per expression is unchanged; only how the
draws spread over them changes. `zipf:0` is uniform. Both values are written to each record's
`provenance`, and `defined_operators` gives the empirical frequencies. `uniform` (the default)
samples exactly as before, so a seed gives the same expressions as in earlier versions.
