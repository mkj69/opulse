"""Static type checks for a parsed operator definition."""

from __future__ import annotations

from opulse.core.types import BOOL, INT, NOTE, parse_type, type_of
from opulse.definition import ast


def expression_type(node: ast.Expr, env: dict, resolve):
    if isinstance(node, ast.Var):
        return env[node.name]
    if isinstance(node, ast.Num):
        return INT
    if isinstance(node, ast.Literal):
        return type_of(node.value)
    if isinstance(node, ast.NaN):
        return None
    if isinstance(node, ast.Search):  # the index is an integer; the result is an index or NaN
        condition_type(node.condition, {**env, node.index: INT}, resolve)
        return INT
    op = resolve(node)
    given = tuple(expression_type(arg, env, resolve) for arg in node.args)
    expected = tuple(parse_type(kind) for kind in op.parameter_types)
    for actual, want in zip(given, expected):
        if actual is not None and actual != want and not (actual == INT and want == NOTE) \
                and not (actual == NOTE and want == INT):
            raise TypeError(f"{op.symbol!r} expects {want}, got {actual}")
    return parse_type(op.result_type)


def condition_type(node: ast.Condition, env: dict, resolve) -> None:
    if isinstance(node, ast.Truth):
        actual = expression_type(node.expr, env, resolve)
        if actual is not None and actual != BOOL:
            raise TypeError(f"condition expects bool, got {actual}")
    elif isinstance(node, ast.Compare):
        left = expression_type(node.left, env, resolve)
        right = expression_type(node.right, env, resolve)
        if left is not None and right is not None and left != right:
            raise TypeError("comparison operands must have the same type")
    elif isinstance(node, (ast.And, ast.Or)):
        condition_type(node.left, env, resolve)
        condition_type(node.right, env, resolve)
    else:
        condition_type(node.operand, env, resolve)


def check_definition(definition: ast.Definition, operator, resolve) -> None:
    env = dict(zip(definition.parameters, map(parse_type, operator.parameter_types)))
    want = parse_type(operator.result_type)
    for branch in definition.branches:
        if branch.condition is not None:
            condition_type(branch.condition, env, resolve)
        actual = expression_type(branch.expr, env, resolve)
        if actual is not None and actual != want and not ({actual, want} == {INT, NOTE}):
            raise TypeError(
                f"branch of {operator.symbol!r} returns {actual}, expected {want}"
            )
