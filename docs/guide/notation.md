# Notation

<div class="op-lead" markdown>
Experiments on notation need the same operators written in different symbols, and every text must still parse back to the same tree.
</div>

Brackets, the definition sign, parameter names and the spelling of NaN are settings. The parser and
both renderers read them, so generated text always parses back to the same tree.

```yaml
symbols:
  left_operand: x
  right_operand: y
  left_paren: "["
  right_paren: "]"
  equals: ":="
  nan: Undef
```

--8<-- "docs/snippets/notation_custom.md"

## Operator alphabets

The default naming mode combines a shape and an index. See [Operator names](naming.md).
The following character sets apply to the `legacy` naming mode. Every set holds symbols that common fonts
draw and that do not look like letters, digits, arithmetic or comparison signs:

| Set | Characters |
| --- | --- |
| `circled` | ⊕ ⊗ ⊝ |
| `squared` | ⊞ ⊟ ⊠ |
| `logic` | ∧ ∨ ⊻ ⊼ ⊽ ¬ ∀ ∃ ∄ |
| `sets` | ∩ ∪ ⊂ ⊃ ∈ ∋ ∉ ⊎ ⊓ ⊔ |
| `calculus` | ∑ ∏ ∐ ∫ ∮ √ ∛ ∜ ∞ ∂ ∇ ∆ |
| `math` | all five sets above |
| `arrows` | ← → ↑ ↓ ↔ ↕ ↖ ↗ ↘ ↙ ⇐ ⇒ ⇑ ⇓ ⇔ ↦ ↩ ↪ ↺ ↻ ⇄ ⇆ |
| `shapes` | ■ □ ▲ △ ▼ ▽ ◆ ◇ ● ○ ★ ☆ |
| `suits` | ♠ ♣ ♥ ♦ ♤ ♧ ♡ ♢ |
| `greek` | Γ Δ Θ Λ Ξ Π Σ Φ Ψ Ω (capitals that do not look like Latin letters) |

```yaml
operators:
  naming: legacy
  symbol_sets: [math, arrows, shapes]
  symbol_chars: "♪♫"                     # more characters, listed directly
  symbol_max_len: 3
```

`symbol_blocks` (raw Unicode ranges such as `2200-22FF`) remains available for special cases.

### How many operators fit

Legacy symbols are kept **prefix free**: no symbol is the beginning of another, so a run of symbols splits
in exactly one way. With k characters and symbols of at most L characters, at most k^L symbols fit.
The shown 71 characters with L = 3 allow 357,911 operators; L = 2 would allow only 5,041. The
generator draws long symbols more often so the set can approach that capacity, checks each new
symbol in constant time, and stops before it starts if the requested number of operators cannot fit.

With `symbol_sets: [greek]` operators are Greek capitals:

--8<-- "docs/snippets/notation_greek.md"

## Plain-word names

For experiments about symbol familiarity, `AliasMap.build(registry, rng)` assigns each generated
operator a distinct pronounceable pseudo-word. Pass `style="english"` to draw from a fixed list of
common English words that excludes arithmetic names. `aliased_registry(registry, alias)` copies the
registry with those names in its definitions; `alias_tree(tree, copied_registry)` gives an expression
tree that renders with them. Base operations and numeral-base markers retain their symbols. The
alias map also contains the inverse names, so a display can be traced back to the original symbol.
The reference interpreter gives the same values and operation counts under either notation.

```python
import random

from opulse.expression.aliases import AliasMap, aliased_registry, alias_tree

aliases = AliasMap.build(registry, random.Random(7))
display_registry = aliased_registry(registry, aliases)
display_tree = alias_tree(tree, display_registry)
```

## Reading rules

* Unary operators bind tighter than binary ones, and postfix tighter than prefix: `- a @` is `- (a @)`.
* Unary operators chain: `- - a`, `& - 1`, `a @ $`.
* A run of legacy operator characters splits into registered symbols in exactly one way. The registered
  legacy symbols form a uniquely decodable set; a run with two splits is a
  syntax error, never a guess. Shape and index names are separated from operands by spaces or brackets.
* A numeral may start with a base marker: `⊺⇮1A` is 1A in the marker's base.
* In expressions, binary operators follow their priority and associativity; in definitions every
  binary application is bracketed.

--8<-- "docs/snippets/parse.md"
