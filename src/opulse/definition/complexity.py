"""Structural complexity of a definition: longest call path and edge count.

For one operator application ``op(x, y)``:

* ``max_path_depth``  L = max(L of arguments) + L(op)
* ``max_edge_count``  E = sum(E of arguments) + E(op)

Atoms contribute ``(0, 0)``. Across branches both numbers take the maximum,
because only one branch runs. Conditions are not counted. Primitive operators
carry their own ``(L, E)`` (``(1, 2)`` for ``+``, ``(1, 1)`` for unary ``-``).
"""

from __future__ import annotations

from dataclasses import dataclass

from opulse.definition import ast
from opulse.definition.codegen import Resolver


@dataclass(frozen=True)
class Complexity:
    max_path_depth: int = 0
    max_edge_count: int = 0


def expr_complexity(node: ast.Expr, resolve: Resolver) -> Complexity:
    if isinstance(node, ast.Search):
        return condition_complexity(node.condition, resolve)
    if not isinstance(node, ast.Apply):
        return Complexity()
    operator = resolve(node)
    parts = [expr_complexity(arg, resolve) for arg in node.args]
    return Complexity(
        max(p.max_path_depth for p in parts) + operator.max_path_depth,
        sum(p.max_edge_count for p in parts) + operator.max_edge_count,
    )


def condition_complexity(node: ast.Condition, resolve: Resolver) -> Complexity:
    if isinstance(node, ast.Compare):
        parts = (expr_complexity(node.left, resolve), expr_complexity(node.right, resolve))
    elif isinstance(node, ast.Not):
        return condition_complexity(node.operand, resolve)
    else:
        parts = (condition_complexity(node.left, resolve), condition_complexity(node.right, resolve))
    return Complexity(max(part.max_path_depth for part in parts), sum(part.max_edge_count for part in parts))


def definition_complexity(definition: ast.Definition, resolve: Resolver) -> Complexity:
    parts = [expr_complexity(branch.expr, resolve) for branch in definition.branches]
    return Complexity(
        max(p.max_path_depth for p in parts),
        max(p.max_edge_count for p in parts),
    )
