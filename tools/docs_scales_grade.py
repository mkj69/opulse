"""Export checked middle-cut derivations for the scale tour.

Run ``python tools/docs_scales_grade.py [--only s10 s100 ...] [--cache DIR]``.
Only scales with a finished integer cache and a published scale example are written.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import docs_scales as scales

from opulse.config import Settings
from opulse.core import OperatorRegistry
from opulse.definition.parser import DefinitionParser
from opulse.expression.nodes import Number, from_ast
from opulse.expression.render import ExpressionRenderer
from opulse.runtime import PythonRuntime
from opulse.trace.reducer import _replace_at
from opulse.trace.tree import build_tree, flatten
from opulse.verify import Oracle, verify_trace
from opulse.verify.steps import check_steps
from opulse.worlds.present import alias

OUT = ROOT / "docs/assets/data/scales_grade"
MAX_FILE = 1_000_000


def prepare(entry: dict, cache: Path):
    """Load the published example's source set and its exact symbol aliases."""
    name = entry["set"]
    original = OperatorRegistry.from_jsonl(cache / f"{name}.jsonl")
    example = json.loads((scales.OUT / entry["scale"] / f"{entry['id']}.json").read_text())
    rows = example["operators"]
    names = {original.get(row["id"]).symbol: row["symbol"] for row in rows}
    selected = {row["id"] for row in rows}
    registry = OperatorRegistry(
        replace(op, symbol=names[op.symbol], definition=alias(op.definition, names))
        if op.func_id in selected and op.definition is not None else op
        for op in original if op.func_id in selected
    )
    settings = Settings.load(scales.ROOT / scales.SPECS[name][3])
    parser = DefinitionParser(settings.symbols, registry)
    renderer = ExpressionRenderer(settings.symbols)
    source = from_ast(parser.parse_expr(entry["expression"], expression_mode=True), registry)
    oracle = Oracle(registry, settings.symbols, settings.semantics.build())
    runtime = PythonRuntime(registry, settings.semantics.build())
    return example, registry, parser, renderer, source, oracle, runtime


def export(entry: dict, cache: Path) -> tuple[Path, int]:
    example, registry, parser, renderer, source, oracle, runtime = prepare(entry, cache)
    header = example["header"]
    tree = build_tree(source, registry, runtime, parser, max_nodes=scales.MAX_NODES)
    cuts = header["cut_table"]
    # Prefer several hundred lines and keep headroom for long intermediate expressions.
    choices = sorted((row for row in cuts if 100 <= row["steps"] <= 2000),
                     key=lambda row: (abs(row["steps"] - 500), row["L"]))
    if not choices:
        choices = sorted(cuts, key=lambda row: abs(row["steps"] - 500))
    for choice in choices:
        limit = choice["L"]
        trace = flatten(tree, lambda op, cutoff=limit: op.definition is not None and (op.recursive_layer or 0) >= cutoff)
        verify_trace(trace, oracle)
        lines = [renderer.full(step.expression_after) for step in trace.steps]
        evals = [i for i, step in enumerate(trace.steps)
                 if step.kind == "eval" and isinstance(step.output, int) and 2 <= i < len(lines) - 2]
        if not evals:
            continue
        slip = min(evals, key=lambda i: abs(i - len(lines) * .7))
        step = trace.steps[slip]
        wrong = renderer.full(_replace_at(step.expression_before, step.path, Number(step.output + 1)))
        bad_lines = lines.copy()
        bad_lines[slip] = wrong
        payload = {
            "schema": "opulse.scales-grade/1", "scale": entry["scale"], "example": entry["id"],
            "set": entry["set"], "set_size": entry["set_size"], "layer": entry["layer"],
            "closure_size": entry["closure_size"], "cut": limit, "full_steps": entry["full_steps"],
            "question": entry["expression"], "answer": entry["value"],
            "slip": slip, "expected_value": str(step.output), "wrong_value": str(step.output + 1),
            "runs": []
        }
        answer = tree.value
        statuses = []
        previous = source
        for line in lines:
            single = check_steps(previous, [line], parser, registry, oracle, answer)
            if single.first_error is not None:
                raise ValueError(f"individual step failed in {entry['id']}: {single.errors}")
            statuses.append("repeat" if single.steps == 0 else "single" if single.single_steps else "jump")
            previous = from_ast(parser.parse_expr(line, expression_mode=True, strict=True), registry)
        for run_lines in (lines, bad_lines):
            report = check_steps(source, run_lines, parser, registry, oracle, answer)
            row_statuses = statuses if run_lines is lines else statuses[:slip] + ["error"] + ["skipped"] * (len(lines) - slip - 1)
            payload["runs"].append({"lines": run_lines, "statuses": row_statuses, "report": report.to_dict()})
        good, bad = (run["report"] for run in payload["runs"])
        if not good["derivation_correct"] or good["first_error"] is not None:
            raise ValueError(f"good derivation failed: {entry['id']} cut {limit}: {good}")
        if bad["first_error"] != slip:
            raise ValueError(f"slip was not found: {entry['id']} cut {limit}: {bad}")
        content = scales.compact(payload)
        if len(content) <= MAX_FILE:
            OUT.mkdir(parents=True, exist_ok=True)
            path = OUT / f"{entry['scale']}.json"
            path.write_bytes(content)
            return path, len(content)
    raise ValueError(f"no grading cut fits {MAX_FILE} bytes for {entry['id']}")


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    cli.add_argument("--only", nargs="+", choices=[row[0] for row in scales.SCALES])
    cli.add_argument("--cache", type=Path, default=Path("/tmp/opulse_scales"))
    args = cli.parse_args()
    index = json.loads((scales.OUT / "index.json").read_text())
    for row in index["scales"]:
        if args.only and row["key"] not in args.only:
            continue
        candidates = [dict(item, scale=row["key"], set_size=next(
            (source["size"] for source in row["sets"] if source["name"] == item["set"]), 0))
            for item in row["examples"] if item["world"] == "integer" and
            scales.finished(args.cache, item["set"]) is not None]
        if not candidates:
            print(f"{row['key']}: pending")
            continue
        chosen = max(candidates, key=lambda item: (
            item["layer"], item["kind"] == "recursive" if row["key"] == "s10" else False,
            item["full_steps"], item["closure_size"]))
        path, size = export(chosen, args.cache)
        print(f"{path}: {size} bytes", flush=True)


if __name__ == "__main__":
    main()
