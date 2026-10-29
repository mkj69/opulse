"""Static checks on definitions with z3 (docs/reference/semantics.md section 9, obligation 4).

Inputs range over the value domain ``[-B, B]`` (all values an operator ever
receives lie there in exact mode). A conditional branch is *reachable* if
some input passes every earlier branch without matching or aborting and then
matches this branch.
"""

from __future__ import annotations

import itertools
import random

import z3

from opulse.core.operator import Operator
from opulse.core.semantics import NAN
from opulse.solver.z3_encode import NotExpressible, Z3Encoder

RLIMIT_PER_NODE = 2_000  # z3 resource units allowed per unit of budget
OBSERVE_LIMIT = 512  # concrete points tried before asking z3 (only saves solver calls)


def reachable_branches(operator: Operator, encoder: Z3Encoder, timeout_ms: int = 10_000,
                       budget: int = 600, check_undefined: bool = True) -> list[str]:
    """Per conditional branch: ``"reachable"``, ``"dead"``, ``"undefined"`` or ``"unknown"``.

    ``budget`` limits encoding nodes and gives z3 a proportional resource limit.

    ``"undefined"``: the branch is reached by some input but its body is NaN on all of them
    (e.g. ``b / (a - a)``), so it only ever contributes NaN.
    """
    definition = encoder.oracle._definition_of(operator)
    observed = _observed_branches(operator, encoder)  # concrete witnesses need no solver call
    xs, args = encoder.variables(operator, definition.parameters)
    env = dict(zip(definition.parameters, args))
    domain = [encoder.in_bound(x) for x in xs]
    encoder.reset()
    previous = []  # "earlier branch neither matched nor aborted"
    verdicts = []
    for index, branch in enumerate(definition.branches):
        if branch.condition is None:
            break
        abort, truth = encoder._condition(branch.condition, env, operator, 0, {})
        reached = [*domain, *previous, z3.Not(abort), truth]
        if index in observed:
            verdict = "reachable"
        else:
            verdict = _check(reached, timeout_ms, budget)
            if verdict == "reachable" and check_undefined and \
                    _always_undefined(encoder, branch, env, operator, reached, timeout_ms, budget):
                verdict = "undefined"
        verdicts.append(verdict)
        previous.append(z3.And(z3.Not(abort), z3.Not(truth)))
    return verdicts


def _observed_branches(operator: Operator, encoder: Z3Encoder) -> set[int]:
    """Branches seen taken with a defined result on a sample around the condition thresholds."""
    from opulse.analysis.coverage import selected_branch
    from opulse.verify.differential import literals

    oracle = encoder.oracle
    constants = {abs(c) for c in literals(oracle._definition_of(operator))} | {0, 1, 100, 1000}
    bound = encoder.bound
    values = sorted({sign * (c + d) for c in constants for d in (-1, 0, 1) for sign in (1, -1)
                     if bound is None or c + d <= bound})  # witnesses must lie in [-B, B] (review finding)
    if operator.n_ary > 2 and len(values) ** operator.n_ary > OBSERVE_LIMIT:
        # The full grid is too large to list: draw tuples with a fixed seed instead.
        draw = random.Random(operator.func_id)
        points = [tuple(draw.choice(values) for _ in range(operator.n_ary)) for _ in range(OBSERVE_LIMIT)]
    else:
        points = list(itertools.product(values, repeat=operator.n_ary))
    if len(points) > OBSERVE_LIMIT:  # a fixed-seed sample keeps the result reproducible
        points = random.Random(operator.func_id).sample(points, OBSERVE_LIMIT)
    seen = set()
    for args in points:
        branch = selected_branch(operator, args, oracle)
        if branch is not None and branch not in seen and oracle.evaluate(operator, args).value is not NAN:
            seen.add(branch)
    return seen


def _always_undefined(encoder: Z3Encoder, branch, env: dict, operator: Operator, reached: list,
                      timeout_ms: int, budget: int) -> bool:
    """True only when z3 proves the body NaN wherever the branch is taken (bounded effort)."""
    saved = encoder._nodes, encoder.max_nodes
    encoder._nodes = 0
    encoder.max_nodes = budget
    try:
        body = encoder._expr(branch.expr, env, operator, 0, {})
    except NotExpressible:
        return False  # too large to encode within the budget: no claim
    finally:
        encoder._nodes, encoder.max_nodes = saved
    return _check([*reached, body.defined], timeout_ms, budget) == "dead"


def _check(constraints: list, timeout_ms: int, budget: int) -> str:
    """Satisfiability of ``constraints`` in a killable worker process (see opulse.solver.isolated)."""
    from opulse.solver.isolated import check

    status, _ = check(constraints, timeout_ms, rlimit=budget * RLIMIT_PER_NODE)
    return {"sat": "reachable", "unsat": "dead"}.get(status, "unknown")


def dead_branch_reason(operator: Operator, encoder: Z3Encoder, timeout_ms: int = 30_000,
                       budget: int = 600, check_undefined: bool = True) -> str | None:
    """Acceptance check: reject definitions with a provably dead or always-undefined branch."""
    try:
        verdicts = reachable_branches(operator, encoder, timeout_ms, budget, check_undefined)
    except NotExpressible:
        return None  # cannot decide; other checks still apply
    for kind in ("dead", "undefined"):
        if kind in verdicts:
            return f"{kind} branch {verdicts.index(kind) + 1}"
    return None
