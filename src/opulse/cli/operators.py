"""``opulse operators``: generate operators per recursive layer."""

from __future__ import annotations

import json
import logging
import random
from collections import Counter
from dataclasses import replace
from pathlib import Path

from opulse.config import Settings, normalize_arity_weights
from opulse.core.registry import OperatorRegistry
from opulse.core.starting_sets import starting_registry
from opulse.generation.pipeline import OperatorFactory, build_layers
from opulse.generation.priority import assign_priorities
from opulse.presets import PRESETS

TYPED_PRESETS = ("strings", "lists")  # opulse.core.presets

logger = logging.getLogger(__name__)
_root = Path(__file__).resolve().parents[3]
_package_data = Path(__file__).resolve().parents[1] / "data"
_source_config = _root / "configs" / "default.yaml"
_source_atomic_config = _root / "configs" / "atomic.yaml"
DEFAULT_CONFIG = _source_config if _source_config.is_file() else _package_data / "default.yaml"
ATOMIC_CONFIG = _source_atomic_config if _source_atomic_config.is_file() else _package_data / "atomic.yaml"


def register(commands) -> None:
    cmd = commands.add_parser("operators", help="generate operators layer by layer")
    cmd.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    cmd.add_argument("--initial", type=Path, default=None, help="starting operator set")
    cmd.add_argument("--set", choices=("integer", "atomic"), default="integer",
                     help="built in starting set when --initial is absent")
    cmd.add_argument("--preset", choices=(*PRESETS, *TYPED_PRESETS), default=None,
                     help="named atom set: numeric worlds with generation defaults, or the typed strings and lists")
    cmd.add_argument("--out", type=Path, required=True, help="output JSONL; resumed if it exists")
    cmd.add_argument("--layers", type=int, nargs="+", default=None,
                     help="target number of generated operators per layer, e.g. 40 30 20 10")
    cmd.add_argument("--proportions", type=float, nargs=3, default=None,
                     metavar=("SIMPLE", "BRANCH", "RECURSIVE"))
    cmd.add_argument("--seed", type=int, default=0)
    cmd.add_argument("--no-simple", action="store_true", help="disable simple definitions")
    cmd.add_argument("--no-branches", action="store_true", help="disable branch definitions")
    cmd.add_argument("--no-recursion", action="store_true", help="disable recursive definitions")
    cmd.add_argument("--max-substitution-depth", type=int, help="maximum call depth in definition bodies")
    cmd.add_argument("--max-if-branches", type=int, help="maximum branches per branch definition")
    cmd.add_argument("--max-condition-comparisons", type=int, help="maximum comparisons per branch condition")
    cmd.add_argument("--condition-atoms", type=str, help="comma-separated atom names for branch conditions")
    cmd.add_argument("--max-arity", type=int, help="maximum generated operator arity")
    cmd.add_argument("--recursion-styles", type=str, help="comma-separated recursion templates to sample")
    cmd.add_argument("--recursion-direct-bound", type=int, help="bound for direct and peano recursion")
    cmd.add_argument("--recursion-modulus-min", type=int, help="smallest bounded_mod modulus")
    cmd.add_argument("--recursion-modulus-max", type=int, help="largest bounded_mod modulus")
    cmd.add_argument("--max-recursive-calls", type=int, choices=(1, 2),
                     help="maximum recursive calls in one recursive branch")
    cmd.add_argument("--check-variety", action="store_true", help="reject near-constant operators")
    cmd.add_argument("--enable-definedness", action="store_true", help="include the defined atom")
    cmd.add_argument("--max-priority-levels", type=int, default=None)
    cmd.add_argument("--arity-weights", default=None,
                     help="arity:weight pairs, for example 1:0.25,2:0.5,3:0.25")
    cmd.add_argument("--recursion-style", choices=("bounded_mod", "direct", "peano", "bits", "primitive"),
                     default=None)
    cmd.add_argument("--search", action="store_true", help="enable bounded search definitions")
    cmd.add_argument("--search-bound", type=int, default=None)
    cmd.add_argument("--dedup", action="store_true",
                     help="reject behavioural duplicates (interest.dedup)")
    cmd.add_argument("--interest-selection", choices=("off", "sample", "best"), default=None,
                     help="choose each operator from a pool of candidates by interest score (interest.selection)")
    cmd.add_argument("--interest-pool", type=int, default=None, help="candidates per operator (interest.pool)")
    cmd.set_defaults(run=run)


def run(args) -> int:
    numeric = args.preset if args.preset in PRESETS else None  # typed presets only choose the atoms
    config = (ATOMIC_CONFIG if args.set == "atomic" and args.initial is None and args.preset is None
              and args.config == DEFAULT_CONFIG else args.config)
    settings = (Settings.from_dict({"preset": numeric})
                if numeric and config == DEFAULT_CONFIG else Settings.load(config, numeric))
    if args.arity_weights is not None:
        try:
            weights = {arity: float(weight) for arity, weight in
                       (part.split(":", 1) for part in args.arity_weights.split(","))}
            settings = replace(settings, operators=replace(settings.operators,
                               arity_weights=normalize_arity_weights(weights)))
        except (ValueError, TypeError) as exc:
            raise ValueError("--arity-weights expects arity:weight pairs") from exc
    operator_overrides = {key: getattr(args, key) for key in
                          ("max_substitution_depth", "max_if_branches", "max_condition_comparisons", "max_arity")
                          if getattr(args, key) is not None}
    if args.condition_atoms is not None:
        operator_overrides["condition_atoms"] = tuple(name.strip() for name in args.condition_atoms.split(",")
                                                      if name.strip())
    if args.no_simple:
        operator_overrides["allow_simple"] = False
    if args.no_branches:
        operator_overrides["allow_branches"] = False
    recursion_overrides = {}
    if args.no_recursion:
        recursion_overrides["enabled"] = False
    if args.recursion_style is not None:
        recursion_overrides["style"] = args.recursion_style
    if args.search or args.search_bound is not None:
        recursion_overrides["search_enabled"] = True
    if args.search_bound is not None:
        recursion_overrides["search_bound"] = args.search_bound
    if args.recursion_styles is not None:
        recursion_overrides["styles"] = tuple(name.strip() for name in args.recursion_styles.split(",")
                                                if name.strip())
    for source, target in (("recursion_direct_bound", "direct_bound"),
                           ("recursion_modulus_min", "modulus_min"),
                           ("recursion_modulus_max", "modulus_max"),
                           ("max_recursive_calls", "max_recursive_calls")):
        if getattr(args, source) is not None:
            recursion_overrides[target] = getattr(args, source)
    if operator_overrides or recursion_overrides:
        settings = replace(settings, operators=replace(settings.operators, **operator_overrides),
                           recursion=replace(settings.recursion, **recursion_overrides))
    interest_overrides = {key: value for key, value in (("dedup", True if args.dedup else None),
                                                        ("selection", args.interest_selection),
                                                        ("pool", args.interest_pool)) if value is not None}
    if interest_overrides:
        settings = replace(settings, interest=replace(settings.interest, **interest_overrides))
    preset = PRESETS.get(settings.preset)
    layers = args.layers or (preset["layers"] if preset else None)
    if layers is None:
        raise ValueError("--layers is required without a preset")
    proportions = args.proportions or (preset["proportions"] if preset else (0.4, 0.4, 0.2))
    resume = args.out.exists() and args.out.stat().st_size > 0
    typed = args.preset in TYPED_PRESETS
    if resume or args.initial is not None:
        registry = OperatorRegistry.from_jsonl(args.out if resume else args.initial)
    elif preset is None and not typed:
        registry = starting_registry(args.set)
    elif typed:
        from opulse.core.operator import Operator
        from opulse.core.presets import PRESETS as TYPED
        from opulse.core.presets import register_preset
        from opulse.core.primitives import atom_records

        register_preset(args.preset)
        registry = OperatorRegistry(Operator.from_dict(row) for row in atom_records(TYPED[args.preset]))
    else:
        from opulse.core.operator import Operator
        from opulse.core.primitives import atom_records

        rows = atom_records(preset["atoms"], args.seed)
        if settings.preset == "integer":
            priorities = {"/": 2, "%": 3, "-": 4, "@": 5, "#": 6, "$": 5}
            for row in rows:
                if row["n_ary"] == 1 or row["symbol"] in ("/", "%"):
                    row["priority"] = priorities.get(row["symbol"], row["priority"])
        registry = OperatorRegistry(Operator(**row) for row in rows)
    if settings.operators.definedness or args.enable_definedness:
        from opulse.core.primitives import enable_definedness

        enable_definedness(registry)
    existing = Counter(op.recursive_layer for op in registry if op.definition is not None)
    remaining = [max(0, target - existing.get(layer, 0)) for layer, target in enumerate(layers)]
    logger.info("existing per layer %s, generating %s", dict(existing), remaining)

    rng = random.Random(args.seed + len(registry))  # resumed runs do not replay the same draws
    factory = OperatorFactory(settings, registry, rng, check_variety=args.check_variety)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if not resume:
        registry.to_jsonl(args.out)
    with open(args.out, "a", encoding="utf-8") as handle:
        build_layers(factory, remaining, tuple(proportions),
                     on_accept=lambda op: (handle.write(op.to_json() + "\n"), handle.flush()))

    assign_priorities(registry, rng, args.max_priority_levels)
    if settings.interest.enabled:  # final scores: reuse is known once every caller exists
        from opulse.generation.interest import score_registry, summarize

        records = score_registry(registry, settings)
        for op in registry:
            if op.func_id in records:
                op.interest = records[op.func_id]
    registry.to_jsonl(args.out)  # rewrite with priorities filled in
    summary = factory.stats.summary()
    if settings.interest.enabled:
        summary["interest"] = summarize(records.values())
    summary["layers"] = dict(Counter(op.recursive_layer for op in registry if op.definition is not None))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0
