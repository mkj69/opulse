# Operators and definitions

<div class="op-lead" markdown>
To read, evaluate or write an operator, you need its exact value on every input, including division by zero and overflow.
</div>

An operator has a symbol, an arity (unary prefix, unary postfix, or binary) and, unless it is a
base operation, a **definition**. Opulse compiles the definition to Python (or Cython) and checks
the compiled code against a reference interpreter that reads the definition itself.

## Three kinds of definitions

| Kind | Shape |
| --- | --- |
| simple | one expression over the parameters |
| branch | conditions tried in order, the first that holds gives the result |
| recursive | one of three [templates](../reference/semantics.md#41-recursion) that call the operator itself on a smaller value |

Two of each kind, taken from a generated operator set:

--8<-- "docs/snippets/operators.md"

## Values: integers and NaN

Every value is an integer or `NaN` (undefined). `NaN` comes from exactly four situations:

* division by zero, `7 / 0`;
* remainder by zero, `7 % 0`;
* a base-operation result larger than the bound B = 2³¹ − 1 in absolute value;
* a definition in which no branch matches (a branch definition without `else`).

`NaN` propagates through base operations. If one side of an evaluated comparison in a condition is
`NaN`, the whole call is `NaN`. Division and remainder truncate toward zero: `-7 / 2 = -3`,
`-7 % 2 = -1`.

## Watching a recursion unfold

One of the recursive operators above, applied to small inputs. The first condition that holds
selects a branch; the recursive call receives a smaller control value, until the base case ends
the recursion. Yellow marks the part rewritten in each step, green the result.

<div class="opulse-anim" data-kind="trace">
<script type="application/json">
--8<-- "docs/snippets/anim_recursion.json"
</script>
--8<-- "docs/snippets/anim_recursion_static.html"
</div>
<p class="op-hint">Press play, or use the arrows and slider to follow recursion.</p>

Every recursion template unfolds a bounded number of times (at most m − 1 for `v % m`), so every
operator terminates on every input.

## Counting work

Each evaluation also returns `base_ops`, the number of base operations actually executed.
Short-circuited conditions are not counted; a branch that returns a constant or a variable counts
0. The reference interpreter and the compiled code agree on this count too:

--8<-- "docs/snippets/evaluate.md"

## The operator record

Operators are stored one per JSON line:

--8<-- "docs/snippets/operator_record.md"

`op_compute_func` and `op_count_func` hold the compiled source; `dependencies` lists the operators
the definition calls. `opulse analyze` and `opulse describe` add solver and language fields
([SMT-LIB export](smt.md), [descriptions](step-by-step.md#operator-descriptions)).

## Using operators from Python

```python
from opulse.core import OperatorRegistry
from opulse.verify import Oracle

registry = OperatorRegistry.from_jsonl("outputs/operators.jsonl")
oracle = Oracle(registry)                       # the reference interpreter
op = next(op for op in registry if op.definition_type == "recursive_definition")
result = oracle.evaluate(op, (7, 7))
print(result.value, result.base_ops, result.calls)
```
