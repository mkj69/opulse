# Glossary

These terms describe what Opulse builds and checks. See [Concepts](getting-started/concepts.md) for examples and [Notation](guide/notation.md) for symbols.

## Atom

An operation computed directly, such as addition or reversing digits.

## Binary infix

`a ◆ b` puts a two-input operator between its left and right inputs.

## Branch

A definition whose tests select the first matching body. Also called a conditional definition. Example: `a ◆ b = { a, if a > b; b, else }`.

## Call form

`◆(a, b, c)` passes three inputs in parentheses, in order.

## Closure

All definitions needed to evaluate an expression, including definitions they call in turn.

## Derivation

A sequence of checked rewrites from an expression to its value.

## Granularity

How much of a derivation each step shows. Known operators can stay as single steps.

## Interpreter

The reference program that applies the written rules to compute a value.

## Layer

A generation level. Higher layers can use operators from lower layers.

## Multi-branch form

`{ x, if c; y, else }` uses `x` when condition `c` holds and `y` otherwise. Branches are checked in order.

## NaN

Opulse's value for an undefined result, such as division by zero or a result outside the value bound.

## Operator

A named operation. A generated operator has a definition built from atoms or earlier operators.

## Recursion

A definition that calls itself with a smaller argument until a base case stops it. Opulse bounds the calls. Example: `a ◆ b = { 0, if b <= 0; (a ◆ (b - 1)) + a, else }`.

## Substitution

A definition that calls atoms or other operators and combines their results. Also called a simple or composition definition. Example: `a ◆ b = { (a + b) * 2 }`.

## Unary postfix

`a △` puts a one-input operator after its input.

## Unary prefix

`■ a` puts a one-input operator before its input.

## Unfold

Replace a defined operator call with the branch selected by its inputs.

## z3

A solver that checks whether constraints have a solution. Opulse uses it for some proofs and generation checks.
