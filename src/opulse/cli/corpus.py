"""``opulse corpus``: write a sharded plain-text pretraining corpus (and probe data)."""

from __future__ import annotations

import json
from pathlib import Path

from opulse.cli.operators import DEFAULT_CONFIG
from opulse.config import Settings


def register(commands) -> None:
    cmd = commands.add_parser("corpus", help="write a sharded pretraining corpus and probe data")
    cmd.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    cmd.add_argument("--operators", action="append", required=True, metavar="[NAME=]PATH",
                     help="operator set; with --split set, repeat as NAME=PATH, one per split")
    cmd.add_argument("--out", type=Path, required=True, help="output directory")
    cmd.add_argument("--world-mix", help="weighted world names, for example strings:0.5,lists:0.5")
    cmd.add_argument("--world-settings", type=Path,
                     help="JSON object keyed by world with config, frequency and skeleton weights")
    cmd.add_argument("--seed", type=int, default=0)
    cmd.add_argument("--documents", default="1000", metavar="N|NAME=N,...",
                     help="documents per split: one number for every split, or a count per split name")
    cmd.add_argument("--mix", default="definitions=1,values=4,derivations=2,descriptions=0",
                     help="relative weights of the document kinds definitions, values, derivations, descriptions")
    cmd.add_argument("--definitions", choices=("separate", "prefix", "none"), default="separate",
                     help="separate: definitions only in definition documents; prefix: also at the start of every "
                          "expression document (the definitions it needs); none: no definitions anywhere "
                          "(the mix must give definitions and descriptions weight 0)")
    cmd.add_argument("--definitions-per-document", type=int, default=8,
                     help="operators per definition or description document")
    cmd.add_argument("--expressions-per-document", type=int, default=8, help="expressions per values document")
    cmd.add_argument("--derivation-style", choices=("chain", "en", "zh"), default="chain",
                     help="chain: one '= expression' line per step; en/zh: the narrated solution of --cot")
    cmd.add_argument("--description-lang", choices=("en", "zh", "both"), default="en")
    cmd.add_argument("--max-steps", type=int, default=200,
                     help="largest number of steps of a derivation; longer ones are skipped")
    cmd.add_argument("--max-layer", type=int, default=None)
    cmd.add_argument("--keep-undefined", action="store_true", help="also use expressions whose value is NaN")
    cmd.add_argument("--operator-frequency", default="uniform", metavar="uniform|zipf:ALPHA",
                     help="how often each defined operator is drawn in expressions (as in opulse expressions)")
    cmd.add_argument("--frequency-seed", type=int, default=0, help="seed of the random frequency ranking")
    cmd.add_argument("--cot-depth", type=int, default=None,
                     help="derivations unfold definitions at most this many levels deep")
    cmd.add_argument("--cot-known-layers", type=int, default=0,
                     help="derivations compute operators of layers below this one in one step")
    cmd.add_argument("--cot-known", nargs="*", default=(),
                     help="operator symbols that derivations compute in one step")
    cmd.add_argument("--split", choices=("none", "operator", "set"), default="none",
                     help="none: one split; operator: assign the operators of one set to splits; "
                          "set: one operator set per split")
    cmd.add_argument("--split-ratios", default="train=0.8,val=0.1,test=0.1",
                     help="with --split operator: split names and shares of the defined operators; "
                          "the first split takes the operators the others leave")
    cmd.add_argument("--no-dedup", action="store_true", help="keep documents whose text occurred before")
    cmd.add_argument("--shard-size", type=int, default=100_000, help="documents per shard")
    cmd.add_argument("--block-size", type=int, default=20,
                     help="generated documents per block (part of what determines the output)")
    cmd.add_argument("--workers", type=int, default=1, help="worker processes (the output does not depend on it)")
    cmd.add_argument("--probe", action="store_true",
                     help="also write probe records: spans and values of every derivation step")
    cmd.add_argument("--tokenizer", default=None, metavar="NAME",
                     help="Hugging Face tokenizer for exact token counts and token-aligned probe spans "
                          "(needs transformers; otherwise only character spans and estimates)")
    cmd.set_defaults(run=run)


def operator_sets(values: list[str], split: str) -> dict[str, Path]:
    sets: dict[str, Path] = {}
    for value in values:
        name, sep, path = value.partition("=")
        if not sep or not name or "/" in name:
            name, path = ("train" if split != "set" else Path(value).stem), value
        if name in sets:
            raise SystemExit(f"--operators: split name {name!r} given twice")
        sets[name] = Path(path)
    return sets


def document_counts(text: str, names: list[str]) -> dict[str, int]:
    if text.strip().isdigit():
        return {name: int(text) for name in names}
    counts = {}
    for part in text.split(","):
        name, sep, value = part.partition("=")
        if not sep or not value.strip().isdigit():
            raise SystemExit(f"--documents: expected N or NAME=N,..., got {text!r}")
        counts[name.strip()] = int(value)
    return counts


def run(args) -> int:
    from opulse.corpus import CorpusOptions, build_corpus
    from opulse.corpus.options import parse_weights

    settings = Settings.load(args.config)
    if args.operator_frequency == "uniform" and args.frequency_seed and not args.world_mix:
        print("Note: --frequency-seed affects only zipf operator frequency.")
    if args.world_mix:
        return run_world_mix(args)
    sets = operator_sets(args.operators, args.split)
    ratios = parse_weights(args.split_ratios, "--split-ratios")
    names = list(ratios) if args.split == "operator" else list(sets)
    try:
        options = CorpusOptions(
            seed=args.seed, documents=document_counts(args.documents, names),
            mix=parse_weights(args.mix, "--mix"), definitions=args.definitions,
            definitions_per_document=args.definitions_per_document,
            expressions_per_document=args.expressions_per_document, derivation_style=args.derivation_style,
            description_lang=args.description_lang, max_layer=args.max_layer, keep_undefined=args.keep_undefined,
            operator_frequency=args.operator_frequency, frequency_seed=args.frequency_seed,
            cot_depth=args.cot_depth, cot_known_layers=args.cot_known_layers, cot_known=tuple(args.cot_known),
            max_steps=args.max_steps, split=args.split, split_ratios=ratios, dedup=not args.no_dedup,
            shard_size=args.shard_size, block_size=args.block_size, probe=args.probe, tokenizer=args.tokenizer)
        manifest = build_corpus(settings, sets, options, args.out, workers=args.workers)
    except ValueError as exc:
        raise SystemExit(f"opulse corpus: {exc}") from None
    print(json.dumps({"out": str(args.out), "totals": manifest["totals"],
                      "splits": {name: split["documents"] for name, split in manifest["splits"].items()}},
                     ensure_ascii=False))
    return 0


def run_world_mix(args) -> int:
    """Generate one checked corpus per world and interleave its documents."""
    from opulse.corpus import CorpusOptions, build_corpus
    from opulse.corpus.options import parse_weights
    from opulse.world_mix import parse_world_mix, world_schedule, world_seed

    if not args.documents.isdigit():
        raise ValueError("--world-mix needs a single total --documents count")
    weights = parse_world_mix(args.world_mix)
    sets = operator_sets(args.operators, "set")
    if set(sets) != set(weights):
        raise ValueError("named --operators entries must match --world-mix names")
    settings_by_world = (json.loads(args.world_settings.read_text(encoding="utf-8"))
                         if args.world_settings else {})
    if set(settings_by_world) - set(sets):
        raise ValueError("world settings contain an unknown world")
    schedule = world_schedule(int(args.documents), weights, args.seed)
    args.out.mkdir(parents=True, exist_ok=True)
    documents = {}
    manifests = {}
    for name, path in sets.items():
        count = schedule.count(name)
        if count == 0:
            continue
        spec = settings_by_world.get(name, {})
        options = CorpusOptions(seed=world_seed(args.seed, name), documents={"train": count},
                                mix=parse_weights(args.mix, "--mix"), definitions=args.definitions,
                                definitions_per_document=args.definitions_per_document,
                                expressions_per_document=args.expressions_per_document,
                                derivation_style=args.derivation_style, description_lang=args.description_lang,
                                max_steps=args.max_steps, max_layer=args.max_layer,
                                keep_undefined=args.keep_undefined,
                                operator_frequency=spec.get("operator_frequency", args.operator_frequency),
                                frequency_seed=spec.get("frequency_seed", args.frequency_seed),
                                skeleton_weights=spec.get("skeleton_weights", {}),
                                cot_depth=args.cot_depth, cot_known_layers=args.cot_known_layers,
                                cot_known=tuple(args.cot_known), dedup=not args.no_dedup,
                                shard_size=args.shard_size, block_size=args.block_size,
                                probe=args.probe, tokenizer=args.tokenizer)
        world_out = args.out / "worlds" / name
        manifests[name] = build_corpus(Settings.load(Path(spec.get("config", args.config))),
                                       {"train": path}, options, world_out, workers=args.workers)
        documents[name] = [json.loads(line) for shard in sorted((world_out / "train").glob("*.jsonl"))
                           for line in shard.read_text(encoding="utf-8").splitlines() if line]
        if len(documents[name]) != count:
            raise ValueError(f"world {name} produced {len(documents[name])} of {count} documents")
    positions = {name: 0 for name in sets}
    with (args.out / "mixture.jsonl").open("w", encoding="utf-8") as sink:
        for name in schedule:
            document = documents[name][positions[name]]
            positions[name] += 1
            sink.write(json.dumps({"world": name, **document}, ensure_ascii=False) + "\n")
    report = {"worlds": {name: schedule.count(name) for name in sets}, "weights": weights,
              "seed": args.seed, "items": len(schedule),
              "manifests": {name: f"worlds/{name}/manifest.json" for name in manifests}}
    (args.out / "world_mix.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0
