"""``opulse expressions``: sample expressions and write evaluated records."""

from __future__ import annotations

import json
import random
from pathlib import Path

from opulse.cli.operators import DEFAULT_CONFIG
from opulse.config import Settings
from opulse.core.registry import OperatorRegistry
from opulse.expression.dataset import ExpressionDataset
from opulse.runtime import PythonRuntime


def register(commands) -> None:
    cmd = commands.add_parser("expressions", help="sample and evaluate expressions")
    cmd.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    cmd.add_argument("--operators", type=Path, required=True)
    cmd.add_argument("--out", type=Path, required=True)
    cmd.add_argument("--count", type=int, required=True)
    cmd.add_argument("--max-layer", type=int, default=None)
    cmd.add_argument("--seed", type=int, default=0)
    cmd.add_argument("--cython-build-dir", type=Path, default=None,
                     help="compile operators with Cython (faster for large runs)")
    cmd.add_argument("--keep-undefined", action="store_true",
                     help="also write expressions whose value is undefined (NaN)")
    cmd.add_argument("--cot", choices=("zh", "en", "none"), default="none",
                     help="include a verified narrated reduction trace")
    cmd.add_argument("--cot-depth", type=int, default=None,
                     help="unfold definitions at most this many levels deep; deeper calls are computed in one step")
    cmd.add_argument("--cot-known-layers", type=int, default=0,
                     help="treat operators of layers below this one as known (computed in one step)")
    cmd.add_argument("--cot-known", nargs="*", default=(),
                     help="operator symbols treated as known (computed in one step)")
    cmd.add_argument("--operator-frequency", default="uniform", metavar="uniform|zipf:ALPHA",
                     help="how often each defined operator is drawn: uniform, or a long tail (within each operator kind, "
                         "rank r drawn with weight proportional to r^-ALPHA)")
    cmd.add_argument("--frequency-seed", type=int, default=0, help="seed of the random frequency ranking")
    cmd.add_argument("--max-answer-share", type=float, default=None, metavar="SHARE",
                     help="limit any one answer to this share of records (for example 0.2)")
    cmd.add_argument("--workers", type=int, default=None, metavar="N",
                     help="generate in blocks with N processes; block k uses a seed derived from --seed and k, "
                          "so the output is the same for every N (and differs from a run without --workers)")
    cmd.add_argument("--block-size", type=int, default=200,
                     help="records per block with --workers (part of what determines the output)")
    cmd.set_defaults(run=run)


def run(args) -> int:
    settings = Settings.load(args.config)
    if args.cot == "none" and (args.cot_depth is not None or args.cot_known_layers or args.cot_known):
        raise SystemExit("--cot-depth and --cot-known options require --cot en or --cot zh")
    if args.operator_frequency == "uniform" and args.frequency_seed:
        print("Note: --frequency-seed affects only zipf operator frequency.")
    options = {"max_layer": args.max_layer, "keep_undefined": args.keep_undefined, "cot": args.cot,
               "cot_depth": args.cot_depth, "cot_known_layers": args.cot_known_layers,
               "cot_known": tuple(args.cot_known), "operator_frequency": args.operator_frequency,
               "frequency_seed": args.frequency_seed, "max_answer_share": args.max_answer_share}
    if args.workers is not None:
        from opulse.expression.parallel import ExpressionJob, write_expressions

        if args.workers < 1:
            raise SystemExit("--workers must be at least 1")
        if args.max_answer_share is not None:
            raise SystemExit("--max-answer-share currently needs a run without --workers")
        job = ExpressionJob(settings, args.operators, args.seed, args.block_size, options, args.cython_build_dir)
        write_expressions(job, args.count, args.out, args.workers)
        from opulse.cli.data_summary import print_data_summary
        print_data_summary(args.out)
        return 0
    registry = OperatorRegistry.from_jsonl(args.operators)
    semantics = settings.semantics.build()
    if args.cython_build_dir:
        from opulse.runtime.cython_backend import CythonRuntime
        runtime = CythonRuntime(registry, args.cython_build_dir, semantics)
    else:
        runtime = PythonRuntime(registry, semantics)
    dataset = ExpressionDataset(settings, registry, runtime, random.Random(args.seed), seed=args.seed, **options)
    dataset.generator.max_base = settings.numerals.max_base
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        handle.writelines(json.dumps(record, ensure_ascii=False) + "\n" for record in dataset.records(args.count))
    from opulse.cli.data_summary import print_data_summary
    print_data_summary(args.out)
    return 0
