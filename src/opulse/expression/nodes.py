"""Expression trees whose operators are already resolved to :class:`Operator` records.

Unlike :mod:`opulse.definition.ast` (surface syntax, symbols only), these nodes
point at concrete operators, so they can be evaluated directly. Use
:func:`to_ast` to embed an expression into a definition.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace

from opulse.core.operator import Operator
from opulse.core.semantics import NAN
from opulse.definition import ast


@dataclass(frozen=True)
class Number:
    value: object  # int, or NAN for an undefined intermediate result
    base: int = 10

    def __post_init__(self) -> None:
        if isinstance(self.value, (list, tuple)):
            from opulse.core.types import freeze

            object.__setattr__(self, "value", freeze(self.value))


@dataclass(frozen=True)
class Variable:
    name: str


@dataclass(frozen=True)
class Call:
    operator: Operator
    args: tuple[Node, ...]

    def __post_init__(self) -> None:
        if len(self.args) != self.operator.n_ary:
            raise ValueError(f"{self.operator.symbol!r} takes {self.operator.n_ary} argument(s)")


Node = Number | Variable | Call


def iter_calls(node: Node) -> Iterator[Call]:
    """Every call in ``node``, children before parents."""
    if isinstance(node, Call):
        for arg in node.args:
            yield from iter_calls(arg)
        yield node


def defined_operators(node: Node) -> list[str]:
    """Sorted func_ids of the defined operators applied in ``node``, one entry per application."""
    return sorted(call.operator.func_id for call in iter_calls(node) if call.operator.definition is not None)


def has_variable(node: Node) -> bool:
    if isinstance(node, Variable):
        return True
    return isinstance(node, Call) and any(has_variable(arg) for arg in node.args)


def map_operators(node: Node, swap: Callable[[Operator], Operator]) -> Node:
    """Rebuild ``node`` with every operator replaced by ``swap(operator)``."""
    if not isinstance(node, Call):
        return node
    return replace(node, operator=swap(node.operator), args=tuple(map_operators(a, swap) for a in node.args))


def depth(node: Node) -> int:
    return 1 + max((depth(arg) for arg in node.args), default=0) if isinstance(node, Call) else 1


def literal_form(node: Node, registry) -> Node:
    """Write every negative number atom as unary minus of its magnitude (spec section 7).

    Expression trees must be in this form before they are evaluated, so that the evaluator
    and the reference interpreter count the same negation (review finding).
    """
    if isinstance(node, Number) and isinstance(node.value, int) and not isinstance(node.value, bool) and node.value < 0:
        neg = registry.find("-", 1, "prefix")
        if neg is None:
            raise ValueError("a negative number needs the prefix negation operator '-'")
        return Call(neg, (Number(-node.value, node.base),))
    if isinstance(node, Call):
        return Call(node.operator, tuple(literal_form(arg, registry) for arg in node.args))
    return node


def to_ast(node: Node) -> ast.Expr:
    if isinstance(node, Number):
        if node.value is NAN:
            return ast.NaN()
        if isinstance(node.value, int) and not isinstance(node.value, bool):
            return ast.negate(node.value)
        return ast.Literal(node.value)
    if isinstance(node, Variable):
        return ast.Var(node.name)
    op = node.operator
    return ast.Apply(op.symbol, tuple(to_ast(arg) for arg in node.args), op.unary_position)


def to_dict(node: Node) -> dict:
    """JSON form compatible with the legacy ``tree`` field."""
    if isinstance(node, Number):
        if node.value is NAN:
            return {"type": "nan"}
        from opulse.worlds.perm import Permutation

        if isinstance(node.value, Permutation):
            return {"type": "perm_literal", "value": list(node.value)}
        if not isinstance(node.value, int) or isinstance(node.value, bool):
            return {"type": "typed_literal", "value": node.value}
        return {"type": "numeric_atoms", "value": node.value, "base": node.base}
    if isinstance(node, Variable):
        return {"type": "variable", "variable": node.name}
    op = node.operator
    if op.n_ary > 2:
        return {"type": "call", "operator": op.symbol, "n_ary": op.n_ary, "args": [to_dict(a) for a in node.args]}
    if op.n_ary == 2:
        return {"type": "binary", "operator": op.symbol,
                "left_expr": to_dict(node.args[0]), "right_expr": to_dict(node.args[1])}
    return {"type": "unary", "operator": op.symbol, "position": op.unary_position,
            "unary_expr": to_dict(node.args[0])}


def from_dict(data: dict, registry) -> Node:
    kind = data["type"]
    if kind == "nan":
        return Number(NAN)
    if kind == "perm_literal":
        from opulse.worlds.perm import Permutation

        return Number(Permutation(data["value"]))
    if kind == "numeric_atoms":
        return Number(int(data["value"]), data.get("base") or 10)
    if kind == "typed_literal":
        value = data["value"]
        return Number(tuple(value) if isinstance(value, list) else value)
    if kind == "variable":
        return Variable(data["variable"])
    if kind == "call":
        args = tuple(from_dict(arg, registry) for arg in data["args"])
        return Call(registry.find(data["operator"], len(args)), args)
    if kind == "binary":
        op = registry.find(data["operator"], 2)
        return Call(op, (from_dict(data["left_expr"], registry), from_dict(data["right_expr"], registry)))
    position = data.get("position")
    op = registry.find(data["operator"], 1, position) if position else (
        registry.find(data["operator"], 1, "prefix") or registry.find(data["operator"], 1, "postfix"))
    return Call(op, (from_dict(data["unary_expr"], registry),))


def from_ast(node: ast.Expr, registry) -> Node:
    """Resolve a parsed expression against ``registry``."""
    if isinstance(node, ast.Num):
        return Number(node.value, node.base)
    if isinstance(node, ast.Literal):
        return Number(node.value)
    if isinstance(node, ast.NaN):
        return Number(NAN)
    if isinstance(node, ast.Var):
        return Variable(node.name)
    operator = registry.find(node.symbol, node.n_ary, node.unary_position)
    if operator is None:
        shape = node.unary_position or ("binary" if node.n_ary == 2 else f"{node.n_ary} arguments")
        raise LookupError(f"no operator {node.symbol!r} ({shape})")
    return Call(operator, tuple(from_ast(arg, registry) for arg in node.args))
