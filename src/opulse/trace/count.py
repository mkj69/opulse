"""Count the steps of a reduction without building it.

:class:`~opulse.trace.Reducer` rewrites one application per step, and every step copies the
path to the focus. A trace that would exceed ``max_steps`` is discarded by its callers, so
building it first wastes most of the time spent on such expressions. :func:`count_steps`
returns the exact number of steps ``reducer.reduce(expression)`` takes, from the same
decisions the reducer makes (which operators are unfolded, the depth limit, the selected
branch), memoised per ``(operator, inputs, depth)``. It never replaces a trace: a counted
expression that fits is still reduced and verified step by step.
"""

from __future__ import annotations

from opulse.core.semantics import NAN
from opulse.definition import ast
from opulse.expression.nodes import Node, Number, Variable


class StepCounter:
    """Exact step counts for one reducer; the memo is kept across expressions."""

    def __init__(self, reducer, memo_limit: int = 1 << 20) -> None:
        self.reducer = reducer
        self.memo: dict[tuple, tuple] = {}
        self.memo_limit = memo_limit

    def count(self, expression: Node) -> int:
        """Number of steps ``reducer.reduce(expression)`` takes (0 for a number)."""
        return self._node(expression, 0)[1]

    # ---------------------------------------------------------------- internals
    def _node(self, node: Node, depth: int) -> tuple:
        """``(value, steps)`` of an expression subtree whose applications sit at ``depth``."""
        if isinstance(node, Number):
            return node.value, 0
        if isinstance(node, Variable):
            raise ValueError(f"cannot reduce an expression with variable {node.name!r}")  # noqa: TRY004
        steps = 0
        inputs = []
        for arg in node.args:
            value, n = self._node(arg, depth)
            inputs.append(value)
            steps += n
        value, n = self._apply(node.operator, tuple(inputs), depth)
        return value, steps + n

    def _apply(self, op, inputs: tuple, depth: int) -> tuple:
        reducer = self.reducer
        limit = reducer.max_depth
        too_deep = limit is not None and depth >= limit
        if not reducer.expand(op) or op.definition is None or too_deep:
            return reducer.runtime.compute(op)(*inputs), 1
        key = (op.func_id, inputs, None if limit is None else depth)
        found = self.memo.get(key)
        if found is not None:
            return found
        definition = reducer._definition(op)
        env = dict(zip(definition.parameters, inputs))
        _, branch, _ = reducer._choose_branch(definition, env)
        if branch is None:
            found = (NAN, 1)
        else:
            value, steps = self._body(branch.expr, env, depth + 1)
            found = (value, steps + 1)
        if len(self.memo) >= self.memo_limit:
            self.memo.clear()
        self.memo[key] = found
        return found

    def _body(self, node: ast.Expr, env: dict, depth: int) -> tuple:
        """``(value, steps)`` of an instantiated branch body (parameters bound in ``env``)."""
        if isinstance(node, ast.Var):
            return env[node.name], 0
        if isinstance(node, ast.Num):
            return node.value, 0
        if isinstance(node, ast.NaN):
            return NAN, 0
        if isinstance(node, ast.Literal):
            return node.value, 0
        if isinstance(node, ast.Search):  # the reducer evaluates a search in place, without steps
            return self.reducer._value(node, env), 0
        steps = 0
        inputs = []
        for arg in node.args:
            value, n = self._body(arg, env, depth)
            inputs.append(value)
            steps += n
        value, n = self._apply(self.reducer._resolve(node), tuple(inputs), depth)
        return value, steps + n


def count_steps(reducer, expression: Node) -> int:
    """Exact number of steps ``reducer.reduce(expression)`` takes, without building the trace."""
    return StepCounter(reducer).count(expression)


__all__ = ["StepCounter", "count_steps"]
