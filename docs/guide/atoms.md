# Atoms: choose your own

<div class="op-lead" markdown>
This page explains how to choose and register the atomic operations used to build operator sets,
datasets and benchmarks.
</div>

Every operator Opulse grows is a composition of **atoms**: operations computed directly and never
unfolded. The atoms in the [specification](../reference/semantics.md#3-atomic-operations), including
`+`, `⁺` and `@`, are the ones Opulse ships. Everything downstream (generation, the
reference interpreter, compiled code, expressions, step-by-step solutions, fill-in-the-blank
problems, the benchmark and its prompt check) treats an atom as *a function with a symbol and a
rule*, so you can replace them.

## Two shipped starting sets

| Set | Source | Atoms |
| --- | --- | --- |
| integer | built in, default | `+ - * / %`, negation, `@` (reverse digits), `#` (triangle), `$` (popcount), `&` (digit sum) |
| atomic | built in, select with `--set atomic` | negation, `⁺` successor, `⁻` predecessor, `«` double, `»` halve, `°` lowest bit |

Starting from the atomic set, even addition has to be invented layer by layer; recursion steps
with the atoms themselves (`recursion.style: peano`):

```bash
opulse operators --config configs/atomic.yaml --set atomic \
                 --out outputs/atomic_operators.jsonl --layers 20 15 10
```

This command grows operators from the atomic set with the recursion settings in `configs/atomic.yaml`.

```bash
opulse atoms export --set integer --out outputs/integer_atoms.jsonl
opulse atoms export --set atomic --out outputs/atomic_atoms.jsonl
```

These commands write the built in starting sets as JSONL files for use with `--initial PATH`.

--8<-- "docs/snippets/atoms.md"

## Register your own atoms

An atom is a Python function on integers, a symbol, a shape (unary prefix, unary postfix, binary,
or three or more arguments) and one sentence that says how to compute it. Put the registrations in a module:

```bash
# run
cat > my_atoms.py <<'PY'
import z3
from opulse.core.primitives import register_primitive

register_primitive("cube", "⊛", lambda a: a ** 3, rule="a ⊛ is a * a * a.")
register_primitive("maxab", "⩔", lambda a, b: max(a, b), n_ary=2, position=None,
                   rule="a ⩔ b is the larger of a and b.",
                   z3=lambda a, b: z3.If(a > b, a, b))       # optional: enables the solvers
register_primitive("mod3", "ᵗ", lambda a: abs(a) % 3, rule="a ᵗ is |a| % 3 (0, 1 or 2).")
PY
```

Choose a starting set from any atoms, built-in or registered, and grow operators from it. Load the
module with `--plugin` (or the `OPULSE_PLUGINS` environment variable) on every command:

```bash
# run
python - <<'PY'
from opulse.core.primitives import write_initial_set
import my_atoms  # noqa: F401  (registers the atoms)

write_initial_set("my_start.jsonl", ["succ", "pred", "neg", "add", "sub", "mod", "cube", "maxab", "mod3"])
PY
```

```bash
opulse --plugin my_atoms.py operators   --initial my_start.jsonl --out ops.jsonl --layers 20 10 5
opulse --plugin my_atoms.py expressions --operators ops.jsonl --out expr.jsonl --count 1000 --cot en
opulse --plugin my_atoms.py verify      --operators ops.jsonl --expressions expr.jsonl
opulse --plugin my_atoms.py bench build --operators ops.jsonl --out tasks.jsonl --count 300
opulse --plugin my_atoms.py bench check --tasks tasks.jsonl --operators ops.jsonl
```

Generated operators then compose your atoms, for example `◆₁ a = { a ⩔ (a ⊛) }`, and benchmark
prompts state your rule sentences: `a ⊛ is a * a * a.`

### Atoms with three or more arguments

Pass `n_ary=3` (or more). Such an atom is written in call form, `⩙(a, b, c)`, everywhere; its
`position` is ignored and it has no priority:

```python title="my_atoms.py"
register_primitive("mid", "⩙", lambda a, b, c: sorted((a, b, c))[1], n_ary=3,
                   rule="⩙(a, b, c) is the middle value of a, b and c.",
                   z3=lambda a, b, c: z3.If(z3.Or(z3.And(a <= b, b <= c), z3.And(c <= b, b <= a)), b,
                                            z3.If(z3.Or(z3.And(b <= a, a <= c), z3.And(c <= a, a <= b)), a, c)))
```

`write_initial_set` writes a valid record for it (`"n_ary": 3`, `"unary_position": null`,
`"priority": null`). Generation, the interpreter, compiled code, z3 and SMT-LIB export, traces,
step grading, the benchmark and `bench check` all read the call form. Operators that
use it look like `a ◆₂ b = { ⩙(a, b, a + b) }`. Prompts that contain a call-form operator add
one sentence explaining the notation. To also *grow* operators with three arguments, set
`operators.arity_weights` ([Generating operators](generation.md#arity)).

### Rules every atom follows

Set `operators.definedness: true` or pass `opulse operators --enable-definedness` to include `defined a`, which returns 1 for an integer and 0 for NaN.

* Except for `defined`, a NaN argument gives NaN; a registered atom's function only sees integers.
* The result must be an integer (or `None` for "undefined"); it is checked against the bound
  like every built-in result.
* The symbol must not contain spaces, digits (including Unicode digits such as `³`) or
  `( ) { } ; , =`, and must not already denote an atom of the same shape (symbol and arity; a
  symbol may be a prefix atom and a call-form atom at once).
* Without a `z3` encoding, operators that use the atom are skipped by the solver-based analyses
  (fill-in-the-blank uniqueness proofs, laws, SMT-LIB export). Generation checks that sample
  values, the interpreter, datasets and step-by-step grading still work.

## Everything else is configuration too

| What | Where |
| --- | --- |
| Names of generated operators | `operators.naming`, `shape_sets`, `shape_chars`, `index_chars` ([Operator names](naming.md)) |
| Parameter names, brackets, argument separator, `=`, the NaN spelling | `symbols` section of the configuration |
| Arity of generated operators | `operators.arity_weights` |
| Digits and numeral bases | `numerals`, `expressions.numeral_base` |
| Operator names in benchmark prompts | `bench build --naming symbols / pseudo / english` |
| Numeric mode and bound | `semantics.mode`, `semantics.bound` |
| How recursion steps | `recursion.style` (`bounded_mod`, `direct`, `peano`, `primitive`) |

The condition keywords (`if`, `else`, `and`, `or`, `not`) and the integer value domain are fixed
in this release.
