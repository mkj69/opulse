"""Export verified deep-operator fill-in problems from finished scale caches.

Run ``python tools/docs_scales_solve.py [--only s10000] [--cache DIR]``.
Each ``sN.json`` uses schema ``opulse.scales-solve/1``. The unknown is an
argument of the generated operator. Candidate values are checked by the
reference interpreter. ``steps`` counts each candidate check fully opened to
atoms, with a selection cap of 200,000 steps and 1,800 DAG nodes per check.
The exported counts are exact; an operator form exceeding either cap is skipped.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

from docs_scales import (
    ROOT,
    SCALES,
    SPECS,
    candidates,
    closure,
    compact,
    count_cuts,
    finished,
    inputs_for,
)

sys.path.insert(0, str(ROOT / "src"))

from opulse.cli.holes import record
from opulse.config import Settings
from opulse.core import NAN, OperatorRegistry
from opulse.definition.parser import DefinitionParser
from opulse.expression.nodes import Call, Number, Variable, to_ast
from opulse.expression.render import ExpressionRenderer
from opulse.runtime import PythonRuntime
from opulse.solver.holes import HoleSolver
from opulse.trace.tree import build_tree, flatten, verify_tree
from opulse.verify import Oracle, verify_trace

OUT = ROOT / "docs/assets/data/scales_solve"
MAX_FILE = 1_000_000
MAX_STEPS = 200_000
MAX_NODES = 1_800
DOMAIN = (-12, 12)
PREFERRED_ANSWER = {"s10": -4, "s100": 6, "s1000": 12, "s10000": -9}
MIN_ANSWER_STEPS = {"s10": 100, "s100": 100, "s1000": 1_000, "s10000": 1_000}


def expression(op, inputs: tuple, position: int, x: int | None):
    """Build one deep call, with its chosen slot either numeric or unknown."""
    return Call(op, tuple(Variable("x") if i == position and x is None else
                          Number(x if i == position else value)
                          for i, value in enumerate(inputs)))


def scan_form(op, inputs: tuple, position: int, oracle: Oracle) -> list[dict]:
    node = expression(op, inputs, position, None)
    rows = []
    for x in range(DOMAIN[0], DOMAIN[1] + 1):
        value = oracle.evaluate_expr(to_ast(node), {"x": x}).value
        rows.append({"x": x, "value": None if value is NAN else value})
    return rows


def candidate_batches(registry):
    """Try high-layer closure leaders, then descend when their traces hit caps."""
    for breadth, input_limit in ((6, 1), (18, 5)):
        yield ([op for kind in ("simple", "branch", "recursive")
                for op in candidates(registry, kind)[:breadth]], input_limit)
    defined = [op for op in registry if op.definition is not None]
    top = max(op.recursive_layer or 0 for op in defined)
    for layer in range(top - 2, -1, -1):
        pool = [op for op in defined if op.recursive_layer == layer]
        pool.sort(key=lambda op: (-len(closure(op, registry)), op.func_id))
        yield pool[:36], 3


def forms(oracle: Oracle, operators: list, input_limit: int):
    """Yield input slots with a unique answer in a deterministic order."""
    for op in operators:
        for position, parameter_type in enumerate(op.parameter_types):
            if parameter_type != "int":
                continue
            seen = set()
            for raw_inputs in inputs_for(op)[:input_limit]:
                inputs = tuple(0 if i == position else v for i, v in enumerate(raw_inputs))
                if inputs in seen:
                    continue
                seen.add(inputs)
                rows = scan_form(op, inputs, position, oracle)
                frequency = Counter(row["value"] for row in rows if row["value"] is not None)
                unique = [row["x"] for row in rows
                          if row["value"] is not None and frequency[row["value"]] == 1]
                if unique:
                    noninjective = any(count > 1 for count in frequency.values())
                    yield noninjective, op, inputs, position, rows, unique


def counted_scan(op, inputs: tuple, position: int, rows: list[dict],
                 registry, runtime, parser) -> list[dict]:
    """Count the full DAG unfolding for every candidate; reject capped forms."""
    for row in rows:
        tree = build_tree(expression(op, inputs, position, row["x"]),
                          registry, runtime, parser, max_nodes=MAX_NODES)
        steps = count_cuts(tree)[0]
        if steps > MAX_STEPS:
            raise ValueError("candidate exceeds unfolded step cap")
        if tree.value is NAN:
            if row["value"] is not None:
                raise AssertionError("DAG and reference interpreter disagree")
        elif tree.value != row["value"]:
            raise AssertionError("DAG and reference interpreter disagree")
        row["steps"] = steps
    return rows


def make_problem(scale: str, name: str, config: str, cache: Path) -> dict:
    started = time.monotonic()
    settings = Settings.load(ROOT / config)
    registry = OperatorRegistry.from_jsonl(cache / f"{name}.jsonl")
    oracle = Oracle(registry, settings.symbols, settings.semantics.build())
    runtime = PythonRuntime(registry, settings.semantics.build())
    parser = DefinitionParser(settings.symbols, registry)
    chosen = None
    fallback = None
    fallback_rank = (-1, -1)
    for operators, input_limit in candidate_batches(registry):
        for noninjective, op, inputs, position, rows, unique in forms(
                oracle, operators, input_limit):
            try:
                rows = counted_scan(op, inputs, position, rows, registry, runtime, parser)
            except (RecursionError, ValueError, OverflowError, TypeError):
                continue
            answer = max(unique, key=lambda x: (rows[x - DOMAIN[0]]["steps"],
                                                -abs(x - PREFERRED_ANSWER[scale]), x))
            option = op, inputs, position, rows, answer
            if noninjective and rows[answer - DOMAIN[0]]["steps"] >= MIN_ANSWER_STEPS[scale]:
                chosen = option
                break
            rank = (rows[answer - DOMAIN[0]]["steps"], noninjective)
            if rank > fallback_rank:
                fallback = option
                fallback_rank = rank
        if chosen is not None:
            break
    chosen = chosen or fallback
    if chosen is None:
        raise ValueError(f"{name}: no unique deep problem within trace caps")
    op, inputs, position, scan, answer = chosen
    tree = expression(op, inputs, position, answer)
    solver = HoleSolver(None, oracle, fallback_domain=DOMAIN,
                        not_expressible_domain=None)
    problem = solver.problem(tree, (position,))
    if problem is None or not problem.solutions.unique or not all(step.complete for step in problem.reverse):
        raise ValueError(f"{name}: no complete unique problem")
    renderer = ExpressionRenderer(settings.symbols)
    data = record(problem, 0, renderer)
    hits = [row["x"] for row in scan if row["value"] == data["target"]]
    if hits != data["solutions"] or hits != [answer]:
        raise AssertionError(f"{name}: forward scan disagrees with solver")
    proof = build_tree(tree, registry, runtime, parser, max_nodes=MAX_NODES)
    nodes_verified = verify_tree(proof, oracle)
    full = flatten(proof)
    verify_trace(full, oracle)
    steps = scan[answer - DOMAIN[0]]["steps"]
    if len(full.steps) != steps or proof.value != data["target"]:
        raise AssertionError(f"{name}: unfolded check disagrees with interpreter")
    data.update({
        "schema": "opulse.scales-solve/1", "scale": scale, "set": name,
        "set_size": sum(item.definition is not None for item in registry),
        "target_operator": op.symbol, "target_id": op.func_id,
        "target_layer": op.recursive_layer, "closure_size": len(closure(op, registry)),
        "operator_inputs": list(inputs), "unknown_position": position,
        "scan": scan, "hits": hits, "window": list(DOMAIN),
        "check_value": proof.value, "check_steps": steps,
        "scan_steps": sum(row["steps"] for row in scan), "step_cap": MAX_STEPS,
        "verification": {"interpreter_candidates": len(scan),
                         "reverse_complete": True, "nodes_verified": nodes_verified,
                         "full_trace_verified": True,
                         "seconds": round(time.monotonic() - started, 3)},
    })
    del data["tree"]
    prior = OUT / f"{scale}.json"
    if prior.exists():
        previous = json.loads(prior.read_text())
        if (previous.get("target_id") == data["target_id"] and
                previous.get("answer") == answer and
                previous.get("scan_steps") == data["scan_steps"]):
            data["verification"]["seconds"] = previous["verification"]["seconds"]
    return data


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--only", nargs="*", choices=[row[0] for row in SCALES])
    cli.add_argument("--cache", type=Path, default=Path("/tmp/opulse_scales"))
    args = cli.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    for scale in args.only or [row[0] for row in SCALES]:
        options = [(name, spec) for name, spec in SPECS.items()
                   if spec[0] == scale and spec[1] == "integer" and finished(args.cache, name) is not None]
        if not options:
            print(f"{scale}: no finished integer set", flush=True)
            continue
        name, spec = options[0]
        data = make_problem(scale, name, spec[3], args.cache)
        payload = compact(data)
        if len(payload) > MAX_FILE:
            raise ValueError(f"{scale}: {len(payload)} bytes exceeds 1 MB")
        (OUT / f"{scale}.json").write_bytes(payload)
        print(f"{scale}: {data['expression']} = {data['target']}; x={data['answer']}; "
              f"steps={data['check_steps']}; scan={data['scan_steps']}; {len(payload)} bytes; "
              f"{data['verification']['seconds']} s", flush=True)


if __name__ == "__main__":
    main()
