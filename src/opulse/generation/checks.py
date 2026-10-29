"""Acceptance checks for a compiled candidate operator.

Each check returns ``None`` when the candidate passes, or a short reason.
The pipeline counts reasons so rejection rates are visible in the run summary.
"""

from __future__ import annotations

import hashlib
import random

from opulse.core.operator import RECURSIVE, SIMPLE, Operator
from opulse.core.semantics import NAN
from opulse.definition import ast
from opulse.generation.drafts import Draft
from opulse.verify import check_operator


def uses_all_parameters(draft: Draft) -> str | None:
    """Every parameter must influence the definition somewhere (body or condition)."""
    used = set().union(*(ast.branch_variables(branch) for branch in draft.definition.branches))
    missing = set(draft.definition.parameters) - used
    return f"unused parameter {sorted(missing)}" if missing else None


def not_a_renaming(draft: Draft) -> str | None:
    """Reject ``f(a, b) = { g(x, y) }``: one call of the same arity is just ``g`` again."""
    if draft.definition_type != SIMPLE:
        return None
    if isinstance(draft.definition.branches[0].expr, ast.Search):
        return None
    applications = list(ast.iter_applications(draft.definition.branches[0].expr))
    if len(applications) == 1 and applications[0].n_ary == draft.n_ary:
        return "single call of the same arity"
    return None


def distinct_branches(draft: Draft) -> str | None:
    bodies = [branch.expr for branch in draft.definition.branches]
    return "duplicate branch bodies" if len(set(bodies)) != len(bodies) else None


def body_fingerprint(operator: Operator) -> str:
    """Hash of the generated code with the operator's own id blanked out."""
    source = (operator.op_compute_func or "").replace(operator.func_id, "SELF")
    return hashlib.sha256(source.encode()).hexdigest()


def agrees_with_reference(operator: Operator, runtime, oracle, rng: random.Random,
                          random_trials: int = 60) -> str | None:
    """Compiled code == reference interpreter (value, base_ops, calls) on every probe."""
    mismatches = check_operator(operator, runtime.evaluate(operator), oracle, rng, random_trials)
    if mismatches:
        return f"disagrees with reference: {mismatches[0]}"
    return None


def defined_somewhere(operator: Operator, runtime, rng: random.Random, trials: int = 60) -> str | None:
    """Reject operators that are undefined on every probe (small, boundary and random inputs)."""
    compute = runtime.compute(operator)
    probes = [tuple(rng.randint(-20, 20) for _ in range(operator.n_ary)) for _ in range(trials)]
    probes += [tuple(rng.randint(-1000, 1000) for _ in range(operator.n_ary)) for _ in range(trials)]
    for args in probes:
        if compute(*args) is not NAN:
            return None
    return "undefined on all samples"


def varied_outputs(operator: Operator, runtime, rng: random.Random, trials: int = 30,
                   min_distinct: int = 5, max_echo_ratio: float = 0.8) -> str | None:
    """Optional: the operator should not be nearly constant or mostly echo an input."""
    compute = runtime.compute(operator)
    outputs, echoes = set(), 0
    for _ in range(trials):
        inputs = [rng.randint(-1000, 1000) for _ in range(operator.n_ary)]
        value = compute(*inputs)
        outputs.add(value)
        echoes += any(value is x or value == x for x in inputs)
    if len(outputs) < min_distinct:
        return "nearly constant"
    if echoes > trials * max_echo_ratio:
        return "mostly returns an input"
    return None



def intentionally_partial(draft: Draft, recursion_style: str) -> bool:
    """Definitions meant to be undefined on part of the domain: no ``else`` branch, or a
    recursion bounded by |v| <= T (templates B, C and D)."""
    if draft.definition_type == RECURSIVE:
        return recursion_style in ("direct", "peano", "primitive")
    if isinstance(draft.definition.branches[-1].expr, ast.Search):
        return True
    return draft.definition.branches[-1].condition is not None


def defined_share(operator: Operator, runtime, rng: random.Random, min_share: float,
                  value_range: tuple[int, int], trials: int = 80) -> str | None:
    """The operator must be defined on at least ``min_share`` of inputs drawn from the range
    expressions use, so that sampled expressions are not mostly NaN."""
    compute = runtime.compute(operator)
    lo, hi = value_range
    probes = [tuple(rng.randint(lo, hi) for _ in range(operator.n_ary)) for _ in range(trials)]
    defined = sum(compute(*args) is not NAN for args in probes)
    return "defined on too few inputs" if defined < min_share * trials else None


SUBEXPRESSION_SAMPLE = (0, 1, -1, 2, -2, 3, -3, 5, -7, 10, -10, 37, 100, -100, 1000)


def degenerate_subexpression(draft: Draft, operator: Operator, oracle, encoder, budget: int,
                             safety_timeout_ms: int = 30_000) -> str | None:
    """Reject a subexpression that uses a parameter yet takes at most one defined value,
    such as ``a - a`` (always 0) or ``a % a`` (0 wherever defined). Used as a divisor, such a
    subexpression makes the operator NaN almost everywhere.

    Concrete inputs pick the suspects; a suspect is rejected only when z3 proves it
    (no two inputs give two different defined values). Undecided suspects are accepted.
    """
    import itertools

    import z3

    from opulse.solver.isolated import check
    from opulse.solver.static import RLIMIT_PER_NODE
    from opulse.solver.z3_encode import NotExpressible, ZVal

    params = draft.definition.parameters
    # Three or more parameters: a shorter sample per parameter keeps the grid small (7^3 = 343).
    sample = SUBEXPRESSION_SAMPLE if len(params) <= 2 else SUBEXPRESSION_SAMPLE[: max(3, int(400 ** (1 / len(params))))]
    points = [dict(zip(params, p)) for p in itertools.product(sample, repeat=len(params))]
    seen: set = set()
    for node in _subexpressions(draft.definition):
        if node in seen or not ast_variables(node):
            continue
        seen.add(node)
        first = NAN
        defined_count = 0
        varies = False
        for env in points:
            value = oracle.evaluate_expr(node, env).value
            if value is NAN:
                continue
            defined_count += 1
            if first is NAN:
                first = value
            elif value != first:
                varies = True
                break
        # Suspect only a subexpression seen defined at two or more points, always with the same
        # value; one that is NaN almost everywhere is the business of ``defined_share``.
        if varies or defined_count < 2 or encoder is None:
            continue
        # Suspect: prove it with two independent copies of the parameters.
        try:
            encoder.reset()
            encoder.max_nodes, saved = budget, encoder.max_nodes
            try:
                xs = {p: z3.Int(f"{p}_1") for p in params}
                ys = {p: z3.Int(f"{p}_2") for p in params}
                left = encoder._expr(node, {p: ZVal(z3.BoolVal(True), x) for p, x in xs.items()}, operator, 0, {})
                right = encoder._expr(node, {p: ZVal(z3.BoolVal(True), y) for p, y in ys.items()}, operator, 0, {})
            finally:
                encoder.max_nodes = saved
        except NotExpressible:
            continue
        domain = [encoder.in_bound(v) for v in (*xs.values(), *ys.values())]
        status, _ = check([*domain, left.defined, right.defined, left.value != right.value],
                          safety_timeout_ms, rlimit=budget * RLIMIT_PER_NODE)
        if status == "unsat":
            return "degenerate subexpression"
    return None


def ast_variables(node) -> set[str]:
    if isinstance(node, ast.Var):
        return {node.name}
    if isinstance(node, ast.Apply):
        return set().union(*(ast_variables(arg) for arg in node.args))
    return set()


def _subexpressions(definition: ast.Definition):
    """Every application inside branch bodies and condition operands (not the whole lhs)."""
    def walk(node):
        if isinstance(node, ast.Apply):
            yield node
            for arg in node.args:
                yield from walk(arg)
        elif isinstance(node, ast.Search):
            yield from walk(node.condition)
        elif isinstance(node, ast.Compare):
            yield from walk(node.left)
            yield from walk(node.right)
        elif isinstance(node, ast.Not):
            yield from walk(node.operand)
        elif isinstance(node, (ast.And, ast.Or)):
            yield from walk(node.left)
            yield from walk(node.right)

    for branch in definition.branches:
        if branch.condition is not None:
            yield from walk(branch.condition)
        yield from walk(branch.expr)
