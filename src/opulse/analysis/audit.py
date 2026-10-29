"""Statistics and quality gates for expression records and benchmark tasks."""

from __future__ import annotations

import json
import math
import random
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from opulse.core.registry import OperatorRegistry

BUCKET_EDGES = (0, 1, 2, 3, 4, 5, 10, 20, 50, 100, 200, 500, 1000)
MISSING = "<missing>"


def _key(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _numbers(tree: dict) -> set[int]:
    if tree.get("type") == "numeric_atoms":
        return {tree["value"]}
    return set().union(*(_numbers(child) for child in _children(tree)))


def _children(tree: dict) -> list[dict]:
    if tree.get("type") == "call":  # three or more arguments
        return list(tree["args"])
    return [tree[name] for name in ("left_expr", "right_expr", "unary_expr") if name in tree]


def _depth(tree: dict) -> int:
    return 1 + max((_depth(child) for child in _children(tree)), default=0)


def _calls(tree: dict):
    for child in _children(tree):
        yield from _calls(child)
    if tree.get("type") in ("binary", "unary", "call"):
        yield tree


def _histogram(values: list[float]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for value in values:
        if value < 0:
            label = "<0"
        elif value > BUCKET_EDGES[-1]:
            label = ">1000"
        else:
            lower = 0
            for edge in BUCKET_EDGES:
                if value <= edge:
                    label = str(edge) if edge <= 5 else f"{lower + 1}-{edge}"
                    break
                lower = edge
        counts[label] += 1
    return dict(counts)


def _percentile(values: list[float], fraction: float) -> float:
    position = (len(values) - 1) * fraction
    lower = math.floor(position)
    return values[lower] + (values[math.ceil(position)] - values[lower]) * (position - lower)


def _distribution(values: list[float]) -> dict:
    ordered = sorted(values)
    return {"count": len(values), "min": ordered[0], "median": statistics.median(ordered),
            "p90": _percentile(ordered, 0.9), "max": ordered[-1], "histogram": _histogram(values)}


def _duplicates(keys: list[str], labels: dict[str, str]) -> dict:
    counts = Counter(keys)
    duplicates = sum(count - 1 for count in counts.values())
    examples = [{"value": labels[key][:160], "count": count} for key, count in counts.most_common()
                if count > 1][:3]
    return {"count": duplicates, "share": duplicates / len(keys) if keys else 0.0, "examples": examples}


def _overlap(left: set[str], right: set[str], labels: dict[str, str]) -> dict:
    shared = left & right
    denominator = min(len(left), len(right))
    return {"count": len(shared), "share": len(shared) / denominator if denominator else 0.0,
            "examples": [labels[key][:160] for key in sorted(shared)[:3]]}


def _gini(values: list[int]) -> float:
    total = sum(values)
    if not total:
        return 0.0
    ordered = sorted(values)
    return sum((2 * index - len(values) - 1) * value for index, value in enumerate(ordered, 1)) / (
        len(values) * total)


def _operator_calls(record: dict, kind: str, registry: OperatorRegistry, parsers: dict) -> list[str] | None:
    if kind == "expression":
        calls = _calls(record["tree"])
        found = []
        for call in calls:
            n_ary = len(call["args"]) if call["type"] == "call" else 1 if call["type"] == "unary" else 2
            op = registry.find(call["operator"], n_ary, call.get("position"))
            if op is None:
                return None
            found.append(op.func_id)
        return found
    # Benchmark tasks carry rendered expressions, but no serialized tree.
    from opulse.config import Symbols
    from opulse.definition.parser import DefinitionParser
    from opulse.expression.aliases import AliasMap, aliased_registry
    from opulse.expression.nodes import from_ast, iter_calls

    naming = record.get("axes", {}).get("naming", "symbols")
    if naming not in parsers:
        if naming == "symbols":
            display = registry
        elif naming in ("pseudo", "english"):
            display = aliased_registry(registry, AliasMap.build(registry, random.Random(20261019),
                                                               style=naming, symbols=Symbols()))
        else:
            return None
        parsers[naming] = (display, DefinitionParser(Symbols(), display))
    display, parser = parsers[naming]
    try:
        tree = from_ast(parser.parse_expr(record["expression"], expression_mode=True), display)
    except (KeyError, ValueError):
        return None  # e.g. a benchmark built with aliased operator names
    return [call.operator.func_id for call in iter_calls(tree)]


def audit_data(paths: list[Path], operators: Path | None = None, *, max_duplicate_share: float = 0.01,
               max_common_answer_share: float = 0.2, max_cross_file_overlap: float = 0.0,
               require_uniform_provenance: bool = True) -> dict:
    """Audit JSONL files. Duplicate shares count repeated rows; overlap uses unique keys.

    Answer shares use defined answers as the denominator. Cross-file overlap is
    divided by the smaller file's unique-key count for each pair and key type.
    """
    registry = OperatorRegistry.from_jsonl(operators) if operators else None
    files = []
    all_answers: Counter[str] = Counter()
    answer_values: dict[str, object] = {}
    axes: dict[str, list[float]] = defaultdict(list)
    provenance: dict[str, Counter[str]] = {"operator_set": Counter(), "config": Counter()}
    undefined = equals_literal = 0
    usage: Counter[str] = Counter()
    parsers: dict = {}
    unparsed = 0
    labels: dict[str, str] = {}

    for path in paths:
        trees: list[str] = []
        prompts: list[str] = []
        kind = None
        count = 0
        with path.open(encoding="utf-8") as source:
            for line_no, line in enumerate(source, 1):
                if not line.strip():
                    continue
                record = json.loads(line)
                row_kind = "expression" if "tree" in record and "result" in record else (
                    "benchmark" if "prompt" in record and "answer" in record else None)
                if row_kind is None or (kind is not None and row_kind != kind):
                    raise ValueError(f"{path}:{line_no}: expected one kind of expression records or benchmark tasks")
                kind = row_kind
                count += 1
                answer = record["result"] if kind == "expression" else record["answer"]
                is_undefined = (record.get("undefined", answer is None) if kind == "expression"
                                else answer is None)
                if is_undefined:
                    undefined += 1
                else:
                    answer_key = _key(answer)
                    all_answers[answer_key] += 1
                    answer_values[answer_key] = answer
                    if isinstance(answer, int) and not isinstance(answer, bool):
                        literals = (_numbers(record["tree"]) if kind == "expression" else
                                    {int(value) for value in re.findall(r"(?<!\w)\d+(?!\w)",
                                                                        record["expression"])})
                        equals_literal += answer in literals
                prompt = record["expression"] if kind == "expression" else record["prompt"]
                prompts.append(prompt)
                labels[prompt] = prompt
                if kind == "expression":
                    tree_key = _key(record["tree"])
                    trees.append(tree_key)
                    labels[tree_key] = record["expression"]
                    fields = {"expression_depth": _depth(record["tree"]),
                              "applications": sum(1 for _ in _calls(record["tree"])),
                              "steps": len(record.get("steps", []))}
                    fields.update({name: record[name] for name in ("expansion", "max_path_depth",
                                                                     "max_edge_count", "operation_count",
                                                                     "highest_layer", "priority_levels")
                                   if name in record})
                    if record.get("cot") is not None:
                        fields["cot_length"] = len(record["cot"])
                else:
                    fields = record.get("axes", {})
                for name, value in fields.items():
                    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
                        axes[name].append(value)
                meta = record.get("provenance") or {}
                for name, values in provenance.items():
                    values[_key(meta.get(name, MISSING))] += 1
                if registry:
                    calls = _operator_calls(record, kind, registry, parsers)
                    if calls is None:
                        unparsed += 1
                    else:
                        usage.update(calls)
        files.append({"path": str(path), "kind": kind or "empty", "count": count,
                      "duplicates": {"trees": _duplicates(trees, labels),
                                     "prompts": _duplicates(prompts, labels)},
                      "_trees": set(trees), "_prompts": set(prompts)})

    total = sum(item["count"] for item in files)
    defined = sum(all_answers.values())
    top = [{"answer": answer_values[key], "count": count} for key, count in all_answers.most_common(10)]
    answer_report = {"defined_count": defined, "undefined_count": undefined,
                     "undefined_share": undefined / total if total else 0.0,
                     "distinct": len(all_answers), "top_10": top,
                     "most_common_share": top[0]["count"] / defined if defined else 0.0,
                     "zero_share": all_answers[_key(0)] / defined if defined else 0.0,
                     "equals_expression_number_share": equals_literal / defined if defined else 0.0}
    pairs = []
    for index, left in enumerate(files):
        for right in files[index + 1:]:
            pairs.append({"files": [left["path"], right["path"]],
                          "trees": _overlap(left["_trees"], right["_trees"], labels),
                          "prompts": _overlap(left["_prompts"], right["_prompts"], labels)})
    for item in files:
        del item["_trees"]
        del item["_prompts"]
    uniform = all(len(values) <= 1 for values in provenance.values())
    provenance_report = {"uniform": uniform,
                         **{name: [{"value": json.loads(value), "count": count} for value, count in values.items()]
                            for name, values in provenance.items()}}
    coverage = None
    if registry:
        defined_ops = [op for op in registry if op.definition is not None]
        layers: dict[str, list] = defaultdict(list)
        for op in defined_ops:
            layers[str(op.recursive_layer or 0)].append(op)
        coverage = {"defined_total": len(defined_ops),
                    "used_count": sum(usage[op.func_id] > 0 for op in defined_ops),
                    "by_layer": {layer: {"defined": len(ops),
                                         "used": sum(usage[op.func_id] > 0 for op in ops)}
                                 for layer, ops in sorted(layers.items(), key=lambda pair: int(pair[0]))},
                    "gini": _gini([usage[op.func_id] for op in defined_ops]),
                    "usage": {op.func_id: usage[op.func_id] for op in defined_ops},
                    "unparsed_records": unparsed}
    max_duplicate = max((item["duplicates"][key]["share"] for item in files
                         for key in ("trees", "prompts")), default=0.0)
    max_overlap = max((pair[key]["share"] for pair in pairs for key in ("trees", "prompts")), default=0.0)
    failures = []
    if max_duplicate > max_duplicate_share:
        failures.append("duplicate share")
    if answer_report["most_common_share"] > max_common_answer_share:
        failures.append("most-common-answer share")
    if max_overlap > max_cross_file_overlap:
        failures.append("cross-file overlap")
    if require_uniform_provenance and not uniform:
        failures.append("provenance mixture")
    by_kind: Counter[str] = Counter()
    for item in files:
        if item["count"]:
            by_kind[item["kind"]] += item["count"]
    return {"counts": {"total": total, "by_kind": dict(by_kind)},
            "answers": answer_report, "axes": {name: _distribution(values) for name, values in sorted(axes.items())},
            "operator_coverage": coverage, "files": files,
            "overlap": {"pairs": pairs, "max_share": max_overlap}, "provenance": provenance_report,
            "gates": {"passed": not failures, "failures": failures,
                      "thresholds": {"max_duplicate_share": max_duplicate_share,
                                     "max_most_common_answer_share": max_common_answer_share,
                                     "max_cross_file_overlap": max_cross_file_overlap,
                                     "require_uniform_provenance": require_uniform_provenance},
                      "max_duplicate_share": max_duplicate}}
