"""Evaluate expression trees and collect the statistics written to datasets.

Evaluation follows docs/reference/semantics.md section 6: strict, bottom-up, left to
right; values are ints or ``NAN``. The expansion degree is the sum of every
application's ``base_ops`` (a base operation counts 1).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from opulse.core.operator import Operator
from opulse.core.registry import OperatorRegistry
from opulse.expression.nodes import Node, Number, Variable, iter_calls


@dataclass(frozen=True)
class Step:
    """One operator application in evaluation order (innermost first)."""

    operator: Operator
    inputs: tuple
    output: object
    base_ops: int
    depth: int  # distance from the root

    def render(self, write=str, symbols=None) -> str:
        args = [write(value) for value in self.inputs]
        return f"{self.operator.apply_str(*args, symbols=symbols)} = {write(self.output)}"


@dataclass
class Evaluation:
    value: object
    expansion: int  # sum of base_ops over all applications (legacy "normalized_expansion_degree")
    steps: list[Step] = field(default_factory=list)
    max_path_depth: int = 0
    max_edge_count: int = 0

    @property
    def operation_count(self) -> int:
        return len(self.steps)


class Evaluator:
    """Evaluates trees with a runtime (anything with ``evaluate(op)``)."""

    def __init__(self, runtime, env: dict | None = None) -> None:
        self.runtime = runtime
        self.env = env or {}

    def evaluate(self, node: Node) -> Evaluation:
        steps: list[Step] = []
        value, expansion, path, edges = self._walk(node, 0, steps)
        return Evaluation(value, expansion, steps, path, edges)

    def _walk(self, node: Node, depth: int, steps: list[Step]) -> tuple:
        if isinstance(node, Number):
            return node.value, 0, 0, 0
        if isinstance(node, Variable):
            if node.name not in self.env:
                raise ValueError(f"variable {node.name!r} has no value")
            return self.env[node.name], 0, 0, 0
        results = [self._walk(arg, depth + 1, steps) for arg in node.args]
        inputs = tuple(r[0] for r in results)
        op = node.operator
        value, base_ops, _calls = self.runtime.evaluate(op)(*inputs)
        steps.append(Step(op, inputs, value, base_ops, depth))
        return (
            value,
            base_ops + sum(r[1] for r in results),
            max(r[2] for r in results) + op.max_path_depth,
            sum(r[3] for r in results) + op.max_edge_count,
        )


def structure_stats(node: Node, registry: OperatorRegistry) -> dict:
    """Statistics that do not need evaluation."""
    calls = list(iter_calls(node))
    used = list(dict.fromkeys(call.operator.func_id for call in calls))
    dependents: set[str] = set()
    for func_id in used:
        dependents |= _dependency_closure(registry, func_id)
    priorities = {call.operator.priority for call in calls if call.operator.priority is not None}
    return {
        "operation_count": len(calls),
        "highest_layer": max((call.operator.recursive_layer or 0 for call in calls), default=0),
        "priority_levels": len(priorities),
        "used_operators": used,
        "dependent_operators": sorted(dependents),
    }


def _dependency_closure(registry: OperatorRegistry, func_id: str) -> frozenset[str]:
    """Transitive dependencies of one operator, cached on the registry per operator object."""
    cache = registry.__dict__.setdefault("_dependency_closure_cache", {})
    operator = registry.get(func_id)
    found = cache.get(func_id)
    if found is not None and found[0] is operator:
        return found[1]
    closure: set[str] = set()
    stack = list(operator.dependencies)
    while stack:
        dep = stack.pop()
        if dep not in closure:
            closure.add(dep)
            stack.extend(registry.get(dep).dependencies)
    result = frozenset(closure)
    cache[func_id] = (operator, result)
    return result
