"""``opulse viz``: write a portable report for generated JSONL data."""

from __future__ import annotations

from pathlib import Path

from opulse.viz.report import write_report


def register(commands) -> None:
    cmd = commands.add_parser("viz", help="build an offline HTML report")
    cmd.add_argument("--operators", type=Path, required=True)
    cmd.add_argument("--expressions", type=Path)
    cmd.add_argument("--out", type=Path, required=True)
    cmd.set_defaults(run=run)


def run(args) -> int:
    print(write_report(args.operators, args.out, args.expressions))
    return 0
