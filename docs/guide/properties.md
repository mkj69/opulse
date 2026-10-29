# Laws and equivalence

<div class="op-lead" markdown>
Ordinary algebra fails at the edges of a bounded integer semantics, so a law has to be decided under that semantics, NaN and the bound included.
</div>

## Algebraic properties

`opulse analyze` decides, for every operator, the laws that apply to its arity:

* binary: commutative, associative, idempotent, left/right identity, left/right absorbing element;
* unary: involution, idempotent, odd, even.
* three or more arguments: symmetry under every argument permutation and idempotence when all
  arguments equal the input.

Equality is equality of values including NaN. Each law gets one verdict:

| Verdict | Meaning |
| --- | --- |
| `proved` | z3 shows that no counterexample exists in [−B, B] |
| `refuted` | a counterexample, re-checked by the reference interpreter |
| `bounded` | z3 could not decide in time; no counterexample in the recorded small range |

--8<-- "docs/snippets/properties.md"

`+` is not associative here: `(1 + (-1)) + (-B) = -B`, but `1 + ((-1) + (-B))` overflows to NaN.
Without a bound it is proved associative.

## Dead branches

The same encoding decides whether each branch of a definition can be reached, and whether its
body can be defined there. Generation rejects `dead` and `undefined` branches; `analyze` records the
verdicts:

--8<-- "docs/snippets/reachability.md"

## Equivalence

`opulse equivalences` produces labelled pairs:

* **operators**: two operators with different definitions and the same values everywhere;
* **simplification**: an arithmetic expression and the expanded form proposed by SymPy;
* **commuted**: an expression and the same expression with one binary application's operands swapped.

SymPy only proposes; whether the two sides agree is decided under Opulse semantics:

--8<-- "docs/snippets/equivalence.md"

With the bound, ordinary algebra fails at the edges, and the counterexample shows where.

```bash
opulse operators --out outputs/operators.jsonl --layers 2 1 --seed 1
opulse equivalences --operators outputs/operators.jsonl --out outputs/equivalences.jsonl --count 200
```

## Checking atoms without z3 encodings

The optional `solver.fallback_range: [0, 20]` setting checks every input tuple in that range
with the reference interpreter when z3 cannot encode an operator. This example covers all integers
from 0 through 20 in each argument. The `analyze` and `equivalences` commands also accept
`--fallback-range LO HI`. A law or equivalence with no counterexample has status `checked`, a
`range` field, and strength `checked on range [lo, hi]`. A counterexample has status `refuted`
and the same range label. Only z3 can return `proved`.
