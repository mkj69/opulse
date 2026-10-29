"""Typed syntax tree of the definition language, plus rendering back to text.

Generators build these nodes directly and call :func:`render_definition`;
the parser turns text back into the same nodes. Code generation, complexity
metrics and the reference interpreter all walk this tree, so none of them
depend on lark.

Operator applications store only the *surface* form (symbol, arity, position).
Resolving the symbol to a concrete operator is done later against a registry.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from opulse.config import Symbols
from opulse.core.operator import BINARY, POSTFIX, PREFIX, UNARY

# ----------------------------------------------------------------- expressions


@dataclass(frozen=True)
class Var:
    name: str


@dataclass(frozen=True)
class Num:
    """A non-negative integer literal. Negative constants are written as the
    prefix ``-`` operator applied to a literal, which costs one operation.
    ``base`` only affects how the literal is written (a base-marked numeral)."""

    value: int
    base: int = 10

    def __post_init__(self) -> None:
        if self.value < 0:
            raise ValueError("Num literals are non-negative; use negate() for negative constants")


def negate(value: int) -> Expr:
    """The constant ``value`` as an expression (``- 5`` for negative values)."""
    if value >= 0:
        return Num(value)
    return Apply("-", (Num(-value),), PREFIX)


@dataclass(frozen=True)
class NaN:
    pass


@dataclass(frozen=True)
class Literal:
    """A boolean, string, or list literal."""

    value: object

    def __post_init__(self) -> None:
        if isinstance(self.value, (list, tuple)):
            from opulse.core.types import freeze

            object.__setattr__(self, "value", freeze(self.value))


@dataclass(frozen=True)
class Apply:
    symbol: str
    args: tuple[Expr, ...]
    unary_position: str | None = None

    def __post_init__(self) -> None:
        if len(self.args) == UNARY and self.unary_position not in (PREFIX, POSTFIX):
            raise ValueError("unary application needs a prefix/postfix position")
        if len(self.args) >= BINARY and self.unary_position is not None:
            raise ValueError("binary and call-form applications have no unary position")
        if not self.args:
            raise ValueError("an operator takes at least one argument")

    @property
    def n_ary(self) -> int:
        return len(self.args)


@dataclass(frozen=True)
class Search:
    """Least index from zero through ``bound`` satisfying ``condition``."""

    index: str
    bound: int
    condition: Condition

    def __post_init__(self) -> None:
        if self.bound < 0:
            raise ValueError("search bound must be non-negative")


Expr = Var | Num | NaN | Literal | Apply | Search

# ------------------------------------------------------------------ conditions


@dataclass(frozen=True)
class Compare:
    left: Expr
    op: str
    right: Expr


@dataclass(frozen=True)
class And:
    left: Condition
    right: Condition


@dataclass(frozen=True)
class Or:
    left: Condition
    right: Condition


@dataclass(frozen=True)
class Not:
    operand: Condition


@dataclass(frozen=True)
class Truth:
    expr: Expr


Condition = Compare | And | Or | Not | Truth

# ------------------------------------------------------------------ definition


@dataclass(frozen=True)
class Branch:
    """``expr, if condition`` / ``expr, else`` / bare ``expr`` (both fields None)."""

    expr: Expr
    condition: Condition | None = None
    is_else: bool = False


@dataclass(frozen=True)
class Definition:
    lhs: Apply
    branches: tuple[Branch, ...]

    @property
    def parameters(self) -> tuple[str, ...]:
        return tuple(arg.name for arg in self.lhs.args)  # type: ignore[union-attr]


# ------------------------------------------------------------------- traversal


def iter_applications(node: Expr | Condition) -> Iterator[Apply]:
    """All operator applications inside ``node``, children before parents."""
    if isinstance(node, Apply):
        for arg in node.args:
            yield from iter_applications(arg)
        yield node
    elif isinstance(node, Search):
        yield from iter_applications(node.condition)
    elif isinstance(node, Compare) or isinstance(node, (And, Or)):
        yield from iter_applications(node.left)
        yield from iter_applications(node.right)
    elif isinstance(node, Not):
        yield from iter_applications(node.operand)
    elif isinstance(node, Truth):
        yield from iter_applications(node.expr)


def free_variables(node: Expr) -> set[str]:
    if isinstance(node, Var):
        return {node.name}
    if isinstance(node, Apply):
        return set().union(*(free_variables(arg) for arg in node.args))
    if isinstance(node, Search):
        return set().union(*(free_variables(operand) for operand in condition_operands(node.condition))) - {node.index}
    return set()


def condition_operands(node: Condition) -> Iterator[Expr]:
    """The expressions compared inside a condition."""
    if isinstance(node, Compare):
        yield node.left
        yield node.right
    elif isinstance(node, (And, Or)):
        yield from condition_operands(node.left)
        yield from condition_operands(node.right)
    else:
        if isinstance(node, Truth):
            yield node.expr
        else:
            yield from condition_operands(node.operand)


def branch_variables(branch: Branch) -> set[str]:
    """Variables read by a branch, in its body or its condition."""
    names = free_variables(branch.expr)
    if branch.condition is not None:
        for operand in condition_operands(branch.condition):
            names |= free_variables(operand)
    return names


# ------------------------------------------------------------------- rendering


# Writes a literal written in a non-decimal base: (value, base) -> text with its marker.
NumeralWriter = "Callable[[int, int], str] | None"


def decimal_literal(value: int) -> str:
    """Write an unbounded decimal integer without Python's decimal digit cap."""
    try:
        return str(value)
    except ValueError:
        base = 10 ** 1000
        pieces = []
        while value:
            value, remainder = divmod(value, base)
            pieces.append(str(remainder))
        return pieces[-1] + "".join(piece.zfill(1000) for piece in reversed(pieces[:-1]))


def render_expr(node: Expr, symbols: Symbols, top: bool = True, numerals=None) -> str:
    """Render with every operator application parenthesised except the outermost.

    An application with three or more arguments is written in call form, ``⊕(x, y, z)``. It
    delimits itself, so it is never parenthesised, and its arguments are written as at the top.
    """
    if isinstance(node, Var):
        return node.name
    if isinstance(node, Num):
        if node.base != 10:
            if numerals is None:
                raise ValueError(f"literal in base {node.base} needs a numeral writer")
            return numerals(node.value, node.base)
        return decimal_literal(node.value)
    if isinstance(node, NaN):
        return symbols.nan
    if isinstance(node, Literal):
        from opulse.core.types import literal

        return literal(node.value)
    if isinstance(node, Search):
        sep = symbols.argument_separator + " "
        return (f"search{symbols.left_paren}{node.index}{sep}{node.bound}{sep}"
                f"{render_condition(node.condition, symbols, numerals)}{symbols.right_paren}")
    if node.n_ary > BINARY:
        return symbols.call(node.symbol, [render_expr(arg, symbols, numerals=numerals) for arg in node.args])
    args = [render_expr(arg, symbols, top=False, numerals=numerals) for arg in node.args]
    if node.n_ary == BINARY:
        text = f"{args[0]} {node.symbol} {args[1]}"
    elif node.unary_position == PREFIX:
        text = f"{node.symbol} {args[0]}"
    else:
        text = f"{args[0]} {node.symbol}"
    return text if top else symbols.paren(text)


def render_condition(node: Condition, symbols: Symbols, numerals=None) -> str:
    if isinstance(node, Truth):
        return render_expr(node.expr, symbols, numerals=numerals)
    if isinstance(node, Compare):
        return (f"{render_expr(node.left, symbols, numerals=numerals)} {node.op} "
                f"{render_expr(node.right, symbols, numerals=numerals)}")
    if isinstance(node, And):
        return (f"{_render_operand(node.left, symbols, Or, numerals)} and "
                f"{_render_operand(node.right, symbols, Or, numerals)}")
    if isinstance(node, Or):
        return f"{render_condition(node.left, symbols, numerals)} or {render_condition(node.right, symbols, numerals)}"
    return f"not {_render_operand(node.operand, symbols, (And, Or, Not), numerals)}"


def _render_operand(node: Condition, symbols: Symbols, needs_paren, numerals) -> str:
    text = render_condition(node, symbols, numerals)
    return symbols.paren(text) if isinstance(node, needs_paren) else text


def render_branch(branch: Branch, symbols: Symbols, numerals=None) -> str:
    expr = render_expr(branch.expr, symbols, numerals=numerals)
    if branch.condition is not None:
        return f"{expr}, if {render_condition(branch.condition, symbols, numerals)}"
    if branch.is_else:
        return f"{expr}, else"
    return expr


def render_definition(definition: Definition, symbols: Symbols, numerals=None, *,
                      layout: str = "compact", min_length: int = 120) -> str:
    lhs = render_expr(definition.lhs, symbols)
    body = "; ".join(render_branch(branch, symbols, numerals) for branch in definition.branches)
    compact = f"{lhs} {symbols.equals} {{ {body} }}"
    if layout == "compact":
        return compact
    if layout != "piecewise":
        raise ValueError(f"unknown definition layout {layout!r}")
    if len(definition.branches) < 2 or len(compact) < min_length:
        return compact
    lines = ";\n  ".join(render_branch(branch, symbols, numerals) for branch in definition.branches)
    return f"{lhs} {symbols.equals} {{\n  {lines}\n}}"
