"""Equivalence of expressions and operators.

Two expressions over integer variables are *equivalent* when they agree, as
values in ``ℤ ∪ {NaN}``, for every assignment of the variables in ``[-B, B]``.
Verdicts follow :mod:`opulse.solver.properties`:

* ``refuted`` - a counterexample assignment (concrete search or z3), always
  re-checked with the reference oracle;
* ``proved``  - z3 shows that no counterexample exists;
* ``bounded`` - z3 could not decide within its resource limit; no counterexample on the
  recorded small range.

SymPy is used only to *propose* simplifications of the arithmetic part
(``+ - *`` and negation); whether a proposal is valid is decided here under
Opulse semantics. With a bound it often is not: ``(a + b) - b`` and ``a``
differ where ``a + b`` overflows to NaN.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

import z3

from opulse.config import Symbols
from opulse.core.operator import Operator
from opulse.core.registry import OperatorRegistry
from opulse.core.semantics import NAN, base_operation_name
from opulse.expression.nodes import Call, Node, Number, Variable, to_ast
from opulse.solver.fallback import checked_label, resolve_range
from opulse.solver.isolated import check as isolated_check
from opulse.solver.z3_encode import NotExpressible, Z3Encoder, ZVal, const

EDGES = (0, 1, -1, 2, -2, 7, -7, 100, -100)


@dataclass
class Equivalence:
    status: str  # "proved" | "refuted" | "bounded" | "checked"
    counterexample: dict[str, int] | None = None
    left_value: object = None  # values at the counterexample
    right_value: object = None
    range: list[int] | None = None
    strength: str | None = None

    @property
    def equivalent(self) -> bool | None:
        return {"proved": True, "refuted": False}.get(self.status)

    def to_dict(self) -> dict:
        data = {"status": self.status, "equivalent": self.equivalent}
        if self.strength is not None:
            data["strength"] = self.strength
        if self.counterexample is not None:
            data.update(counterexample=self.counterexample, left_value=_json(self.left_value),
                        right_value=_json(self.right_value))
        if self.range is not None:
            data["range"] = self.range
        return data


def variables_of(node: Node) -> tuple[str, ...]:
    if isinstance(node, Variable):
        return (node.name,)
    if isinstance(node, Call):
        return tuple(dict.fromkeys(name for arg in node.args for name in variables_of(arg)))
    return ()


class EquivalenceChecker:
    def __init__(self, encoder: Z3Encoder, timeout_ms: int = 30_000, small_range: int = 6,
                 max_nodes: int = 20_000, fallback_range: tuple[int, int] | None = None,
                 rlimit: int = 5_000_000) -> None:
        self.encoder = encoder
        self.oracle = encoder.oracle
        self.timeout_ms = timeout_ms
        self.small_range = small_range
        self.max_nodes = max_nodes
        self.rlimit = rlimit
        self.fallback_range = resolve_range(fallback_range, None, encoder.bound)

    def value(self, node: Node, env: dict[str, int]):
        return self.oracle.evaluate_expr(to_ast(node), env).value

    def check(self, left: Node, right: Node) -> Equivalence:
        if not _integer_expression(left) or not _integer_expression(right):
            raise NotExpressible("equivalence checking supports integer expressions only")
        names = tuple(dict.fromkeys(variables_of(left) + variables_of(right)))
        if self.fallback_range is not None:
            try:
                verdict = self._z3(left, right, names)
            except NotExpressible:
                return self._fallback(left, right, names)
            if verdict is not None:
                return verdict
        found = self._search(left, right, names)
        if found is not None:
            return found
        try:
            verdict = self._z3(left, right, names)
            if verdict is not None:
                return verdict
        except NotExpressible:
            pass
        return Equivalence("bounded", range=[-self.small_range, self.small_range])

    def _fallback(self, left: Node, right: Node, names: tuple[str, ...]) -> Equivalence:
        lo, hi = self.fallback_range
        label = checked_label(self.fallback_range)
        for point in itertools.product(range(lo, hi + 1), repeat=len(names)):
            env = dict(zip(names, point))
            diff = self._differ(left, right, env)
            if diff is not None:
                return Equivalence("refuted", env, *diff, range=[lo, hi], strength=label)
        return Equivalence("checked", range=[lo, hi], strength=label)

    # ------------------------------------------------------------- internals
    def _differ(self, left: Node, right: Node, env: dict) -> tuple | None:
        lv, rv = self.value(left, env), self.value(right, env)
        same = (lv is NAN and rv is NAN) or (lv is not NAN and rv is not NAN and lv == rv)
        return None if same else (lv, rv)

    def _search(self, left: Node, right: Node, names: tuple[str, ...]) -> Equivalence | None:
        bound = self.encoder.bound
        r = self.small_range if bound is None else min(self.small_range, bound)
        top = bound or 2**31 - 1
        edges = [v for v in dict.fromkeys((*EDGES, top, -top, top // 2)) if bound is None or abs(v) <= bound]
        points = itertools.chain(itertools.product(range(-r, r + 1), repeat=len(names)),
                                 itertools.product(edges, repeat=len(names)))
        for point in points:
            env = dict(zip(names, point))
            diff = self._differ(left, right, env)
            if diff is not None:
                return Equivalence("refuted", env, *diff)
        return None

    def _z3(self, left: Node, right: Node, names: tuple[str, ...]) -> Equivalence | None:
        enc = self.encoder
        xs = {name: z3.Int(name) for name in names}
        env = {name: ZVal(z3.BoolVal(True), x) for name, x in xs.items()}
        enc.reset()
        for value in _numbers(left) | _numbers(right):
            enc.admit(value)
        enc.max_nodes, saved = self.max_nodes, enc.max_nodes
        try:
            lz, rz = encode_node(enc, left, env), encode_node(enc, right, env)
        finally:
            enc.max_nodes = saved
        differ = z3.Or(lz.defined != rz.defined, z3.And(lz.defined, rz.defined, lz.value != rz.value))
        status, model = isolated_check([*[enc.in_bound(x) for x in xs.values()], differ],
                                       self.timeout_ms, rlimit=self.rlimit, variables=list(xs))
        if status == "unsat":
            return Equivalence("proved")
        if status == "sat":
            point = model
            diff = self._differ(left, right, point)
            if diff is None:
                raise AssertionError(f"z3 counterexample {point} is not one for the reference semantics")
            return Equivalence("refuted", point, *diff)
        return None


def _numbers(node: Node) -> set[int]:
    if isinstance(node, Number):
        return set() if node.value is NAN else {node.value}
    if isinstance(node, Call):
        return set().union(*(_numbers(arg) for arg in node.args))
    return set()


def _integer_operator(op: Operator) -> bool:
    return op.result_type == "int" and all(kind == "int" for kind in op.parameter_types)


def _integer_expression(node: Node) -> bool:
    if isinstance(node, Variable):
        return True
    if isinstance(node, Number):
        return node.value is NAN or type(node.value) is int
    return _integer_operator(node.operator) and all(_integer_expression(arg) for arg in node.args)


def encode_node(encoder: Z3Encoder, node: Node, env: dict[str, ZVal]) -> ZVal:
    """z3 value of an expression tree whose variables are bound in ``env``."""
    if isinstance(node, Variable):
        return env[node.name]
    if isinstance(node, Number):
        return ZVal(z3.BoolVal(False), z3.IntVal(0)) if node.value is NAN else const(node.value)
    return encoder._apply(node.operator, [encode_node(encoder, arg, env) for arg in node.args], 0)


# --------------------------------------------------------------- operators
_NAMES = Symbols().parameter_names  # variable names for operators compared as f(a, b, ...)


def equivalent_operators(registry: OperatorRegistry, checker: EquivalenceChecker,
                         operators: list[Operator] | None = None) -> list[tuple[Operator, Operator, Equivalence]]:
    """Pairs of operators (same arity and position) with the same values on every input.

    Candidates share a fingerprint (values on a fixed sample); each candidate pair
    is then decided by :meth:`EquivalenceChecker.check` on ``f(a, b)`` vs ``g(a, b)``.
    """
    if operators is not None and any(not _integer_operator(op) for op in operators):
        raise NotExpressible("equivalent operators require integer signatures")
    pool = operators if operators is not None else [op for op in registry
                                                   if _is_operation(op) and _integer_operator(op)]
    values = tuple(value for value in (0, 1, -1, 3, -5, 12, 77)
                   if checker.encoder.bound is None or abs(value) <= checker.encoder.bound)
    sample = list(itertools.product(values, repeat=2))
    groups: dict[tuple, list[Operator]] = {}
    for op in pool:
        if op.n_ary > 2:  # a shorter sample per argument for three or more arguments
            args = list(itertools.product(values[:5], repeat=op.n_ary))
        else:
            args = [point[: op.n_ary] for point in sample]
        fingerprint = tuple(_json(checker.oracle.evaluate(op, a).value) for a in dict.fromkeys(args))
        groups.setdefault((op.n_ary, op.unary_position, fingerprint), []).append(op)
    found = []
    for members in groups.values():
        for f, g in itertools.combinations(members, 2):
            names = _NAMES[: f.n_ary] if f.n_ary <= len(_NAMES) else tuple(f"x{i}" for i in range(f.n_ary))
            operands = tuple(Variable(n) for n in names)
            verdict = checker.check(Call(f, operands), Call(g, operands))
            if verdict.status != "refuted":
                found.append((f, g, verdict))
    return found


def _is_operation(op: Operator) -> bool:
    return op.definition is not None or base_operation_name(op.symbol, op.n_ary, op.unary_position) is not None


# ------------------------------------------------------------------- sympy
ARITHMETIC = {"add", "sub", "mul", "neg"}


def sympy_candidate(node: Node, registry: OperatorRegistry) -> Node | None:
    """SymPy's expanded form of an arithmetic expression (``+ - *``, negation), or None.

    The result is only a proposal; check it with :class:`EquivalenceChecker`.
    """
    import sympy

    def to_sympy(n: Node):
        if isinstance(n, Number):
            return None if n.value is NAN else sympy.Integer(n.value)
        if isinstance(n, Variable):
            return sympy.Symbol(n.name, integer=True)
        name = base_operation_name(n.operator.symbol, n.operator.n_ary, n.operator.unary_position)
        if n.operator.definition is not None or name not in ARITHMETIC:
            return None
        args = [to_sympy(a) for a in n.args]
        if any(a is None for a in args):
            return None
        return {"add": lambda x, y: x + y, "sub": lambda x, y: x - y,
                "mul": lambda x, y: x * y, "neg": lambda x: -x}[name](*args)

    expr = to_sympy(node)
    if expr is None:
        return None
    ops = {name: registry.find(symbol, n_ary, position)
           for (symbol, n_ary, position), name in _base_symbols().items() if name in ARITHMETIC}
    if any(op is None for op in ops.values()):
        return None
    return _from_sympy(sympy.expand(expr), ops)


def _base_symbols():
    from opulse.core.semantics import BASE_OPERATIONS

    return BASE_OPERATIONS


def _from_sympy(e, ops: dict[str, Operator]) -> Node:
    import sympy

    def number(n: int) -> Node:
        return Number(n) if n >= 0 else Call(ops["neg"], (Number(-n),))

    if e.is_Integer:
        return number(int(e))
    if e.is_Symbol:
        return Variable(e.name)
    if e.is_Pow and e.exp.is_Integer and int(e.exp) > 0:
        base = _from_sympy(e.base, ops)
        result = base
        for _ in range(int(e.exp) - 1):
            result = Call(ops["mul"], (result, base))
        return result
    if e.is_Mul:
        coefficient, rest = e.as_coeff_Mul()
        if coefficient == -1:
            return Call(ops["neg"], (_from_sympy(rest, ops),))
        factors = [sympy.Integer(coefficient)] if coefficient != 1 else []
        factors += list(sympy.Mul.make_args(rest))
        result = _from_sympy(factors[0], ops)
        for factor in factors[1:]:
            result = Call(ops["mul"], (result, _from_sympy(factor, ops)))
        return result
    if e.is_Add:
        terms = list(sympy.Add.make_args(e))
        terms.sort(key=lambda t: t.could_extract_minus_sign())  # positive terms first
        result = _from_sympy(terms[0], ops)
        for term in terms[1:]:
            if term.could_extract_minus_sign():
                result = Call(ops["sub"], (result, _from_sympy(-term, ops)))
            else:
                result = Call(ops["add"], (result, _from_sympy(term, ops)))
        return result
    raise ValueError(f"unsupported SymPy expression {e!r}")


def _json(value):
    return None if value is NAN else value
