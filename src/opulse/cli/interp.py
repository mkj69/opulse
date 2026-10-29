"""Collect residual states and test exact intermediate values with nnsight."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from opulse.canary import marked
from opulse.cli.operators import DEFAULT_CONFIG


def register(commands) -> None:
    command = commands.add_parser("interp", help="nnsight activation collection, probes and patching")
    sub = command.add_subparsers(dest="interp_command", required=True)
    for name in ("collect", "patch"):
        p = sub.add_parser(name)
        p.add_argument("--model", required=True, help="locally cached Hugging Face model")
        p.add_argument("--tasks", type=Path, required=True, help="full context compute JSONL")
        p.add_argument("--operators", type=Path, required=True)
        p.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
        p.add_argument("--layers", required=True, help="comma separated zero based layer indices")
        p.add_argument("--device", default="cpu")
        p.add_argument("--out", type=Path, required=True)
        if name == "patch":
            p.add_argument("--max-pairs", type=int, default=None,
                           help="maximum number of usable counterfactual pairs")
        p.set_defaults(run=collect_command if name == "collect" else patch_command)
    p = sub.add_parser("probe")
    p.add_argument("--activations", type=Path, required=True, help="directory written by collect")
    p.add_argument("--bins", default="-10,0,10", help="comma separated value boundaries")
    p.add_argument("--site", choices=("subexpression", "reduction_step"), default="subexpression")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--out", type=Path, required=True)
    p.set_defaults(run=probe_command)


def _inputs(args):
    from opulse.config import Settings
    from opulse.core.registry import OperatorRegistry
    from opulse.integrations.nnsight import _read_tasks, load_model

    model, tokenizer = load_model(args.model, args.device)
    layers = [int(value) for value in args.layers.split(",")]
    return _read_tasks(args.tasks), OperatorRegistry.from_jsonl(args.operators), Settings.load(args.config), model, tokenizer, layers


def collect_command(args):
    from opulse.integrations.nnsight import collect

    print(json.dumps(collect(*_inputs(args), args.out), indent=2))
    return 0


def patch_command(args):
    from opulse.integrations.nnsight import patch

    print(json.dumps(patch(*_inputs(args), args.out, args.max_pairs), indent=2))
    return 0


def probe_command(args):
    from opulse.integrations.nnsight import probe

    bundle = np.load(args.activations / "activations.npz")
    metadata = [json.loads(line) for line in (args.activations / "metadata.jsonl").read_text(
        encoding="utf-8").splitlines() if line.strip()]
    bins = [float(value) for value in args.bins.split(",")]
    report = probe(bundle["activations"], metadata, bins, args.seed, site=args.site)
    report["layer_indices"] = bundle["layers"].tolist()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(marked(report), indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0
