"""``opulse interest``: interestingness scores of an operator set (opulse.generation.interest).

Prints the score distribution, the number of behavioural duplicates and the top operators.
``--out`` writes the operator set back with an ``interest`` field per defined operator.
"""

from __future__ import annotations

import json
from pathlib import Path

from opulse.cli.operators import DEFAULT_CONFIG
from opulse.config import INTEREST_COMPONENTS, Settings
from opulse.core.registry import OperatorRegistry


def register(commands) -> None:
    cmd = commands.add_parser("interest", help="interestingness scores and behavioural duplicates")
    cmd.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    cmd.add_argument("--operators", type=Path, required=True)
    cmd.add_argument("--out", type=Path, default=None, help="operators JSONL with an interest field")
    cmd.add_argument("--top", type=int, default=10, help="operators listed by score")
    cmd.add_argument("--per-layer", type=int, default=None, help="at most this many listed per layer")
    cmd.add_argument("--solver", action="store_true", help="confirm or refute regularities with z3")
    cmd.add_argument("--json", action="store_true", help="print the report as JSON")
    cmd.set_defaults(run=run)


def run(args) -> int:
    from opulse.generation.interest import featured_operators, score_registry, summarize

    settings = Settings.load(args.config)
    registry = OperatorRegistry.from_jsonl(args.operators)
    records = score_registry(registry, settings, solver=args.solver)
    top = featured_operators(registry, settings, args.top, args.per_layer, records)
    report = {
        "summary": summarize(records.values()),
        "top": [{"symbol": op.symbol, "layer": op.recursive_layer, "definition": op.definition,
                 **{key: record[key] for key in ("score", *INTEREST_COMPONENTS)},
                 "regularities": sorted(name for name, info in record["regularities"].items()
                                        if info["status"] != "refuted")}
                for op, record in top],
    }
    if args.out is not None:
        for op in registry:
            if op.func_id in records:
                op.interest = records[op.func_id]
        args.out.parent.mkdir(parents=True, exist_ok=True)
        registry.to_jsonl(args.out)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    summary = report["summary"]
    print(f"{summary['operators']} scored operators, {summary['duplicates']} behavioural duplicates "
          "(novelty 0)")
    print(f"{'':16}{'mean':>8}{'min':>8}{'q1':>8}{'median':>8}{'q3':>8}{'max':>8}")
    for name in ("score", *INTEREST_COMPONENTS):
        if name in summary:
            row = summary[name]
            print(f"{name:16}" + "".join(f"{row[k]:8.3f}" for k in ("mean", "min", "q1", "median", "q3", "max")))
    print()
    for item in report["top"]:
        marks = ", ".join(item["regularities"]) or "-"
        print(f"{item['score']:.3f}  L{item['layer']}  {item['definition']}  [{marks}]")
    return 0
