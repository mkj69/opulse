# SMT-LIB export

<div class="op-lead" markdown>
To ask a solver your own questions about an operator, the solver needs the operator in its own language, with Opulse's truncating division and bound.
</div>

`opulse analyze` writes each operator as SMT-LIB functions (the `z3` field), so z3 or any other SMT
solver can reason about it directly.

```bash
opulse operators --out outputs/operators.jsonl --layers 2 1 --seed 1
opulse analyze --operators outputs/operators.jsonl --out outputs/operators.analyzed.jsonl
```

An operator `f` becomes two functions over (definedness, value) pairs: `f_d` says whether the result
is defined, `f_v` gives the value where it is. Operands carry definedness because a definition may
ignore an undefined operand. The recursive operator from the [quickstart](../getting-started/quickstart.md):

--8<-- "docs/snippets/smt.md"

* Calls to other operators are by name, so each export is about as long as its definition.
* Base operations come from a shared prelude (`<out>.prelude.smt2`) in which truncating division
  and the bound are written out. SMT-LIB `div` and `mod` are Euclidean; using them directly would be
  wrong for negative operands.
* Every operator is declared with `define-funs-rec`, recursive or not, because z3 expands `define-fun`
  as a macro and would inline whole dependency chains.

## Checked before it is written

`opulse.solver.smt.module` assembles a self-contained script (prelude, dependencies, the operator).
Before an export is written, z3 parses it and an independent SMT-LIB evaluator compares it with the
reference interpreter on boundary inputs and NaN inputs.

## Solving with the export

```lisp
; <module text>
(declare-const x Int)
(assert (op_<id>_d true x))
(assert (= (op_<id>_v true x) 42))
(check-sat)
(get-model)
```
