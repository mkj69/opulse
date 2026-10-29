"""Iterative, checked operator discovery and record replay."""

from __future__ import annotations

import json
import os
from pathlib import Path

from opulse.cli.operators import DEFAULT_CONFIG


def register(commands) -> None:
    parser = commands.add_parser("discover", help="propose definitions and keep measured improvements")
    parser.add_argument("--operators", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--replay", action="store_true", help="reverify a prior discovery record")
    parser.add_argument("--problems", type=Path, help="one expression per line")
    parser.add_argument("--script", type=Path, help="JSONL proposals for a deterministic run")
    parser.add_argument("--model", help="model at an OpenAI compatible chat endpoint")
    parser.add_argument("--base-url", default="http://localhost:8000/v1")
    parser.add_argument("--rounds", type=int, default=4)
    parser.add_argument("--metric", choices=("usefulness", "size", "cost", "library_size"),
                        default="usefulness")
    parser.add_argument("--target", help="operator symbol to replace for size or cost")
    parser.add_argument("--inputs", type=Path, help="JSON array of input tuples for cost")
    parser.set_defaults(run=discover)


def discover(args) -> int:
    from opulse.bench.check import base_registry
    from opulse.config import Settings
    from opulse.core.registry import OperatorRegistry
    from opulse.discovery.loop import replay, run

    settings = Settings.load(args.config)
    registry = OperatorRegistry.from_jsonl(args.operators)
    base = base_registry(registry)
    if args.replay:
        print(json.dumps(replay(args.record, base, settings.symbols, settings.semantics.build(),
                                [op.definition for op in registry if op.definition]),
                         ensure_ascii=False, indent=2))
        return 0
    if args.problems is None or not (args.script or args.model):
        raise SystemExit("--problems and either --script or --model are required")
    problems = [line.strip() for line in args.problems.read_text(encoding="utf-8").splitlines() if line.strip()]
    definitions = [op.definition for op in registry if op.definition]
    inputs = ([tuple(point) for point in json.loads(args.inputs.read_text(encoding="utf-8"))]
              if args.inputs else None)
    if args.script:
        proposals = [json.loads(line) for line in args.script.read_text(encoding="utf-8").splitlines()
                     if line.strip()]
        if len(proposals) < args.rounds:
            raise SystemExit("the script has fewer proposals than rounds")

        def proposer(index, library, questions):
            return {"proposer": "scripted", **proposals[index - 1]}
    else:
        from opulse.bench.client import chat
        from opulse.bench.context import rules_text
        from opulse.bench.score import extract_answer
        from opulse.core.semantics import base_operation_name

        names = [base_operation_name(op.symbol, op.n_ary, op.unary_position) for op in base]
        names = [name for name in names if name is not None]

        def proposer(index, library, questions):
            prompt = ("Rules:\n" + rules_text(names, settings.semantics.build(), settings.symbols.nan) +
                      "\nDefinitions:\n" + "\n".join(library) + "\nProblems:\n" +
                      "\n".join(questions) + "\nPropose one definition using listed atoms and "
                      "bounded recursion only. " +
                      (f"Replace operator {args.target}. " if args.target else "Use a fresh symbol. ") +
                      "End with Answer: <definition>.")
            result = chat(args.base_url, args.model, prompt, 1024, 0.0,
                          api_key=os.environ.get("OPENAI_API_KEY"))
            truncated = result.get("finish_reason") == "length"
            return {"proposer": args.model,
                    "definition": "" if truncated else extract_answer(result.get("response", "")) or "",
                    "replaces": args.target, "error": result.get("error") or ("truncated" if truncated else None)}

    report = run(base, settings.symbols, settings.semantics.build(), problems, definitions,
                 proposer, args.rounds, args.record, args.metric, args.target, inputs)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0
