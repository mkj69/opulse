# Step-by-step solutions

<div class="op-lead" markdown>
Chain-of-thought data written by a model can contain wrong steps; Opulse writes each step from a trace the interpreter has checked.
</div>

`--cot en` (or `zh`) adds a worked solution to every expression record:

```bash
opulse operators --out outputs/operators.jsonl --layers 2 1 --seed 1
opulse expressions --operators outputs/operators.jsonl --out outputs/expressions.jsonl \
                   --count 1000 --cot en
```

## How a solution is built

The reducer rewrites the expression one step at a time, always at the leftmost application whose
arguments are already numbers:

* **unfold** a defined operator: replace it by the body of the branch whose condition holds, with
  the arguments substituted;
* **compute** a base operation;
* **undefined**: a compared value is NaN, or no branch holds, and the application becomes NaN.

<div class="opulse-anim" data-kind="trace">
<script type="application/json">
--8<-- "docs/snippets/anim_trace.json"
</script>
--8<-- "docs/snippets/anim_trace_static.html"
</div>
<p class="op-hint">Press play, or use the arrows and slider to inspect each rewrite.</p>

Every step is re-evaluated by the reference interpreter before the text is written; the narrator
only reads values from the checked trace. The same record as text:

--8<-- "docs/snippets/cot.md"

Records whose full unfolding needs more than 2000 steps are skipped in this mode.

## Granularity

A full solution unfolds every operator down to base operations, which can take hundreds of steps.
Granularity is not a fixed list of levels: any choice of which operators are known gives a
derivation. A known operator is computed in one step, and that step is checked like every other
(its value must equal the operator's value); every other defined operator is unfolded. These options
choose the known operators:

| Option | Effect |
| --- | --- |
| `--cot-depth K` | unfold definitions at most K levels deep; deeper calls are computed in one step (`0`: nothing is unfolded) |
| `--cot-known-layers L` | operators of layers below L are known and computed in one step |
| `--cot-known SYMBOL ...` | the named operators are known |

Four of the possible granularities for one expression:

--8<-- "docs/snippets/granularity.md"

With `--cot-depth 1` only the operators written in the expression are unfolded:

--8<-- "docs/snippets/granularity_depth1.md"

## Any granularity

--8<-- "docs/snippets/granularity_anim.html"

The chips choose the cut. Each defined operator in the expression is either known, computed in one
step, or unfolded into its definition; atoms are always applied directly. With three operators there
are eight cuts, and all eight are precomputed and checked step by step by the reference interpreter.
The middle column follows your choice. The left column has every operator known, the right one
unfolds everything to atoms, and each shaded band holds the steps that stand for one step of the left
column. The three shortcuts are examples, not the only levels.

### Explorer

The explorer does the same for a whole operator set: any cut, chosen by layer with the slider or one
operator at a time in the dependency graph. The examples use operators generated with seed 7 and
named with a shape and subscript index by `python tools/docs_granularity.py`.
Example 1 computes `☆₁` after a nested `★₁` call. Example 2 computes `☆₁` after a nested
`▼₁` call. Example 3 applies `$` to the result of calls to `☆₁` and `■₂`.

<div class="op-gran" data-base="../../assets/data/" data-files="granularity_1.json granularity_2.json granularity_3.json" data-lang="en">
<p class="og-static">The explorer needs JavaScript. The same derivation as text is shown under Command line.</p>
</div>

* The slider makes whole layers known at once; at the left end every operator is unfolded down to
  base operations, at the right end each application in the expression is one step.
* Clicking an operator in the graph switches it between known (dashed) and unfolded (filled) and shows
  its explanation below. Any combination is allowed, not only the ones the slider reaches.
* Steps are coloured by kind: `expand` unfolds a definition, `eval` computes a defined operator in one
  step, `atom` computes a base operation.
* Clicking an `eval` step opens its nested derivation in place; its own `eval` steps open the same way.

Colours of operators follow the rest of this site: cyan for composition, amber for branching, magenta
for recursion.

### How a cut is computed

A derivation can also be kept as a tree. Its top level computes every defined operator in one step
(an `eval` step). Each such step opens into the derivation of that one application: the operator is
unfolded once, and the applications in its body are again computed in one step, each with a
derivation of its own below it. Opening every step reaches base operations.

A cut chooses which operators are known. Flattening the tree at a cut replaces the `eval` step of
every unfolded operator by its derivation, and gives exactly the steps the reducer writes with
`--cot-known` and `--cot-known-layers` (the tests compare the two at every layer cut and at all eight
cuts of the animation above). Every node of the tree is checked by the reference interpreter like any
other trace.

### Command line

`opulse trace` prints the derivation at a cut and opens the remaining evaluations done in one step `--open N`
levels deep. Here every operator is known and each evaluation is opened one level:

--8<-- "docs/snippets/granularity_tree.md"

| Option | Effect |
| --- | --- |
| `--known SYMBOL ...` | these operators are known (symbols or func_ids) |
| `--known-layers L` | operators of layers below L are known |
| `--depth K` | unfold at most K levels |
| `--open N` | under each remaining `eval` step, show its nested derivation, N levels deep |
| `--format json` | write the whole tree instead |

The JSON tree (schema `opulse.derivation/1`) lists every node once: its operator and inputs (none for
the expression itself), its source, its value and its steps. A step records its kind, the path of the
rewritten application, the operator, the inputs, the replacement, the branch and condition for an
`expand` step, and for an `eval` step of a defined operator the id of the node that opens it. Equal
applications share one node. The full schema is in [`opulse.trace.tree`](../api/trace/tree.md).

```python
from opulse.trace import build_tree, cut, flatten, to_json, verify_tree

root = build_tree(expression, registry, runtime, parser)
verify_tree(root, oracle)                       # every node, step by step
trace = flatten(root, cut(known_layers=1))      # the reducer's trace at this cut
data = to_json(root, renderer)
```

### Explaining one operator

`opulse explain` shows three views of an operator, built from its definition text:

* **formula**: each branch with the definitions of simple callees inlined, and SymPy's shorter form
  where the operator does not recurse; z3 decides each rewrite under Opulse semantics (bounded
  integers, NaN) and the output says whether it is proved, refuted with a counterexample, or undecided;
* **behaviour**: the branch path and the value on every input of a range, with consecutive inputs on
  the same path grouped (for a binary operator, blocks of `a` with the same runs over `b`);
* **uses**: the operators it depends on, as a tree.

The example for `△₁` shows its six branches, grouped input ranges, and dependencies.

--8<-- "docs/snippets/granularity_explain.md"

Each `inlined` and `SymPy form` line ends with the verdict of z3 on that rewrite.

## Operator descriptions

`opulse describe` writes mathematical and controlled prose descriptions in English and Chinese:

```bash
opulse operators --out outputs/operators.jsonl --layers 2 1 --seed 1
opulse describe --operators outputs/operators.jsonl --out outputs/operators.described.jsonl
```

--8<-- "docs/snippets/describe.md"

Base operations state their exact rules:

--8<-- "docs/snippets/describe_base.md"

| Field | Content |
| --- | --- |
| `nl_description_math_en`, `nl_description_math_zh` | mathematical style (also `nl_description_en/zh`) |
| `nl_description_natural_en`, `nl_description_natural_zh` | controlled prose that parses back to the definition |
| `nl_description_chain_en`, `nl_description_chain_zh` | the complete dependency chain, read from definition text |

The mathematical style keeps the conditions and bodies in operator notation. The natural style
states the same ordered cases in controlled language. Both use the configured operand names,
brackets, digits, and spelling of undefined values. Registered atoms use their registered rule.
For a recursive operator, the description also states the control expression, a proved decreasing
measure when one is found, and the proved bound on nested calls when available.

The chain follows applications in the parsed definitions. To shorten a large chain explicitly,
use `--chain-limit N`; the output states how many dependencies were omitted.

--8<-- "docs/snippets/describe_chain.md"

## Narration styles

The stored solution uses the full style, which shows each expression before and after a rewrite.
The Python API also offers `terse` and `explained` in English and Chinese. The terse style names
the part that changed. The explained style substitutes the input values into each tested condition
and shows the arithmetic that decided the case.

--8<-- "docs/snippets/narrate_terse.md"

--8<-- "docs/snippets/narrate_explained.md"

`narrate(trace, renderer, "en", "explained", registry=registry)` renders the explained style.
For a trace made with a custom arithmetic bound, pass the same `semantics` object to `narrate`.
Pass `collapse="atoms"` to combine consecutive atom evaluations into one sentence. Pass
`collapse="known"` to combine consecutive evaluations of operators treated as known at the
chosen granularity. The reverse narrator describes the missing input in reader terms.

--8<-- "docs/snippets/narrate_collapsed.md"

See [Views of a definition](views.md) for the other representations.
