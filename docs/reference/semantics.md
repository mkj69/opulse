# Semantics

This page is the specification of Opulse. The reference interpreter
(`opulse.definition.interpreter`) implements it rule by rule; the generated Python and Cython
code, the z3 encoding, the SMT-LIB export and the expression evaluator must agree with the
reference interpreter value by value. Section 9 lists the checks. Where the code and this page
disagree, the code is wrong.

## 1. Values

Every value belongs to **V = ℤ ∪ {⊥}**.

* ℤ are integers of any size (Python `int`).
* ⊥ ("undefined", written `NaN`) is the result of division by zero, remainder by zero,
  a result outside the bound, a definition in which no branch matches, or a bounded search
  that finds no matching index.
* ⊥ is not the floating-point NaN. The implementation uses the singleton
  `opulse.core.semantics.NAN`, written as the setting `symbols.nan` (default `NaN`).

## 2. Numeric modes

Selected by `semantics.mode`; one dataset uses one mode.

| Mode | Result outside the bound | Zero divisor | Use |
| --- | --- | --- | --- |
| `exact` (default) | ⊥ when \|x\| > B | ⊥ | new data |
| `legacy` | folded: x mod B for x > B, −(\|x\| mod B) for x < −B | treated as 1 | reproduce old datasets |
| `modular` | every integer atom result becomes x mod n in the range 0 through n minus 1 | undefined | clock world |

The bound B is `semantics.bound`, default 2³¹ − 1. In `exact` mode `bound: null` means no bound.
The bound applies to the **result of each base operation**; intermediate values are exact integers.
In modular mode, `semantics.modulus` is an integer of at least two. The integer bound does not apply in this mode. A result is reduced after each integer atom, including an atom inside a generated definition. Division by zero and a missing branch remain undefined. The default clock preset sets the modulus to 12.

## 3. Atomic operations

Atomic operations (*atoms*, also called base operations) are the only operations computed
directly; every other operator is a composition of atoms and unfolds to them.

**The atoms below are examples.** Opulse ships them as two ready-made
starting sets, but any function from integers to an integer can be registered as an atom, under
any symbol and with its own rule text ([Custom atoms](../guide/atoms.md)). A registered atom obeys
the same rules as the built-in ones (the rules at the end of this section). An atom may take any
number of arguments (section 4.0). In the same way, the symbols of generated operators, the
parameter names `a`, `b`, `c`, …, the brackets, the argument separator, the spelling of NaN and
the digits are configuration ([Notation](../guide/notation.md)); only the condition
keywords `if`, `else`, `and`, `or`, `not` and the integer value domain are fixed in this release.

The built-in atoms (sgn(x) is the sign of x, sgn(0) = 0; trunc rounds toward zero):

| Symbol | Arity / position | Name | Definition (`exact`) |
| --- | --- | --- | --- |
| `+` | binary | add | a + b |
| `-` | binary | subtract | a − b |
| `*` | binary | multiply | a × b |
| `/` | binary | truncating division | ⊥ if b = 0, else trunc(a / b) |
| `%` | binary | truncating remainder | ⊥ if b = 0, else a − b × trunc(a / b) (sign of a, or 0) |
| `-` | unary prefix | negate | −a |
| `@` | unary postfix | reverse digits | decimal digits of \|a\| reversed (leading zeros dropped: 120 → 21), times sgn(a) |
| `#` | unary prefix | triangle number | sgn(a) × \|a\|(\|a\| + 1) / 2 |
| `$` | unary postfix | popcount | number of 1 bits of \|a\| (non-negative) |
| `&` | unary prefix | digit sum | sgn(a) × (sum of the decimal digits of \|a\|) |
| `⁺` | unary postfix | successor | a + 1 |
| `⁻` | unary postfix | predecessor | a − 1 |
| `«` | unary postfix | double (shift left) | 2a |
| `»` | unary postfix | halve (shift right) | trunc(a / 2) |
| `°` | unary postfix | lowest bit | \|a\| mod 2 (0 or 1) |
| `defined` | unary prefix | definedness | 1 for an integer argument, 0 for ⊥ |

The `defined` atom is available with `operators.definedness: true` or the `opulse operators --enable-definedness` flag. It returns 0 for ⊥, so the propagation rule below applies to every other atom.

The starting operator set decides which atoms are available. Opulse constructs two sets in memory:

* `integer`, the default: `+ - * / %`, negation, `@ # $ &`;
* `atomic`, selected with `opulse operators --set atomic`: negation and `⁺ ⁻ « » °`.

`opulse atoms export --set integer --out atoms.jsonl` writes the integer set to a file.

Any other set is a file written by `opulse.core.primitives.write_initial_set` from built-in and
registered atoms.

Rules (for every atom, built-in or registered):

1. **⊥ propagates**: an atom other than `defined` with a ⊥ argument gives ⊥.
2. **Bound**: every result is checked as in section 2 (a registered atom must return an integer,
   or ⊥).
3. **Base independent**: `@` and `&` are always decimal and `$` always binary, whatever base a
   number is written in.
4. In `legacy` mode `@`, `#`, `&` first reduce \|a\| modulo B, and `/`, `%` treat a zero divisor as 1.

## 4. Definitions

### 4.0 Arity and notation

An operator takes k ≥ 1 arguments (its *arity*, `n_ary`). How an application is written depends
only on k:

| Arity | Form | Example definition | Example use |
| --- | --- | --- | --- |
| 1, prefix | `S x` | `⊖ a = { a * 2 }` | `⊖ 5` |
| 1, postfix | `x S` | `a ⊖ = { a * 2 }` | `5 ⊖` |
| 2 | `x S y` | `a ⊕ b = { (a + b) * 2 }` | `3 ⊕ 4` |
| k ≥ 3 | `S(x₁, …, x_k)` (call form) | `⊕(a, b, c) = { (a + b) * c }` | `⊕(3, x, 5)` |

The parameters are the first k names of `symbols.operand_names` (default `a b c d e f g h`; the
first two are also `symbols.left_operand` and `symbols.right_operand`), so the number of names is
the largest arity. The brackets of the call form are `symbols.left_paren` / `right_paren`, and
`symbols.argument_separator` (default `,`) separates the arguments. A left-hand side names k
distinct parameters. Evaluation does not depend on the arity: the arguments are evaluated left to
right (rule 4 below) and bound to the parameters in order. Arity 1 and 2 are written exactly as in
earlier releases.

A definition has the form `lhs = { branch; branch; … }`. A branch is `expression, if condition`,
`expression, else`, or a bare `expression`. Evaluating f(x):

1. Branches are tried in order. A conditional branch evaluates its condition and, if true,
   returns its expression. `else` and bare branches return unconditionally.
2. **Conditions**: `and`, `or` short-circuit from left to right; `not` negates. A comparison
   evaluates its left side, then its right side. **If either side of an evaluated comparison is ⊥,
   f(x) is ⊥** and no further branch is tried.
3. **No branch matches**: f(x) = ⊥. Values outside the regions a definition covers are undefined.
4. **Strict evaluation**: all arguments are evaluated, left to right, before an operator applies.

### 4.1 Recursion

Recursive operators follow one of four templates. `v` is the recursion variable, `g` the operator
called with the recursive result `R`.

**Template A, bounded remainder** (`recursion.style: bounded_mod`, default)

```opulse
f(…v…) = { base,                      if v % m == 0;
           g(… R = f(…(v % m) - 1…) …), if v % m > 0;
           g(… R = f(…(v % m) + 1…) …), if v % m < 0 }
```

`%` keeps the sign of the dividend, so v > 0 takes the second branch and v < 0 the third; both are
reachable. If v % m ∈ (0, m), the next value v′ = (v % m) − 1 ∈ [0, m − 2] and v′ % m = v′, which
decreases strictly to 0; the negative side is symmetric. At most m − 1 unfoldings.

**Template B, direct** (`recursion.style: direct`)

```opulse
f(…v…) = { base,                   if v == 0;
           g(… R = f(…v - 1…) …), if v > 0 and v <= T;
           g(… R = f(…v + 1…) …), if v < 0 and v >= - T }
```

The direction follows the sign of v; the size is limited by T (`recursion.direct_bound`). For
\|v\| > T no branch matches and the result is ⊥. At most T unfoldings.

**Template C, atomic** (`recursion.style: peano`): template B written with the atoms `v ⁻` and
`v ⁺`, which have the same values as `v - 1` and `v + 1`.

**Template D, primitive recursion** (`recursion.style: primitive`). Templates A, B and C call one
operator g whose argument slots hold the recursive result or a parameter, so a step never sees
the counter. Template D is the primitive-recursion schema h(x̄, 0) = base(x̄),
h(x̄, n + 1) = g(x̄, n, h(x̄, n)), bounded like template B. The counter n is the **last**
parameter, x̄ the others:

```
h(x̄, n) = { base(x̄),                       if n == 0;
            g(x̄, n - 1, h(x̄, n - 1)),      if n > 0 and n <= T;
            g(x̄, n + 1, h(x̄, n + 1)),      if n < 0 and n >= - T }
```

* `base(x̄)` is an expression over the other parameters built from lower layers (a constant when
  there are none).
* The step `g(…)` is a lower-layer operator or a composed expression of lower-layer operators
  that reads the stepped counter (`n - 1`, or `n + 1` on the negative side) **and** the previous
  result; the other parameters may fill further argument slots. A unary g reads both through a
  binary lower-layer operator, as in `g((n - 1) ⊙ h(x̄, n - 1))`.
* Termination and range are those of template B: the counter walks toward 0, at most T
  (`recursion.direct_bound`) unfoldings, and for \|n\| > T no branch matches and the result is ⊥.
  Negative counters are handled as in template B: the third branch walks n up to 0.
* The definition is ordinary syntax: the interpreter, compiled code, z3 encoding (the same case
  split per control value as template B), traces and prompts treat it like any definition.
  Every parameter other than n must be read by the base case or the step, not only passed along.
* The counter steps with `- +`, or with the atoms `⁻ ⁺` when the starting set has no binary
  `- +`.

Example (multiplication from addition, T = 8):
`a ⊠ b = { 0, if b == 0; (a ⊠ (b - 1)) + a, if b > 0 and b <= 8; (a ⊠ (b + 1)) - a, if b < 0 and b >= - 8 }`;
the sum 1 + … + n reads the counter in its step:
`a ∑ = { 0, if a == 0; ((a - 1) ∑) + ((a - 1) + 1), if a > 0 and a <= 8; … }`.

The generator checks before it starts that the starting set has the base operations its template
is written with (A: `% - +`, B: `- +`, C: `⁻ ⁺`, D: `- +` or `⁻ ⁺`).

### 4.2 Bounded search

The expression `search(i, T, condition)` returns the least integer `i` from 0 through `T`
whose condition is true. The index `i` is local to the search expression. `T` is a literal
integer at least 0. If no index matches, the result is `NaN`. If a comparison evaluates an
undefined operand at a tried index, the result is immediately `NaN`. Conditions use the same
evaluation order and short circuit rules as definition branches. Every operation evaluated in a
tried condition contributes to the operation and call counts.
An expanded derivation evaluates the search in one step and lists every tried index in its
explanation. A depth limit can evaluate the whole containing operator in one step.

Example: `a ⊕ b = { search(i, 4, (i + a) == b) }` gives 2 for inputs `a = 2` and `b = 4`,
and gives `NaN` for `a = 2` and `b = 8`.

The generator creates this form only when `recursion.search_enabled` is true. It uses
`recursion.search_bound` for `T`, with a maximum of 32 for generated definitions. Search can
appear in a written definition regardless of that switch. The z3 and SMT encodings support
bounds through 32 and report larger bounds as inexpressible.

## 5. Counting

Every evaluation also produces two non-negative counts:

* **base operations** (`base_ops`, the value of `op_count_func`): base-operation applications that
  are actually executed, including those in evaluated conditions. Short-circuited parts are not
  counted; repeated subexpressions are counted each time; a base operation with a ⊥ argument still
  counts; a branch that returns a constant or a variable contributes 0.
* **calls** (`calls`): operator applications of any kind that are executed, not counting f itself.

Example: `a ⊕ b = { (a + b) * 2 }` has `base_ops` = 2 for every input;
`a ⊗ b = { a, if a > b; b, else }` always has `base_ops` = 0.

## 6. Expressions

An expression is a tree of numbers, variables and operator applications, evaluated strictly
(section 4, rule 4). Expression statistics:

* **expansion**: the sum of `base_ops` of all applications plus the number of base operations that
  appear directly in the expression;
* **operation count**: the number of applications in the tree.

## 7. Numerals

* Values are integers; a base only changes how a number is written.
* A number in base k is an optional base marker (a registered prefix symbol with `is_base == k`)
  followed by base-k digits from `numerals.digits`.
* Literals in expressions and definitions are non-negative; negative numbers use unary `-`.
* ⊥ is written `symbols.nan`.

## 8. Writing and parsing

* In legacy naming mode, all registered operator symbols form a **uniquely decodable** set
  (Sardinas and Patterson test): a run of operator characters splits into symbols in at most one
  way. The generator checks this before it adds a symbol. Shape and index names are separated from
  operands by spaces or brackets. The tokenizer reads a complete indexed name before it reads
  numeral characters.
* Unary operators bind tighter than binary ones; postfix binds tighter than prefix:
  `- a @` is `- (a @)`. Unary operators chain: `- - a`, `& - 1`, `a @ $`.
* An application with three or more arguments is written in call form `S(x, y, z)` (section 4.0).
  It delimits itself, so it is an operand like a number and is never bracketed:
  `- ⊕(1, 2, 3) @` is `- (⊕(1, 2, 3) @)`, and `⊕(1 + 2, 3, 4) * 5` needs no brackets. Each argument
  is a full expression. A symbol that is both a prefix operator and a call-form operator is read
  as a call when the bracket holds three or more separated arguments, else as the prefix operator.
  Call-form operators have no `priority`.
* In definitions every binary application is bracketed. In expressions binary operators follow
  their `priority` (higher binds tighter) and `associativity_direction`; the renderer omits only
  brackets the parser does not need.
* Brackets, the argument separator, the definition sign, parameter names and the spelling of ⊥
  come from the `symbols` settings, for both the parser and the renderers.

## 9. Obligations

Each item has automated checks; any failure is an engine bug.

1. **Base operations**: `opulse.core.semantics` matches section 3, including 0, negative operands,
   zero divisors and both edges of the bound.
2. **Definitions**: for every generated operator, the reference interpreter and the compiled Python
   and Cython functions agree on value and both counts on boundary and random inputs. For three or
   more arguments the boundary values are combined at random (the full grid is too large).
3. **z3**: the encoding covers every base operation (digit operations and atoms exactly within the
   bound; `/` and `%` truncate, unlike z3's Euclidean operators) and splits recursion on its control
   value. It agrees with the reference interpreter on boundary and ⊥ inputs; every z3
   counterexample is re-checked by the reference interpreter; the SMT-LIB export (`z3` field) is
   re-checked by an independent SMT-LIB evaluator on boundary and ⊥ inputs.
4. **Static properties**: a generated definition is rejected if z3 proves a branch unreachable, or
   reachable but always ⊥. If z3 cannot decide in time the definition is accepted and
   `opulse analyze` records the branch as `unknown`. Section 4.1 guarantees termination.
5. **Expressions**: the evaluator's result equals the reference interpreter's result for the
   expression.
6. **Step-by-step solutions**: every step of a trace is re-evaluated by the reference interpreter.
7. **Verify on write**: every dataset record is recomputed, value and counts, by an evaluator
   independent of the generation path before it is written; a mismatch stops the run.
8. **Round trip**: rendering then parsing gives the same tree, for definitions and expressions,
   under custom notations.
9. **Solving**: every solution of a fill-in-the-blank problem is checked by the reference
   interpreter; a solution set marked `complete` misses no solution in its recorded domain (z3
   proves unsatisfiability, or the domain is searched exhaustively); every candidate of a reverse
   step is checked forward.
