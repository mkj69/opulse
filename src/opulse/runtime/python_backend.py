"""Run generated operator code with ``exec`` in one shared namespace.

Base operations are bound from :class:`~opulse.core.semantics.Semantics`; the
hand-written ``op_compute_func`` strings stored for base operators in old JSON
files are ignored, so there is exactly one implementation of the arithmetic.
Every other operator's code is executed into the same globals dict, so a
function can call any other operator (or itself) by name regardless of load
order.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from opulse.core.operator import Operator
from opulse.core.semantics import NAN, Semantics, base_operation_name
from opulse.definition.codegen import evaluator_name, is_base
from opulse.definition.interpreter import run_with_deep_stack


def _stack_safe(fn: Callable) -> Callable:
    def call(*args):
        try:
            return fn(*args)
        except RecursionError:
            return run_with_deep_stack(fn, *args)

    return call


def base_bindings(operator: Operator, semantics: Semantics) -> dict[str, Callable]:
    """Namespace entries for one base operator: value, count and evaluator."""
    fn = semantics.operations()[base_operation_name(operator.symbol, operator.n_ary,
                                                    operator.unary_position)]
    return {
        operator.compute_name: fn,
        operator.count_name: lambda *args: 1,
        evaluator_name(operator.func_id): lambda *args: (fn(*args), 1, 0),
    }


def _memoized(fn: Callable, limit: int = 1 << 16) -> Callable:
    """Cache an evaluator's ``(value, base_ops, calls)`` by arguments.

    Generated code calls other operators through these global names, so every call site
    shares the cache. Definitions are pure functions of their arguments, so this changes
    nothing but speed; without it deep chains of definitions re-evaluate exponentially.
    """
    cache: dict = {}

    def evaluator(*args):
        try:
            hash(args)
            key = args
        except TypeError:
            from opulse.core.types import freeze

            key = tuple(freeze(arg) for arg in args)
        found = cache.get(key)
        if found is None:
            found = fn(*args)
            if len(cache) >= limit:
                cache.clear()
            cache[key] = found
        return found

    evaluator.__wrapped__ = fn
    return evaluator


class PythonRuntime:
    def __init__(self, operators: Iterable[Operator] = (), semantics: Semantics | None = None) -> None:
        self.semantics = semantics or Semantics()
        self._namespace: dict[str, Any] = {"NAN": NAN, "__builtins__": __builtins__}
        from opulse.worlds.perm import Permutation

        self._namespace["Permutation"] = Permutation
        self._dynamic_atoms = False
        for operator in operators:
            self.load(operator)

    def load(self, operator: Operator) -> None:
        if is_base(operator):
            if operator.symbol in {"↟", "↝", "↔"}:
                self._dynamic_atoms = True
            self._namespace.update(base_bindings(operator, self.semantics))
            return
        if not operator.has_code:
            return  # numeral-base markers have no code
        exec(compile(operator.op_compute_func, f"<{operator.compute_name}>", "exec"), self._namespace)  # noqa: S102
        exec(compile(operator.op_count_func, f"<{operator.count_name}>", "exec"), self._namespace)  # noqa: S102
        name = evaluator_name(operator.func_id)
        if name in self._namespace and not self._dynamic_atoms:
            self._namespace[name] = _memoized(self._namespace[name])

    def unload(self, operator: Operator) -> None:
        for name in (operator.compute_name, operator.count_name, evaluator_name(operator.func_id)):
            self._namespace.pop(name, None)

    def compute(self, operator: Operator) -> Callable[..., Any]:
        return _stack_safe(self._namespace[operator.compute_name])

    def count(self, operator: Operator) -> Callable[..., int]:
        return _stack_safe(self._namespace[operator.count_name])

    def evaluate(self, operator: Operator) -> Callable[..., tuple]:
        """``(*args) -> (value, base_ops, calls)``."""
        return _stack_safe(self._namespace[evaluator_name(operator.func_id)])
