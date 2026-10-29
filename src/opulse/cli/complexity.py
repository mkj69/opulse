"""``opulse complexity``: measure and fit empirical base-operation costs."""

from __future__ import annotations

import json
from pathlib import Path

from opulse.analysis.complexity import analyze_registry
from opulse.cli.operators import DEFAULT_CONFIG
from opulse.config import Settings
from opulse.core.registry import OperatorRegistry
from opulse.runtime import PythonRuntime


def register(commands) -> None:
    cmd = commands.add_parser("complexity", help="fit base-operation costs of defined operators")
    cmd.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    cmd.add_argument("--operators", type=Path, required=True)
    cmd.add_argument("--out", type=Path, required=True, help="output JSONL")
    cmd.set_defaults(run=run)


def run(args) -> int:
    from opulse.canary import marked
    settings = Settings.load(args.config)
    registry = OperatorRegistry.from_jsonl(args.operators)
    runtime = PythonRuntime(registry, settings.semantics.build())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as handle:
        for result in analyze_registry(registry, runtime, symbols=settings.symbols):
            handle.write(json.dumps(marked(result), ensure_ascii=False, allow_nan=False) + "\n")
    return 0
