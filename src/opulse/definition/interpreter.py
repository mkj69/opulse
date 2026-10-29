"""Reference interpreter: the executable form of docs/reference/semantics.md (section 4-5).

It evaluates definitions by walking their syntax trees and shares nothing with
:mod:`opulse.definition.codegen` except the AST and the base operations of
:class:`~opulse.core.semantics.Semantics`. Compiled code is checked against it.
It deliberately does no caching or sharing: every occurrence is evaluated, in
the order the specification prescribes.
"""

from __future__ import annotations

import operator as py_operator
import sys
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from opulse.core.semantics import NAN, Semantics, base_operation_name
from opulse.definition import ast

COMPARISONS: dict[str, Callable[[int, int], bool]] = {
    "==": py_operator.eq,
    "!=": py_operator.ne,
    ">": py_operator.gt,
    "<": py_operator.lt,
    ">=": py_operator.ge,
    "<=": py_operator.le,
}


class EngineError(RuntimeError):
    """The engine broke an invariant (for example unbounded recursion). Never data."""


@dataclass(frozen=True)
class Result:
    value: object  # int or NAN
    base_ops: int
    calls: int


class _Counter:
    __slots__ = ("base_ops", "calls", "max_depth")

    def __init__(self) -> None:
        self.base_ops = 0
        self.calls = 0
        self.max_depth = 0


_stack_worker = None
_stack_lock = threading.Lock()


def run_with_deep_stack(fn, *args):
    """Retry a bounded evaluation on one reusable thread with a larger stack."""
    global _stack_worker
    with _stack_lock:
        if _stack_worker is None:
            previous = threading.stack_size()
            try:
                threading.stack_size(128 * 1024 * 1024)
                worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="opulse-eval")
                worker.submit(lambda: None).result()  # start the thread while stack_size is set
                _stack_worker = worker
            finally:
                threading.stack_size(previous)

    def invoke():
        previous_limit = sys.getrecursionlimit()
        if previous_limit < 100_000:
            sys.setrecursionlimit(100_000)
        try:
            return fn(*args)
        finally:
            if previous_limit < 100_000:
                sys.setrecursionlimit(previous_limit)

    return _stack_worker.submit(invoke).result()


class _Undefined(Exception):
    """A comparison saw NaN: the current definition frame evaluates to NaN."""


# Looks up the operator an application denotes: Apply -> Operator.
Resolver = Callable[[ast.Apply], object]
# Parsed definition of a non-base operator: Operator -> ast.Definition.
DefinitionOf = Callable[[object], ast.Definition]


class ReferenceInterpreter:
    def __init__(self, resolve: Resolver, definition_of: DefinitionOf,
                 semantics: Semantics | None = None, max_depth: int = 10_000,
                 extra_primitives: dict | None = None) -> None:
        self.resolve = resolve
        self.definition_of = definition_of
        self.operations = (semantics or Semantics()).operations()
        self.max_depth = max_depth
        # func_id -> function, treated like base operations (used only to audit legacy data).
        self.extra = extra_primitives or {}
        # func_id -> {args: (value, base_ops, calls, relative_depth)}. A definition is a pure function of its
        # arguments, so a call's value and both counts can be reused; counting still happens
        # per occurrence because the cached counts are added at every call site.
        self._memo: dict[str, dict[tuple, tuple]] = {}
        self._memo_size = 0
        # callee func_id -> func_ids of the defined operators whose definitions apply it
        self._dependents: dict[str, set[str]] = {}
        self._linked: set[str] = set()
        self.memo_limit = 2_000_000

    def forget(self, func_id: str) -> None:
        """Drop cached results of this operator and of every operator that applies it, directly
        or through other operators (their values may change with its definition)."""
        pending, seen = [func_id], set()
        while pending:
            current = pending.pop()
            if current in seen:
                continue
            seen.add(current)
            self._memo_size -= len(self._memo.pop(current, {}))
            self._linked.discard(current)
            pending.extend(self._dependents.pop(current, ()))

    def _primitive(self, operator):
        """The function of a base (or extra) operator, or None for defined operators."""
        if operator.func_id in self.extra:
            return self.extra[operator.func_id]
        if operator.definition is not None:
            return None
        name = base_operation_name(operator.symbol, operator.n_ary, operator.unary_position)
        return self.operations[name] if name is not None else None

    def evaluate(self, operator, args: tuple) -> Result:
        """Value and counts of ``operator(*args)``; the call itself is not counted."""
        counter = _Counter()
        args = tuple(args)
        try:
            hash(args)
        except TypeError:
            from opulse.core.types import freeze

            args = tuple(freeze(arg) for arg in args)
        try:
            value = self._call(operator, args, counter, depth=0)
        except RecursionError:
            counter = _Counter()
            try:
                value = run_with_deep_stack(self._call, operator, args, counter, 0)
            except RecursionError:
                raise EngineError(f"recursion of {operator.symbol!r} exceeds the Python call stack") from None
        return Result(value, counter.base_ops, counter.calls)

    def evaluate_expr(self, node: ast.Expr, env: dict[str, object]) -> Result:
        """Value and counts of a free-standing expression (section 6)."""
        counter = _Counter()
        if any(isinstance(value, (list, tuple)) for value in env.values()):
            from opulse.core.types import freeze

            env = {name: freeze(value) for name, value in env.items()}
        try:
            value = self._eval(node, env, counter, depth=0)
        except RecursionError:
            counter = _Counter()
            try:
                value = run_with_deep_stack(self._eval, node, env, counter, 0)
            except RecursionError:
                raise EngineError("recursion exceeds the Python call stack") from None
        return Result(value, counter.base_ops, counter.calls)

    # ---------------------------------------------------------------- internals
    def _call(self, operator, args: tuple, counter: _Counter, depth: int):
        counter.max_depth = max(counter.max_depth, depth)
        if len(args) != operator.n_ary:
            raise TypeError(f"{operator.symbol!r} takes {operator.n_ary} arguments, got {len(args)}")
        primitive = self._primitive(operator)
        if primitive is not None:
            counter.base_ops += 1
            return primitive(*args)
        if operator.result_type != "int" or any(t != "int" for t in operator.parameter_types):
            from opulse.core.types import matches

            if len(args) != len(operator.parameter_types) or not all(
                    value is NAN or matches(value, kind)
                    for value, kind in zip(args, operator.parameter_types)):
                return NAN
        if depth > self.max_depth:
            raise EngineError(f"recursion deeper than {self.max_depth} in {operator.symbol!r}")
        definition = self.definition_of(operator)
        if operator.func_id not in self._linked:
            self._link(operator, definition)
        env = dict(zip(definition.parameters, args))
        try:
            for branch in definition.branches:
                if branch.condition is None or self._condition(branch.condition, env, counter, depth):
                    return self._eval(branch.expr, env, counter, depth)
        except _Undefined:
            return NAN
        return NAN  # no branch matched: undefined on this input (section 4, rule 3)

    def _link(self, operator, definition: ast.Definition) -> None:
        """Record which operators this definition applies (for ``forget``)."""
        for branch in definition.branches:
            nodes = [branch.expr] if branch.condition is None else [branch.expr, branch.condition]
            for node in nodes:
                for application in ast.iter_applications(node):
                    try:
                        callee = self.resolve(application)
                    except Exception:  # noqa: BLE001 - an unknown callee fails later, at evaluation
                        continue
                    self._dependents.setdefault(callee.func_id, set()).add(operator.func_id)
        self._linked.add(operator.func_id)

    def _eval(self, node: ast.Expr, env: dict, counter: _Counter, depth: int):
        if isinstance(node, ast.Var):
            return env[node.name]
        if isinstance(node, ast.Num):
            return node.value
        if isinstance(node, ast.NaN):
            return NAN
        if isinstance(node, ast.Search):
            for index in range(node.bound + 1):
                local = {**env, node.index: index}
                try:
                    if self._condition(node.condition, local, counter, depth):
                        return index
                except _Undefined:
                    return NAN
            return NAN
        if isinstance(node, ast.Literal):
            return node.value
        args = tuple(self._eval(arg, env, counter, depth) for arg in node.args)
        callee = self.resolve(node)
        counter.calls += 1
        primitive = self._primitive(callee)
        if primitive is not None:
            counter.base_ops += 1
            return primitive(*args)
        table = self._memo.setdefault(callee.func_id, {})
        cached = table.get(args)
        if cached is None:
            inner = _Counter()
            value = self._call(callee, args, inner, depth + 1)
            cached = (value, inner.base_ops, inner.calls, inner.max_depth - depth - 1)
            if self._memo_size >= self.memo_limit:
                self._memo.clear()
                self._memo_size = 0
                table = self._memo.setdefault(callee.func_id, {})
            table[args] = cached
            self._memo_size += 1
        if depth + 1 + cached[3] > self.max_depth:
            raise EngineError(f"recursion deeper than {self.max_depth} in {callee.symbol!r}")
        counter.max_depth = max(counter.max_depth, depth + 1 + cached[3])
        counter.base_ops += cached[1]
        counter.calls += cached[2]
        return cached[0]

    def _condition(self, node: ast.Condition, env: dict, counter: _Counter, depth: int) -> bool:
        if isinstance(node, ast.Truth):
            value = self._eval(node.expr, env, counter, depth)
            if value is NAN:
                raise _Undefined
            if not isinstance(value, bool):
                raise TypeError("condition must have bool type")
            return value
        if isinstance(node, ast.Compare):
            left = self._eval(node.left, env, counter, depth)
            right = self._eval(node.right, env, counter, depth)
            if left is NAN or right is NAN:
                raise _Undefined
            return COMPARISONS[node.op](left, right)
        if isinstance(node, ast.And):
            return self._condition(node.left, env, counter, depth) and \
                self._condition(node.right, env, counter, depth)
        if isinstance(node, ast.Or):
            return self._condition(node.left, env, counter, depth) or \
                self._condition(node.right, env, counter, depth)
        return not self._condition(node.operand, env, counter, depth)
