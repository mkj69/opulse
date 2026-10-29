"""Algebraic properties of operators, including commutativity.

Equality is equality in V = Z u {NaN}: two sides agree when both are NaN or
both are defined and equal. Each property gets one of four verdicts:

* ``proved``    - z3 shows no counterexample exists in the value domain [-B, B];
* ``refuted``   - a counterexample, found by a concrete search (small range, then
                  boundary values) or by z3 and always re-checked with the oracle;
* ``bounded``   - z3 could not decide; no counterexample on an exhaustive small
                  range (the range is recorded);
* ``not_found`` - (identity / absorbing element) no element among the candidates
                  works; other elements were not ruled out (candidates' range recorded);
* ``undecided`` - neither z3 nor the bounded check applies.

Laws over all integers are undecidable in general (nonlinear arithmetic), so
``bounded`` is the honest answer when z3 reaches its resource limit.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable
from dataclasses import dataclass, field

import z3

from opulse.core.operator import Operator
from opulse.core.semantics import NAN
from opulse.definition.interpreter import EngineError
from opulse.solver.fallback import checked_label, resolve_range
from opulse.solver.isolated import check as isolated_check
from opulse.solver.z3_encode import NotExpressible, Z3Encoder, ZVal, const

BINARY_PROPERTIES = ("commutative", "associative", "idempotent", "left_identity", "right_identity",
                     "left_absorbing", "right_absorbing")
UNARY_PROPERTIES = ("involution", "idempotent", "odd", "even")
NARY_PROPERTIES = ("symmetric", "idempotent")


def properties_for(n_ary: int) -> tuple[str, ...]:
    """The laws meaningful for an operator of this arity."""
    return {1: UNARY_PROPERTIES, 2: BINARY_PROPERTIES}.get(n_ary, NARY_PROPERTIES if n_ary >= 3 else ())


@dataclass
class Verdict:
    status: str
    counterexample: list | None = None
    witness: int | None = None  # the element, for identity/absorbing properties
    range: list[int] | None = None  # for ``bounded``
    strength: str | None = None

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class _Law:
    """``lhs(xs) == rhs(xs)`` for all ``xs``; both sides built symbolically and concretely."""

    arity: int
    symbolic: Callable[[list[ZVal]], tuple[ZVal, ZVal]]
    concrete: Callable[[tuple], tuple]
    candidates: list[int] = field(default_factory=list)


def same(x, y) -> bool:
    return (x is NAN and y is NAN) or (x is not NAN and y is not NAN and x == y)


class PropertyChecker:
    def __init__(self, encoder: Z3Encoder, timeout_ms: int = 30_000, small_range: int = 12,
                 max_nodes: int = 20_000, fallback_range: tuple[int, int] | None = None,
                 rlimit: int = 5_000_000) -> None:
        self.encoder = encoder
        self.max_nodes = max_nodes
        self.rlimit = rlimit
        self.oracle = encoder.oracle
        self.timeout_ms = timeout_ms
        self.small_range = small_range
        self.fallback_range = resolve_range(fallback_range, None, encoder.bound)

    # ------------------------------------------------------------ public API
    def check_all(self, operator: Operator) -> dict[str, dict]:
        """Every law of the operator's arity."""
        return {name: self.check(operator, name).to_dict() for name in properties_for(operator.n_ary)}

    def check(self, operator: Operator, name: str) -> Verdict:
        names = properties_for(operator.n_ary)
        if name not in names:
            raise ValueError(f"{name!r} is not a property of {operator.n_ary}-ary operators; use one of {names}")
        if name in ("left_identity", "right_identity", "left_absorbing", "right_absorbing"):
            return self._element(operator, name)
        if name == "symmetric":
            verdicts = [self._decide(self._symmetry_law(operator, index))
                        for index in range(operator.n_ary - 1)]
            return next((v for v in verdicts if v.status == "refuted"),
                        Verdict("proved") if all(v.status == "proved" for v in verdicts)
                        else next(v for v in verdicts if v.status != "proved"))
        return self._decide(self._law(operator, name))

    def distributes_over(self, f: Operator, g: Operator) -> Verdict:
        """f(a, g(b, c)) == g(f(a, b), f(a, c))."""
        enc, ev = self.encoder, self._value

        def symbolic(x):
            return (enc._apply(f, [x[0], enc._apply(g, [x[1], x[2]], 0)], 0),
                    enc._apply(g, [enc._apply(f, [x[0], x[1]], 0), enc._apply(f, [x[0], x[2]], 0)], 0))

        def concrete(a):
            return ev(f, (a[0], ev(g, (a[1], a[2])))), ev(g, (ev(f, (a[0], a[1])), ev(f, (a[0], a[2]))))

        return self._decide(_Law(3, symbolic, concrete))

    # ------------------------------------------------------------- internals
    def _value(self, operator: Operator, args: tuple):
        # NaN arguments (from an undefined inner application) go through the definition too:
        # a definition that never compares or uses that argument can still be defined.
        return self.oracle.evaluate(operator, args).value

    def _law(self, f: Operator, name: str) -> _Law:
        enc, ev = self.encoder, self._value
        app = lambda *xs: enc._apply(f, list(xs), 0)
        if name == "idempotent" and f.n_ary >= 3:
            return _Law(1, lambda x: (app(*([x[0]] * f.n_ary)), x[0]),
                        lambda a: (ev(f, (a[0],) * f.n_ary), a[0]))
        if name == "commutative":
            return _Law(2, lambda x: (app(x[0], x[1]), app(x[1], x[0])),
                        lambda a: (ev(f, (a[0], a[1])), ev(f, (a[1], a[0]))))
        if name == "associative":
            return _Law(3, lambda x: (app(app(x[0], x[1]), x[2]), app(x[0], app(x[1], x[2]))),
                        lambda a: (ev(f, (ev(f, (a[0], a[1])), a[2])), ev(f, (a[0], ev(f, (a[1], a[2]))))))
        if name == "idempotent" and f.n_ary == 2:
            return _Law(1, lambda x: (app(x[0], x[0]), x[0]), lambda a: (ev(f, (a[0], a[0])), a[0]))
        if name == "idempotent":
            return _Law(1, lambda x: (app(app(x[0])), app(x[0])), lambda a: (ev(f, (ev(f, a),)), ev(f, a)))
        if name == "involution":
            return _Law(1, lambda x: (app(app(x[0])), x[0]), lambda a: (ev(f, (ev(f, a),)), a[0]))
        neg = self._negate
        if name == "odd":
            return _Law(1, lambda x: (app(neg(x[0])), neg(app(x[0]))),
                        lambda a: (ev(f, (-a[0],)), _neg(ev(f, a))))
        if name == "even":
            return _Law(1, lambda x: (app(neg(x[0])), app(x[0])), lambda a: (ev(f, (-a[0],)), ev(f, a)))
        raise ValueError(f"unknown property {name!r}")

    def _symmetry_law(self, f: Operator, index: int) -> _Law:
        """Adjacent exchanges generate every permutation of the arguments."""
        enc, ev = self.encoder, self._value

        def exchanged(xs):
            swapped = list(xs)
            swapped[index], swapped[index + 1] = swapped[index + 1], swapped[index]
            return swapped

        return _Law(f.n_ary,
                    lambda xs: (enc._apply(f, xs, 0), enc._apply(f, exchanged(xs), 0)),
                    lambda xs: (ev(f, tuple(xs)), ev(f, tuple(exchanged(xs)))))

    @staticmethod
    def _negate(x: ZVal) -> ZVal:
        return ZVal(x.defined, -x.value)

    def _element(self, f: Operator, name: str) -> Verdict:
        """Search a small set of candidate elements, then prove the law for the first that holds."""
        enc, ev = self.encoder, self._value
        left = name.startswith("left")
        absorbing = name.endswith("absorbing")
        candidates = sorted(set(range(-3, 4)) | _literals(self.oracle, f), key=abs)
        if enc.bound is not None:
            candidates = [e for e in candidates if abs(e) <= enc.bound]
        for e in candidates:
            def symbolic(x, e=e):
                args = [const(e), x[0]] if left else [x[0], const(e)]
                return enc._apply(f, args, 0), (const(e) if absorbing else x[0])

            def concrete(a, e=e):
                args = (e, a[0]) if left else (a[0], e)
                return ev(f, args), (e if absorbing else a[0])

            # Cheap filter before asking z3.
            if not (self.fallback_range is not None and not enc.expressible(f)) and any(
                    not same(*concrete((a,))) for a in self._clip(range(-self.small_range, self.small_range + 1))):
                continue
            verdict = self._decide(_Law(1, symbolic, concrete))
            if verdict.status != "refuted":
                verdict.witness = e
                return verdict
        # No candidate works, but no proof that no element works: say so (review finding).
        strength = (checked_label(self.fallback_range)
                    if self.fallback_range is not None and not enc.expressible(f) else None)
        return Verdict("not_found", range=[min(candidates), max(candidates)], strength=strength)

    def _decide(self, law: _Law) -> Verdict:
        if self.fallback_range is not None:
            try:
                verdict = self._z3(law)
            except NotExpressible:
                return self._fallback(law)
            if verdict is not None:
                return verdict
        # Most laws fail; a concrete counterexample is cheaper than a solver call.
        found = self._search(law)
        if found is not None:
            return found
        try:
            verdict = self._z3(law)
            if verdict is not None:
                return verdict
        except NotExpressible:
            pass
        return self._bounded(law)

    def _fallback(self, law: _Law) -> Verdict:
        lo, hi = self.fallback_range
        label = checked_label(self.fallback_range)
        for point in itertools.product(range(lo, hi + 1), repeat=law.arity):
            if not same(*law.concrete(point)):
                return Verdict("refuted", counterexample=list(point), range=[lo, hi], strength=label)
        return Verdict("checked", range=[lo, hi], strength=label)

    def _z3(self, law: _Law) -> Verdict | None:
        enc = self.encoder
        xs = [z3.Int(f"x{i}") for i in range(law.arity)]
        args = [ZVal(z3.BoolVal(True), x) for x in xs]
        enc.reset()
        enc.max_nodes, saved = self.max_nodes, enc.max_nodes
        try:
            lhs, rhs = law.symbolic(args)
        finally:
            enc.max_nodes = saved
        differ = z3.Or(lhs.defined != rhs.defined,
                       z3.And(lhs.defined, rhs.defined, lhs.value != rhs.value))
        status, model = isolated_check([*[enc.in_bound(x) for x in xs], differ], self.timeout_ms,
                                       rlimit=self.rlimit, variables=[str(x) for x in xs])
        if status == "unsat":
            return Verdict("proved")
        if status == "sat":
            point = tuple(model[str(x)] for x in xs)
            left, right = law.concrete(point)
            if same(left, right):
                raise EngineError(f"z3 counterexample {point} is not one for the reference semantics")
            return Verdict("refuted", counterexample=list(point))
        return None  # z3 returned unknown

    def _small_points(self, arity: int):
        r = self.small_range if arity <= 2 else max(1, min(3, int(4000 ** (1 / arity)) // 2))
        if self.encoder.bound is not None:
            r = min(r, self.encoder.bound)  # never look outside the value domain [-B, B]
        return r, itertools.product(range(-r, r + 1), repeat=arity)

    def _clip(self, values):
        bound = self.encoder.bound
        return [v for v in values if bound is None or abs(v) <= bound]

    def _search(self, law: _Law) -> Verdict | None:
        """Small exhaustive range, then combinations of boundary values."""
        _, small = self._small_points(law.arity)
        bound = self.encoder.bound or 2**31 - 1
        edges = [0, 1, -1, 2, -2, 100, -100, bound, -bound, bound - 1, -(bound - 1), bound // 2, -(bound // 2)]
        edge_points = itertools.islice(itertools.product(self._clip(dict.fromkeys(edges)),
                                                       repeat=law.arity), 4096)
        for point in itertools.chain(small, edge_points):
            left, right = law.concrete(point)
            if not same(left, right):
                return Verdict("refuted", counterexample=list(point))
        return None

    def _bounded(self, law: _Law) -> Verdict:
        r, _ = self._small_points(law.arity)
        return Verdict("bounded", range=[-r, r])


def _neg(value):
    return NAN if value is NAN else -value


def _literals(oracle, operator: Operator) -> set[int]:
    from opulse.verify.differential import literals

    try:
        return {n for n in literals(oracle._definition_of(operator)) if abs(n) <= 100}
    except Exception:  # noqa: BLE001 - base operators have no definition
        return set()
