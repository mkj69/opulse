"""``opulse export``: Hugging Face datasets, pretraining corpora and tokenizer files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from opulse.cli.operators import DEFAULT_CONFIG


def register(commands) -> None:
    command = commands.add_parser("export", help="package generated data for other tools")
    sub = command.add_subparsers(dest="export_command", required=True)
    hf = sub.add_parser("hf", help="write a local Hugging Face dataset directory")
    add_arguments(hf)

    megatron = sub.add_parser("megatron", help="write Megatron text JSONL")
    megatron.add_argument("--input", type=Path, nargs="+", required=True, help="Opulse JSONL files")
    megatron.add_argument("--out", type=Path, required=True)
    megatron.add_argument("--fields", nargs="+", default=(), help="text fields to join with newlines")
    megatron.set_defaults(run=run_megatron)

    tokenizer = sub.add_parser("tokenizer", help="build a Hugging Face fast tokenizer")
    tokenizer.add_argument("--operators", type=Path, required=True)
    tokenizer.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    tokenizer.add_argument("--out", type=Path, required=True, help="tokenizer directory")
    tokenizer.add_argument("--corpus", type=Path, nargs="*", default=(), help="JSONL files checked for exact round trips")
    tokenizer.add_argument("--fields", nargs="+", default=())
    tokenizer.add_argument("--operator-mode", choices=("whole", "character"), default="whole")
    tokenizer.add_argument("--naming", choices=("symbols", "pseudo", "english"), default="symbols",
                           help="include benchmark operator aliases of this naming style")
    tokenizer.add_argument("--number-bound", type=int, default=0)
    tokenizer.add_argument("--extend-from", type=Path, default=None)
    tokenizer.set_defaults(run=run_tokenizer)


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--train-operators", type=Path, required=True)
    parser.add_argument("--test-operators", type=Path, required=True)
    parser.add_argument("--train-expressions", type=Path, required=True)
    parser.add_argument("--test-expressions", type=Path, required=True)
    parser.add_argument("--train-tasks", type=Path, nargs="+", required=True,
                        help="one or more benchmark JSONL files from the train operator set")
    parser.add_argument("--test-tasks", type=Path, nargs="+", required=True,
                        help="matching benchmark JSONL files from the test operator set")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--train-seed", type=int, required=True)
    parser.add_argument("--test-seed", type=int, required=True)
    parser.add_argument("--generation-command", required=True,
                        help="literal shell commands used to generate the input files")
    parser.add_argument("--license", default="cc-by-4.0", dest="license_id",
                        help="dataset license identifier (default: cc-by-4.0); unknown records that none was specified")
    parser.set_defaults(run=run)


def run(args) -> int:
    from opulse.hf_export import export

    result = export(args.train_operators, args.test_operators, args.train_expressions,
                    args.test_expressions, args.train_tasks, args.test_tasks, args.out,
                    args.train_seed, args.test_seed, args.generation_command, args.license_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def run_megatron(args) -> int:
    from opulse.export.corpus import export_megatron

    count = export_megatron(args.input, args.out, tuple(args.fields))
    print(f"wrote {count} documents to {args.out}")
    return 0


def run_tokenizer(args) -> int:
    from opulse.config import Settings
    from opulse.core.registry import OperatorRegistry
    from opulse.export.corpus import iter_text
    from opulse.export.tokenizer import build_tokenizer

    tokenizer = build_tokenizer(OperatorRegistry.from_jsonl(args.operators), Settings.load(args.config), args.out,
                                operator_mode=args.operator_mode, number_bound=args.number_bound, naming=args.naming,
                                corpus=iter_text(args.corpus, tuple(args.fields)), extend_from=args.extend_from)
    print(f"wrote {tokenizer.get_vocab_size()} tokens to {args.out}")
    return 0
