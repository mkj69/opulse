"""Fit measured base-operation counts without changing operator semantics.

The fit describes observed, defined evaluations; it is not a worst-case bound.
Branch witnesses supplement a sign-balanced logarithmic grid so narrow branches
are represented even when the regular grid misses them.
"""

from __future__ import annotations

from collections.abc import Iterator
from itertools import product

import numpy as np

from opulse.analysis.coverage import branch_witnesses, selected_branch
from opulse.config import Symbols
from opulse.core.operator import Operator
from opulse.core.registry import OperatorRegistry
from opulse.core.semantics import NAN
from opulse.definition import ast
from opulse.solver.z3_encode import NotExpressible, Z3Encoder, recursion_control
from opulse.verify import Oracle


def _magnitudes() -> list[int]:
    return sorted({round(float(x)) for x in np.geomspace(1, 1_000_000, 13)})


def measurement_grid(operator: Operator) -> list[tuple[int, ...]]:
    """A fixed grid through zero, both signs, and six orders of magnitude."""
    signed = [0] + [sign * n for n in _magnitudes() for sign in (-1, 1)]
    if operator.is_unary:
        # The small sweep resolves short bounded-mod periods near the origin.
        return [(n,) for n in sorted(set(signed) | set(range(-32, 33)))]
    if operator.n_ary > 2:  # a coarser grid keeps three or more arguments affordable
        coarse = [0] + [sign * n for n in _magnitudes()[::3] for sign in (-1, 1)]
        return list(product(coarse, repeat=operator.n_ary))
    return list(product(signed, repeat=2))


def _modulus_feature(operator: Operator, oracle: Oracle, inputs: np.ndarray) -> np.ndarray | None:
    """The bounded control value of a template-A recursion, if present."""
    if operator.definition_type != "recursive_definition":
        return None
    definition = oracle._definition_of(operator)
    try:
        variable, control, _ = recursion_control(definition)
    except NotExpressible:
        return None
    if not isinstance(control, ast.Apply) or not isinstance(control.args[1], ast.Num):
        return None
    modulus = control.args[1].value
    if modulus == 0:
        return None
    column = definition.parameters.index(variable)
    return np.mod(np.abs(inputs[:, column]), modulus)


def _candidates(operator: Operator, oracle: Oracle,
                inputs: np.ndarray) -> Iterator[tuple[str, tuple[np.ndarray, ...]]]:
    a = np.abs(inputs[:, 0])
    yield "constant", ()
    yield "log_abs_a", (np.log1p(a),)
    yield "linear_abs_a", (a,)
    yield "n_log_n_abs_a", (a * np.log1p(a),)
    yield "quadratic_abs_a", (a * a,)
    if not operator.is_unary:
        b = np.abs(inputs[:, 1])
        yield "log_abs_b", (np.log1p(b),)
        yield "log_abs_a_and_b", (np.log1p(a), np.log1p(b))
        yield "linear_abs_b", (b,)
        yield "n_log_n_abs_b", (b * np.log1p(b),)
        yield "quadratic_abs_b", (b * b,)
        yield "linear_abs_a_plus_b", (a + b,)
        yield "linear_max_abs_a_b", (np.maximum(a, b),)
        yield "product_abs_a_b", (a * b,)
        yield "log_abs_a_plus_b", (np.log1p(a + b),)
        yield "log_max_abs_a_b", (np.log1p(np.maximum(a, b)),)
    # Template A runs for at most m-1 steps. A periodic candidate prevents a
    # spurious global linear trend from being reported for its bounded cost.
    mod = _modulus_feature(operator, oracle, inputs)
    if mod is not None:
        yield "bounded_mod", (mod,)


def _fit(operator: Operator, oracle: Oracle, samples: list[tuple[tuple[int, ...], int]]) -> dict:
    count = len(samples)
    if not count:
        return {"model": None, "coefficients": [], "r2": None,
                "max_abs_residual": None, "n_points": 0}
    y = np.asarray([cost for _, cost in samples], dtype=float)
    if np.all(y == y[0]):
        return {"model": "constant", "coefficients": [float(y[0])], "r2": 1.0,
                "max_abs_residual": 0.0, "n_points": count}
    inputs = np.asarray([args for args, _ in samples], dtype=float)
    total = float(np.sum((y - np.mean(y)) ** 2))
    best = None
    for name, features in _candidates(operator, oracle, inputs):
        scales = [float(np.max(np.abs(feature))) for feature in features]
        if any(scale == 0 for scale in scales):
            continue
        design = np.column_stack([np.ones(count)] +
                                 [feature / scale for feature, scale in zip(features, scales)])
        coefficients, _, rank, _ = np.linalg.lstsq(design, y, rcond=None)
        if rank != design.shape[1]:
            continue
        residual = y - design @ coefficients
        rss = float(residual @ residual)
        # A tiny floor makes numerically exact fits comparable across features.
        bic = count * np.log(max(rss / count, 1e-24)) + design.shape[1] * np.log(count)
        if best is None or bic < best[0]:
            original_coefficients = [float(coefficients[0])] + [
                float(coefficient / scale)
                for coefficient, scale in zip(coefficients[1:], scales)
            ]
            best = (bic, name, original_coefficients, rss, float(np.max(np.abs(residual))))
    _, name, coefficients, rss, max_residual = best
    return {"model": name, "coefficients": coefficients,
            "r2": float(1 - rss / total), "max_abs_residual": max_residual,
            "n_points": count}


def analyze_operator(operator: Operator, runtime, oracle: Oracle,
                     encoder: Z3Encoder | None = None) -> dict:
    """Measure one defined operator and return its cost fit and branch coverage."""
    if operator.definition is None:
        raise ValueError("complexity analysis requires a defined operator")
    definition = oracle._definition_of(operator)
    witnesses = [None] * len(definition.branches)
    if encoder is not None:
        try:
            witnesses = branch_witnesses(operator, encoder)
        except NotExpressible:
            pass
    bound = runtime.semantics.bound
    points = {point for point in measurement_grid(operator)
              if bound is None or all(abs(value) <= bound for value in point)}
    points.update(witness for witness in witnesses if witness is not None)
    measured = []
    hit = set()
    evaluator = runtime.evaluate(operator)
    for args in sorted(points):
        branch = selected_branch(operator, args, oracle)
        if branch is not None:
            hit.add(branch)
        value, base_ops, _ = evaluator(*args)
        if value is not NAN:
            measured.append((args, base_ops))
    return {"func_id": operator.func_id, "symbol": operator.symbol,
            **_fit(operator, oracle, measured),
            "branch_coverage": len(hit) / len(definition.branches)}


def analyze_registry(registry: OperatorRegistry, runtime, *, symbols: Symbols | None = None) -> Iterator[dict]:
    """Analyze every defined operator using the runtime's configured semantics."""
    oracle = Oracle(registry, symbols or Symbols(), runtime.semantics)
    try:
        encoder = Z3Encoder(oracle)
    except NotExpressible:
        encoder = None  # legacy mode has no exact z3 encoding
    for operator in registry:
        if operator.definition is not None:
            yield analyze_operator(operator, runtime, oracle, encoder)
