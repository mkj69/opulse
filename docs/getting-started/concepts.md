# Concepts

Opulse builds definitions from operations it can compute directly. This page explains the parts of a definition with examples. For short definitions, see the [glossary](../glossary.md).

## Atom

An atomic operation is computed directly and never unfolded. Examples include successor `a ⁺`,
halving `a »`, `+` or `@` (reverse the decimal digits). Every other operator is built from atoms,
layer upon layer, and evaluating it means unfolding it back into atoms.

The atoms Opulse ships are examples. You can start from any integer functions, including a single
successor, bit operations, `max` or a cube, and give them any symbols
([Custom atoms](../guide/atoms.md)). The same holds for the notation: operator symbols, parameter
names, brackets, the NaN spelling and the digits are all configuration. What Opulse fixes is
the *way* concepts are composed (definitions, branches, recursion, layers) and the checking that
comes with it. The built-in atoms are listed in the
[specification](../reference/semantics.md#3-atomic-operations).

## Operator and definition

An **operator** has a symbol, an arity and a **definition** that says how to compute it from
atoms and operators that already exist:

```text
a ▲₁ b = { (a + b) * 2 }
```

`▲₁` is the symbol, `a` and `b` are its parameters, and the part in braces is its definition.
Unary operators are written before (`■₂ a`, prefix) or after (`a △₂`, postfix) their operand.
Operators with three or more parameters are written in call form, both where they are defined and
where they are used:

```text
⊕(a, b, c) = { (a + b) * c }          ⊕(3, x, 5)
```

The arity is a setting: `operators.arity_weights` says how many operators of each arity to grow
(by default only unary and binary ones), and `symbols.operand_names` names the parameters.
The shape and subscript names here, such as ◆₁, aid reading but mean nothing; Opulse can give models the same operators as symbol strings, pseudo words, English words, or names with your own alphabet and index characters ([notation](../guide/notation.md)).

## Branch

A definition may try several cases in order. The first case whose condition holds gives the
result; `else` catches the rest:

```text
a △₂ = { a * 41, if a < 21; # a, if a < 83; 4 / a, else }
```

## Recursion

A definition may call its own operator on a smaller value. Opulse only generates recursion that
provably stops: the value it recurses on is walked toward 0 and is limited in size, so the
recursion unfolds a few times at most.

```text
a ●₁ b = { - 57, if a % 5 == 0; ■₂ (((a % 5) - 1) ●₁ b), if a % 5 > 0; ■₂ (((a % 5) + 1) ●₁ b), if a % 5 < 0 }
```

The style `primitive` generates the full primitive-recursion shape: the step sees the
parameters, the counter and the previous result, h(x̄, n) = g(x̄, n - 1, h(x̄, n - 1)).
Multiplication from addition, for example:

```text
a ⊠ b = { 0, if b == 0; (a ⊠ (b - 1)) + a, if b > 0 and b <= 8; (a ⊠ (b + 1)) - a, if b < 0 and b >= - 8 }
```

How far a recursion may unfold is a setting (`recursion.direct_bound`, here 8); beyond it the
value is NaN.

## NaN and the bound

Every value is an integer or **NaN** (undefined). NaN appears when dividing by zero, when a
result's absolute value exceeds the **bound** B = 2³¹ − 1, or when no case of a definition applies. NaN
carries through every later operation.

## Layer

Operators are generated in **layers**. Layer 0 uses only atoms and other layer-0 operators; a recursive operator over a layer-k operator starts layer k + 1. Higher layers mean
deeper chains of definitions.

## Reference interpreter

The reference interpreter follows the [specification](../reference/semantics.md). Before Opulse
writes compiled code, datasets, step-by-step solutions or solver answers, it compares their
values with the reference interpreter.
