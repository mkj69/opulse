# Solving for unknowns

<div class="op-lead" markdown>
Forward computation tests one direction of reasoning; these problems ask for the input that gives a known result, with every solution found and checked.
</div>

`opulse holes` turns expressions into fill-in-the-blank problems: one number is replaced by `x`,
and the task is to find every `x` that gives the original value.

```bash
opulse operators --out outputs/operators.jsonl --layers 2 1 --seed 1
opulse holes --operators outputs/operators.jsonl --out outputs/holes.jsonl --count 1000 --unique-only
```

## Watching the reverse derivation

The solver peels operators from the outside. At each operator the other arguments are known, so the
value the unknown argument must take is a smaller problem. Every candidate is checked forward.

<div class="opulse-anim" data-kind="holes">
<script type="application/json">
--8<-- "docs/snippets/anim_holes.json"
</script>
--8<-- "docs/snippets/anim_holes_static.html"
</div>
<p class="op-hint">Press play, or use the arrows and slider to follow the solution.</p>

## Is the answer unique?

z3 encodes the expression exactly, recursive operators included (their recursion is bounded by
construction), and enumerates solutions over the whole value range [−B, B]. When z3 reports that
no further solution exists, the set is **complete**; with exactly one element it is **unique**.

--8<-- "docs/snippets/holes_unique.md"

A problem with two solutions, both listed:

--8<-- "docs/snippets/holes_multi.md"

If z3 cannot decide within its resource allowance, the solver exhaustively searches the
configured finite domain and records it. A safety timeout raises an error. Every claim in a
record refers to the domain it states.

| Field | Meaning |
| --- | --- |
| `solutions` | every solution found, each checked by the reference interpreter |
| `complete` | no other solution exists in `domain` |
| `unique` | `complete` and exactly one solution |
| `method` | `z3` (domain [−B, B]) or `exhaustive` (domain [−N, N]) |
| `reverse` | the outside-in steps with their candidate sets |

## The reverse steps as text

--8<-- "docs/snippets/holes_reverse.md"

## From Python

```python
from opulse.solver.holes import HoleSolver
from opulse.solver.z3_encode import Z3Encoder
from opulse.verify import Oracle

oracle = Oracle(registry)
solver = HoleSolver(Z3Encoder(oracle), oracle)
problem = solver.problem(tree, path)          # path of the number to blank out
print(problem.solutions.values, problem.solutions.unique)
```

## Reference range checks

Set `solver.fallback_range: [0, 20]` in a YAML configuration to enable reference interpreter
checks when an atom has no z3 encoding. This example checks each integer input from 0 through 20.
The `holes`, `equivalences`, and `analyze` commands also accept `--fallback-range LO HI`, which
overrides the configuration. A fallback record says `checked on range [lo, hi]`; a complete hole
solution set is complete only within that range. A z3 proof says `proved`. A range check never
sets equivalence to true. For an operator without a z3 encoding, `analyze` records
`z3_status: unavailable: no z3 encoding` and leaves its SMT text empty.
