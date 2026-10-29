"""What the library does with a world's operators: the data of the task tabs of a showcase.

For one world and one seed (the default seed of :mod:`opulse.worlds.showcase`, so operator
names match the operator browser) this writes ``<world>/tasks.json`` and lazily loaded detail
files under ``<world>/tasks/``:

* ``expressions``: compound expressions over two to four of the world's operators, each with
  its value and its derivation at three granularities (one step per operator, written
  operators unfolded, every step), in ``tasks/expr-<i>.json``;
* ``holes``: one number or value of an expression replaced by ``x``. Integer worlds use
  :class:`opulse.solver.holes.HoleSolver` (z3 where the operators are expressible, else an
  exhaustive range). Typed worlds search the world's own value sampler. Every candidate with
  its value goes to ``tasks/hole-<i>.json``;
* ``laws``: commutativity, associativity, idempotence, identities and involution for several
  operators. Integer worlds use :class:`opulse.solver.properties.PropertyChecker` where z3
  matches the semantics; modular worlds check a stated range with the interpreter. Typed
  worlds check combinations of sampled values. A failing law keeps both sides' values;
* ``equivalence``: operator pairs that look alike on samples, checked by
  :class:`opulse.solver.equivalence.EquivalenceChecker` where possible, directly over an
  integer range, or over sampled typed values;
* ``contrast``, ``edit``, ``simplify``: one swapped definition with both answers, one edited
  definition with the answers that change, one definition with its helpers inlined and the
  short form it simplifies to.

Every value is computed by the reference interpreter (:class:`opulse.verify.Oracle`) and
every derivation by the reducer, whose final value is checked against the interpreter. Each
item records how it was established: ``{"method": "z3"}`` (proved), ``{"method": "range",
"range": [lo, hi]}`` (every integer in the range checked), ``{"method": "sample", "size": n}``
(every combination of n sampled values checked) or ``{"method": "all", "size": n}`` (the
sample is the whole finite domain, so the check is complete).
"""

from __future__ import annotations

import itertools
import json
import random
from dataclasses import dataclass, replace
from pathlib import Path

from opulse.core.operator import RECURSIVE, SIMPLE, Operator
from opulse.core.registry import OperatorRegistry
from opulse.core.semantics import MODULAR, NAN
from opulse.core.types import same_value
from opulse.definition.parser import DefinitionParser
from opulse.expression.nodes import Call, Node, Number, Variable, to_ast, to_dict
from opulse.expression.render import ExpressionRenderer
from opulse.runtime.python_backend import PythonRuntime
from opulse.trace.reducer import Reducer
from opulse.verify import Oracle
from opulse.worlds.present import Describer, operator_names
from opulse.worlds._atomic_export import staged_export
from opulse.worlds.showcase import Tools, _featured, _notes, world_spec

TASK_SEED = 20261024
GRANULARITIES = (
    {"key": "operator", "en": "one step per operator", "zh": "每个运算符一步", "max_depth": 0},
    {"key": "unfold", "en": "written operators unfolded", "zh": "展开写出的运算符", "max_depth": 1},
    {"key": "full", "en": "every step", "zh": "每一步", "max_depth": None},
)
LAWS = ("commutative", "associative", "idempotent", "left_identity", "right_identity", "involution")
SMALL = {"successor": (0, 40), "bits": (0, 63), "clock": (-12, 24)}
LAW_RANGE = {"successor": (0, 24), "bits": (0, 31), "clock": (0, 11)}


@dataclass
class World:
    spec: object
    seed: int
    tools: Tools
    ordered: list[Operator]
    featured: list[Operator]
    integer: bool  # every operator maps integers to integers
    encoder: object | None  # a Z3Encoder when z3 can encode the world's atoms

    @property
    def oracle(self) -> Oracle:
        return self.tools.oracle

    def show(self, text: str) -> str:
        return self.tools.show(text)

    def name(self, op: Operator) -> str:
        return self.tools.names.get(op.symbol, op.symbol)

    def enc(self, value, kind: str | None = None) -> dict:
        return self.spec.encode(value, kind)

    def text(self, node: Node) -> str:
        return self.show(self.tools.renderer.full(node))

    def tree(self, node: Node) -> dict:
        return _rename_tree(to_dict(node), self.tools.names)

    def value(self, node: Node, env: dict | None = None):
        return self.oracle.evaluate_expr(to_ast(node), env or {}).value

    def pool(self, kind: str, limit: int = 16) -> list:
        values = list(dict.fromkeys(_key_value(v) for v in self.spec.values(kind)))
        values = [_unkey(v) for v in values]
        if kind == "int":
            if self.tools.settings.semantics.mode == MODULAR:
                values = list(range(self.tools.settings.semantics.modulus))
            else:
                lo, hi = SMALL.get(self.spec.world, (-6, 9))
                values = list(dict.fromkeys([*values[:8], *range(lo, min(hi, lo + 12) + 1)]))
        return values[:limit]


def _rename_tree(value, names: dict[str, str]):
    """Rename operator fields in a serialized expression, leaving values and atoms alone."""
    if isinstance(value, list):
        return [_rename_tree(item, names) for item in value]
    if isinstance(value, dict):
        return {key: names.get(item, item) if key == "operator" and isinstance(item, str)
                else _rename_tree(item, names) for key, item in value.items()}
    return value


def _key_value(value):
    return (type(value).__name__, repr(value)), value


def _unkey(item):
    return item[1]


def prepare(world: str, seed: int | None = None) -> World:
    """The world's operator set with the same names as the operator browser of the same seed."""
    spec = world_spec(world)
    seed = spec.seed if seed is None else seed
    settings, registry, generated = spec.build(seed)
    semantics = settings.semantics.build()
    parser = DefinitionParser(settings.symbols, registry)
    oracle = Oracle(registry, settings.symbols, semantics)
    runtime = PythonRuntime(registry, semantics)
    reducer = Reducer(registry, runtime, parser, max_steps=2000, max_depth=2)
    renderer = ExpressionRenderer(settings.symbols)
    atom_symbols = [op.symbol for op in registry if op.definition is None]
    names = operator_names(generated, settings, atom_symbols, seed)
    describer = Describer(registry, names, parser, spec.value_text)
    tools = Tools(spec, settings, registry, names, oracle, reducer, renderer, parser, describer)
    featured = spec.order(generated) if spec.order else _featured(generated, tools)
    ordered = featured + [op for op in generated if op not in featured]
    tools.names = operator_names(ordered, settings, atom_symbols, seed)
    tools.describer = Describer(registry, tools.names, parser, spec.value_text)
    integer = all(op.result_type == "int" and all(t == "int" for t in op.parameter_types) for op in registry)
    encoder = None
    # Modular base operations fold values, while the z3 encoding bounds them differently.
    if integer and settings.semantics.mode != MODULAR:
        from opulse.solver.z3_encode import NotExpressible, Z3Encoder

        try:
            encoder = Z3Encoder(oracle)
        except NotExpressible:
            encoder = None
    return World(spec, seed, tools, ordered, featured, integer, encoder)


def _expressible(world: World, ops) -> bool:
    return world.encoder is not None and all(world.encoder.expressible(op) for op in ops)


def _check(method: str, **extra) -> dict:
    return {"method": method, **extra}


# ------------------------------------------------------------------ expressions


def _defined_calls(node: Node) -> list[Operator]:
    if not isinstance(node, Call):
        return []
    own = [node.operator] if node.operator.definition is not None else []
    return own + [op for arg in node.args for op in _defined_calls(arg)]


def _depth(node: Node) -> int:
    return 1 + max((_depth(arg) for arg in node.args), default=0) if isinstance(node, Call) else 0


def _leaves(node: Node, path: tuple = ()) -> list[tuple[tuple, Number]]:
    if isinstance(node, Number):
        return [(path, node)]
    if isinstance(node, Call):
        return [item for i, arg in enumerate(node.args) for item in _leaves(arg, path + (i,))]
    return []


def _kinds(node: Node, path: tuple = (), kind: str | None = None) -> dict[tuple, str]:
    """Value type of every leaf, read from the operator that receives it."""
    if isinstance(node, Call):
        out = {}
        for i, arg in enumerate(node.args):
            out.update(_kinds(arg, path + (i,), node.operator.parameter_types[i]))
        return out
    return {path: kind}


def _replace(node: Node, path: tuple, new: Node) -> Node:
    if not path:
        return new
    args = list(node.args)
    args[path[0]] = _replace(args[path[0]], path[1:], new)
    return Call(node.operator, tuple(args))


def _grow_tree(world: World, rng: random.Random, root: Operator, depth: int, helpers: list[Operator]) -> Node:
    by_result: dict[str, list[Operator]] = {}
    for op in helpers:
        by_result.setdefault(op.result_type, []).append(op)

    def leaf(kind):
        pool = world.pool(kind)
        return Number(rng.choice(pool[: max(4, len(pool) // 2)] if rng.random() < 0.6 else pool))

    def grow(kind: str, level: int) -> Node:
        options = by_result.get(kind, [])
        if level <= 0 or not options or rng.random() < 0.3:
            return leaf(kind)
        op = rng.choice(options)
        return Call(op, tuple(grow(t, level - 1) for t in op.parameter_types))

    return Call(root, tuple(grow(t, depth - 1) for t in root.parameter_types))


def _trace_steps(world: World, tree: Node, max_depth: int | None, kinds: dict) -> list[dict] | None:
    tools = world.tools
    runtime = tools.reducer.runtime
    reducer = Reducer(tools.registry, runtime, tools.parser, max_steps=400, max_depth=max_depth)
    trace = reducer.reduce(tree)
    if trace.truncated or not same_value(trace.value, world.value(tree)):
        return None
    out = []
    for step in trace.steps:
        note, note_zh = _notes(step, tools, kinds)
        kind = kinds.get(step.operator.func_id)
        record = {"kind": step.kind, "expression": tools.show(tools.renderer.full(step.expression_after)),
                  "focus": tools.show(tools.renderer.full(step.before)),
                  "value": world.enc(step.output, kind) if step.output is not None else None,
                  "note": note, "note_zh": note_zh,
                  "gate": tools.names.get(step.operator.symbol, step.operator.symbol), "branch": step.branch_index}
        if world.spec.step_extra:
            world.spec.step_extra(step, record, tools)
        out.append(record)
    return out


def _size_ok(value) -> bool:
    if value is NAN:
        return True
    if isinstance(value, bool) or not isinstance(value, int):
        return True
    return abs(value) <= 100_000


def expressions(world: World, folder: Path, count: int = 8) -> list[dict]:
    rng = random.Random(TASK_SEED)
    ops = world.ordered
    kinds = {op.func_id: op.result_type for op in world.tools.registry}
    plans = [(2, 2), (2, 3), (2, 3), (3, 3), (3, 4), (3, 4), (4, 4), (4, 5), (2, 2), (3, 3)]
    chosen: list[dict] = []
    seen_roots: set[str] = set()
    seen_text: set[str] = set()
    for want_ops, want_depth in plans:
        if len(chosen) >= count:
            break
        for _ in range(600):
            root = rng.choice(ops[:12] if rng.random() < 0.6 else ops[:60])
            if root.func_id in seen_roots and rng.random() < 0.8:
                continue
            helpers = [op for op in ops[:70] if op.func_id != root.func_id]
            tree = _grow_tree(world, rng, root, want_depth, helpers)
            distinct = {op.func_id for op in _defined_calls(tree)}
            if not 2 <= len(distinct) <= 4 or len(distinct) != min(want_ops, 4):
                continue
            if _depth(tree) != want_depth:
                continue
            text = world.text(tree)
            if text in seen_text or len(text) > 400:
                continue
            try:
                value = world.value(tree)
            except Exception:  # noqa: BLE001, S112 - a rejected draw is skipped
                continue
            if value is NAN or not _size_ok(value):
                continue
            granular = []
            for level in GRANULARITIES:
                steps = _trace_steps(world, tree, level["max_depth"], kinds)
                if steps is None:
                    break
                granular.append(steps)
            if len(granular) < len(GRANULARITIES) or len(granular[-1]) > 260 or len(granular[-1]) < 3:
                continue
            index = len(chosen)
            (folder / f"expr-{index}.json").write_text(json.dumps(granular, ensure_ascii=False, separators=(",", ":")),
                                                      encoding="utf-8")
            leaf_kinds = _kinds(tree)
            first = _leaves(tree)[0]
            names = list(dict.fromkeys(world.name(op) for op in _defined_calls(tree)))
            chosen.append({"id": f"expr-{index}", "expression": text, "tree": world.tree(tree),
                           "value": world.enc(value, root.result_type),
                           "depth": want_depth, "operators": names,
                           "definitions": [{"name": world.name(op), "definition": world.show(op.definition)}
                                           for op in _unique(_defined_calls(tree))],
                           "first": world.enc(first[1].value, leaf_kinds[first[0]]),
                           "steps": [len(s) for s in granular], "_tree": tree})
            seen_roots.add(root.func_id)
            seen_text.add(text)
            break
    return chosen


def _unique(ops: list[Operator]) -> list[Operator]:
    out, seen = [], set()
    for op in ops:
        if op.func_id not in seen:
            seen.add(op.func_id)
            out.append(op)
    return out


# ------------------------------------------------------------------ holes


def holes(world: World, items: list[dict], folder: Path, count: int = 5) -> list[dict]:
    rng = random.Random(TASK_SEED + 1)
    out: list[dict] = []
    trees = [item["_tree"] for item in items]
    # Smaller expressions read better as equations: add some one and two level ones.
    extra_rng = random.Random(TASK_SEED + 2)
    for _ in range(400):
        root = extra_rng.choice(world.ordered[:40])
        helpers = [op for op in world.ordered[:60] if op.func_id != root.func_id]
        tree = _grow_tree(world, extra_rng, root, extra_rng.choice((1, 2, 2)), helpers)
        trees.append(tree)
    rng.shuffle(trees)
    # Two one level equations first, then deeper ones, so the search runs through operators.
    trees = ([t for t in trees if _depth(t) == 1][:40] + [t for t in trees if _depth(t) in (2, 3)])
    want_multi = 1
    seen: set[str] = set()
    for tree in trees:
        if len(out) >= count:
            break
        if _depth(tree) == 1 and sum(item["depth"] == 1 for item in out) >= 2:
            continue
        try:
            target = world.value(tree)
        except Exception:  # noqa: BLE001, S112
            continue
        if target is NAN:
            continue
        leaves = _leaves(tree)
        kinds = _kinds(tree)
        paths = [path for path, _ in leaves]
        rng.shuffle(paths)
        for path in paths[:2]:
            item = (_int_hole(world, tree, path, target) if world.integer
                    else _sample_hole(world, tree, path, target, kinds[path]))
            if item is None or item["equation"] in seen:
                continue
            solutions = item["solutions"]
            if len(solutions) > 1:
                if want_multi <= 0 or len(solutions) > 6:
                    continue
                want_multi -= 1
            index = len(out)
            detail = item.pop("_detail")
            (folder / f"hole-{index}.json").write_text(json.dumps(detail, ensure_ascii=False, separators=(",", ":")),
                                                      encoding="utf-8")
            item["id"] = f"hole-{index}"
            item["depth"] = _depth(tree)
            seen.add(item["equation"])
            out.append(item)
            break
    return out


def _equation(world: World, expression: Node, target, kind: str | None) -> str:
    from opulse.worlds.showcase import short_text

    shown = world.text(expression)
    value = short_text(target, kind) if not isinstance(target, int) or isinstance(target, bool) else target
    return f"{shown} = {value}"


def _int_hole(world: World, tree: Node, path: tuple, target) -> dict | None:
    from opulse.solver.holes import HoleSolver

    node = tree
    for i in path:
        node = node.args[i]
    answer = node.value
    expression = _replace(tree, path, Variable("x"))
    small = SMALL.get(world.spec.world)
    solver = HoleSolver(world.encoder, world.oracle, fallback_domain=small or (-60, 60),
                        not_expressible_domain=small or (-60, 60))
    try:
        found = solver.solve(expression, target)
    except Exception:  # noqa: BLE001 - an expression z3 cannot decide is skipped
        return None
    if not found.complete or answer not in found.values:
        return None
    lo, hi = found.domain
    if found.method == "z3":
        check = _check("z3", domain=[lo, hi])
        window = sorted(set(range(answer - 8, answer + 9)) | set(found.values))
        window = [x for x in window if lo <= x <= hi]
        summary = True
    else:
        check = _check("range", range=[lo, hi])
        window = list(range(lo, hi + 1))
        summary = False
    candidates = []
    for x in window:
        value = solver.value(expression, x)
        if (value == target and value is not NAN) != (x in found.values):
            raise AssertionError("the interpreter and the solver disagree on a hole candidate")
        candidates.append([x, value if value is not NAN else None])
    kind = "int"
    return {"equation": _equation(world, expression, target, kind), "expression": world.text(expression),
            "tree": world.tree(expression),
            "target": world.enc(target, kind), "answer": world.enc(answer, kind),
            "solutions": [world.enc(v, kind) for v in found.values], "unique": len(found.values) == 1,
            "domain": {"kind": "int", "lo": lo, "hi": hi, "size": hi - lo + 1}, "check": check,
            "summary": summary, "x_kind": kind, "tried": len(candidates),
            "_detail": {"candidates": [[world.enc(x, kind), None if v is None else world.enc(v, kind)]
                                       for x, v in candidates]}}


def _sample_hole(world: World, tree: Node, path: tuple, target, kind: str) -> dict | None:
    node = tree
    for i in path:
        node = node.args[i]
    answer = node.value
    expression = _replace(tree, path, Variable("x"))
    if kind == "int":
        if abs(answer) > 60:
            return None
        domain = list(range(min(-12, answer), max(20, answer) + 1))
        complete = False
    else:
        domain = world.pool(kind, limit=40)
        if not any(same_value(answer, v) for v in domain):
            domain.append(answer)
        complete = kind == "bool"
    result_kind = tree.operator.result_type
    rows, solutions = [], []
    for x in domain:
        try:
            value = world.value(expression, {"x": x})
        except Exception:  # noqa: BLE001 - a value of the wrong shape for this operator
            value = NAN
        hit = value is not NAN and same_value(value, target)
        rows.append([world.enc(x, kind), world.enc(value, result_kind)])
        if hit:
            solutions.append(x)
    if not any(same_value(answer, s) for s in solutions):
        raise AssertionError("the removed value does not solve its own hole")
    if len(solutions) == len(domain):
        return None  # every candidate works: not a question
    check = (_check("all", size=len(domain)) if complete else
             _check("range", range=[domain[0], domain[-1]]) if kind == "int" else
             _check("sample", size=len(domain)))
    return {"equation": _equation(world, expression, target, result_kind), "expression": world.text(expression),
            "tree": world.tree(expression),
            "target": world.enc(target, result_kind), "answer": world.enc(answer, kind),
            "solutions": [world.enc(v, kind) for v in solutions], "unique": len(solutions) == 1,
            "domain": {"kind": kind, "size": len(domain),
                       **({"lo": domain[0], "hi": domain[-1]} if kind == "int" else {})},
            "check": check, "summary": False, "x_kind": kind, "tried": len(domain),
            "_detail": {"candidates": rows}}


# ------------------------------------------------------------------ laws


def _law_shape(op: Operator, law: str) -> bool:
    types, result = tuple(op.parameter_types), op.result_type
    if op.n_ary == 2:
        if law == "commutative":
            return types[0] == types[1]
        if law == "associative":
            return types[0] == types[1] == result
        if law == "idempotent":
            return types[0] == types[1] == result
        if law == "left_identity":
            return types[1] == result
        if law == "right_identity":
            return types[0] == result
        return False
    if op.n_ary == 1:
        return law in ("idempotent", "involution") and types[0] == result
    return False


def _sides(world: World, op: Operator, law: str, point: tuple, element=None) -> tuple:
    ev = lambda *args: world.oracle.evaluate(op, args).value
    if law == "commutative":
        a, b = point
        return ev(a, b), ev(b, a)
    if law == "associative":
        a, b, c = point
        return ev(ev(a, b), c), ev(a, ev(b, c))
    if law == "idempotent" and op.n_ary == 2:
        return ev(point[0], point[0]), point[0]
    if law == "idempotent":
        return ev(ev(point[0])), ev(point[0])
    if law == "involution":
        return ev(ev(point[0])), point[0]
    if law == "left_identity":
        return ev(element, point[0]), point[0]
    if law == "right_identity":
        return ev(point[0], element), point[0]
    raise ValueError(law)


def _law_forms(world: World, op: Operator, law: str, values: list, element=None) -> dict:
    """Both sides of a law at one point, as text with the operator's name and as values."""
    name = world.name(op)
    shown = [world.tools.renderer.full(Number(v)) if not isinstance(v, str) else json.dumps(v) for v in values]
    shown = [world.show(text) for text in shown]

    def app(*args):
        if op.n_ary == 2 and op.unary_position is None:
            return f"({args[0]} {name} {args[1]})"
        if op.n_ary == 1 and op.unary_position == "prefix":
            return f"{name} {args[0]}"
        if op.n_ary == 1:
            return f"{args[0]} {name}"
        return f"{name}({', '.join(args)})"

    e = None if element is None else world.show(world.tools.renderer.full(Number(element)))
    if law == "commutative":
        return {"left": app(shown[0], shown[1]), "right": app(shown[1], shown[0])}
    if law == "associative":
        return {"left": app(app(shown[0], shown[1]), shown[2]), "right": app(shown[0], app(shown[1], shown[2]))}
    if law == "idempotent" and op.n_ary == 2:
        return {"left": app(shown[0], shown[0]), "right": shown[0]}
    if law == "idempotent":
        return {"left": app(app(shown[0])), "right": app(shown[0])}
    if law == "involution":
        return {"left": app(app(shown[0])), "right": shown[0]}
    if law == "left_identity":
        return {"left": app(e, shown[0]), "right": shown[0]}
    return {"left": app(shown[0], e), "right": shown[0]}


def _arity(law: str, op: Operator) -> int:
    return {"commutative": 2, "associative": 3}.get(law, 1)


def laws(world: World, count: int = 6) -> dict:
    ops = [op for op in world.ordered[:40] if op.n_ary in (1, 2) and any(_law_shape(op, law) for law in LAWS)]
    ops = ops[:5] + [op for op in ops[5:] if op.n_ary == 2][:10] + [op for op in ops[5:] if op.n_ary == 1][:4]
    rows = []
    for op in ops:
        cells = {}
        for law in LAWS:
            if not _law_shape(op, law):
                continue
            cells[law] = (_int_law(world, op, law) if world.integer else _sample_law(world, op, law))
        rows.append({"name": world.name(op), "definition": world.show(op.definition),
                     "signature": list(op.parameter_types) + [op.result_type], "n_ary": op.n_ary, "cells": cells})
    # Operators where some law holds come first; keep a mix of shapes and at most two unary ones.
    holds = lambda row: sum(bool(cell.get("holds")) for cell in row["cells"].values())
    ranked = sorted(rows, key=lambda row: (-min(holds(row), 2), rows.index(row)))
    picked, patterns = [], set()
    for row in ranked:
        pattern = tuple(sorted((k, bool(v.get("holds"))) for k, v in row["cells"].items()))
        if len(picked) >= count:
            break
        if row["n_ary"] == 1 and sum(r["n_ary"] == 1 for r in picked) >= 2:
            continue
        if pattern in patterns and len(rows) - ranked.index(row) > count - len(picked):
            continue
        patterns.add(pattern)
        picked.append(row)
    picked.sort(key=lambda row: (row["n_ary"] == 1, rows.index(row)))
    return {"laws": [law for law in LAWS if any(law in row["cells"] for row in picked)], "rows": picked}


def _int_law(world: World, op: Operator, law: str) -> dict:
    from opulse.solver.properties import PropertyChecker

    small = LAW_RANGE.get(world.spec.world)
    fallback = small if not _expressible(world, [op]) else None
    if world.encoder is None:
        return _range_law(world, op, law)
    checker = PropertyChecker(world.encoder, timeout_ms=4000, fallback_range=fallback or (-12, 12))
    if fallback is None:
        checker.fallback_range = None
    verdict = checker.check(op, law)
    status, element = verdict.status, verdict.witness
    cell: dict = {}
    if status == "proved":
        cell = {"holds": True, "check": _check("z3")}
    elif status in ("checked", "bounded"):
        lo, hi = verdict.range
        cell = {"holds": True, "check": _check("range", range=[lo, hi])}
    elif status == "not_found":
        lo, hi = verdict.range
        return {"holds": False, "none": True, "check": _check("range", range=[lo, hi]),
                "note": f"No element in [{lo}, {hi}] works on both sides.",
                "note_zh": f"[{lo}, {hi}] 里没有一个元素能让两边都相等。"}
    elif status == "refuted":
        point = tuple(verdict.counterexample)
        left, right = _sides(world, op, law, point, element)
        if same_value(left, right):
            raise AssertionError("a solver counterexample is not one for the interpreter")
        cell = {"holds": False, "check": _check("z3" if fallback is None else "range",
                                                **({"range": list(fallback)} if fallback else {})),
                "counterexample": _counter(world, op, law, point, left, right, element)}
    else:
        return _range_law(world, op, law)
    if element is not None:
        cell["element"] = world.enc(element, "int")
        cell["element_text"] = str(element)
    return cell


def _range_law(world: World, op: Operator, law: str) -> dict:
    lo, hi = LAW_RANGE.get(world.spec.world, (-12, 12))
    values = range(lo, hi + 1)
    check = _check("range", range=[lo, hi])
    if law in ("left_identity", "right_identity"):
        for element in values:
            if all(_safe_same(world, op, law, (value,), element) for value in values):
                return {"holds": True, "check": check, "element": world.enc(element, "int"),
                        "element_text": str(element)}
        return {"holds": False, "none": True, "check": check,
                "note": f"No element in [{lo}, {hi}] works on both sides.",
                "note_zh": f"[{lo}, {hi}] 里没有一个元素能让两边都相等。"}
    for point in itertools.product(values, repeat=_arity(law, op)):
        left, right = _sides(world, op, law, point)
        if not same_value(left, right):
            return {"holds": False, "check": check,
                    "counterexample": _counter(world, op, law, point, left, right)}
    return {"holds": True, "check": check}


def _counter(world: World, op: Operator, law: str, point: tuple, left, right, element=None) -> dict:
    kinds = list(op.parameter_types)
    names = ["a", "b", "c"]
    kind_of = lambda i: kinds[min(i, len(kinds) - 1)] if law != "commutative" else kinds[i]
    return {"inputs": [{"name": names[i], "value": world.enc(v, kind_of(i))} for i, v in enumerate(point)],
            **_law_forms(world, op, law, list(point), element),
            "left_value": world.enc(left, op.result_type), "right_value": world.enc(right, op.result_type)}


def _sample_law(world: World, op: Operator, law: str) -> dict:
    kinds = list(op.parameter_types)
    pools = [world.pool(k, limit=12 if _arity(law, op) < 3 else 7) for k in kinds]
    complete = all(k == "bool" for k in kinds)
    if law == "commutative":
        points = list(itertools.product(pools[0], pools[1]))
    elif law == "associative":
        points = list(itertools.product(pools[0], pools[0], pools[0]))
    elif law in ("idempotent", "involution"):
        points = [(v,) for v in pools[0]]
    else:
        points = [(v,) for v in pools[1 if law == "left_identity" else 0]]
    size = len({repr(p) for pool in pools for p in pool})
    check = _check("all", size=size) if complete else _check("sample", size=size)
    if law in ("left_identity", "right_identity"):
        candidates = world.pool(kinds[0 if law == "left_identity" else 1], limit=16)
        for element in candidates:
            if all(_safe_same(world, op, law, p, element) for p in points):
                return {"holds": True, "check": check, "element": world.enc(element, kinds[0]),
                        "element_text": _value_text(element)}
        return {"holds": False, "none": True, "check": check,
                "note": f"No sampled element works on both sides ({len(candidates)} tried).",
                "note_zh": f"试了 {len(candidates)} 个取样元素，没有一个能让两边都相等。"}
    for point in points:
        try:
            left, right = _sides(world, op, law, point)
        except Exception:  # noqa: BLE001, S112
            continue
        if not same_value(left, right):
            return {"holds": False, "check": check, "counterexample": _counter(world, op, law, point, left, right)}
    return {"holds": True, "check": check}


def _safe_same(world, op, law, point, element) -> bool:
    try:
        left, right = _sides(world, op, law, point, element)
    except Exception:  # noqa: BLE001
        return False
    return same_value(left, right)


def _value_text(value) -> str:
    from opulse.worlds.showcase import short_text

    return short_text(value)


# ------------------------------------------------------------------ equivalence


def _points(world: World, op: Operator, limit: int = 160) -> list[tuple]:
    pools = [world.pool(k, limit=14) for k in op.parameter_types]
    points = list(itertools.product(*pools))
    random.Random(TASK_SEED + 3).shuffle(points)
    return points[:limit]


def _safe(world: World, op: Operator, point: tuple):
    try:
        return world.oracle.evaluate(op, point).value
    except Exception:  # noqa: BLE001
        return NAN


def _same_shape(a: Operator, b: Operator) -> bool:
    return (a.n_ary == b.n_ary and a.unary_position == b.unary_position
            and tuple(a.parameter_types) == tuple(b.parameter_types) and a.result_type == b.result_type)


def equivalence(world: World) -> list[dict]:
    ops = [op for op in world.ordered[:80] if op.n_ary in (1, 2)]
    table = {}
    for op in ops:
        points = _points(world, op)
        table[op.func_id] = (points, [_safe(world, op, p) for p in points])
    scored = []
    for a, b in itertools.combinations(ops, 2):
        if not _same_shape(a, b) or a.definition == b.definition:
            continue
        points, va = table[a.func_id]
        _, vb = table[b.func_id]
        defined = sum(x is not NAN for x in va)
        if defined < len(va) // 2:
            continue
        agree = sum(same_value(x, y) for x, y in zip(va, vb)) / len(va)
        scored.append((agree, a, b))
    scored.sort(key=lambda row: -row[0])
    items: list[dict] = []
    equal = [row for row in scored if row[0] == 1.0]
    near = [row for row in scored if 0.6 <= row[0] < 1.0]
    for agree, a, b in equal[:4]:
        item = _decide_pair(world, a, b)
        if item is not None and item["equal"] and not any(i["equal"] for i in items):
            items.append(item)
        elif item is not None and not item["equal"] and not any(not i["equal"] for i in items):
            items.append(item)  # equal on samples, yet the solver finds a difference
        if len(items) >= 2:
            break
    for agree, a, b in near:
        if sum(not i["equal"] for i in items) >= 2 or len(items) >= 3:
            break
        item = _decide_pair(world, a, b, agree)
        if item is not None and not item["equal"]:
            items.append(item)
    if not any(i["equal"] for i in items):
        # A law the solver proves is an equivalence too: a ◇ b = b ◇ a.
        for op in ops:
            if op.n_ary == 2 and _law_shape(op, "commutative"):
                cell = _int_law(world, op, "commutative") if world.integer else _sample_law(world, op, "commutative")
                if cell.get("holds"):
                    name = world.name(op)
                    items.insert(0, {"left": f"a {name} b", "right": f"b {name} a", "equal": True,
                                     "kind": "law", "check": cell["check"],
                                     "definitions": [{"name": name, "definition": world.show(op.definition)}]})
                    break
    return items[:3]


def _decide_pair(world: World, a: Operator, b: Operator, agree: float | None = None) -> dict | None:
    names = ("a", "b")[: a.n_ary]
    left_node = Call(a, tuple(Variable(n) for n in names))
    right_node = Call(b, tuple(Variable(n) for n in names))
    lt, rt = world.text(left_node), world.text(right_node)
    item = {"left": lt, "right": rt, "kind": "operators",
            "definitions": [{"name": world.name(a), "definition": world.show(a.definition)},
                            {"name": world.name(b), "definition": world.show(b.definition)}]}
    if agree is not None:
        item["agreement"] = round(agree, 3)
    if world.integer and world.encoder is None:
        lo, hi = LAW_RANGE.get(world.spec.world, (-12, 12))
        check = _check("range", range=[lo, hi])
        point = next((p for p in itertools.product(range(lo, hi + 1), repeat=a.n_ary)
                      if not same_value(_safe(world, a, p), _safe(world, b, p))), None)
        if point is None:
            return {**item, "equal": True, "check": check}
    elif world.integer and world.encoder is not None:
        from opulse.solver.equivalence import EquivalenceChecker

        small = LAW_RANGE.get(world.spec.world)
        fallback = None if _expressible(world, [a, b]) else (small or (-12, 12))
        verdict = EquivalenceChecker(world.encoder, timeout_ms=4000, fallback_range=fallback).check(
            left_node, right_node)
        if verdict.status == "proved":
            return {**item, "equal": True, "check": _check("z3")}
        if verdict.status in ("checked", "bounded"):
            return {**item, "equal": True, "check": _check("range", range=list(verdict.range))}
        if verdict.status != "refuted":
            return None
        env = dict(verdict.counterexample)
        point = tuple(env[n] for n in names)
        check = _check("z3") if fallback is None else _check("range", range=list(fallback))
    else:
        points = _points(world, a, limit=400)
        point = next((p for p in points if not same_value(_safe(world, a, p), _safe(world, b, p))), None)
        complete = all(k == "bool" for k in a.parameter_types)
        size = len(points)
        check = _check("all", size=size) if complete else _check("sample", size=size)
        if point is None:
            return {**item, "equal": True, "check": check}
    lv, rv = world.value(left_node, dict(zip(names, point))), world.value(right_node, dict(zip(names, point)))
    if same_value(lv, rv):
        raise AssertionError("an equivalence counterexample is not one for the interpreter")
    return {**item, "equal": False, "check": check,
            "counterexample": {"inputs": [{"name": n, "value": world.enc(v, k)}
                                          for n, v, k in zip(names, point, a.parameter_types)],
                               "left_value": world.enc(lv, a.result_type),
                               "right_value": world.enc(rv, b.result_type)}}


# ------------------------------------------------------------------ contrast, edit, simplify


def contrast(world: World, items: list[dict], count: int = 2) -> list[dict]:
    out = []
    for item in items:
        if len(out) >= count:
            break
        tree = item["_tree"]
        target = tree.operator
        others = [op for op in world.ordered[:80] if op.func_id != target.func_id and _same_shape(op, target)
                  and op.definition is not None]
        for other in others:
            from opulse.bench.context import closure

            twin = _swap(tree, target, other)
            if any(op.func_id == target.func_id for op in closure(world.tools.registry, twin)):
                continue
            first, second = world.value(tree), world.value(twin)
            if same_value(first, second) or first is NAN or second is NAN:
                continue
            name = world.name(target)
            shown = world.show(other.definition).replace(world.name(other), name)
            out.append({"expression": item["expression"], "operator": name,
                        "a": {"definition": world.show(target.definition),
                              "value": world.enc(first, target.result_type)},
                        "b": {"definition": shown, "value": world.enc(second, target.result_type),
                              "from": world.name(other)}})
            break
    return out


def _swap(node: Node, target: Operator, other: Operator) -> Node:
    if not isinstance(node, Call):
        return node
    op = other if node.operator.func_id == target.func_id else node.operator
    return Call(op, tuple(_swap(arg, target, other) for arg in node.args))


def _with_definition(world: World, op: Operator, text: str) -> Oracle:
    registry = OperatorRegistry(replace(other, definition=text) if other.func_id == op.func_id else other
                                for other in world.tools.registry)
    return Oracle(registry, world.tools.settings.symbols, world.oracle.semantics)


def _mutations(definition, rng):
    from opulse.bench.families import common
    from opulse.definition import ast

    found = []
    for path, node in common.nodes_of(definition):
        if isinstance(node, ast.Num) and isinstance(node.value, int) and not isinstance(node.value, bool):
            value = node.value + rng.choice((1, 2, 3))
            found.append(("literal", lambda p=path, n=node, v=value: common.replace_at(
                definition, p, replace(n, value=v))))
        elif isinstance(node, ast.Compare):
            found.append(("comparison", lambda p=path, n=node: common.replace_at(
                definition, p, replace(n, op=common.FLIPPED[n.op]))))
        elif isinstance(node, ast.Apply) and node.n_ary == 2 and node.args[0] != node.args[1]:
            found.append(("swap_operands", lambda p=path, n=node: common.replace_at(
                definition, p, replace(n, args=n.args[::-1]))))
    return found


EDIT_ZH = {"literal": "改一个数", "comparison": "翻转一个比较", "swap_operands": "交换两个操作数"}
EDIT_EN = {"literal": "a number changed", "comparison": "a comparison flipped",
           "swap_operands": "two operands swapped"}


def edit(world: World) -> list[dict]:
    from opulse.bench.families import common
    from opulse.bench.families.edit import dependents

    rng = random.Random(TASK_SEED + 4)
    reach = dependents(world.tools.registry)
    shown = {op.func_id for op in world.ordered[:60]}
    lows = [op for op in world.ordered if op.definition_type != RECURSIVE
            and len(reach[op.func_id] & shown) >= 2]
    lows.sort(key=lambda op: -len(reach[op.func_id] & shown))
    for low in lows[:12]:
        parsed = world.oracle._definition_of(low)
        options = _mutations(parsed, rng)
        rng.shuffle(options)
        for kind, make in options[:6]:
            try:
                new_text = common.render(make(), world.tools.settings.symbols)
                changed = _with_definition(world, low, new_text)
            except Exception:  # noqa: BLE001, S112 - an edit that does not parse is skipped
                continue
            dependents_shown = [op for op in world.ordered[:60] if op.func_id in reach[low.func_id]][:7]
            untouched = [op for op in world.ordered[:30] if op.func_id not in reach[low.func_id]
                         and op.func_id != low.func_id][:2]
            rows = []
            for op in [low, *dependents_shown, *untouched]:
                point = next((p for p in _points(world, op, 40) if _safe(world, op, p) is not NAN), None)
                if point is None:
                    continue
                # Prefer an input whose answer the edit changes.
                for candidate in _points(world, op, 40):
                    before = _safe(world, op, candidate)
                    if before is NAN:
                        continue
                    try:
                        after = changed.evaluate(changed.registry.get(op.func_id), candidate).value
                    except Exception:  # noqa: BLE001
                        after = NAN
                    if not same_value(before, after):
                        point = candidate
                        break
                before = _safe(world, op, point)
                try:
                    after = changed.evaluate(changed.registry.get(op.func_id), point).value
                except Exception:  # noqa: BLE001
                    after = NAN
                call = world.text(Call(op, tuple(Number(v) for v in point)))
                rows.append({"name": world.name(op), "expression": call,
                             "reaches": op.func_id == low.func_id or op.func_id in reach[low.func_id],
                             "before": world.enc(before, op.result_type), "after": world.enc(after, op.result_type),
                             "changed": not same_value(before, after)})
            if sum(row["changed"] for row in rows if row["name"] != world.name(low)) < 2:
                continue
            affected = [world.name(op) for op in world.ordered if op.func_id in reach[low.func_id]]
            return [{"operator": world.name(low), "before": world.show(low.definition),
                     "after": world.show(new_text), "edit": kind, "edit_en": EDIT_EN[kind],
                     "edit_zh": EDIT_ZH[kind], "affected_count": len(affected), "affected": affected[:12],
                     "rows": rows}]
    return []


def simplify(world: World, count: int = 1) -> list[dict]:
    from opulse.bench.families import common

    out = []
    for op in world.ordered[:80]:
        if len(out) >= count:
            break
        if op.definition_type == RECURSIVE:
            continue
        parsed = world.oracle._definition_of(op)
        simple = {}
        for apply_key, callee in _callees(world, parsed):
            if callee.definition_type == SIMPLE and callee.func_id != op.func_id:
                simple[apply_key] = world.oracle._definition_of(callee)
        if not simple:
            continue
        try:
            expanded = common.inline(parsed, simple)
            bloated = common.render(expanded, world.tools.settings.symbols)
        except Exception:  # noqa: BLE001, S112
            continue
        before_ops, after_ops = common.count_operations(expanded), common.count_operations(parsed)
        if before_ops <= after_ops + 1 or len(bloated) > 260:
            continue
        verdict = _same_operator(world, op, bloated)
        if verdict is None:
            continue
        out.append({"operator": world.name(op), "before": world.show(bloated), "after": world.show(op.definition),
                    "before_operations": before_ops, "after_operations": after_ops,
                    "inlined": sorted(world.name(world.tools.registry.find(*key)) for key in simple),
                    "check": verdict})
    return out


def _callees(world: World, definition):
    from opulse.definition import ast

    found = {}
    for branch in definition.branches:
        for node in [branch.expr] + ([branch.condition] if branch.condition is not None else []):
            for apply in ast.iter_applications(node):
                key = (apply.symbol, apply.n_ary, apply.unary_position)
                op = world.tools.registry.find(*key)
                if op is not None and op.definition is not None:
                    found[key] = op
    return list(found.items())


def _same_operator(world: World, op: Operator, text: str) -> dict | None:
    """Whether ``op`` defined by ``text`` is the same operator; z3 when it can tell, else samples."""
    changed = _with_definition(world, op, text)
    names = ("a", "b")[: op.n_ary]
    if world.integer and world.encoder is not None and _expressible(world, [op]):
        from opulse.solver.equivalence import EquivalenceChecker
        from opulse.solver.z3_encode import Z3Encoder

        twin = replace(op, func_id=op.func_id + "-simplified", symbol=_fresh(world), definition=None)
        twin = replace(twin, definition=text.replace(op.symbol, twin.symbol, 1))
        registry = OperatorRegistry([*world.tools.registry, twin])
        oracle = Oracle(registry, world.tools.settings.symbols, world.oracle.semantics)
        verdict = EquivalenceChecker(Z3Encoder(oracle), timeout_ms=5000).check(
            Call(op, tuple(Variable(n) for n in names)), Call(twin, tuple(Variable(n) for n in names)))
        if verdict.status == "proved":
            return _check("z3")
        if verdict.status != "bounded":
            return None
        return _check("range", range=list(verdict.range))
    if world.integer and world.encoder is None:
        lo, hi = LAW_RANGE.get(world.spec.world, (-12, 12))
        for point in itertools.product(range(lo, hi + 1), repeat=op.n_ary):
            before = _safe(world, op, point)
            try:
                after = changed.evaluate(changed.registry.get(op.func_id), point).value
            except Exception:  # noqa: BLE001
                return None
            if not same_value(before, after):
                return None
        return _check("range", range=[lo, hi])
    points = _points(world, op, limit=400)
    for point in points:
        before = _safe(world, op, point)
        try:
            after = changed.evaluate(changed.registry.get(op.func_id), point).value
        except Exception:  # noqa: BLE001
            return None
        if not same_value(before, after):
            return None
    small = SMALL.get(world.spec.world)
    if world.integer and small:
        lo, hi = small
        for point in itertools.product(range(lo, hi + 1), repeat=op.n_ary):
            after = changed.evaluate(changed.registry.get(op.func_id), point).value
            if not same_value(_safe(world, op, point), after):
                return None
        return _check("range", range=[lo, hi])
    complete = all(k == "bool" for k in op.parameter_types)
    return _check("all" if complete else "sample", size=len(points))


def _fresh(world: World) -> str:
    used = {op.symbol for op in world.tools.registry}
    return next(s for s in "⊛⊜⊝⊚⊘⊗⊖⊕⋄⋇" if s not in used and not any(s in u for u in used))


# ------------------------------------------------------------------ export


def export_tasks(world_name: str, directory: str | Path, seed: int | None = None) -> dict:
    """Write ``<world>/tasks.json`` and ``<world>/tasks/*.json`` under ``directory``."""
    directory = Path(directory)
    world = None if world_name == "action" else prepare(world_name, seed)
    browser = directory / f"{world_name}.json"
    if browser.exists():
        published = json.loads(browser.read_text(encoding="utf-8"))
        if world_name == "action":
            from opulse.worlds.action import generate_skills
            from opulse.worlds.showcase_tasks_action import SEED

            expected = [(skill.name, skill.definition()) for skill in generate_skills(seed=SEED)]
        else:
            expected = [(world.name(op), world.show(op.definition)) for op in world.ordered]
        try:
            actual = [(row["name"], row["definition"]) for row in published["operators"]]
        except (KeyError, TypeError) as exc:
            raise ValueError(f"{browser} has no usable operator list") from exc
        if actual != expected:
            raise ValueError(f"{browser} has operators that differ from the task exporter; regenerate the showcase")
    folder = directory / world_name / "tasks"
    with staged_export(folder, directory / world_name / "tasks.json") as (staged, staged_json):
        if world_name == "action":
            from opulse.worlds.showcase_tasks_action import export_action_tasks

            data = export_action_tasks(directory, staged)
        else:
            items = expressions(world, staged)
            data = {"world": world_name, "seed": world.seed, "files": f"{world_name}/tasks/",
                    "granularities": [{k: v for k, v in g.items() if k != "max_depth"} for g in GRANULARITIES],
                    "solver": "z3" if world.encoder is not None and _expressible(world, world.ordered[:1]) else
                    ("range" if world.integer else "sample"),
                    "expressions": items, "holes": holes(world, items, staged), "laws": laws(world),
                    "equivalence": equivalence(world), "contrast": contrast(world, items), "edit": edit(world),
                    "simplify": simplify(world)}
            if world_name == "rel" and not data["edit"]:
                data["notes"] = {"edit": {
                    "en": "No tested edit to a Relations definition changed enough dependent answers to show an edit effect.",
                    "zh": "在关系世界中，测试过的定义改动都没有改变足够多的下游答案，因此没有可展示的改动影响。"}}
            for item in items:
                item.pop("_tree", None)
        data["unsupported"] = sorted(key for key in ("expressions", "holes", "equivalence", "contrast", "edit", "simplify")
                                     if not data.get(key))
        staged_json.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n",
                               encoding="utf-8")
    return data
