"""Extract typed skeletons and instantiate them in registered atom worlds."""

from __future__ import annotations

import json
import math
from pathlib import Path

from opulse.canary import marked
from opulse.cli.operators import DEFAULT_CONFIG


def register(commands) -> None:
    cmd = commands.add_parser("skeleton", help="extract and instantiate operator skeletons")
    sub = cmd.add_subparsers(dest="skeleton_command", required=True)
    extract = sub.add_parser("extract", help="extract a set of skeletons")
    extract.add_argument("--operators", type=Path, required=True)
    extract.add_argument("--out", type=Path, required=True)
    extract.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    extract.set_defaults(run=run_extract)

    instance = sub.add_parser("instantiate", help="bind skeleton holes to a target atom set")
    instance.add_argument("--skeletons", type=Path, required=True)
    instance.add_argument("--atoms", type=Path, required=True)
    instance.add_argument("--world", required=True)
    instance.add_argument("--out", type=Path, required=True)
    instance.add_argument("--records", type=Path)
    instance.add_argument("--type-map", type=Path, help="JSON object mapping source types to target types")
    instance.add_argument("--correspondence", type=Path, help="JSON object mapping skeleton:hole to atom id")
    instance.add_argument("--sample-values", type=Path, help="JSON object of probe values keyed by target type")
    instance.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    instance.add_argument("--seed", type=int, default=0)
    instance.add_argument("--attempts", type=int, default=100)
    instance.set_defaults(run=run_instantiate)

    match = sub.add_parser("match", help="instantiate one skeleton set in several worlds")
    match.add_argument("--skeletons", type=Path, required=True)
    match.add_argument("--world", action="append", required=True, metavar="NAME=ATOMS_JSONL")
    match.add_argument("--out-dir", type=Path, required=True)
    match.add_argument("--type-maps", type=Path, help="JSON object of type maps keyed by world name")
    match.add_argument("--sample-values", type=Path, help="JSON object of probe values keyed by world and type")
    match.add_argument("--grade-domains", type=Path, help="finite domains keyed by world and type")
    match.add_argument("--equations", type=Path, help="JSON list of equations for G2")
    match.add_argument("--partial-domains", action="store_true",
                       help="grade finite restrictions where outputs outside the domain are undefined")
    match.add_argument("--nan-tolerance", type=float, default=None,
                       help="largest allowed difference in probe undefined rates")
    match.add_argument("--length-tolerance", type=float, default=None,
                       help="largest allowed difference in unfolded trace length on any paired probe")
    match.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    match.add_argument("--seed", type=int, default=0)
    match.add_argument("--attempts", type=int, default=100)
    match.set_defaults(run=run_match)


def _settings(path):
    from opulse.config import Settings

    return Settings.load(path)


def run_extract(args) -> int:
    from opulse.core.registry import OperatorRegistry
    from opulse.skeleton import extract

    skeletons = extract(OperatorRegistry.from_jsonl(args.operators), _settings(args.config))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    skeletons.write(args.out)
    print(json.dumps({"skeletons": len(skeletons.records), "out": str(args.out)}, ensure_ascii=False))
    return 0


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8")) if path is not None else {}


def run_instantiate(args) -> int:
    from opulse.core.registry import OperatorRegistry
    from opulse.skeleton import NoMatchError, SkeletonSet, instantiate

    try:
        registry, rows = instantiate(SkeletonSet.read(args.skeletons), OperatorRegistry.from_jsonl(args.atoms),
                                     world=args.world, settings=_settings(args.config),
                                     type_map=_read_json(args.type_map),
                                     correspondence=_read_json(args.correspondence),
                                     seed=args.seed, attempts=args.attempts,
                                     sample_values=_read_json(args.sample_values))
    except NoMatchError as exc:
        raise SystemExit(str(exc)) from exc
    args.out.parent.mkdir(parents=True, exist_ok=True)
    registry.to_jsonl(args.out)
    records = args.records or args.out.with_suffix(".instances.jsonl")
    records.write_text("".join(json.dumps(marked(row), ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    print(json.dumps({"world": args.world, "grade": "G1", "instances": len(rows), "operators": str(args.out),
                      "records": str(records)}, ensure_ascii=False))
    return 0


def run_match(args) -> int:
    from opulse.core.registry import OperatorRegistry
    from opulse.matched import correspondence_grade
    from opulse.skeleton import (
        NoMatchError,
        SkeletonSet,
        instantiate,
        value_table,
        verify_match,
    )

    for value in (args.nan_tolerance, args.length_tolerance):
        if value is not None and (not math.isfinite(value) or value < 0):
            raise ValueError("match tolerances must be finite and nonnegative")

    skeletons = SkeletonSet.read(args.skeletons)
    type_maps = _read_json(args.type_maps)
    samples = _read_json(args.sample_values)
    domains = _read_json(args.grade_domains)
    equations = _read_json(args.equations) if args.equations else []
    worlds = {}
    for spec in args.world:
        if "=" not in spec:
            raise ValueError("--world expects NAME=ATOMS_JSONL")
        name, path = spec.split("=", 1)
        if not name or name in worlds:
            raise ValueError(f"duplicate or empty world name {name!r}")
        worlds[name] = OperatorRegistry.from_jsonl(path)
    if len(worlds) < 2:
        raise ValueError("match needs at least two worlds")
    accepted = {}
    accepted_rows = {}
    rows = []
    rejects = {}
    for index, (name, atoms) in enumerate(worlds.items()):
        last_reason = "same sampled values"
        rejected = {}
        for offset in range(args.attempts):
            try:
                registry, records = instantiate(skeletons, atoms, world=name, settings=_settings(args.config),
                                                type_map=type_maps.get(name, {}),
                                                seed=args.seed + index * 100000 + offset,
                                                attempts=1, sample_values=samples.get(name),
                                                probe_seed=args.seed)
            except NoMatchError as exc:
                last_reason = str(exc)
                rejected[last_reason] = rejected.get(last_reason, 0) + 1
                continue
            if accepted and any(any(
                [row["value"] for row in value_table(registry, record["skeleton_id"], _settings(args.config),
                                                      samples.get(name))] ==
                [row["value"] for row in value_table(previous, record["skeleton_id"], _settings(args.config),
                                                      samples.get(previous_name))]
                for record in records) for previous_name, previous in accepted.items()):
                rejected["same sampled values"] = rejected.get("same sampled values", 0) + 1
                continue
            if accepted and (args.nan_tolerance is not None or args.length_tolerance is not None):
                by_id = {row["skeleton_id"]: row for row in records}
                mismatch = None
                for previous_rows in accepted_rows.values():
                    for before in previous_rows:
                        after = by_id[before["skeleton_id"]]
                        if abs(before["probe"]["nan_rate"] - after["probe"]["nan_rate"]) > \
                                (args.nan_tolerance if args.nan_tolerance is not None else 0):
                            mismatch = "undefined rate tolerance"
                        if max(abs(a - b) for a, b in zip(before["probe"]["lengths"],
                                                           after["probe"]["lengths"])) > \
                                (args.length_tolerance if args.length_tolerance is not None else 0):
                            mismatch = "unfolded length tolerance"
                        if mismatch:
                            break
                    if mismatch:
                        break
                if mismatch:
                    last_reason = mismatch
                    rejected[mismatch] = rejected.get(mismatch, 0) + 1
                    continue
            accepted[name] = registry
            accepted_rows[name] = records
            rows.extend(records)
            break
        else:
            raise SystemExit(f"no matched set in {name}: {last_reason}; rejects: {json.dumps(rejected)}")
        rejects[name] = rejected
    names = list(accepted)
    comparisons = {}
    grades = {}
    source_name = names[0]
    for name, registry in list(accepted.items())[1:]:
        checks = []
        grade_rows = []
        for record in skeletons.records:
            source_row = next(row for row in accepted_rows[source_name] if row["skeleton_id"] == record["id"])
            target_row = next(row for row in accepted_rows[name] if row["skeleton_id"] == record["id"])
            atom_map = {}
            compatible = True
            grade_type_map = {}
            for hole, atom in source_row["correspondence"].items():
                mapped = target_row["correspondence"][hole]
                if atom in atom_map and atom_map[atom] != mapped:
                    compatible = False
                atom_map[atom] = mapped
                left_atom = accepted[source_name].get(atom)
                right_atom = registry.get(mapped)
                for left_type, right_type in zip((*left_atom.parameter_types, left_atom.result_type),
                                                 (*right_atom.parameter_types, right_atom.result_type)):
                    if left_type in grade_type_map and grade_type_map[left_type] != right_type:
                        compatible = False
                    grade_type_map[left_type] = right_type
            grade = (correspondence_grade(accepted[source_name], registry, atom_map,
                                           type_map=grade_type_map,
                                           equations=[item for item in equations if item["atom"] in atom_map],
                                           source_domains=domains.get(source_name), target_domains=domains.get(name),
                                           partial=args.partial_domains,
                                           settings=_settings(args.config)) if compatible and atom_map else
                     {"grade": "G1", "method": "signature", "equations": [],
                      "isomorphism": "not established: no consistent atom mapping"})
            grade_rows.append(grade)
            target_row["grade"] = grade["grade"]
            accepted[name].get(target_row["func_id"]).correspondence_grade = grade["grade"]
            check = verify_match(accepted[source_name], registry, record["id"], _settings(args.config),
                                 samples.get(source_name), samples.get(name), grade=grade["grade"])
            check["nan_rate_difference"] = abs(source_row["probe"]["nan_rate"] - target_row["probe"]["nan_rate"])
            check["unfolded_length_difference"] = max(
                abs(a - b) for a, b in zip(source_row["probe"]["lengths"], target_row["probe"]["lengths"]))
            check["mean_unfolded_length_difference"] = abs(
                source_row["unfolded_length"] - target_row["unfolded_length"])
            checks.append(check)
        comparisons[name] = checks
        grades[name] = grade_rows
    if grades:
        order = {"G1": 1, "G2": 2, "G3": 3}
        for index, row in enumerate(accepted_rows[source_name]):
            grade = min((grades[name][index]["grade"] for name in grades), key=order.get)
            row["grade"] = grade
            accepted[source_name].get(row["func_id"]).correspondence_grade = grade
    report = {"worlds": names, "skeletons": len(skeletons.records), "instances": len(rows),
              "comparisons": comparisons, "grades": grades, "rejects": rejects}
    report["grade"] = min((grade["grade"] for values in grades.values() for grade in values),
                          key={"G1": 1, "G2": 2, "G3": 3}.get, default="G1")
    if any(not all(check[key] for key in ("structural_hash_equal", "composition_depth_equal",
                                             "value_tables_differ"))
           for checks in comparisons.values() for check in checks):
        raise SystemExit("matched instances failed structure, depth, or value table verification")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for name, registry in accepted.items():
        registry.to_jsonl(args.out_dir / f"{name}.jsonl")
    with (args.out_dir / "instances.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(marked(row), ensure_ascii=False) + "\n")
    (args.out_dir / "match.json").write_text(json.dumps(marked(report), indent=2, ensure_ascii=False) + "\n",
                                               encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0
