"""Differential checks: every backend must agree with the reference oracle.

Inputs are random values plus boundary values that the definition itself
suggests: the integer literals it mentions (branch thresholds, moduli) and
their neighbours, 0, +-1, and values around the semantic bound.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from itertools import product

from opulse.core.operator import Operator
from opulse.core.semantics import Semantics
from opulse.definition import ast
from opulse.verify.oracle import Oracle

Triple = tuple  # (value, base_ops, calls)


@dataclass(frozen=True)
class Mismatch:
    operator: str
    inputs: tuple
    expected: Triple
    actual: Triple | str

    def __str__(self) -> str:
        return f"{self.operator}{self.inputs}: expected {self.expected}, got {self.actual}"


def literals(definition: ast.Definition) -> set[int]:
    """Integer literals appearing anywhere in a definition."""
    found: set[int] = set()

    def walk(node) -> None:
        if isinstance(node, ast.Num):
            found.add(node.value)
        elif isinstance(node, ast.Search):
            found.add(node.bound)
            walk(node.condition)
        elif isinstance(node, ast.Apply):
            for arg in node.args:
                walk(arg)
        elif isinstance(node, (ast.Compare, ast.And, ast.Or)):
            walk(node.left)
            walk(node.right)
        elif isinstance(node, ast.Not):
            walk(node.operand)

    for branch in definition.branches:
        walk(branch.expr)
        if branch.condition is not None:
            walk(branch.condition)
    return found


def boundary_values(definition: ast.Definition | None, semantics: Semantics) -> list[int]:
    values = {0, 1, -1, 2, -2, 7, -7, 10, -10, 99, -99, 100, -100}
    if definition is not None:
        for n in literals(definition):
            values.update({n - 1, n, n + 1, -n - 1, -n, -n + 1})
    if semantics.bound is not None:
        b = semantics.bound
        values.update({b, -b, b - 1, -(b - 1), b // 2, -(b // 2)})
    return sorted(values)


def input_tuples(operator: Operator, definition: ast.Definition | None, semantics: Semantics,
                 rng: random.Random, random_trials: int, value_range: tuple[int, int],
                 max_boundary_pairs: int = 400) -> Iterator[tuple]:
    if operator.result_type != "int" or any(kind != "int" for kind in operator.parameter_types):
        kinds = operator.parameter_types
        per_type = {
            "int": boundary_values(definition, semantics),
            "bool": [False, True],
            "str": ["", "a", "B", "ab", "a b", "xy"],
            "list[int]": [(), (0,), (1, 2), (-1, 0, 3)],
            "note": [0, 48, 60, 64, 72, 120, 127],
            "melody": [(), ((60, 1),), ((60, 1), (64, 2), (67, 1))],
        }
        combinations = list(product(*(per_type[kind] for kind in kinds)))
        if len(combinations) > max_boundary_pairs:
            combinations = rng.sample(combinations, max_boundary_pairs)
        yield from combinations
        from opulse.generation.typed import sample_value

        for _ in range(random_trials):
            yield tuple(sample_value(kind, rng) for kind in kinds)
        return
    edges = boundary_values(definition, semantics)
    if operator.n_ary == 1:
        yield from ((v,) for v in edges)
    elif operator.n_ary == 2:
        pairs = list(product(edges, repeat=2))
        if len(pairs) > max_boundary_pairs:
            pairs = rng.sample(pairs, max_boundary_pairs)
        yield from pairs
    else:  # three or more arguments: boundary values combined at random (the full grid is too large)
        yield tuple(edges[0] for _ in range(operator.n_ary))
        for _ in range(max_boundary_pairs):
            yield tuple(rng.choice(edges) for _ in range(operator.n_ary))
    for _ in range(random_trials):
        yield tuple(rng.randint(*value_range) for _ in range(operator.n_ary))


def check_operator(operator: Operator, evaluate: Callable[..., Triple], oracle: Oracle,
                   rng: random.Random, random_trials: int = 200,
                   value_range: tuple[int, int] = (-1000, 1000),
                   inputs: Iterable[tuple] | None = None) -> list[Mismatch]:
    """Compare ``evaluate(*args)`` with the oracle on boundary and random inputs."""
    definition = oracle._definition_of(operator) if operator.definition else None
    if inputs is None:
        inputs = input_tuples(operator, definition, oracle.semantics, rng, random_trials, value_range)
    mismatches = []
    for args in inputs:
        reference = oracle.evaluate(operator, args)
        expected = (reference.value, reference.base_ops, reference.calls)
        try:
            actual = tuple(evaluate(*args))
        except Exception as exc:  # noqa: BLE001 - any exception is a disagreement
            actual = f"raises {type(exc).__name__}: {exc}"
        if actual != expected:
            mismatches.append(Mismatch(operator.symbol, tuple(args), expected, actual))
    return mismatches
