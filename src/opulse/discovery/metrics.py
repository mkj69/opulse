"""Measurements on parsed definitions and a recorded set of inputs."""

from __future__ import annotations

import itertools

from opulse.bench.families import common, invent
from opulse.definition import ast


def size(definition: ast.Definition) -> int:
    """Count applications in all bodies and conditions, as in simplify."""
    return common.count_operations(definition)


def library_size(definitions: list[ast.Definition]) -> int:
    return sum(size(definition) for definition in definitions)


def require_acyclic_dependencies(definitions: list[ast.Definition]) -> None:
    """Reject cycles across definitions; a validated bounded self call is separate."""
    keys = {common.key_of(definition.lhs) for definition in definitions}
    graph = {}
    for definition in definitions:
        own = common.key_of(definition.lhs)
        graph[own] = {common.key_of(call) for branch in definition.branches
                      for node in [branch.expr] + ([branch.condition] if branch.condition else [])
                      for call in ast.iter_applications(node)
                      if common.key_of(call) in keys and common.key_of(call) != own}
    visited, active = set(), set()

    def visit(key):
        if key in active:
            raise ValueError("cyclic operator dependencies")
        if key in visited:
            return
        active.add(key)
        for child in graph[key]:
            visit(child)
        active.remove(key)
        visited.add(key)

    for key in graph:
        visit(key)


def cost(ops, lhs: str, inputs: list[tuple[int, ...]]) -> int:
    """Sum interpreter base operation counts, preserving sample multiplicity."""
    if not inputs:
        raise ValueError("the input distribution is empty")
    node = ops.parser.parse_expr(lhs, expression_mode=True)
    arity = len(node.args) if isinstance(node, ast.Apply) else 0
    total = 0
    for point in inputs:
        if len(point) != arity:
            raise ValueError("input arity differs from the operator")
        values = dict(zip(ops.parser.symbols.operands(arity), point))
        total += ops.oracle.evaluate_expr(node, values).base_ops
    return total


def usefulness(problems: list[ast.Expr], definitions: list[ast.Definition]) -> int:
    """Description length after the invent family's deterministic rewrite."""
    return sum(invent.size(problem) for problem in problems) - invent.reduction(problems, definitions)


def equivalence(ops, left: str, right: str, checked_range: tuple[int, int] | None = None) -> dict:
    """Prove equality, or explicitly label a complete finite input check."""
    a, b = common.expression(ops, left), common.expression(ops, right)
    verdict = common.decide(ops, a, b)
    if verdict.status == "proved":
        return {"status": "proved", "method": verdict.method, "strength": "proved"}
    if verdict.status == "refuted":
        return {"status": "refuted", "method": verdict.method,
                "counterexample": verdict.counterexample, "strength": "refuted"}
    if checked_range is None:
        return {"status": "undecided", "method": verdict.method, "strength": "undecided"}
    lo, hi = checked_range
    if ops.oracle.semantics.bound is not None:
        lo = max(lo, -ops.oracle.semantics.bound)
        hi = min(hi, ops.oracle.semantics.bound)
    if lo > hi or hi - lo > 100 or (hi - lo + 1) ** len(common.variables_in(a, b)) > 200_000:
        raise ValueError("invalid or too large checked range")
    for point in itertools.product(range(lo, hi + 1), repeat=len(common.variables_in(a, b))):
        env = dict(zip(common.variables_in(a, b), point))
        if not common.same(common.evaluate(ops, a, env), common.evaluate(ops, b, env)):
            return {"status": "refuted", "method": "range", "counterexample": env,
                    "strength": f"checked on range [{lo}, {hi}]"}
    return {"status": "checked", "method": "range", "range": [lo, hi],
            "strength": f"checked on range [{lo}, {hi}]"}
