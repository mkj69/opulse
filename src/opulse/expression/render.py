"""Render expression trees as text.

Two styles:

* ``full`` - every operator application except the outermost is parenthesised.
  Used inside definitions, where the grammar has a single precedence level.
* ``minimal`` - brackets only where precedence (``priority``, larger binds
  tighter) or associativity requires them. Unary applications below the root
  are always bracketed, and so is a binary operand of a unary operator,
  because unary operators bind tighter than every binary operator
  (docs/reference/semantics.md section 8). Operators without a priority fall back
  to ``full``.

Operators with three or more arguments are written in call form, ``⊕(x, y, z)``,
in both styles: the call delimits itself, so it is never bracketed, and each
argument is written as a top-level expression.
"""

from __future__ import annotations

from opulse.config import Symbols
from opulse.core.operator import BINARY, Operator
from opulse.core.semantics import NAN
from opulse.expression.nodes import Node, Number, Variable
from opulse.expression.numerals import NumeralWriter


class ExpressionRenderer:
    def __init__(self, symbols: Symbols, numerals: NumeralWriter | None = None) -> None:
        self.symbols = symbols
        self.numerals = numerals

    def full(self, node: Node) -> str:
        return self._render(node, parent=None, side=None, minimal=False)

    def minimal(self, node: Node) -> str:
        return self._render(node, parent=None, side=None, minimal=True)

    # ------------------------------------------------------------------
    def _render(self, node: Node, parent: Operator | None, side: str | None, minimal: bool) -> str:
        if isinstance(node, Number):
            text = self._number(node)
            negative = isinstance(node.value, int) and not isinstance(node.value, bool) and node.value < 0
            return self.symbols.paren(text) if negative and parent is not None else text
        if isinstance(node, Variable):
            return node.name
        op = node.operator
        if op.n_ary > BINARY:
            return op.apply_str(*(self._render(arg, None, None, minimal) for arg in node.args),
                                symbols=self.symbols)
        if op.n_ary == BINARY:
            left = self._render(node.args[0], op, "left", minimal)
            right = self._render(node.args[1], op, "right", minimal)
            text = op.apply_str(left, right)
        else:
            text = op.apply_str(self._render(node.args[0], op, None, minimal))
        if parent is None:
            return text
        if not minimal or op.n_ary != BINARY or self._needs_brackets(op, parent, side):
            return self.symbols.paren(text)
        return text

    def _number(self, node: Number) -> str:
        if node.value is NAN:
            return self.symbols.nan
        if not isinstance(node.value, int) or isinstance(node.value, bool):
            from opulse.core.types import literal

            return literal(node.value)
        if self.numerals is not None:
            return self.numerals.write(node.value, node.base)
        return str(node.value)

    @staticmethod
    def _needs_brackets(child: Operator, parent: Operator, side: str | None) -> bool:
        if parent.n_ary != BINARY:  # binary operand of a unary operator
            return True
        if child.priority is None or parent.priority is None:
            return True
        if child.priority != parent.priority:
            return child.priority < parent.priority
        if parent.associativity_direction == "left":
            return side == "right"
        if parent.associativity_direction == "right":
            return side == "left"
        return True
