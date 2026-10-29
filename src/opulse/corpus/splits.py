"""Assign the defined operators of one set to train/val/test splits.

A held-out split must be *closed under callers*: if an operator is held out, every operator
whose definition calls it is held out in the same split. Otherwise a training document that
unfolds or defines the caller would show the held-out operator. The first split takes the
remaining operators; it is closed under callees, so its documents mention only its own
operators. A held-out split's documents mention its own operators and, through definitions
and derivations, operators of the first split, never operators of another held-out split.
"""

from __future__ import annotations

import random

from opulse.bench.context import callees
from opulse.core.registry import OperatorRegistry


def callers(registry: OperatorRegistry) -> dict[str, set[str]]:
    """func_id -> func_ids of the defined operators whose definitions call it (self-calls excluded)."""
    found: dict[str, set[str]] = {op.func_id: set() for op in registry}
    for op in registry:
        if op.definition is None:
            continue
        for callee in callees(registry, op):
            if callee.func_id != op.func_id:
                found[callee.func_id].add(op.func_id)
    return found


def caller_closure(func_id: str, called_by: dict[str, set[str]]) -> set[str]:
    closure = {func_id}
    stack = [func_id]
    while stack:
        for caller in called_by[stack.pop()]:
            if caller not in closure:
                closure.add(caller)
                stack.append(caller)
    return closure


def split_operators(registry: OperatorRegistry, ratios: dict[str, float], seed: int,
                    max_layer: int | None = None) -> dict[str, list[str]]:
    """Defined operators per split (sorted func_ids). The first split of ``ratios`` takes the rest.

    Held-out splits are filled in order: operators are visited in a seeded random order, and an
    operator joins the split with its whole caller closure when the closure is still unassigned
    and fits the split's target size. Targets are ``round(ratio * defined operators)``.
    """
    if not ratios:
        raise ValueError("at least one split is needed")
    if any(r < 0 for r in ratios.values()) or max(ratios.values()) <= 0:
        raise ValueError("split ratios must be non-negative and not all zero")
    defined = sorted(op.func_id for op in registry if op.definition is not None
                     and (max_layer is None or (op.recursive_layer or 0) <= max_layer))
    eligible = set(defined)
    called_by = callers(registry)
    largest = max(ratios.values())
    weights = {name: ratio / largest for name, ratio in ratios.items()}
    total = sum(weights.values())
    names = list(ratios)
    assigned: dict[str, str] = {}
    result: dict[str, list[str]] = {name: [] for name in names}
    order = list(defined)
    random.Random(seed).shuffle(order)
    for name in names[1:]:
        target = round(weights[name] / total * len(defined))
        members: set[str] = set()
        for func_id in order:
            if len(members) >= target:
                break
            if func_id in assigned or func_id in members:
                continue
            closure = caller_closure(func_id, called_by) & eligible | {func_id}
            # Callers above --max-layer never appear in documents, so they do not need to follow.
            if any(other in assigned for other in closure) or len(members | closure) > target:
                continue
            members |= closure
        for func_id in members:
            assigned[func_id] = name
    for func_id in defined:
        assigned.setdefault(func_id, names[0])
    for func_id in defined:
        result[assigned[func_id]].append(func_id)
    return result
