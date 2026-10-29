"""Fill-in-the-blank problems and their reverse derivation.

A problem replaces one number of an evaluated expression by the unknown
``x``: ``E(x) = R``. Solutions are searched in a stated integer domain: by
default the whole value domain ``[-B, B]`` with z3; when z3 cannot decide,
by exhaustive evaluation over a small stated range. A problem is *unique*
when exactly one ``x`` in its domain solves it; the domain is part of the
problem, so "unique" is always a precise claim.

The reverse derivation peels operators from the outside: at an application
``f(..., s, ...) = R`` whose other arguments are known, solve for the value
``s`` of the sub-expression that contains ``x``, then continue inside it.
Every step lists all candidate values (non-injective operators can give
several); every candidate is re-checked forward with the reference oracle.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import z3

from opulse.core.semantics import NAN
from opulse.expression.nodes import Call, Node, Number, Variable, to_ast
from opulse.solver.fallback import checked_label, resolve_range
from opulse.solver.isolated import check as isolated_check
from opulse.solver.z3_encode import NotExpressible, Z3Encoder, ZVal, const

HOLE = "x"


@dataclass
class Solutions:
    values: list[int]
    complete: bool  # True when no other solution exists in the domain
    method: str  # "z3" | "exhaustive"
    domain: tuple[int, int]

    @property
    def unique(self) -> bool:
        return self.complete and len(self.values) == 1

    @property
    def strength(self) -> str:
        if self.method == "z3":
            return "proved" if self.complete else "incomplete z3 enumeration"
        return checked_label(self.domain)


@dataclass
class ReverseStep:
    operator_symbol: str
    known: dict[int, object]  # argument position -> known value
    unknown_position: int
    target: object
    candidates: list[int]
    complete: bool
    domain: tuple[int, int] | None = None  # where this step's candidates were searched


@dataclass
class HoleProblem:
    expression: Node  # contains Variable(HOLE) exactly once
    target: int
    answer: int  # the number that was removed
    solutions: Solutions
    reverse: list[ReverseStep] = field(default_factory=list)


def _numbers(node: Node) -> set[int]:
    if isinstance(node, Number):
        return set() if node.value is NAN else {node.value}
    if isinstance(node, Call):
        return set().union(*(_numbers(arg) for arg in node.args))
    return set()


def hole_paths(node: Node, path: tuple = ()) -> list[tuple]:
    """Paths of every number leaf."""
    if isinstance(node, Number):
        return [path]
    if isinstance(node, Call):
        return [p for i, arg in enumerate(node.args) for p in hole_paths(arg, path + (i,))]
    return []


def replace(node: Node, path: tuple, new: Node) -> Node:
    if not path:
        return new
    head, *rest = path
    args = list(node.args)
    args[head] = replace(args[head], tuple(rest), new)
    return Call(node.operator, tuple(args))


def subtree(node: Node, path: tuple) -> Node:
    for i in path:
        node = node.args[i]
    return node


class HoleSolver:
    def __init__(self, encoder: Z3Encoder | None, oracle, timeout_ms: int = 30_000,
                 fallback_domain: tuple[int, int] = (-200, 200), max_solutions: int = 5,
                 max_nodes: int = 300,
                 not_expressible_domain: tuple[int, int] | None = None,
                 rlimit: int = 5_000_000) -> None:
        self.encoder = encoder
        self.max_nodes = max_nodes
        self.rlimit = rlimit
        self.oracle = oracle
        self.timeout_ms = timeout_ms
        self.fallback_domain = fallback_domain
        self.not_expressible_domain = resolve_range(not_expressible_domain, None, oracle.semantics.bound)
        self.max_solutions = max_solutions

    # ---------------------------------------------------------------- values
    def value(self, node: Node, x: int | None = None):
        env = {} if x is None else {HOLE: x}
        return self.oracle.evaluate_expr(to_ast(node), env).value

    # ------------------------------------------------------------- solving
    def solve(self, expression: Node, target) -> Solutions:
        """All x with ``expression(x)`` equal to ``target`` (an int) or in it (a set of ints)."""
        targets = {target} if isinstance(target, int) else set(target)
        if self.encoder is None and self.not_expressible_domain is not None:
            return self._exhaustive(expression, targets, self.not_expressible_domain, "fallback")
        if self.encoder is not None and self.encoder.bound is not None and len(targets) <= 64:
            try:
                found = self._z3(expression, targets)
                if found is not None:
                    return found
            except NotExpressible:
                if self.not_expressible_domain is not None:
                    return self._exhaustive(expression, targets, self.not_expressible_domain, "fallback")
        return self._exhaustive(expression, targets)

    def _z3(self, expression: Node, targets: set[int]) -> Solutions | None:
        x = z3.Int(HOLE)
        self.encoder.reset()
        for value in _numbers(expression) | targets:
            self.encoder.admit(value)
        self.encoder.max_nodes, saved = self.max_nodes, self.encoder.max_nodes
        try:
            zv = self._encode(expression, ZVal(z3.BoolVal(True), x))
        finally:
            self.encoder.max_nodes = saved
        constraints = [self.encoder.in_bound(x), zv.defined,
                       z3.Or([zv.value == t for t in sorted(targets)])]
        values: list[int] = []
        while len(values) <= self.max_solutions:
            status, model = isolated_check(constraints, self.timeout_ms, rlimit=self.rlimit,
                                           variables=[HOLE])
            if status == "unsat":
                return Solutions(sorted(values), True, "z3", (-self.encoder.bound, self.encoder.bound))
            if status != "sat":
                return None
            v = model[HOLE]
            if self.value(expression, v) not in targets:
                raise AssertionError(f"z3 solution x={v} does not satisfy the reference semantics")
            values.append(v)
            constraints.append(x != v)
        return Solutions(sorted(values), False, "z3", (-self.encoder.bound, self.encoder.bound))

    def _encode(self, node: Node, hole: ZVal) -> ZVal:
        if isinstance(node, Variable):
            return hole
        if isinstance(node, Number):
            return const(node.value) if node.value is not NAN else ZVal(z3.BoolVal(False), z3.IntVal(0))
        args = [self._encode(arg, hole) for arg in node.args]
        return self.encoder._apply(node.operator, args, 0)

    def _exhaustive(self, expression: Node, targets: set[int], domain=None,
                    method: str = "exhaustive") -> Solutions:
        lo, hi = self.fallback_domain if domain is None else domain
        bound = self.encoder.bound if self.encoder is not None else None
        if bound is not None:
            lo, hi = max(lo, -bound), min(hi, bound)
        values = [v for v in range(lo, hi + 1) if self.value(expression, v) in targets]
        return Solutions(values, True, method, (lo, hi))

    # ------------------------------------------------------------ problems
    def problem(self, tree: Node, path: tuple, with_reverse: bool = True) -> HoleProblem | None:
        """Blank out the number at ``path``; optionally defer its reverse derivation."""
        target = self.value(tree)
        if target is NAN:
            return None
        answer = subtree(tree, path).value
        expression = replace(tree, path, Variable(HOLE))
        solutions = self.solve(expression, target)
        if answer not in solutions.values:
            lo, hi = solutions.domain
            if solutions.complete and lo <= answer <= hi:
                raise AssertionError(f"the removed number {answer} is missing from the complete solutions")
            # Enumeration stopped early (or the answer lies outside the searched range).
            solutions.values = sorted(set(solutions.values) | {answer})
            solutions.complete = False
        return HoleProblem(expression, target, answer, solutions,
                           self.reverse(tree, path) if with_reverse else [])

    def reverse(self, tree: Node, path: tuple) -> list[ReverseStep]:
        """Outside-in derivation along ``path`` (the hole's position) of the original ``tree``.

        Step i solves ``f(..., s_i, ...) = t`` for every target ``t`` kept from step i-1.
        A step is complete only when its own enumeration is complete and so is every
        earlier step; the true intermediate value is always checked to be a candidate.
        """
        steps: list[ReverseStep] = []
        node, targets, complete = tree, [self.value(tree)], True
        for position in path:
            known = {i: self.value(arg) for i, arg in enumerate(node.args) if i != position}
            truth = self.value(node.args[position])
            if truth is NAN:
                # The sub-expression holding x is undefined, yet the operator above it is defined
                # (its definition does not need that argument). Integer candidates cannot describe
                # this, so the derivation stops here, marked incomplete.
                steps.append(ReverseStep(node.operator.symbol, known, position,
                                         targets[0] if len(targets) == 1 else targets, [], False, None))
                break
            found = self._solve_slot(node, position, known, targets)
            candidates = set(found.values)
            lo, hi = found.domain
            complete &= found.complete and lo <= truth <= hi
            for s in candidates:  # forward check of every candidate
                args = [Number(s) if i == position else Number(known[i]) for i in range(len(node.args))]
                if self.value(Call(node.operator, tuple(args))) not in targets:
                    raise AssertionError("reverse step candidate fails the forward check")
            if truth not in candidates:
                if complete:
                    raise AssertionError("the true intermediate value is missing from a complete step")
                candidates.add(truth)
            steps.append(ReverseStep(node.operator.symbol, known, position,
                                     targets[0] if len(targets) == 1 else targets,
                                     sorted(candidates), complete, found.domain))
            node, targets = node.args[position], sorted(candidates)
        return steps

    def _solve_slot(self, node: Call, position: int, known: dict, target) -> Solutions:
        args = tuple(Variable(HOLE) if i == position else Number(known[i]) for i in range(len(node.args)))
        return self.solve(Call(node.operator, args), target)



def all_problems(solver: HoleSolver, tree: Node) -> list[HoleProblem]:
    problems = []
    for path in hole_paths(tree):
        problem = solver.problem(tree, path)
        if problem is not None:
            problems.append(problem)
    return problems


__all__ = ["HOLE", "HoleProblem", "HoleSolver", "ReverseStep", "Solutions", "all_problems",
           "hole_paths"]
