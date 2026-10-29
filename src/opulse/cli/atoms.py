"""Export a built-in starting operator set."""

from __future__ import annotations

from pathlib import Path

from opulse.core.starting_sets import STARTING_NAMES, export_starting_set


def register(commands) -> None:
    cmd = commands.add_parser("atoms", help="work with built in starting sets")
    actions = cmd.add_subparsers(dest="atoms_command", required=True)
    export = actions.add_parser("export", help="write a starting set as JSONL")
    export.add_argument("--set", choices=tuple(STARTING_NAMES), required=True)
    export.add_argument("--out", type=Path, required=True)
    export.set_defaults(run=run_export)


def run_export(args) -> int:
    args.out.parent.mkdir(parents=True, exist_ok=True)
    export_starting_set(args.set, args.out)
    return 0
