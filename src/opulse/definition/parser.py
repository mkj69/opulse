"""Parse definition and expression strings into :mod:`opulse.definition.ast` nodes.

A thin front end over :mod:`opulse.definition.syntax`. Without a registry the
parser knows the ten base operations (so ``&-1`` still splits into ``&`` and
``-``); with a registry it knows every operator's role, priority and the base
markers, which is needed for unseparated symbols, marked numerals and
priority-based expression parsing.
"""

from __future__ import annotations

from opulse.config import Symbols
from opulse.core.semantics import BASE_OPERATIONS
from opulse.definition import ast
from opulse.definition.syntax import (
    Notation,
    SyntaxProblem,
    parse_condition,
    parse_definition,
    parse_expression,
    role_of,
)


class DefinitionSyntaxError(ValueError):
    pass


def base_notation(symbols: Symbols) -> Notation:
    notation = Notation(symbols)
    for symbol, n_ary, position in BASE_OPERATIONS:
        notation.roles.setdefault(symbol, set()).add(role_of(n_ary, position))
    return notation


class DefinitionParser:
    """Parser bound to one set of :class:`~opulse.config.Symbols` (and optionally a registry)."""

    def __init__(self, symbols: Symbols, registry=None, digits: str | None = None,
                 variables: tuple[str, ...] = ()) -> None:
        self.symbols = symbols
        self.registry = registry
        if registry is None:
            self.notation = base_notation(symbols)
            self.notation.variables = variables
        else:
            self.notation = Notation.from_registry(registry, symbols, digits, variables)

    def refresh(self) -> None:
        """Re-read the registry (after operators were added)."""
        if self.registry is not None:
            self.notation = Notation.from_registry(self.registry, self.symbols, self.notation.digits,
                                                   self.notation.variables)

    def add(self, operator) -> None:
        """Register one new operator's role (O(1); ``refresh`` re-reads the whole registry)."""
        self.notation.check_symbol(operator.symbol)
        if operator.is_base is not None:
            self.notation.markers[operator.symbol] = operator.is_base
            return
        role = role_of(operator.n_ary, operator.unary_position)
        self.notation.roles.setdefault(operator.symbol, set()).add(role)
        if operator.priority is not None:
            self.notation.priority[(operator.symbol, role)] = (operator.priority,
                                                               operator.associativity_direction or "left")

    def parse(self, text: str) -> ast.Definition:
        return self._run(parse_definition, text)

    def parse_expr(self, text: str, expression_mode: bool = False, strict: bool = False) -> ast.Expr:
        """``expression_mode`` uses operator priorities; otherwise one binary level, left-assoc.
        ``strict`` requires parentheses around every binary operand that is itself binary."""
        return self._run(lambda t, n: parse_expression(t, n, expression_mode, strict), text)

    def parse_condition(self, text: str) -> ast.Condition:
        return self._run(parse_condition, text)

    def _run(self, fn, text: str):
        try:
            return fn(text, self.notation)
        except SyntaxProblem as exc:
            raise DefinitionSyntaxError(f"cannot parse {text!r}: {exc}") from exc
