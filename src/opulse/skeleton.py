"""Typed operator skeletons and checked instances in registered atom worlds."""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass, replace
from pathlib import Path

from opulse.canary import marked
from opulse.config import Settings
from opulse.core.operator import Operator
from opulse.core.registry import OperatorRegistry
from opulse.core.semantics import NAN, base_operation_name
from opulse.core.types import freeze
from opulse.definition import ast
from opulse.definition.interpreter import EngineError
from opulse.definition.parser import DefinitionParser
from opulse.generation.drafts import Draft
from opulse.generation.pipeline import OperatorFactory
from opulse.generation.typed import sample_value


class NoMatchError(ValueError):
    """No checked correspondence was found in the target world."""


def _digest(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _role(op: Operator) -> str:
    if op.result_type == "bool":
        return "predicate"
    return "unary transform" if op.n_ary == 1 else "binary combine" if op.n_ary == 2 else "combine"


def _shape(node):
    """Remove material types while retaining every edge, condition and literal."""
    if isinstance(node, dict):
        return {key: _shape(value) for key, value in node.items()
                if key not in ("parameter_types", "result_type", "role", "position",
                               "recursion_form")}
    if isinstance(node, list):
        return [_shape(value) for value in node]
    return node


@dataclass
class SkeletonSet:
    records: list[dict]

    def to_dict(self) -> dict:
        return marked({"format": "opulse.skeleton.v1", "skeletons": self.records})

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> SkeletonSet:
        if data.get("format") != "opulse.skeleton.v1":
            raise ValueError("unknown skeleton format")
        records = data["skeletons"]
        if len({record["id"] for record in records}) != len(records):
            raise ValueError("duplicate skeleton id")
        for record in records:
            if _digest(_shape({key: value for key, value in record.items()
                               if key not in ("id", "structural_hash", "source_symbol", "source_func_id",
                                              "source_correspondence")})) != record["structural_hash"]:
                raise ValueError(f"invalid structural hash for {record['id']}")
            if not record["id"].startswith(record["structural_hash"]):
                raise ValueError(f"invalid skeleton id {record['id']}")
        return cls(records)

    @classmethod
    def read(cls, path: str | Path) -> SkeletonSet:
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def write(self, path: str | Path) -> None:
        Path(path).write_text(self.to_json() + "\n", encoding="utf-8")


def extract(registry: OperatorRegistry, settings: Settings | None = None) -> SkeletonSet:
    """Extract every defined operator in dependency order."""
    settings = settings or Settings()
    parser = DefinitionParser(settings.symbols, registry)
    ids: dict[str, str] = {}
    records = []
    counts: dict[str, int] = {}
    for op in registry.topological_order():
        if op.definition is None:
            continue
        definition = parser.parse(op.definition)
        holes: list[dict] = []
        source_correspondence: dict[str, str] = {}
        dependencies: list[str] = []

        def expr(node, op=op, dependencies=dependencies, holes=holes,
                 source_correspondence=source_correspondence):
            if isinstance(node, ast.Var):
                return {"kind": "var", "name": node.name}
            if isinstance(node, ast.Num):
                return {"kind": "num", "value": node.value, "base": node.base}
            if isinstance(node, ast.Literal):
                return {"kind": "literal", "value": node.value}
            if isinstance(node, ast.NaN):
                return {"kind": "nan"}
            if isinstance(node, ast.Search):
                return {"kind": "search", "index": node.index, "bound": node.bound,
                        "condition": condition(node.condition)}
            callee = registry.find(node.symbol, node.n_ary, node.unary_position)
            if callee is None:
                raise ValueError(f"unresolved application {node.symbol!r}")
            args = [expr(arg) for arg in node.args]
            if callee.func_id == op.func_id:
                return {"kind": "self", "args": args}
            if callee.definition is not None:
                target = ids[callee.func_id]
                if target not in dependencies:
                    dependencies.append(target)
                return {"kind": "call", "target": target, "args": args}
            hole_id = f"h{len(holes)}"
            holes.append({"id": hole_id, "arity": callee.n_ary,
                          "parameter_types": list(callee.parameter_types),
                          "result_type": callee.result_type, "position": callee.unary_position,
                          "role": _role(callee)})
            source_correspondence[hole_id] = callee.func_id
            return {"kind": "hole", "hole": hole_id, "args": args}

        def condition(node):
            if isinstance(node, ast.Compare):
                return {"kind": "compare", "op": node.op, "left": expr(node.left), "right": expr(node.right)}
            if isinstance(node, (ast.And, ast.Or)):
                return {"kind": "and" if isinstance(node, ast.And) else "or",
                        "left": condition(node.left), "right": condition(node.right)}
            if isinstance(node, ast.Not):
                return {"kind": "not", "operand": condition(node.operand)}
            return {"kind": "truth", "expr": expr(node.expr)}

        body = [{"expr": expr(branch.expr), "condition": condition(branch.condition)
                 if branch.condition is not None else None, "else": branch.is_else}
                for branch in definition.branches]
        record = {"kind": op.definition_type, "arity": op.n_ary, "position": op.unary_position,
                  "parameter_types": list(op.parameter_types), "result_type": op.result_type,
                  "parameters": list(definition.parameters), "branches": body, "holes": holes,
                  "complexity": [op.max_path_depth, op.max_edge_count],
                  "dependencies": dependencies, "source_symbol": op.symbol,
                  "source_func_id": op.func_id, "source_correspondence": source_correspondence}
        if op.definition_type == "recursive_definition":
            modulus_guard = any(
                base_operation_name(call.symbol, call.n_ary, call.unary_position) == "mod"
                for branch in definition.branches if branch.condition is not None
                for call in ast.iter_applications(branch.condition)
            )
            record["recursion_form"] = "bounded_mod" if modulus_guard else "direct"
        record["structural_hash"] = _digest(_shape({key: value for key, value in record.items()
                                                     if key not in ("source_symbol", "source_func_id",
                                                                    "source_correspondence")}))
        base = record["structural_hash"]
        counts[base] = counts.get(base, 0) + 1
        record["id"] = base if counts[base] == 1 else f"{base}.{counts[base]}"
        ids[op.func_id] = record["id"]
        records.append(record)
    return SkeletonSet(records)


def _mapped(kind: str, types: dict[str, str]) -> str:
    if kind in types:
        return types[kind]
    if kind.startswith("list[") and kind.endswith("]"):
        return f"list[{_mapped(kind[5:-1], types)}]"
    return kind


def _candidates(hole: dict, atoms: OperatorRegistry, types: dict[str, str]) -> list[Operator]:
    params = tuple(_mapped(t, types) for t in hole["parameter_types"])
    result = _mapped(hole["result_type"], types)
    return [op for op in atoms if op.definition is None and op.is_base is None
            and op.n_ary == hole["arity"] and op.parameter_types == params and op.result_type == result]


def _definition(record: dict, bindings: dict[str, Operator], made: dict[str, Operator],
                symbol: str) -> ast.Definition:
    def expr(node):
        kind = node["kind"]
        if kind == "var":
            return ast.Var(node["name"])
        if kind == "num":
            return ast.Num(node["value"], node["base"])
        if kind == "literal":
            return ast.Literal(freeze(node["value"]))
        if kind == "nan":
            return ast.NaN()
        if kind == "search":
            return ast.Search(node["index"], node["bound"], condition(node["condition"]))
        op = bindings[node["hole"]] if kind == "hole" else made[node["target"]] if kind == "call" else None
        if kind == "self":
            return ast.Apply(symbol, tuple(expr(arg) for arg in node["args"]), record["position"])
        if op is None:
            raise ValueError(f"unknown skeleton node {kind}")
        return ast.Apply(op.symbol, tuple(expr(arg) for arg in node["args"]), op.unary_position)

    def condition(node):
        kind = node["kind"]
        if kind == "compare":
            return ast.Compare(expr(node["left"]), node["op"], expr(node["right"]))
        if kind in ("and", "or"):
            cls = ast.And if kind == "and" else ast.Or
            return cls(condition(node["left"]), condition(node["right"]))
        if kind == "not":
            return ast.Not(condition(node["operand"]))
        return ast.Truth(expr(node["expr"]))

    lhs = ast.Apply(symbol, tuple(ast.Var(name) for name in record["parameters"]), record["position"])
    return ast.Definition(lhs, tuple(ast.Branch(expr(branch["expr"]),
                          condition(branch["condition"]) if branch["condition"] is not None else None,
                          branch["else"]) for branch in record["branches"]))


def _sample(kind: str, rng: random.Random, samples: dict[str, list] | None = None):
    if samples and kind in samples:
        if not samples[kind]:
            raise ValueError(f"empty sample values for {kind}")
        return freeze(rng.choice(samples[kind]))
    return sample_value(kind, rng)


def _sample_reason(factory: OperatorFactory, draft: Draft, op: Operator, rng: random.Random,
                   samples: dict[str, list] | None = None) -> str | None:
    """Require defined and varying values in addition to the factory checks."""
    values = []
    for _ in range(80):
        args = tuple(_sample(t, rng, samples) if t != "int" or samples and "int" in samples
                     else rng.randint(-20, 20)
                     for t in op.parameter_types)
        value = factory.oracle.evaluate(op, args).value
        if value is not NAN:
            values.append(repr(value))
    partial = (draft.definition_type == "recursive_definition" and draft.recursion_style != "bounded_mod") or \
        (draft.definition_type != "recursive_definition" and
         (draft.definition.branches[-1].condition is not None or
          isinstance(draft.definition.branches[-1].expr, ast.Search)))
    share = 0.05 if partial else factory.settings.operators.min_defined_share
    minimum = max(2, int(share * 80))
    if len(values) < minimum:
        return "defined on too few inputs"
    if len(set(values)) < 2:
        return "no varied outputs"
    return None


def instantiate(skeletons: SkeletonSet, atoms: OperatorRegistry, *, world: str,
                settings: Settings | None = None, type_map: dict[str, str] | None = None,
                correspondence: dict[str, str] | None = None, seed: int = 0,
                attempts: int = 100, sample_values: dict[str, list] | None = None,
                probe_seed: int | None = None) -> tuple[OperatorRegistry, list[dict]]:
    """Search deterministic hole bindings and return checked instances and their records.

    Correspondence keys are ``skeleton_id:hole_id`` and values are target atom func ids.
    Explicit mappings constrain the search. A failed search raises :class:`NoMatchError`.
    """
    settings = settings or Settings()
    type_map = type_map or {}
    correspondence = correspondence or {}
    rng = random.Random(seed)
    for record in skeletons.records:
        for hole in record["holes"]:
            if not _candidates(hole, atoms, type_map):
                raise NoMatchError(f"no atom matches {record['id']}:{hole['id']} in {world}")
    last_reason = "no candidates"
    for _ in range(attempts):
        registry = OperatorRegistry(atoms)
        # Drafting requirements are irrelevant here: the tree is already fixed.
        checks_settings = replace(settings,
                                  operators=replace(settings.operators, condition_atoms=()),
                                  recursion=replace(settings.recursion, enabled=False, search_enabled=False))
        factory = OperatorFactory(checks_settings, registry, random.Random(rng.randrange(2**63)))
        made: dict[str, Operator] = {}
        rows = []
        for record in skeletons.records:
            bindings = {}
            for hole in record["holes"]:
                key = f"{record['id']}:{hole['id']}"
                candidates = _candidates(hole, atoms, type_map)
                if key in correspondence:
                    candidates = [op for op in candidates if op.func_id == correspondence[key]]
                if not candidates:
                    raise NoMatchError(f"invalid correspondence for {key} in {world}")
                bindings[hole["id"]] = rng.choice(candidates)
            symbol = record["source_symbol"]
            if any(op.symbol == symbol for op in registry) or any(op.symbol == symbol for op in made.values()):
                symbol = factory.symbols.new_symbol()
            definition = _definition(record, bindings, made, symbol)
            draft = Draft(symbol, record["arity"], record["position"], definition, record["kind"],
                          complexity=tuple(record["complexity"]),
                          recursion_style=record.get("recursion_form"),
                          parameter_types=tuple(_mapped(t, type_map) for t in record["parameter_types"]),
                          result_type=_mapped(record["result_type"], type_map))
            try:
                operator = factory._compile(draft)
                sampler = (lambda kind, draw, registry: _sample(kind, draw, sample_values)) if sample_values else None
                reason = factory._reject_reason(draft, operator, operator.recursive_layer or 0,
                                                sample_value_fn=sampler)
                if reason is None:
                    reason = _sample_reason(factory, draft, operator, rng, sample_values)
            except (ValueError, TypeError, KeyError, RuntimeError, OverflowError, EngineError,
                    RecursionError) as exc:
                reason = str(exc)
            if reason is not None:
                last_reason = f"{record['id']}: {reason}"
                break
            operator.skeleton_id = record["id"]
            operator.world = world
            operator.correspondence_grade = "G1"
            factory.add(operator)
            made[record["id"]] = operator
            from opulse.matched import probe_instance

            probe = probe_instance(registry, operator, count=16, seed=seed if probe_seed is None else probe_seed,
                                   sample_values=sample_values, settings=settings)
            rows.append({"skeleton_id": record["id"], "world": world, "func_id": operator.func_id,
                         "structural_hash": record["structural_hash"],
                         "correspondence": {hole: op.func_id for hole, op in bindings.items()},
                         "grade": "G1", "unfolded_length": probe["unfolded_length"], "probe": probe})
        else:
            observed = extract(registry, settings).records
            if [(row["id"], row["structural_hash"], row["complexity"]) for row in observed] == \
                    [(row["id"], row["structural_hash"], row["complexity"])
                     for row in skeletons.records]:
                return registry, rows
            last_reason = "structural hash or composition depth changed"
    raise NoMatchError(f"no accepted correspondence in {world} after {attempts} attempts; last rejection: {last_reason}")


def value_table(registry: OperatorRegistry, skeleton_id: str, settings: Settings | None = None,
                sample_values: dict[str, list] | None = None) -> list:
    """A reproducible sample table for comparing instances in compatible value types."""
    from opulse.verify import Oracle

    settings = settings or Settings()
    op = _operator_for(registry, skeleton_id, settings)
    oracle = Oracle(registry, settings.symbols, settings.semantics.build())
    rng = random.Random(0)
    table = []
    for _ in range(16):
        args = tuple(_sample(t, rng, sample_values) for t in op.parameter_types)
        value = oracle.evaluate(op, args).value
        table.append({"inputs": args, "value": None if value is NAN else value})
    return table


def verify_match(left: OperatorRegistry, right: OperatorRegistry, skeleton_id: str,
                 settings: Settings | None = None, left_samples: dict[str, list] | None = None,
                 right_samples: dict[str, list] | None = None, grade: str | None = None) -> dict:
    """Compare structure, depth, and sampled values for two instances."""
    settings = settings or Settings()
    a = _operator_for(left, skeleton_id, settings)
    b = _operator_for(right, skeleton_id, settings)
    same_structure = skeleton_id in {record["id"] for record in extract(left, settings).records} and \
        skeleton_id in {record["id"] for record in extract(right, settings).records}
    same_depth = a.max_path_depth == b.max_path_depth
    different_values = [row["value"] for row in value_table(left, skeleton_id, settings, left_samples)] != \
        [row["value"] for row in value_table(right, skeleton_id, settings, right_samples)]
    if grade is None:
        labels = (a.correspondence_grade or "G1", b.correspondence_grade or "G1")
        grade = min(labels, key={"G1": 1, "G2": 2, "G3": 3}.get)
    return {"structural_hash_equal": same_structure, "composition_depth_equal": same_depth,
            "value_tables_differ": different_values, "grade": grade}


def _operator_for(registry: OperatorRegistry, skeleton_id: str, settings: Settings) -> Operator:
    for op in registry:
        if op.skeleton_id == skeleton_id:
            return op
    for record in extract(registry, settings).records:
        if record["id"] == skeleton_id:
            return registry.get(record["source_func_id"])
    raise KeyError(skeleton_id)
