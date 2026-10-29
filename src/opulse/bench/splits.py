"""Held-out operator sets and leakage checks.

The clean way to test concept learning is to train on one operator set and test on another
grown from the same base operations with a different seed: every test operator is new. Two
sets can still contain operators that are *the same concept* under another name, so this
module fingerprints operators in two ways and reports test operators that also occur in the
training set:

* **structural** — the definition with every operator symbol replaced by its callee's own
  fingerprint (recursively) and every self-call by a placeholder: identical definitions up to
  renaming collide;
* **behavioural** — values on a fixed sample of inputs nominate candidate matches;
  only equivalence proved for the full input domain counts as shared.
"""

from __future__ import annotations

import hashlib
import itertools
import random
from dataclasses import replace

from opulse.core.operator import Operator
from opulse.core.registry import OperatorRegistry
from opulse.core.semantics import NAN, base_operation_name
from opulse.definition import ast
from opulse.verify import Oracle

SAMPLE = (0, 1, -1, 2, -2, 3, 5, -7, 10, 13, -20, 37, 64, 99, -100, 1000)


def structural_fingerprints(registry: OperatorRegistry, oracle: Oracle) -> dict[str, str]:
    """func_id -> fingerprint of the definition with operator names abstracted away."""
    memo: dict[str, str] = {}

    def fingerprint(op: Operator) -> str:
        if op.func_id in memo:
            return memo[op.func_id]
        if op.definition is None:
            memo[op.func_id] = f"base:{base_operation_name(op.symbol, op.n_ary, op.unary_position)}"
            return memo[op.func_id]
        memo[op.func_id] = "SELF"  # recursion refers to itself
        definition = oracle._definition_of(op)
        search_indices: set[str] = set()

        def expr(node) -> str:
            if isinstance(node, ast.Var):
                if node.name in search_indices:
                    return "search_index"
                return f"v{definition.parameters.index(node.name)}"
            if isinstance(node, ast.Num):
                return str(node.value)
            if isinstance(node, ast.NaN):
                return "nan"
            if isinstance(node, ast.Search):
                previous = node.index in search_indices
                search_indices.add(node.index)
                condition = cond(node.condition)
                if not previous:
                    search_indices.remove(node.index)
                return f"search({node.bound},{condition})"
            callee = oracle._resolve(node)
            name = "SELF" if callee.func_id == op.func_id else fingerprint(callee)
            return f"({name} {' '.join(expr(arg) for arg in node.args)})"

        def cond(node) -> str:
            if isinstance(node, ast.Compare):
                return f"[{expr(node.left)} {node.op} {expr(node.right)}]"
            if isinstance(node, ast.Not):
                return f"[not {cond(node.operand)}]"
            return f"[{type(node).__name__} {cond(node.left)} {cond(node.right)}]"

        text = f"{op.n_ary}|" + ";".join(
            f"{expr(b.expr)}|{cond(b.condition) if b.condition is not None else 'else'}" for b in definition.branches)
        memo[op.func_id] = hashlib.sha256(text.encode()).hexdigest()[:16]
        return memo[op.func_id]

    return {op.func_id: fingerprint(op) for op in registry if op.definition is not None}


def behavioural_fingerprints(registry: OperatorRegistry, oracle: Oracle) -> dict[str, str]:
    """func_id -> hash of the operator's values on a fixed input sample."""
    prints = {}
    for op in registry:
        if op.definition is None:
            continue
        values = []
        # Three or more arguments: a prefix of the sample keeps the grid at about 4096 points.
        sample = SAMPLE if op.n_ary <= 2 else SAMPLE[: max(2, round(4096 ** (1 / op.n_ary)))]
        for args in itertools.product(sample, repeat=op.n_ary):
            value = oracle.evaluate(op, args).value
            values.append("nan" if value is NAN else str(value))
        prints[op.func_id] = hashlib.sha256(f"{op.n_ary}|{','.join(values)}".encode()).hexdigest()[:16]
    return prints


def leakage(train: OperatorRegistry, test: OperatorRegistry, behavioural: bool = True,
            semantics=None) -> dict:
    """Test operators that also occur in the training set (by definition, by values, by symbol).

    ``semantics`` must be the one both sets were generated with (default: exact)."""
    train_oracle = Oracle(train, semantics=semantics) if semantics is not None else Oracle(train)
    test_oracle = Oracle(test, semantics=semantics) if semantics is not None else Oracle(test)
    report = {"test_operators": sum(op.definition is not None for op in test)}
    train_structural = structural_fingerprints(train, train_oracle)
    test_structural = structural_fingerprints(test, test_oracle)
    structural_seen = set(train_structural.values())
    structural_hits = [fid for fid, fp in test_structural.items() if fp in structural_seen]
    report["structural"] = {"shared": len(structural_hits),
                            "examples": [test.get(fid).definition for fid in structural_hits[:5]]}
    if behavioural:
        from opulse.expression.aliases import AliasMap, aliased_registry, pseudo_words
        from opulse.expression.nodes import Call, Variable
        from opulse.solver.equivalence import EquivalenceChecker
        from opulse.solver.z3_encode import Z3Encoder

        train_behavioural = behavioural_fingerprints(train, train_oracle)
        test_behavioural = behavioural_fingerprints(test, test_oracle)
        by_print: dict[str, list[str]] = {}
        for fid, fingerprint in train_behavioural.items():
            by_print.setdefault(fingerprint, []).append(fid)
        candidates = {fid: by_print[fp] for fid, fp in test_behavioural.items() if fp in by_print}
        confirmed = set(structural_hits) & candidates.keys()
        if any(fid not in confirmed for fid in candidates):
            defined = [op for op in test if op.definition is not None]
            words = pseudo_words(len(defined), random.Random(0), exclude=train.symbols() | test.symbols())
            aliases = {(op.symbol, op.n_ary, op.unary_position): word
                       for op, word in zip(defined, words, strict=True)}
            renamed = aliased_registry(test, AliasMap(aliases, {word: key for key, word in aliases.items()}))
            combined = OperatorRegistry(list(train))
            renamed_ops = {}
            for op in renamed:
                if op.definition is not None:
                    clone = replace(op, func_id=f"leakage_test_{op.func_id}")
                    combined.add(clone)
                    renamed_ops[op.func_id] = clone
            checker = EquivalenceChecker(Z3Encoder(Oracle(combined, semantics=semantics) if semantics is not None
                                                   else Oracle(combined)), timeout_ms=1000)
            for fid, train_ids in candidates.items():
                if fid in confirmed:
                    continue
                op = renamed_ops[fid]
                names = tuple(f"x{i}" for i in range(op.n_ary))
                args = tuple(Variable(name) for name in names)
                for train_id in train_ids:
                    other = train.get(train_id)
                    if other.n_ary != op.n_ary or other.unary_position != op.unary_position:
                        continue
                    if checker.check(Call(other, args), Call(op, args)).status == "proved":
                        confirmed.add(fid)
                        break
        hits = [fid for fid in candidates if fid in confirmed]
        report["behavioural"] = {"shared": len(hits), "candidates": len(candidates),
                                 "examples": [test.get(fid).definition for fid in hits[:5]]}
    shared_ids = {op.func_id for op in test if op.definition} & {op.func_id for op in train if op.definition}
    report["shared_func_ids"] = len(shared_ids)
    # The same written symbol (with arity and position) for a different operator: harmless for
    # concept leakage, but a test of unseen *notation* needs it at zero (or the aliases).
    def keys(registry):
        return {(op.symbol, op.n_ary, op.unary_position) for op in registry if op.definition}
    report["shared_symbols"] = len(keys(train) & keys(test))
    return report


def split_matched_tasks(tasks: list[dict], *, by: str, ratios: dict[str, float],
                        seed: int = 0) -> dict[str, list[dict]]:
    """Assign connected task groups, so a held out key occurs in one split only."""
    if by not in ("skeleton", "world"):
        raise ValueError("split key must be skeleton or world")
    if not ratios or any(value < 0 for value in ratios.values()) or sum(ratios.values()) <= 0:
        raise ValueError("split ratios must be nonnegative with a positive total")
    parent = list(range(len(tasks)))

    def root(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    seen = {}
    for index, task in enumerate(tasks):
        keys = task.get("skeleton_ids", []) if by == "skeleton" else [task.get("world")]
        if not keys or any(key is None for key in keys):
            raise ValueError(f"task {task.get('id', index)} has no {by} metadata")
        for key in keys:
            if key in seen:
                parent[root(index)] = root(seen[key])
            else:
                seen[key] = index
    groups = {}
    for index, task in enumerate(tasks):
        groups.setdefault(root(index), []).append(task)
    output = {name: [] for name in ratios}
    rng = random.Random(seed)
    parts = list(groups.values())
    rng.shuffle(parts)
    total = sum(ratios.values())
    for group in parts:
        name = min(output, key=lambda key: (len(output[key]) / len(tasks) - ratios[key] / total, key))
        output[name].extend(group)
    return output


def matched_task_leakage(train: list[dict], test: list[dict]) -> dict:
    """Count shared skeleton and world identifiers across task files."""
    def keys(tasks, field):
        if field == "skeleton_ids":
            return {value for task in tasks for value in task.get(field, [])}
        return {task[field] for task in tasks if task.get(field) is not None}

    skeletons = sorted(keys(train, "skeleton_ids") & keys(test, "skeleton_ids"))
    worlds = sorted(keys(train, "world") & keys(test, "world"))
    return {"shared_skeletons": len(skeletons), "skeleton_ids": skeletons,
            "shared_worlds": len(worlds), "worlds": worlds}
