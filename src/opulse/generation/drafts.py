"""Candidate definitions ("drafts") for simple and branch operators.

A draft is the definition as a syntax tree plus the new operator's surface
shape. It has no code yet; :mod:`opulse.generation.pipeline` compiles,
checks and registers it.

Branch conditions partition the input space into axis-aligned regions:

* unary: thresholds ``t1 < ... < tn`` on ``a`` give regions ``a < t1``,
  ``t1 <= a < t2``, ..., ``a >= tn``;
* binary: thresholds on ``a`` and on ``b`` give a grid of rectangles;
* three or more parameters: the binary grid on two parameters chosen at random.

Thresholds are distinct, so every region is non-empty (the legacy generator
could emit dead branches such as ``b >= 15 and b < 15``). Regions are shuffled,
the first ``k-1`` become ``if`` branches and the last body is the ``else``.
With probability ``operators.partial_probability`` the definition is partial
instead: all ``k`` bodies get a region and there is no ``else``, so inputs in
the remaining regions are undefined (docs/reference/semantics.md section 4, rule 3).
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from itertools import pairwise

from opulse.config import OperatorSettings, Symbols
from opulse.core.operator import BINARY, BRANCH, SIMPLE, Operator
from opulse.definition import ast
from opulse.expression.nodes import Node, to_ast

Interval = tuple[int | None, int | None]  # [low, high), None = unbounded


@dataclass(frozen=True)
class Draft:
    symbol: str
    n_ary: int
    unary_position: str | None
    definition: ast.Definition
    definition_type: str
    # Set when the structural metrics cannot be derived from the definition (recursion).
    complexity: tuple[int, int] | None = None
    recursion_style: str | None = None
    parameter_types: tuple[str, ...] | None = None
    result_type: str = "int"


def lhs(symbol: str, n_ary: int, unary_position: str | None, symbols: Symbols) -> ast.Apply:
    params = tuple(ast.Var(name) for name in symbols.operands(n_ary))
    return ast.Apply(symbol, params, unary_position)


def simple_draft(symbol, n_ary, unary_position, body: Node, symbols: Symbols) -> Draft:
    definition = ast.Definition(lhs(symbol, n_ary, unary_position, symbols), (ast.Branch(to_ast(body)),))
    return Draft(symbol, n_ary, unary_position, definition, SIMPLE)


def branch_draft(symbol, n_ary, unary_position, bodies: list[Node], settings: OperatorSettings,
                 symbols: Symbols, rng: random.Random, defined_symbol: str | None = None,
                 division_symbol: str | None = None, condition_atom: Operator | None = None) -> Draft:
    if len(bodies) < 2:
        raise ValueError("a branch definition needs at least two bodies")
    names = symbols.operands(n_ary)
    partial = rng.random() < settings.partial_probability
    terms = {name: _condition_term(name, condition_atom) for name in names}
    limit = settings.max_condition_comparisons
    if limit == 1:
        # Ordered cuts use first-match semantics and one comparison per guard.
        name = rng.choice(names)
        cuts = _thresholds(len(bodies) if partial else len(bodies) - 1, settings, rng)
        if len(cuts) < (len(bodies) if partial else len(bodies) - 1):
            raise ValueError("condition threshold range is too small for the branch count")
        branches = [ast.Branch(to_ast(body), ast.Compare(terms[name], "<", ast.Num(cut)))
                    for body, cut in zip(bodies, cuts)]
    else:
        # One-dimensional intervals need at most two comparisons.
        if limit is not None and limit < 4:
            name = rng.choice(names)
            needed = len(bodies) + (1 if partial else 0)
            cuts = _thresholds(needed, settings, rng)
            if len(cuts) < needed:
                raise ValueError("condition threshold range is too small for the branch count")
            regions = [(part,) for part in _intervals(cuts)]
            region_names = (name,)
        else:
            regions = _regions(len(bodies) + (1 if partial else 0), n_ary, settings, rng)
            region_names = names
        if len(regions) < len(bodies) + (1 if partial else 0):
            raise ValueError("condition threshold range is too small for the branch count")
        rng.shuffle(regions)
        guarded = bodies if partial else bodies[:-1]
        branches = [ast.Branch(to_ast(body), _region_condition(region, region_names, terms))
                    for body, region in zip(guarded, regions)]
    if defined_symbol is not None and rng.random() < 0.5:
        name = rng.choice(names)
        probe = (ast.Apply(division_symbol, (ast.Num(1), ast.Var(name))) if division_symbol else
                 to_ast(bodies[0]))
        branches[0] = ast.Branch(to_ast(bodies[0]), ast.Compare(
            ast.Apply(defined_symbol, (probe,), "prefix"), "==", ast.Num(0 if division_symbol else 1)))
    if not partial:
        branches.append(ast.Branch(to_ast(bodies[-1]), is_else=True))
    definition = ast.Definition(lhs(symbol, n_ary, unary_position, symbols), tuple(branches))
    return Draft(symbol, n_ary, unary_position, definition, BRANCH)


def _thresholds(count: int, settings: OperatorSettings, rng: random.Random) -> list[int]:
    span = range(settings.condition_min, settings.condition_max + 1)
    return sorted(rng.sample(span, min(count, len(span))))


def _intervals(thresholds: list[int]) -> list[Interval]:
    bounds: list[int | None] = [None, *thresholds, None]
    return list(pairwise(bounds))


def _regions(branch_count: int, n_ary: int, settings: OperatorSettings, rng: random.Random) -> list:
    """At least ``branch_count`` non-empty regions (one interval per parameter).

    Three or more parameters: a grid on two parameters chosen at random; the others are free.
    """
    if n_ary > BINARY:
        first, second = sorted(rng.sample(range(n_ary), 2))
        grid = _regions(branch_count, BINARY, settings, rng)
        free = (None, None)
        return [tuple(a if i == first else b if i == second else free for i in range(n_ary)) for a, b in grid]
    if n_ary == BINARY:
        cuts_a = rng.randint(1, branch_count)
        cuts_b = branch_count // cuts_a + 1
        a_parts = _intervals(_thresholds(cuts_a, settings, rng))
        b_parts = _intervals(_thresholds(cuts_b, settings, rng))
        return [(a, b) for a in a_parts for b in b_parts]
    return [(part,) for part in _intervals(_thresholds(branch_count, settings, rng))]


def _condition_term(name: str, atom: Operator | None) -> ast.Expr:
    var = ast.Var(name)
    if atom is None:
        return var
    args = (var,) if atom.n_ary == 1 else (var, ast.Num(2))
    return ast.Apply(atom.symbol, args, atom.unary_position)


def _interval_condition(term: ast.Expr, interval: Interval) -> ast.Condition | None:
    low, high = interval
    parts = []
    if low is not None:
        parts.append(ast.Compare(term, ">=", ast.Num(low)))
    if high is not None:
        parts.append(ast.Compare(term, "<", ast.Num(high)))
    return _conjoin(parts)


def _region_condition(region: tuple[Interval, ...], names: tuple[str, ...],
                      terms: dict[str, ast.Expr]) -> ast.Condition:
    parts = [cond for name, interval in zip(names, region)
             if (cond := _interval_condition(terms[name], interval))]
    condition = _conjoin(parts)
    assert condition is not None, "every region is bounded in at least one direction"
    return condition


def _conjoin(parts: list[ast.Condition]) -> ast.Condition | None:
    if not parts:
        return None
    condition = parts[0]
    for part in parts[1:]:
        condition = ast.And(condition, part)
    return condition
