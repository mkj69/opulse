# Operator names

New operator sets use `shape_index` naming. A generated name joins a shape and an index, such as `◆₁` or `▲₂`. The name identifies an operator; its shape and index say nothing about its definition, arity, or recursive layer. Atomic operations keep the names supplied by their owner.

The default shape pool contains `■□▲△▼▽◆◇●○★☆` and `♠♣♥♦♤♧♡♢`. It contains no summation, integral, root, membership, quantifier, or negation glyphs. An index starts at one and uses the configured character alphabet. With the default alphabet, later names can contain several subscript digits, such as `◆₁₀`.

This configuration uses only two shapes and writes indices with plain letters.

```yaml
operators:
  naming: shape_index
  shape_sets: []
  shape_chars: "◆▲"
  index_chars: "abcdefghijklmnopqrstuvwxyz"
```

The first names use `a`, `b`, and later letters as indices. After `z`, the index continues as `aa`. Each candidate draws a shape independently of its definition. A shape glyph cannot also be the complete name of an existing atomic operator.

Set `operators.naming: legacy` to use the earlier random symbol generator. Its `symbol_sets`, `symbol_chars`, `symbol_blocks`, `symbol_ascii`, `symbol_min_len`, and `symbol_max_len` settings still apply. A fixed seed in this mode follows the earlier drawing sequence.

Long branch definitions can put one branch on each line. This configuration enables that layout for compact definitions of at least 80 characters.

```yaml
operators:
  definition_layout: piecewise
  piecewise_min_length: 80
```

For example, this two branch definition has one branch on each line when the threshold is low enough.

```text
a ◆₁ b = {
  a + b, if b > 0;
  a, else
}
```

The definition text remains valid input to the parser, benchmark prompt checker, and reference interpreter.
