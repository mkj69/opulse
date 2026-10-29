"""Encode operators as z3 terms following docs/reference/semantics.md (exact mode).

A value is a pair :class:`ZVal` ``(defined, value)``: ``defined`` is a z3 Bool
that is false exactly when the spec gives NaN, ``value`` a term of the
operator's result sort that matters only when ``defined`` holds.
Division and remainder truncate toward zero
(z3's own ``/`` and ``%`` are Euclidean and must not be used directly).

Every base operation is encodable when the semantics has a bound B: all
values then lie in [-B, B], so ``@`` (reverse), ``&`` (digit sum) and ``$``
(popcount) are encoded exactly by a fixed number of decimal digits / bits,
each a division by a constant. Without a bound only ``+ - * / % neg #`` are
encoded; :meth:`Z3Encoder.expressible` says which operators qualify.

Recursion is unrolled. By the termination argument of spec section 4.1 a
template-A operator unfolds at most ``m - 1`` times and a template-B operator
at most ``T`` times, so unrolling one level further than that is exact; the
tests compare the encoding with the reference interpreter to confirm it.
"""

from __future__ import annotations

from dataclasses import dataclass

import z3

from opulse.core.operator import Operator
from opulse.core.semantics import EXACT, Semantics, base_operation_name
from opulse.definition import ast

ARITHMETIC_BASE = frozenset({"add", "sub", "mul", "div", "mod", "neg", "triangle",
                             "succ", "pred", "double", "half", "parity", "defined"})
DIGIT_BASE = frozenset({"reverse", "digitsum", "popcount"})


class NotExpressible(Exception):
    pass


@dataclass(frozen=True)
class ZVal:
    defined: z3.BoolRef
    value: z3.ExprRef


UNDEF = ZVal(z3.BoolVal(False), z3.IntVal(0))


def _sort(kind: str) -> z3.SortRef:
    from opulse.core.types import parse_type

    parsed = parse_type(kind)
    sorts = {"int": z3.IntSort(), "note": z3.IntSort(),
             "bool": z3.BoolSort(), "str": z3.StringSort()}
    return z3.SeqSort(_sort(str(parsed.element))) if parsed.name == "list" else sorts[parsed.name]


def _undefined(sort: z3.SortRef) -> ZVal:
    if sort == z3.IntSort():
        return UNDEF
    return ZVal(z3.BoolVal(False), z3.Const("undefined", sort))


def _as_sort(value: ZVal, sort: z3.SortRef) -> ZVal:
    if value.value.sort() == sort:
        return value
    if z3.is_false(z3.simplify(value.defined)):
        return _undefined(sort)
    raise TypeError(f"defined z3 value has sort {value.value.sort()}, expected {sort}")


def const(n: object) -> ZVal:
    if isinstance(n, bool):
        value = z3.BoolVal(n)
    elif isinstance(n, str):
        value = z3.StringVal(n)
    elif isinstance(n, (tuple, list)):
        value = z3.Empty(z3.SeqSort(z3.IntSort()))
        for item in n:
            value = z3.Concat(value, z3.Unit(z3.IntVal(item)))
    else:
        value = z3.IntVal(n)
    return ZVal(z3.BoolVal(True), value)


def trunc_div(a, b):
    """Quotient rounded toward zero, for ``b != 0``."""
    q = z3.If(a >= 0,
              z3.If(b > 0, a / b, -(a / -b)),
              z3.If(b > 0, -((-a) / b), (-a) / (-b)))
    return q  # every z3 division above has non-negative operands, where floor == trunc


class Z3Encoder:
    """Builds z3 terms for operator applications; ``oracle`` supplies definitions."""

    def __init__(self, oracle, semantics: Semantics | None = None, max_nodes: int = 200_000,
                 unroll_margin: int = 1) -> None:
        self.oracle = oracle
        self.semantics = semantics or oracle.semantics
        if self.semantics.mode != EXACT:
            raise NotExpressible("z3 encoding covers exact mode only")
        self.bound = self.semantics.bound
        self.max_nodes = max_nodes
        self.unroll_margin = unroll_margin
        self._nodes = 0
        self._memo: dict = {}
        self._expressible: dict[str, bool] = {}
        # Largest magnitude a defined value can have: the bound limits base results and inputs,
        # but literals in definitions and expressions may exceed it (review finding). Digit
        # operations need a width that covers every such value.
        self._limit = self.bound or 0
        self._scanned: set[str] = set()
        self._scan_definitions()

    def _scan_definitions(self) -> None:
        """Admit the literals of every definition not seen yet (the registry may have grown)."""
        from opulse.verify.differential import literals

        operators = list(self.oracle.registry) + list(getattr(self.oracle, "_extra", {}).values())
        for operator in operators:
            if operator.definition is None or operator.func_id in self._scanned:
                continue
            self._scanned.add(operator.func_id)
            for value in literals(self.oracle._definition_of(operator)):
                self.admit(value)

    def admit(self, value: int) -> None:
        """Record a literal that can reach a digit operation (call before encoding it)."""
        if self.bound is not None and abs(value) > self._limit:
            self._limit = abs(value)
            self._memo = {}  # earlier digit encodings used a narrower width

    # ------------------------------------------------------------ public API
    def expressible(self, operator: Operator) -> bool:
        known = self._expressible.get(operator.func_id)
        if known is not None:
            return known
        try:
            for kind in (*operator.parameter_types, operator.result_type):
                _sort(kind)
        except (KeyError, ValueError):
            self._expressible[operator.func_id] = False
            return False
        name = base_operation_name(operator.symbol, operator.n_ary, operator.unary_position)
        if operator.definition is None:
            from opulse.core.primitives import CUSTOM

            custom = CUSTOM.get(name)
            result = (name in ARITHMETIC_BASE or (name in DIGIT_BASE and self.bound is not None)
                      or (custom is not None and custom.z3 is not None))
        else:
            self._expressible[operator.func_id] = True  # recursion: assume, then check the rest
            definition = self.oracle._definition_of(operator)
            if any(_large_search(node) for branch in definition.branches
                   for node in (branch.expr, branch.condition)):
                self._expressible[operator.func_id] = False
                return False
            callees = {self.oracle._resolve(app).func_id: self.oracle._resolve(app)
                       for branch in definition.branches
                       for node in ([branch.expr] + ([branch.condition] if branch.condition else []))
                       for app in ast.iter_applications(node)}
            result = all(self.expressible(op) for fid, op in callees.items() if fid != operator.func_id)
        self._expressible[operator.func_id] = result
        return result

    def apply(self, operator: Operator, args: list[ZVal]) -> ZVal:
        """The z3 value of ``operator(*args)``."""
        if not self.expressible(operator):
            raise NotExpressible(f"{operator.symbol!r} contains an operation outside the z3 encoding")
        self.reset()
        for arg in args:  # concrete arguments are literals and may exceed the bound
            value = z3.simplify(arg.value)
            if z3.is_int_value(value):
                self.admit(value.as_long())
        return self._apply(operator, list(args), depth=0)

    def reset(self, seconds: float | None = None) -> None:
        """Start a new formula with a fresh node budget and memo table."""
        self._scan_definitions()
        self._nodes = 0
        self._memo = {}
        if seconds is not None:
            raise ValueError("encoding uses max_nodes; elapsed time cannot determine a verdict")

    def variables(self, operator: Operator, names=None) -> tuple[list[z3.ArithRef], list[ZVal]]:
        if not self.expressible(operator):
            raise NotExpressible(f"{operator.symbol!r} contains an operation outside the z3 encoding")
        if names is None:
            from opulse.config import Symbols

            names = Symbols().operands(operator.n_ary)
        xs = []
        for name, kind in zip(names[: operator.n_ary], operator.parameter_types):
            xs.append(z3.Const(name, _sort(kind)))
        return xs, [ZVal(z3.BoolVal(True), x) for x in xs]

    def in_bound(self, x) -> z3.BoolRef:
        if x.sort() == z3.StringSort():
            return z3.Length(x) <= self.semantics.max_string_length
        if x.sort().kind() == z3.Z3_SEQ_SORT:
            return z3.Length(x) <= self.semantics.max_list_length
        if x.sort() == z3.BoolSort():
            return z3.BoolVal(True)
        if self.bound is None:
            return z3.BoolVal(True)
        return z3.And(x >= -self.bound, x <= self.bound)

    # ------------------------------------------------------------- internals
    def _tick(self) -> None:
        self._nodes += 1
        if self._nodes > self.max_nodes:
            raise NotExpressible("encoding too large")

    def _base(self, name: str, args: list[ZVal]) -> ZVal:
        self._tick()
        if name == "defined":
            return ZVal(z3.BoolVal(True), z3.If(args[0].defined, z3.IntVal(1), z3.IntVal(0)))
        defined = z3.And(*[a.defined for a in args]) if args else z3.BoolVal(True)
        a = args[0].value
        if name in DIGIT_BASE:
            v = self._digits(name, a)
            return ZVal(z3.And(defined, self.in_bound(v)), v)
        if name not in ARITHMETIC_BASE:  # a user-registered atom: its own encoding, if it has one
            from opulse.core.primitives import CUSTOM

            custom = CUSTOM.get(name)
            if custom is None or custom.z3 is None:
                raise NotExpressible(f"atom {name!r} has no z3 encoding")
            v = custom.z3(*[x.value for x in args])
            return ZVal(z3.And(defined, self.in_bound(v)), v)
        if name == "neg":
            v = -a
        elif name in ("succ", "pred", "double"):
            v = {"succ": a + 1, "pred": a - 1, "double": 2 * a}[name]
        elif name == "half":
            v = trunc_div(a, z3.IntVal(2))
        elif name == "parity":
            v = z3.If(a >= 0, a, -a) % 2  # non-negative operand: Euclidean == exact
        elif name == "triangle":
            n = z3.If(a >= 0, a, -a)
            t = (n * (n + 1)) / 2  # n >= 0: Euclidean == exact
            v = z3.If(a > 0, t, z3.If(a < 0, -t, z3.IntVal(0)))
        else:
            b = args[1].value
            if name == "add":
                v = a + b
            elif name == "sub":
                v = a - b
            elif name == "mul":
                v = a * b
            else:
                nonzero = b != 0
                safe_b = z3.If(nonzero, b, z3.IntVal(1))
                q = trunc_div(a, safe_b)
                v = q if name == "div" else a - safe_b * q
                defined = z3.And(defined, nonzero)
        return ZVal(z3.And(defined, self.in_bound(v)), v)

    def _digits(self, name: str, a):
        """Exact for |a| <= bound: fixed-width decimal digits / bits of |a|."""
        if self.bound is None:
            raise NotExpressible("digit operations need a bound for a fixed digit width")
        concrete = z3.simplify(a)
        if z3.is_int_value(concrete):  # a literal: compute exactly, whatever its size
            from opulse.core.semantics import Semantics

            return z3.IntVal(Semantics(EXACT, None).operations()[name](concrete.as_long()))
        n = z3.If(a >= 0, a, -a)
        sgn = z3.If(a > 0, z3.IntVal(1), z3.If(a < 0, z3.IntVal(-1), z3.IntVal(0)))
        if name == "popcount":
            width = self._limit.bit_length()
            return z3.Sum([(n / (2**k)) % 2 for k in range(width)])  # n >= 0: Euclidean == exact
        width = len(str(self._limit))
        digits = [(n / (10**k)) % 10 for k in range(width)]
        if name == "digitsum":
            return sgn * z3.Sum(digits)
        # reverse: with L digits, digit k moves to position L-1-k; leading zeros of the result drop.
        reversed_by_length = [z3.Sum([digits[k] * 10 ** (length - 1 - k) for k in range(length)])
                              for length in range(1, width + 1)]
        value = reversed_by_length[0]
        for length in range(2, width + 1):
            value = z3.If(n >= 10 ** (length - 1), reversed_by_length[length - 1], value)
        return sgn * value

    def _apply(self, operator: Operator, args: list[ZVal], depth: int) -> ZVal:
        args = [_as_sort(arg, _sort(kind)) for arg, kind in zip(args, operator.parameter_types)]
        name = base_operation_name(operator.symbol, operator.n_ary, operator.unary_position)
        if operator.definition is None:
            result = self._base(name, args)
            if operator.result_type == "note":
                return ZVal(z3.And(result.defined, result.value >= 0, result.value <= 127),
                            result.value)
            return result
        if depth > self._unroll_limit(operator):
            return _undefined(_sort(operator.result_type))  # unreachable by spec 4.1
        key = (operator.func_id, depth, tuple((a.defined.get_id(), a.value.get_id()) for a in args))
        cached = self._memo.get(key)
        if cached is not None:
            return cached
        definition = self.oracle._definition_of(operator)
        env = dict(zip(definition.parameters, args))
        if operator.definition_type == "recursive_definition":
            result = self._recursive(operator, definition, env, depth)
        else:
            result = self._branches(operator, definition, env, depth, {})
        self._memo[key] = result
        return result

    def _recursive(self, operator: Operator, definition: ast.Definition, env: dict, depth: int) -> ZVal:
        """Case-split on the recursion's control value so deeper calls get constant arguments.

        Template A: control ``v % m`` lies in ``[-(m-1), m-1]``; only occurrences of
        that expression are replaced, ``v`` itself stays symbolic. Template B:
        control ``v`` lies in ``[-T, T]`` (beyond, no branch matches); replacing
        ``v`` is exact because the case says ``v == r``.
        """
        variable, control, span = recursion_control(definition)
        loop = env[variable]
        concrete = z3.simplify(loop.value)
        if z3.is_int_value(concrete) or span is None:
            return self._branches(operator, definition, env, depth, {})
        if isinstance(control, ast.Var):  # template B
            control_result = loop
        else:  # template A
            control_result = self._expr(control, env, operator, depth, {})
        result = self._branches(operator, definition, env, depth, {})  # fallback: outside the span
        for r in range(-span, span + 1):
            case = self._branches(operator, definition, env, depth, {control: const(r)})
            hit = z3.And(control_result.defined, control_result.value == r)
            result = ZVal(z3.If(hit, case.defined, result.defined), z3.If(hit, case.value, result.value))
        # A split case substitutes a defined constant, so retain the actual control's
        # definedness even when its value matches a case after an out-of-bound result.
        return ZVal(z3.And(control_result.defined, result.defined), result.value)

    def _branches(self, operator: Operator, definition: ast.Definition, env: dict, depth: int,
                  override: dict) -> ZVal:
        """Branch selection with pruning of conditions that simplify to constants."""
        cases: list[tuple] = []  # (abort, truth, body) kept symbolic
        result_sort = _sort(operator.result_type)
        terminal = _undefined(result_sort)  # no branch matched
        for branch in definition.branches:
            if branch.condition is None:
                terminal = _as_sort(self._expr(branch.expr, env, operator, depth, override), result_sort)
                break
            abort, truth = self._condition(branch.condition, env, operator, depth, override)
            abort, truth = z3.simplify(abort), z3.simplify(truth)
            if z3.is_true(abort):
                terminal = _undefined(result_sort)
                break
            if z3.is_false(truth) and z3.is_false(abort):
                continue
            body = _as_sort(self._expr(branch.expr, env, operator, depth, override), result_sort)
            if z3.is_true(truth) and z3.is_false(abort):
                terminal = body
                break
            cases.append((abort, truth, body))
        result = terminal
        for abort, truth, body in reversed(cases):
            result = ZVal(
                z3.If(abort, z3.BoolVal(False), z3.If(truth, body.defined, result.defined)),
                z3.If(truth, body.value, result.value),
            )
        return result

    def _unroll_limit(self, operator: Operator) -> int:
        if operator.definition_type != "recursive_definition":
            return 10_000
        return recursion_depth(self.oracle._definition_of(operator)) + self.unroll_margin

    def _expr(self, node: ast.Expr, env: dict, self_op: Operator, depth: int, override: dict) -> ZVal:
        if node in override:
            return override[node]
        if isinstance(node, ast.Var):
            return env[node.name]
        if isinstance(node, ast.Num):
            self.admit(node.value)
            return const(node.value)
        if isinstance(node, ast.Literal):
            return const(node.value)
        if isinstance(node, ast.NaN):
            return UNDEF
        if isinstance(node, ast.Search):
            if node.bound > 32:
                raise NotExpressible("search bound exceeds 32")
            result = UNDEF
            for index in reversed(range(node.bound + 1)):
                local = {**env, node.index: const(index)}
                abort, truth = self._condition(node.condition, local, self_op, depth, override)
                result = ZVal(z3.And(z3.Not(abort), z3.Or(truth, result.defined)),
                              z3.If(truth, z3.IntVal(index), result.value))
            return result
        args = [self._expr(arg, env, self_op, depth, override) for arg in node.args]
        callee = self.oracle._resolve(node)
        if callee.func_id == self_op.func_id:
            return self._apply(callee, args, depth + 1)
        return self._apply(callee, args, 0)

    def _condition(self, node: ast.Condition, env: dict, self_op: Operator, depth: int, override: dict):
        """``(abort, truth)``: abort when a compared side is NaN (spec 4, rule 2)."""
        if isinstance(node, ast.Truth):
            result = self._expr(node.expr, env, self_op, depth, override)
            return z3.Not(result.defined), result.value
        if isinstance(node, ast.Compare):
            left = self._expr(node.left, env, self_op, depth, override)
            right = self._expr(node.right, env, self_op, depth, override)
            abort = z3.Not(z3.And(left.defined, right.defined))
            l, r = left.value, right.value
            if l.sort() != r.sort():
                if z3.is_false(z3.simplify(left.defined)):
                    l = _as_sort(left, r.sort()).value
                else:
                    r = _as_sort(right, l.sort()).value
            if node.op == "==":
                truth = l == r
            elif node.op == "!=":
                truth = l != r
            elif node.op == ">":
                truth = l > r
            elif node.op == "<":
                truth = l < r
            elif node.op == ">=":
                truth = l >= r
            else:
                truth = l <= r
            return abort, truth
        if isinstance(node, ast.Not):
            abort, truth = self._condition(node.operand, env, self_op, depth, override)
            return abort, z3.Not(truth)
        la, lt = self._condition(node.left, env, self_op, depth, override)
        ra, rt = self._condition(node.right, env, self_op, depth, override)
        if isinstance(node, ast.And):  # right side evaluated only when the left is true
            return z3.Or(la, z3.And(z3.Not(la), lt, ra)), z3.And(lt, rt)
        return z3.Or(la, z3.And(z3.Not(la), z3.Not(lt), ra)), z3.Or(lt, rt)


def recursion_control(definition: ast.Definition) -> tuple[str, ast.Expr, int | None]:
    """(loop variable, control expression, span of the control value) for the two templates."""
    first = definition.branches[0].condition
    if isinstance(first, ast.Compare) and isinstance(first.left, ast.Apply) and first.left.symbol == "%":
        control = first.left
        return control.args[0].name, control, control.args[1].value - 1
    if isinstance(first, ast.Compare) and isinstance(first.left, ast.Var):
        return first.left.name, first.left, recursion_depth(definition)
    raise NotExpressible("recursive definition does not follow a known template")


def recursion_depth(definition: ast.Definition) -> int:
    """Maximum number of self-calls for the two recursive templates (spec 4.1)."""
    first = definition.branches[0].condition
    if isinstance(first, ast.Compare) and isinstance(first.left, ast.Apply) and first.left.symbol == "%" \
            and isinstance(first.left.args[1], ast.Num):
        return first.left.args[1].value - 1  # template A: at most m - 1
    second = definition.branches[1].condition if len(definition.branches) > 1 else None
    if isinstance(second, ast.And) and isinstance(second.right, ast.Compare) \
            and second.right.op == "<=" and isinstance(second.right.right, ast.Num):
        return second.right.right.value  # template B: at most T
    raise NotExpressible("recursive definition does not follow a known template")


def _large_search(node) -> bool:
    if node is None:
        return False
    if isinstance(node, ast.Search):
        return node.bound > 32 or _large_search(node.condition)
    if isinstance(node, ast.Apply):
        return any(_large_search(arg) for arg in node.args)
    if isinstance(node, (ast.Compare, ast.And, ast.Or)):
        return _large_search(node.left) or _large_search(node.right)
    if isinstance(node, ast.Not):
        return _large_search(node.operand)
    return False


def _numbers(definition: ast.Definition):
    def walk(node):
        if isinstance(node, ast.Num):
            yield node
        elif isinstance(node, ast.Search):
            yield ast.Num(node.bound)
            yield from walk(node.condition)
        elif isinstance(node, ast.Apply):
            for arg in node.args:
                yield from walk(arg)
        elif isinstance(node, (ast.Compare, ast.And, ast.Or)):
            yield from walk(node.left)
            yield from walk(node.right)
        elif isinstance(node, ast.Not):
            yield from walk(node.operand)

    for branch in definition.branches:
        yield from walk(branch.expr)
        if branch.condition is not None:
            yield from walk(branch.condition)


def evaluate_concrete(encoder: Z3Encoder, operator: Operator, args: tuple) -> object:
    """Evaluate an expressible encoding on concrete typed inputs."""
    from opulse.core.semantics import NAN

    if operator.result_type != "int" or any(kind != "int" for kind in operator.parameter_types):
        from opulse.core.types import matches

        if len(args) != len(operator.parameter_types) or any(
                arg is not NAN and not matches(arg, kind)
                for arg, kind in zip(args, operator.parameter_types)):
            return NAN

    zv = encoder.apply(operator, [UNDEF if a is NAN else const(a) for a in args])
    defined = z3.simplify(zv.defined)
    if z3.is_false(defined):
        return NAN
    if not z3.is_true(defined):
        raise AssertionError(f"definedness did not simplify: {defined}")
    value = z3.simplify(zv.value)
    if z3.is_int_value(value):
        return value.as_long()
    if z3.is_true(value):
        return True
    if z3.is_false(value):
        return False
    if z3.is_string_value(value):
        return value.as_string()
    if value.sort().kind() == z3.Z3_SEQ_SORT:
        return _sequence_value(value)
    raise NotExpressible(f"concrete result did not simplify: {value}")


def _sequence_value(node) -> tuple:
    if z3.is_app_of(node, z3.Z3_OP_SEQ_EMPTY):
        return ()
    if z3.is_app_of(node, z3.Z3_OP_SEQ_UNIT):
        return (z3.simplify(node.arg(0)).as_long(),)
    if z3.is_app_of(node, z3.Z3_OP_SEQ_CONCAT):
        return tuple(item for child in node.children() for item in _sequence_value(child))
    raise NotExpressible(f"sequence did not simplify: {node}")
