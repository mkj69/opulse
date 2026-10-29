"""Generation benchmarks (read by notebooks/generation_benchmark.ipynb).

    python tools/benchmark.py scale  --layers 40000 30000 20000 10000 --out outputs/benchmark/scale
    python tools/benchmark.py stages --operators outputs/benchmark/scale/operators.jsonl --out outputs/benchmark/stages

``scale`` grows an operator set and logs one CSV row per accepted operator (elapsed time,
layer, kind, drafts tried, sizes) plus rejection counts, and saves the operator set every
``--checkpoint`` operators. ``stages`` times every downstream stage on a fixed operator set.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from opulse.config import Settings
from opulse.core import OperatorRegistry
from opulse.core.starting_sets import starting_registry
from opulse.generation.pipeline import OperatorFactory, build_layers


def scale(args) -> None:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    settings = Settings.load(args.config) if args.config else Settings()
    registry = OperatorRegistry.from_jsonl(args.initial) if args.initial else starting_registry()
    factory = OperatorFactory(settings, registry, random.Random(args.seed))
    log = (out / "accepted.csv").open("w", newline="", encoding="utf-8")
    writer = csv.writer(log)
    writer.writerow(["index", "elapsed_s", "layer", "kind", "drafts", "n_ary", "symbol_len",
                     "definition_len", "branches", "max_path_depth", "max_edge_count", "registry_size"])
    start = time.perf_counter()
    state = {"drafts": 0, "index": 0}
    rejected_log = (out / "rejected.jsonl").open("w", encoding="utf-8")

    def on_accept(op) -> None:
        state["index"] += 1
        total_drafts = sum(factory.stats.accepted.values()) + sum(factory.stats.rejected.values())
        drafts, state["drafts"] = total_drafts - state["drafts"], total_drafts
        writer.writerow([state["index"], round(time.perf_counter() - start, 4), op.recursive_layer,
                         op.definition_type.split("_")[0], drafts, op.n_ary, len(op.symbol), len(op.definition),
                         op.definition.count(", if ") + op.definition.count(", else"), op.max_path_depth,
                         op.max_edge_count, len(registry)])
        if state["index"] % args.checkpoint == 0:
            log.flush()
            rejected_log.write(json.dumps({"index": state["index"], "rejected": dict(factory.stats.rejected)}) + "\n")
            rejected_log.flush()
            registry.to_jsonl(out / "operators.jsonl")
            print(f"{state['index']} operators, {time.perf_counter() - start:.0f} s", flush=True)

    build_layers(factory, args.layers, on_accept=on_accept)
    log.close()
    rejected_log.write(json.dumps({"index": state["index"], "rejected": dict(factory.stats.rejected)}) + "\n")
    rejected_log.close()
    registry.to_jsonl(out / "operators.jsonl")
    (out / "summary.json").write_text(json.dumps({
        "layers": args.layers, "seed": args.seed, "seconds": time.perf_counter() - start,
        "accepted": dict(factory.stats.accepted), "rejected": dict(factory.stats.rejected)}, indent=2))
    print("done", flush=True)


def stages(args) -> None:
    """Time each stage on samples of one operator set; one JSON line per measurement."""
    from opulse.expression.dataset import ExpressionDataset
    from opulse.runtime import PythonRuntime
    from opulse.solver.holes import HoleSolver, hole_paths
    from opulse.solver.properties import PropertyChecker
    from opulse.solver.smt import export, prelude
    from opulse.solver.z3_encode import Z3Encoder
    from opulse.verify import Oracle, check_operator

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    settings = Settings()
    registry = OperatorRegistry.from_jsonl(args.operators)
    sink = (out / "stages.jsonl").open("w", encoding="utf-8")

    def emit(**row) -> None:
        sink.write(json.dumps(row, ensure_ascii=False) + "\n")
        sink.flush()
        print(row, flush=True)

    runtime = PythonRuntime(registry, settings.semantics.build())
    oracle = Oracle(registry, settings.symbols, settings.semantics.build())
    rng = random.Random(0)
    defined = [op for op in registry if op.definition]
    sample = rng.sample(defined, min(args.sample, len(defined)))

    t = time.perf_counter()
    for op in sample:
        assert not check_operator(op, runtime.evaluate(op), oracle, rng)
    emit(stage="verify_operator", n=len(sample), seconds=time.perf_counter() - t)

    for max_layer in sorted({op.recursive_layer for op in defined}):
        for cot in ("none", "en"):
            dataset = ExpressionDataset(settings, registry, runtime, random.Random(1), max_layer=max_layer,
                                        keep_undefined=True, cot=cot)
            t = time.perf_counter()
            records = list(dataset.records(args.expressions))
            emit(stage="expressions", max_layer=max_layer, cot=cot, n=len(records), seconds=time.perf_counter() - t,
                 undefined=sum(r["undefined"] for r in records),
                 expansion=[r["expansion"] for r in records],
                 steps=[len(r["steps"]) for r in records],
                 cot_chars=[len(r["cot"]) for r in records] if cot != "none" else None)

    encoder = Z3Encoder(oracle)
    solver = HoleSolver(encoder, oracle, timeout_ms=args.timeout_ms)
    from opulse.expression.generator import ExpressionGenerator, OperatorPool
    from opulse.expression.nodes import Call

    pool = OperatorPool.from_registry(registry)
    for depth in (1, 2):
        generator = ExpressionGenerator(settings.expressions, random.Random(depth))
        results = []
        while len(results) < args.holes:
            tree = generator.tree(pool, max_depth=depth, atoms="number")
            if not isinstance(tree, Call):
                continue
            t = time.perf_counter()
            problem = solver.problem(tree, rng.choice(hole_paths(tree)))
            if problem is None:
                continue
            results.append({"seconds": time.perf_counter() - t, "method": problem.solutions.method,
                            "unique": problem.solutions.unique, "complete": problem.solutions.complete,
                            "solutions": len(problem.solutions.values)})
        emit(stage="holes", depth=depth, results=results)

    checker = PropertyChecker(encoder, timeout_ms=args.timeout_ms)
    base = prelude(encoder)
    rows = []
    for op in sample[: args.analyze]:
        t = time.perf_counter()
        verdicts = checker.check_all(op)
        t_props = time.perf_counter() - t
        t = time.perf_counter()
        exported = export(op, encoder, base)
        rows.append({"kind": op.definition_type, "layer": op.recursive_layer, "n_ary": op.n_ary,
                     "properties_s": t_props, "smt_s": time.perf_counter() - t,
                     "smt_chars": len(exported or ""), "verdicts": {k: v["status"] for k, v in verdicts.items()}})
    emit(stage="analyze", results=rows)
    sink.close()


def nan_quality(args) -> None:
    """NaN share of sampled expressions for several acceptance settings (same seed)."""
    import dataclasses

    from opulse.expression.dataset import ExpressionDataset

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    settings_list = [("no new checks (before)", {"reject_degenerate": False, "min_defined_share": 0.0})]
    settings_list += [(f"degenerate + share {share}", {"min_defined_share": share}) for share in (0.5, 0.8, 0.95)]
    rows = []
    for name, overrides in settings_list:
        base = Settings()
        settings = dataclasses.replace(base, operators=dataclasses.replace(base.operators, **overrides))
        registry = starting_registry()
        factory = OperatorFactory(settings, registry, random.Random(args.seed))
        start = time.perf_counter()
        build_layers(factory, args.layers)
        seconds = time.perf_counter() - start
        for layer in range(len(args.layers)):
            dataset = ExpressionDataset(settings, registry, factory.runtime, random.Random(1), max_layer=layer,
                                        keep_undefined=True)
            records = list(dataset.records(args.expressions))
            rows.append({"setting": name, "max_layer": layer, "generation_s": seconds,
                         "nan_share": sum(r["undefined"] for r in records) / len(records),
                         "rejected": dict(factory.stats.rejected)})
            print(rows[-1]["setting"], layer, round(rows[-1]["nan_share"], 3), flush=True)
    (out / "nan_quality.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1))


def main() -> int:
    logging.disable(logging.WARNING)
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    s = commands.add_parser("scale")
    s.add_argument("--layers", type=int, nargs="+", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--config", default=None)
    s.add_argument("--initial", default=None)
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--checkpoint", type=int, default=1000)
    s.set_defaults(run=scale)
    g = commands.add_parser("stages")
    g.add_argument("--operators", required=True)
    g.add_argument("--out", required=True)
    g.add_argument("--sample", type=int, default=200)
    g.add_argument("--expressions", type=int, default=300)
    g.add_argument("--holes", type=int, default=30)
    g.add_argument("--analyze", type=int, default=60)
    g.add_argument("--timeout-ms", type=int, default=3000)
    g.set_defaults(run=stages)
    q = commands.add_parser("nan")
    q.add_argument("--layers", type=int, nargs="+", default=[100, 60, 40, 20])
    q.add_argument("--expressions", type=int, default=300)
    q.add_argument("--seed", type=int, default=3)
    q.add_argument("--out", required=True)
    q.set_defaults(run=nan_quality)
    args = parser.parse_args()
    args.run(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
