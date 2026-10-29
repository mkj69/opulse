# Generating operators

<div class="op-lead" markdown>
**What it is:** `opulse operators` generates new operators layer by layer and keeps those that pass every check.

**You get:** a JSONL file of verified operators with their compiled code.

**Use it when:** you need a new operator set, from tens to hundreds of thousands of operators.
</div>


`opulse operators` grows an operator set. For every requested operator it drafts a definition from
the operators already accepted, compiles it, and keeps it only if every acceptance check passes.

```bash
opulse operators --out outputs/operators.jsonl --layers 40 30 20 10 --seed 0
```

`--layers 40 30 20 10` asks for 40 operators on layer 0, 30 on layer 1 and so on. The layer of an
operator is the number of recursive operators stacked below it. The run resumes if `--out` exists.

<div class="opulse-anim" data-kind="layers">
<script type="application/json">
--8<-- "docs/snippets/anim_layers.json"
</script>
--8<-- "docs/snippets/anim_layers_static.html"
</div>
<p class="op-hint">Press play, or use the arrows and slider to inspect each layer.</p>

## Acceptance checks

A draft is rejected when any of these holds:

| Check | Example of a rejected draft |
| --- | --- |
| it lands on a different layer | a recursive operator over a layer-1 operator requested for layer 1 |
| a parameter is unused | `a ⊕ b = { a * 2 }` |
| it only renames another operator | `a ⊕ b = { a ⊗ b }` |
| two branches have the same body | `{ a + b, if a > 3; a + b, else }` |
| its body duplicates an existing operator | |
| the compiled code disagrees with the reference interpreter on any tested input | |
| it is undefined on every sampled input | |
| z3 proves a branch unreachable | `{ a, if a > 5; b, if a > 10; … }` |
| z3 proves a branch always undefined | `{ (b / (a - a)) * b, if a > 5; … }` |
| (`--check-variety`) it is nearly constant or mostly returns an input | |
| (`interest.dedup`) its values on the probe grid repeat an existing operator, also after permuting or negating arguments or the result | `a ⊗ b = { (a + a) - b }` next to `a ⊕ b = { (a * 2) - b }` |

The number of drafts rejected for each reason is logged at the end of every layer and shown at
the end of the animation above.

## Recursion templates

Chosen with `recursion.style`:

| Style | Control | Unfolds at most | Beyond |
| --- | --- | --- | --- |
| `bounded_mod` (default) | `v % m`, walked toward 0 from either sign | m − 1 times | No extra bound |
| `direct` | `v` itself, for \|v\| ≤ T | T times | NaN |
| `peano` | like `direct`, stepping with the atoms `v ⁻` / `v ⁺` | T times | NaN |
| `primitive` | the counter `n` (last parameter), for \|n\| ≤ T; the step reads `n - 1` and the previous result | T times | NaN |

The remainder keeps the sign of `v`, so the negative branch of `bounded_mod` is reachable exactly
for negative `v`.

### The primitive-recursion style

The first three styles call one lower operator g whose slots hold the previous result or a
parameter, so a step can never use the counter. `recursion.style: primitive` writes the standard
primitive-recursion schema instead (specification, [section 4.1](../reference/semantics.md#41-recursion)):

```text
h(x̄, n) = { base(x̄), if n == 0;
            g(x̄, n - 1, h(x̄, n - 1)), if n > 0 and n <= T;
            g(x̄, n + 1, h(x̄, n + 1)), if n < 0 and n >= - T }
```

* `base` is a random expression over the other parameters made of lower-layer operators, a
  parameter, or a constant.
* The step calls a lower layer operator with the previous result and the stepped counter in two
  of its slots. In `●₄₀(a - 1, a - 1, (a - 1) ●₄₁)`, the first two slots read the stepped
  counter and the last slot reads the previous result.
* Every parameter other than the counter must be read by the base or the step.
* T is `recursion.direct_bound` (default 8), exactly as for `direct`; beyond it the value is NaN.
* The counter steps with `- +`, or with `⁻ ⁺` when the starting set has no binary `- +` (the
  atomic set).

```yaml title="primitive.yaml"
operators:
  arity_weights: {1: 0.3, 2: 0.4, 3: 0.3}
recursion:
  style: primitive
  direct_bound: 6
```

These definitions come from this command, which applies the settings above:

```bash
opulse operators --out outputs/primitive.jsonl --layers 8 5 3 --seed 4 --arity-weights 1:0.3,2:0.4,3:0.3 --recursion-style primitive --recursion-direct-bound 6
```

`♢₂₃` is recursive on layer 1. `●₄₁` is recursive on layer 2 and steps with the three argument operator `●₄₀`:

```text
a ♢₂₃ b = { a, if b == 0; (b - 1) ♠₁₄ (a ♢₂₃ (b - 1)), if b > 0 and b <= 6; (b + 1) ♠₁₄ (a ♢₂₃ (b + 1)), if b < 0 and b >= - 6 }
a ●₄₁ = { - 77, if a == 0; ●₄₀(a - 1, a - 1, (a - 1) ●₄₁), if a > 0 and a <= 6; ●₄₀(a + 1, a + 1, (a + 1) ●₄₁), if a < 0 and a >= - 6 }
●₄₀(a, b, c) = { - 4, if a >= 61 and a < 98 and b >= 82 and b < 96; ((# c) □₃₃ b) ◇₂₂ a, if a >= 44 and a < 61 and b < 82; (◆₁₂ a) ◇₂₂ (12 ♠₁₇), if a >= 44 and a < 61 and b >= 96; b ♢₂₈, if a < 44 and b >= 96; ♡₆(- c, & (c ♢₂₈), & (- a)), else }
```

## Arity

`operators.arity_weights` sets how many new operators of each arity are grown, as relative
weights:

```yaml
operators:
  arity_weights: {1: 0.25, 2: 0.5, 3: 0.25}
```

* Arity 1 is split evenly between prefix and postfix; arity 3 and more is written in call form,
  `⊕(a, b, c)`, in definitions, expressions, prompts and solutions.
* The default `{1: 0.5, 2: 0.5}` draws exactly as earlier releases, so existing seeds give
  byte-identical operator sets; no call-form operator is grown unless you ask for one.
* Parameters are named by `symbols.operand_names` (default `a b c d e f g h`); the generator
  refuses an arity with more parameters than names.
* Branch conditions of a call-form operator cut a grid on two of its parameters, chosen at random.
* In expressions, call-form operators get the weight `expressions.type_weights.call` (default: the
  `binary` weight) and one leaf per argument.
* Algebraic laws (`opulse analyze`) check symmetry under every argument permutation and
  idempotence when all arguments are equal for operators with three or more arguments.
  Associativity and left or right identities use binary argument positions, so they have no
  direct law for this call form.

## Bounded search

Set `recursion.search_enabled: true` to let simple definitions use
`search(i, T, condition)`. The generator tries indices from 0 through
`recursion.search_bound` and returns the first match. The default bound is 8 and generated
search accepts bounds through 32. The default switch is false.

Example: `a ⊕ b = { search(i, 4, (i + a) == b) }` returns 2 when `a` is 2 and `b` is 4.

## Partial definitions and priorities

* `operators.partial_probability` makes some branch definitions end without `else`; they are
  undefined outside their regions.
* `--max-priority-levels N` gives binary operators random priority levels and associativity, so
  expressions can omit brackets. Call-form operators delimit themselves and get no priority.

## Interesting operators

The acceptance checks keep operators that are correct and defined. They do not ask whether an
operator is worth having. Two drafts can be written differently and still compute the same
function, and a draft can be correct but dull: nearly constant, or a copy of an atom. The
`interest` settings judge operators by what they compute, in the spirit of the interestingness
heuristics of Lenat's AM. Every setting is off by default, and a default run computes none of it,
so existing seeds still give byte-identical output.

### Value tables

Every judgement reads the operator's value table: its values on a fixed probe grid.

* Integer arguments take the values in `interest.probe_ints` (default 0, ±1, ±2, ±3, ±5, ±7, ±10,
  ±17, ±31, ±50, ±64, ±83, ±100). The list is closed under negation and reaches the default
  condition and value range, so the table sees most branches.
* `bool`, `str` and `list[int]` arguments take fixed values listed in
  `opulse.generation.interest.TYPED_PROBES`.
* The grid is the product of these lists over the arguments while the product fits
  `interest.max_probe_points` (default 729). For larger arities, the probe set varies
  every argument and stays closed under the argument transformations used by deduplication.
  A cap too small to vary every argument raises a `ValueError`.
* Every score records a short hash of the probe set (`probes`), so scores from different probe
  sets are not mixed up.

### Behavioural deduplication

With `interest.dedup: true` (or `--dedup`) a candidate that passes every other check is rejected
when its value table equals that of an operator already in the set, atoms included. The check
also tries cheap transformations of the candidate:

| Rejection reason | The candidate equals an existing operator after |
| --- | --- |
| `behavioural duplicate` | nothing |
| `behavioural duplicate up to argument order` | permuting its arguments |
| `behavioural duplicate up to negation` | negating some arguments, the result, or both |
| `behavioural duplicate up to argument order and negation` | both |

Negation is `-x` for integers and `not x` for booleans; strings and lists are never negated.
Operators with more than three arguments try only exchanges of two arguments and single
negations. The reasons are counted with the other rejection reasons in the run summary.

The test is on the probe grid only. Two operators that agree on every probe but differ elsewhere
count as duplicates. For example `a ⊗ b = { (a + a) - b }` is a duplicate of
`a ⊕ b = { (a * 2) - b }`, `a ⊘ b = { (b * 2) - a }` is one up to argument order, and
`a ⊖ b = { b - (a * 2) }` is one up to negation.

### The score

Each defined operator gets five components, each between 0 and 1, and a total score: their mean
weighted by `interest.weights`.

| Component | Exact definition |
| --- | --- |
| `novelty` | Share of probe points where the operator differs from the nearest earlier operator with the same argument and result types, minimised over the transformations above. 1 when no earlier operator has those types; 0 for a duplicate. The record names the nearest operator (`nearest`) and the transformation (`nearest_transform`). |
| `regularity` | Share of the regularities tested for this operator that hold. The record lists each one that holds, with its evidence. |
| `reuse` | r / (1 + r), where r (`callers`) is the number of later operators whose code calls it. |
| `non_degeneracy` | Share of defined values on the grid, times the entropy of the output values divided by log2 of the grid size. A constant scores 0. |
| `compression` | t / (t + d), where t and d are the zlib sizes in bytes of the value table and of the definition text. A short definition with a varied table scores high. |

The regularities, and when each is tested:

| Regularity | Tested for | Holds when |
| --- | --- | --- |
| `symmetric` | two or more arguments of one type | exchanging any two such arguments keeps every value |
| `odd`, `even` | one integer argument, integer result | f(-x) = -f(x), or f(-x) = f(x), on the probes |
| `monotone` | an integer argument, integer result | along that argument, with the others at their probes, the defined values never decrease (or never increase) and some line changes |
| `periodic` | an integer argument | the smallest p from 2 to `interest.max_period` with f(x + p) = f(x) on [-R, R], R = `interest.regularity_range`; a constant line does not count |
| `fixed_points` | result type equal to every argument type | f(x, ..., x) = x for some but not all x on [-R, R]; the record lists them |
| `idempotent` | as above | f(f(x)) = f(x) for one argument; f(x, ..., x) = x for more |
| `involution` | one argument of the result type | f(f(x)) = x |

These are read on the value table, so each starts with status `table` (`witness` for fixed points,
which are exact). `opulse interest --solver` asks z3 about every table regularity of an integer
operator in exact semantics, with `interest.solver_timeout_ms` per question. A proof changes the
status to `proved`. A counterexample changes it to `refuted`, and the regularity then no longer
counts. A question z3 cannot answer in time keeps `table`. For example `⊜ a = { 7 - a }` is an
involution on the table, but z3 refutes it: for `a` near -2147483647, `7 - a` leaves the value
domain, so f(f(a)) is NaN there.

### Steering growth

`interest.selection` makes the generator choose each new operator from a pool of
`interest.pool` candidates (default 4) that pass every check:

* `best` keeps the candidate with the highest score (the earlier one on a tie);
* `sample` draws one with weight exp(score / `interest.temperature`), default temperature 0.1;
* the candidates not chosen are counted as `not selected by interest`.

During growth `reuse` is 0 for every candidate, since no later operator exists yet. A run with
`interest` on scores the finished set once more at the end, so the `interest` field of every
defined operator in the output file has its final reuse count, and the run summary has the score
distribution. A pool costs about `pool` times the generation time per operator.

```yaml title="interesting.yaml"
interest:
  dedup: true
  selection: best
  pool: 4
  weights: {novelty: 1, regularity: 1, reuse: 1, non_degeneracy: 1, compression: 1}
```

```bash
opulse operators --out outputs/interesting_baseline.jsonl --layers 10 6 4 --seed 0
cat > interesting.yaml <<'YAML'
interest:
  dedup: true
  selection: best
  pool: 4
  weights: {novelty: 1, regularity: 1, reuse: 1, non_degeneracy: 1, compression: 1}
YAML
opulse operators --config interesting.yaml --out outputs/interesting.jsonl --layers 10 6 4 --seed 0
# the same from the command line
opulse operators --dedup --interest-selection best --interest-pool 4 \
    --out outputs/interesting_cli.jsonl --layers 10 6 4 --seed 0
```

### Reading the scores

`opulse interest` scores any operator set without changing it:

```bash
opulse interest --operators outputs/operators.jsonl --top 10
opulse interest --operators outputs/operators.jsonl --solver --out outputs/scored.jsonl --json
```

It prints the number of behavioural duplicates, the mean and quartiles of the score and of each
component, and the highest scoring operators with the regularities that hold. `--out` writes the
set back with an `interest` field per defined operator; `--per-layer N` lists at most N operators
from one layer.

To pick operators for a showcase, use the function behind `--top`:

```python
from opulse.config import Settings
from opulse.core import OperatorRegistry
from opulse.generation.interest import featured_operators

registry = OperatorRegistry.from_jsonl("outputs/operators.jsonl")
for op, record in featured_operators(registry, Settings(), k=6, per_layer=2):
    print(record["score"], op.definition)
```

## Settings

All generation settings are listed in the [configuration reference](../reference/configuration.md)
(`operators`, `recursion` and `interest` sections).
