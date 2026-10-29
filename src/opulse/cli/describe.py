"""``opulse describe``: operator descriptions and views.

    opulse describe --operators ops.jsonl --out described.jsonl          # language fields per operator
    opulse describe --operators ops.jsonl --view prose --symbol ⊕       # one view, printed
    opulse describe --operators ops.jsonl --view all --lang zh --out views.jsonl
"""

from __future__ import annotations

import json
from pathlib import Path

from opulse.canary import marked
from opulse.cli.operators import DEFAULT_CONFIG

VIEW_CHOICES = ("symbolic", "formula", "code", "prose", "examples", "summary", "all")


def register(commands) -> None:
    cmd = commands.add_parser("describe", help="write bilingual operator descriptions, or show views of operators")
    cmd.add_argument("--operators", type=Path, required=True)
    cmd.add_argument("--out", type=Path, default=None,
                     help="JSONL output (required without --view; with --view, default: print)")
    cmd.add_argument("--config", type=Path, default=DEFAULT_CONFIG,
                     help="settings whose notation, numerals and semantics the texts use")
    cmd.add_argument("--view", action="append", choices=VIEW_CHOICES, default=None,
                     help="show views instead of writing description fields (repeatable; all: every view)")
    cmd.add_argument("--symbol", action="append", default=None,
                     help="only operators with this symbol (repeatable; default: every defined operator)")
    cmd.add_argument("--lang", choices=("en", "zh"), default="en", help="language of the prose and summary views")
    cmd.add_argument("--seed", type=int, default=0, help="paraphrase seed of the prose view")
    cmd.add_argument("--chain-limit", type=int, default=None,
                     help="list at most this many dependencies in the chain fields (the text says how many are left out)")
    cmd.set_defaults(run=run)


def run(args) -> int:
    from opulse.config import Settings
    from opulse.core.registry import OperatorRegistry
    from opulse.language.describe import Describer, annotate

    settings = Settings.load(args.config)
    registry = OperatorRegistry.from_jsonl(args.operators)
    if not args.view:
        if args.out is None:
            raise SystemExit("--out is required unless --view is given")
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.writelines(json.dumps(marked(row), ensure_ascii=False) + "\n"
                              for row in annotate(registry, settings, args.chain_limit))
        return 0
    from opulse.language.views import VIEWS

    views = list(VIEWS) if "all" in args.view else list(dict.fromkeys(args.view))
    chosen = [op for op in registry if (args.symbol is None and op.definition is not None)
              or (args.symbol is not None and op.symbol in args.symbol)]
    if not chosen:
        raise SystemExit("no operator matches")
    describer = Describer(registry, settings)
    rows = []
    for op in chosen:
        for view in views:
            if op.definition is None:
                text = describer.atom(op, "zh" if args.lang == "zh" else "en")
            else:
                text = describer.views.render(op, view, args.lang, args.seed)
            rows.append({"func_id": op.func_id, "symbol": op.symbol, "view": view, "lang": args.lang,
                         "seed": args.seed, "text": text})
            if op.definition is None:
                break
    if args.out is None:
        for row in rows:
            print(f"## {row['view']} ({row['symbol']})\n{row['text']}\n")
    else:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text("".join(json.dumps(marked(row), ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    return 0
