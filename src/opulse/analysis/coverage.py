"""Find and check top-level definition branches for empirical measurements.

The witness constraints mirror the reachability check: an input must pass all
earlier conditions without matching or aborting before it can enter a branch.
The reference oracle checks actual branch selection, including short circuiting.
"""

from __future__ import annotations

from collections.abc import Sequence

import z3

from opulse.core.operator import Operator
from opulse.core.semantics import NAN
from opulse.definition import ast
from opulse.definition.interpreter import COMPARISONS
from opulse.solver.isolated import check as isolated_check
from opulse.solver.z3_encode import Z3Encoder
from opulse.verify import Oracle


def branch_witnesses(operator: Operator, encoder: Z3Encoder,
                     timeout_ms: int = 10_000, rlimit: int = 5_000_000) -> list[tuple[int, ...] | None]:
    """Return one model per top-level branch, or None when none is found.

    This includes a terminal else or bare branch. A None can mean unsatisfiable
    or a resource limit; coverage is checked independently against the oracle.
    """
    definition = encoder.oracle._definition_of(operator)
    xs, args = encoder.variables(operator, definition.parameters)
    env = dict(zip(definition.parameters, args))
    domain = [encoder.in_bound(x) for x in xs]
    encoder.reset()
    previous = []
    witnesses = []
    for index, branch in enumerate(definition.branches):
        requirements = list(previous)
        if branch.condition is not None:
            abort, truth = encoder._condition(branch.condition, env, operator, 0, {})
            requirements.extend((z3.Not(abort), truth))
        constraints = [*domain, *requirements]
        names = [str(x) for x in xs]
        witness = None
        while True:
            status, model = isolated_check(constraints, timeout_ms, rlimit=rlimit, variables=names)
            if status != "sat":
                break
            point = tuple(model[name] for name in names)
            if selected_branch(operator, point, encoder.oracle) == index:
                witness = point
                break
            constraints.append(z3.Or(*(x != value for x, value in zip(xs, point))))
        witnesses.append(witness)
        if branch.condition is None:
            break
        previous.append(z3.And(z3.Not(abort), z3.Not(truth)))
    return witnesses


class _UndefinedCondition(Exception):
    """A compared operand evaluated to NAN, aborting this definition frame."""


def _condition(node: ast.Condition, env: dict[str, int], oracle: Oracle) -> bool:
    if isinstance(node, ast.Truth):
        value = oracle.evaluate_expr(node.expr, env).value
        if value is NAN:
            raise _UndefinedCondition
        return value
    if isinstance(node, ast.Compare):
        left = oracle.evaluate_expr(node.left, env).value
        right = oracle.evaluate_expr(node.right, env).value
        if left is NAN or right is NAN:
            raise _UndefinedCondition
        return COMPARISONS[node.op](left, right)
    if isinstance(node, ast.And):
        return _condition(node.left, env, oracle) and _condition(node.right, env, oracle)
    if isinstance(node, ast.Or):
        return _condition(node.left, env, oracle) or _condition(node.right, env, oracle)
    return not _condition(node.operand, env, oracle)


def selected_branch(operator: Operator, args: Sequence[int], oracle: Oracle) -> int | None:
    """Index of the entered top-level branch; None if selection aborts or misses."""
    definition = oracle._definition_of(operator)
    env = dict(zip(definition.parameters, args))
    try:
        for index, branch in enumerate(definition.branches):
            if branch.condition is None or _condition(branch.condition, env, oracle):
                return index
    except _UndefinedCondition:
        pass
    return None
