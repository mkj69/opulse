# Configuration reference

Generated from `opulse.config` by `tools/docs_reference.py`. A configuration is one YAML file;
every key is optional and omitted keys take the defaults below.

```yaml
# Opulse generation settings. Every key is optional; omitted keys use the
# defaults in src/opulse/config.py.

semantics:
  mode: exact              # exact: overflow and division by zero give NaN; legacy: reproduce old data
  bound: 2147483647        # largest absolute value; every command (equivalences included) uses it

symbols:
  left_operand: a
  right_operand: b
  left_paren: "("
  right_paren: ")"
  equals: "="
  nan: NaN
  inf: Inf
  neg_inf: -Inf

numerals:
  max_base: 16
  digits: "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

operators:
  naming: shape_index       # shape_index or legacy
  shape_sets: [shapes, suits]
  shape_chars: ""            # additional shape glyphs
  index_chars: "₀₁₂₃₄₅₆₇₈₉"  # ordered index alphabet
  definition_layout: compact # compact or piecewise
  piecewise_min_length: 120
  symbol_min_len: 1
  symbol_max_len: 3
  symbol_sets: [math, arrows, shapes]   # legacy mode named sets
  symbol_chars: ""             # more legacy characters, listed directly
  symbol_blocks: []            # legacy mode raw Unicode ranges
  symbol_ascii: ""             # extra ASCII characters in legacy mode
  exclude_confusable: true     # filter lookalikes in legacy mode
  max_if_branches: 10
  condition_min: 0         # branch thresholds are non-negative; prefix "-" supplies negatives
  condition_max: 100

recursion:
  modulus_min: 3           # recursive operators unfold at most modulus-1 times
  modulus_max: 9
  constant_min: -100
  constant_max: 100

expressions:
  variables: [a, b]
  value_min: 0
  value_max: 100
  max_depth: 3
  type_weights: {binary: 0.7, unary_prefix: 0.2, unary_postfix: 0.1, atom: 0.1}
  atom_weights: {variable: 0.8, number: 0.2}
  numeral_base: 10
  random_numeral_base: false
  result_base: 10
  random_result_base: false
  cot_base: 10
```

## `preset`

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `preset` | `str \| None` | `None` | Selects a named world and its generation defaults, including the numeric, typed, and action presets. |

## `semantics`

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `mode` | `str` | `'exact'` | `exact`: overflow and division by zero give NaN. `legacy`: reproduce old datasets (symmetric folding, zero divisor treated as 1). `modular`: reduce integer results modulo `semantics.modulus`. |
| `bound` | `int \| None` | `2147483647` | Largest absolute value B of a base-operation result. `null`: no bound (exact mode only). |
| `max_string_length` | `int` | `256` | Largest number of characters a registered string atom can return before its result becomes NaN. |
| `max_list_length` | `int` | `256` | Largest number of elements a registered list atom can return before its result becomes NaN. |
| `modulus` | `int \| None` | `None` | Integer modulus of at least 2 in modular mode. `null` in other modes. |

## `symbols`

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `left_operand` | `str` | `'a'` | Name of the first parameter in definitions. |
| `right_operand` | `str` | `'b'` | Name of the second parameter in definitions. |
| `left_paren` | `str` | `'('` | Opening bracket. |
| `right_paren` | `str` | `')'` | Closing bracket. |
| `equals` | `str` | `'='` | Sign between the left-hand side and the body of a definition. |
| `nan` | `str` | `'NaN'` | Spelling of the undefined value. |
| `inf` | `str` | `'Inf'` | Spelling of positive infinity (legacy data only). |
| `neg_inf` | `str` | `'-Inf'` | Spelling of negative infinity (legacy data only). |
| `operand_names` | `tuple[str, ...]` | `[]` | All parameter names, in order; their number is the largest arity. Empty: `left_operand`, `right_operand`, then `c d e f g h`. When set, its first two names are the left and right operands. |
| `argument_separator` | `str` | `','` | Separates the arguments of an operator with three or more arguments, written in call form `⊕(a, b, c)`. |

## `numerals`

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `max_base` | `int` | `16` | Largest numeral base used for random bases. |
| `digits` | `str` | `'0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'` | Digit alphabet for numerals in bases above 10. |

## `operators`

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `naming` | `str` | `'shape_index'` | Generated name style. `shape_index` joins a shape and an index; `legacy` uses random symbol strings. |
| `shape_sets` | `tuple[str, ...]` | `['shapes', 'suits']` | Named shape sets used in `shape_index` mode: `shapes` and `suits`. |
| `shape_chars` | `str` | `''` | Additional shape glyphs used in `shape_index` mode. |
| `index_chars` | `str` | `'₀₁₂₃₄₅₆₇₈₉'` | Ordered index alphabet. A zero first alphabet with ten characters writes decimal indices. |
| `definition_layout` | `str` | `'compact'` | `compact` uses one line. `piecewise` puts each branch on a line when long. |
| `piecewise_min_length` | `int` | `120` | Minimum compact definition length for piecewise rendering. |
| `definedness` | `bool` | `False` | Adds the `defined` atom to the starting operator set so branch conditions can test whether a value is defined. |
| `symbol_min_len` | `int` | `1` | Shortest generated operator symbol in `legacy` mode. |
| `symbol_max_len` | `int` | `3` | Longest generated operator symbol in `legacy` mode. |
| `symbol_sets` | `tuple[str, ...]` | `['math', 'arrows', 'shapes']` | Named character sets for `legacy` symbols; see the table below. |
| `symbol_chars` | `str` | `''` | More characters for `legacy` symbols, listed directly, e.g. `"♪♫"`. |
| `symbol_blocks` | `tuple[str, ...]` | `[]` | Advanced `legacy` mode: raw Unicode ranges (`start-end`, hex), e.g. `2200-22FF`. Symbols and non-ASCII letters are accepted. |
| `symbol_ascii` | `str` | `''` | Extra ASCII characters allowed in `legacy` symbols. |
| `exclude_confusable` | `bool` | `True` | Drop legacy glyphs that look like ASCII arithmetic, comparisons or bars. |
| `arity_weights` | `dict[int, float]` | `{1: 0.5, 2: 0.5}` | Relative number of new operators per arity, e.g. `{1: 0.25, 2: 0.5, 3: 0.25}`; unary operators are prefix or postfix with equal chance, arity 3 and more is written in call form. The default draws exactly as before (no call-form operators). |
| `allow_simple` | `bool` | `True` | Permits generated definitions with one unconditional body. |
| `allow_branches` | `bool` | `True` | Permits generated definitions with conditional branches. |
| `max_substitution_depth` | `int \| None` | `None` | Limits the depth of sampled simple and branch bodies; `null` uses `expressions.max_depth`. |
| `max_arity` | `int \| None` | `None` | Limits generated operator arity; `null` retains every arity with a positive weight in `operators.arity_weights`. |
| `max_if_branches` | `int` | `10` | Most branches in a branch definition. |
| `max_condition_comparisons` | `int \| None` | `None` | Limits comparisons in each branch condition; `null` uses the default region sampler. |
| `condition_atoms` | `tuple[str, ...]` | `[]` | Names unary or binary starting atoms applied to parameters in branch conditions; an empty list uses the parameters directly. |
| `partial_probability` | `float` | `0.0` | Probability that a branch definition has no `else` (undefined outside its regions). |
| `reject_dead_branches` | `bool` | `True` | Reject definitions in which z3 proves a branch unreachable or always NaN. |
| `reject_degenerate` | `bool` | `True` | Reject subexpressions that use a parameter yet take one value wherever defined, such as `a - a` or `a % a` (proved with z3). |
| `min_defined_share` | `float` | `0.95` | Total definitions must be defined on at least this share of inputs from the expression value range (0 disables). |
| `undefined_branch_check` | `bool` | `True` | Also reject branches whose body z3 proves always NaN (costlier; consider turning it off for very large runs). |
| `dead_branch_budget` | `int` | `600` | Deterministic effort of that check (encoding nodes; z3 gets a proportional resource limit). Undecided branches are accepted. |
| `degenerate_budget` | `int` | `200` | Deterministic effort of the degenerate subexpression check (encoding nodes; z3 gets a proportional resource limit). Undecided suspects are accepted. |
| `safety_timeout_ms` | `int` | `30000` | Wall clock safety limit per solver check during generation. Reaching it stops the run with an error; it never decides a check. Raise it on slow machines. |
| `condition_min` | `int` | `0` | Smallest threshold in branch conditions. |
| `condition_max` | `int` | `100` | Largest threshold in branch conditions. |

### Named symbol sets

| Name | Characters |
| --- | --- |
| `circled` | ⊕ ⊗ ⊝ |
| `squared` | ⊞ ⊟ ⊠ |
| `logic` | ∧ ∨ ⊻ ⊼ ⊽ ¬ ∀ ∃ ∄ |
| `sets` | ∩ ∪ ⊂ ⊃ ∈ ∋ ∉ ⊎ ⊓ ⊔ |
| `calculus` | ∑ ∏ ∐ ∫ ∮ √ ∛ ∜ ∞ ∂ ∇ ∆ |
| `arrows` | ← → ↑ ↓ ↔ ↕ ↖ ↗ ↘ ↙ ⇐ ⇒ ⇑ ⇓ ⇔ ↦ ↩ ↪ ↺ ↻ ⇄ ⇆ |
| `shapes` | ■ □ ▲ △ ▼ ▽ ◆ ◇ ● ○ ★ ☆ |
| `suits` | ♠ ♣ ♥ ♦ ♤ ♧ ♡ ♢ |
| `greek` | Γ Δ Θ Λ Ξ Π Σ Φ Ψ Ω |
| `math` | ⊕ ⊗ ⊝ ⊞ ⊟ ⊠ ∧ ∨ ⊻ ⊼ ⊽ ¬ ∀ ∃ ∄ ∩ ∪ ⊂ ⊃ ∈ ∋ ∉ ⊎ ⊓ ⊔ ∑ ∏ ∐ ∫ ∮ √ ∛ ∜ ∞ ∂ ∇ ∆ |

## `recursion`

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `style` | `str` | `'bounded_mod'` | Selects the `bounded_mod`, `direct`, `peano`, `bits`, or `primitive` recursion template when `recursion.styles` is `null`. |
| `enabled` | `bool` | `True` | Permits recursive definitions and generated layers above zero. |
| `styles` | `tuple[str, ...] \| None` | `None` | Samples recursive definitions from these templates; `null` uses `recursion.style`. |
| `max_recursive_calls` | `int` | `2` | Sets the maximum number of recursive result slots in a binary callee to one or two. |
| `modulus_min` | `int` | `3` | Smallest modulus m of `bounded_mod` (unfolds at most m - 1 times). |
| `modulus_max` | `int` | `9` | Largest modulus m of `bounded_mod`. |
| `direct_bound` | `int` | `8` | Largest absolute control value allowed by `direct`, `peano`, `bits`, and `primitive` recursive definitions. |
| `search_enabled` | `bool` | `False` | Allows simple definitions to search for the first index equal to a sampled expression. |
| `search_bound` | `int` | `8` | Largest index examined by generated bounded searches, from zero through at most 32. |
| `constant_min` | `int` | `-100` | Smallest constant in the base case. |
| `constant_max` | `int` | `100` | Largest constant in the base case. |
| `step_down` | `str` | `'⁻'` | Symbol of the postfix predecessor atom used for decreasing `peano` recursion. |
| `step_up` | `str` | `'⁺'` | Symbol of the postfix successor atom used for increasing `peano` recursion. |
| `nonnegative` | `bool` | `False` | Omits the negative input branch from generated `bounded_mod`, `direct`, `peano`, and `bits` recursive definitions. |

## `expressions`

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `variables` | `tuple[str, ...]` | `['a', 'b']` | Variable names used in sampled expressions with variables. |
| `value_min` | `int` | `0` | Smallest sampled number. |
| `value_max` | `int` | `100` | Largest sampled number. |
| `max_depth` | `int` | `3` | Largest expression depth. |
| `type_weights` | `dict[str, float]` | `{'binary': 0.7, 'unary_prefix': 0.2, 'unary_postfix': 0.1, 'atom': 0.1}` | Relative weights of binary, prefix, postfix applications and atoms; an optional `call` weight for operators with three or more arguments (default: the `binary` weight). |
| `atom_weights` | `dict[str, float]` | `{'variable': 0.8, 'number': 0.2}` | Relative weights of variables and numbers among atoms. |
| `numeral_base` | `int` | `10` | Base of numerals in expressions. |
| `random_numeral_base` | `bool` | `False` | Draw a random base (2..max_base) for every numeral. |
| `result_base` | `int` | `10` | Base in which results are written. |
| `random_result_base` | `bool` | `False` | Draw a random base for every result. |
| `cot_base` | `int` | `10` | Base of numbers in evaluation steps. |

## `solver`

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `fallback_range` | `tuple[int, int] \| None` | `None` | Inclusive integer input range checked by the reference interpreter when a solver analysis cannot encode an operator. |
| `rlimit` | `int` | `5000000` | Deterministic z3 resource limit per solver question; a question it cannot decide within the limit is reported as unknown, the same way on every machine. |
| `max_nodes` | `int` | `300` | Largest formula, in encoding nodes, that the z3 encoder builds before giving up on a question. |

## `interest`

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `dedup` | `bool` | `False` | Reject a candidate whose value table on the probe grid equals an existing operator's, also after permuting arguments or negating arguments or the result. |
| `selection` | `str` | `'off'` | `off`, `best` or `sample`: draw `pool` accepted candidates per operator and keep the highest scoring one, or one drawn with weight exp(score / temperature). |
| `pool` | `int` | `4` | Accepted candidates drawn per operator when `selection` is on. |
| `temperature` | `float` | `0.1` | Temperature of `selection: sample`. |
| `weights` | `dict[str, float]` | `{'novelty': 1.0, 'regularity': 1.0, 'reuse': 1.0, 'non_degeneracy': 1.0, 'compression': 1.0}` | Weights of the score components `novelty`, `regularity`, `reuse`, `non_degeneracy` and `compression`; unnamed components keep weight 1. |
| `probe_ints` | `tuple[int, ...]` | `[0, 1, 2, 3, 5, 7, 10, 17, 31, 50, 64, 83, 100, -1, -2, -3, -5, -7, -10, -17, -31, -50, -64, -83, -100]` | Integer probe values, closed under negation; the probe grid is their product over the integer arguments. |
| `max_probe_points` | `int` | `729` | Largest probe grid; high arities use fewer, evenly spread values. |
| `regularity_range` | `int` | `12` | Monotonicity, periodicity and fixed points are read on [-R, R] (monotonicity also on the probe values). |
| `max_period` | `int` | `8` | Largest period looked for. |
| `solver_timeout_ms` | `int` | `1000` | z3 time limit per question when `opulse interest --solver` confirms regularities. |

## Expressiveness switches

These settings control numeric definitions written by `opulse operators`. A CLI flag with the same meaning overrides its YAML key for that run. The default values keep the existing generation behavior.

| Form | YAML key | CLI flag | Default | Effect |
| --- | --- | --- | --- | --- |
| Simple definitions | `operators.allow_simple` | `--no-simple` | `true` | Permit definitions with one unconditional body. |
| Substitution | `operators.max_substitution_depth` | `--max-substitution-depth` | `null` | Maximum depth of sampled simple or branch bodies. `null` uses `expressions.max_depth`. |
| Branch definitions | `operators.allow_branches` | `--no-branches` | `true` | Permit conditional definitions. |
| Branch count | `operators.max_if_branches` | `--max-if-branches` | `10` | Maximum bodies in one branch definition. |
| Condition complexity | `operators.max_condition_comparisons` | `--max-condition-comparisons` | `null` | Maximum comparisons in each condition of a branch definition. `null` keeps the original region sampling. |
| Condition thresholds | `operators.condition_min`, `operators.condition_max` | config only | `0`, `100` | Inclusive range of thresholds in branch conditions. |
| Condition atoms | `operators.condition_atoms` | `--condition-atoms` | `[]` | Atom names allowed in branch conditions. An empty list uses raw parameters. Each named atom must be in the starting set. Binary atoms receive the parameter and the constant 2. |
| Arity | `operators.max_arity` | `--max-arity` | `null` | Largest arity of a generated operator. `null` keeps every arity that `operators.arity_weights` gives a positive weight. |
| Recursion | `recursion.enabled` | `--no-recursion` | `true` | Permit recursive definitions and layers above zero. |
| Recursion template | `recursion.style` | `--recursion-style` | `bounded_mod` | Template used when `recursion.styles` is `null`. |
| Recursion templates | `recursion.styles` | `--recursion-styles` | `null` | List of templates sampled for recursive definitions: `bounded_mod`, `direct`, `peano`, `bits`, `primitive`. |
| Recursion calls | `recursion.max_recursive_calls` | `--max-recursive-calls` | `2` | Maximum recursive result slots in a binary callee of a generated recursive definition. |
| Remainder bound | `recursion.modulus_min`, `recursion.modulus_max` | `--recursion-modulus-min`, `--recursion-modulus-max` | `3`, `9` | Inclusive modulus range for `bounded_mod`; unfolding is at most modulus minus 1. |
| Direct bound | `recursion.direct_bound` | `--recursion-direct-bound` | `8` | Maximum unfolding depth for `direct`, `peano`, `bits`, and `primitive`. |

```yaml
operators:
  allow_branches: false
  max_substitution_depth: 1
recursion:
  enabled: false
```

This example generates simple definitions with bodies sampled at depth one and keeps all generated operators on layer zero.
