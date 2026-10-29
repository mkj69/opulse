"""Adapter contract for instantiating skeletons as external world skills."""

from __future__ import annotations

import random
from copy import deepcopy
from dataclasses import dataclass
from typing import Protocol

from opulse.skeleton import NoMatchError, SkeletonSet, _mapped


@dataclass(frozen=True)
class SkillRun:
    value: object
    undefined: bool
    unfolded_length: int


class SkillWorldAdapter(Protocol):
    """Bridge to a world's Skill class and run_skill simulator.

    ``make_skill`` receives the skeleton tree with mapped type annotations and
    bindings from hole IDs to atom IDs. Calls to dependencies use the already
    built skill objects.
    The adapter implements the world's own expression and condition semantics.
    """

    def atoms(self) -> dict[str, tuple[tuple[str, ...], str]]: ...

    def make_skill(self, record: dict, bindings: dict[str, str], dependencies: dict[str, object]) -> object: ...

    def run_skill(self, skill: object, args: tuple[object, ...]) -> SkillRun: ...

    def probe_values(self, kind: str) -> list[object]: ...


def instantiate_skills(skeletons: SkeletonSet, adapter: SkillWorldAdapter, *, world: str,
                       type_map: dict[str, str] | None = None,
                       correspondence: dict[str, str] | None = None,
                       seed: int = 0, probe_count: int = 16) -> tuple[dict[str, object], list[dict]]:
    """Bind typed holes and validate every skill against simulator probes."""
    if probe_count < 1:
        raise ValueError("probe_count must be positive")
    type_map = type_map or {}
    correspondence = correspondence or {}
    rng = random.Random(seed)
    atoms = adapter.atoms()
    made = {}
    rows = []
    for record in skeletons.records:
        bindings = {}
        for hole in record["holes"]:
            key = f"{record['id']}:{hole['id']}"
            params = tuple(_mapped(kind, type_map) for kind in hole["parameter_types"])
            result = _mapped(hole["result_type"], type_map)
            candidates = sorted(atom for atom, signature in atoms.items()
                                if signature == (params, result) and
                                (key not in correspondence or correspondence[key] == atom))
            if not candidates:
                raise NoMatchError(f"no action atom matches {key} in {world}")
            bindings[hole["id"]] = rng.choice(candidates)
        if any(dep not in made for dep in record["dependencies"]):
            raise ValueError("skeleton dependencies must precede their callers")
        target_record = deepcopy(record)
        target_record["parameter_types"] = [_mapped(kind, type_map) for kind in record["parameter_types"]]
        if "result_type" in record:
            target_record["result_type"] = _mapped(record["result_type"], type_map)
        for hole in target_record["holes"]:
            hole["parameter_types"] = [_mapped(kind, type_map) for kind in hole["parameter_types"]]
            hole["result_type"] = _mapped(hole["result_type"], type_map)
        skill = adapter.make_skill(target_record, bindings,
                                   {dep: made[dep] for dep in record["dependencies"]})
        kinds = [_mapped(kind, type_map) for kind in record["parameter_types"]]
        values = [adapter.probe_values(kind) for kind in kinds]
        if any(not domain for domain in values):
            raise ValueError("action probe domains cannot be empty")
        runs = []
        for _ in range(probe_count):
            args = tuple(rng.choice(domain) for domain in values)
            result = adapter.run_skill(skill, args)
            if not isinstance(result, SkillRun) or result.unfolded_length < 0:
                raise ValueError("run_skill must return a SkillRun with a nonnegative length")
            runs.append(result)
        made[record["id"]] = skill
        rows.append({"skeleton_id": record["id"], "world": world, "grade": "G1",
                     "correspondence": bindings,
                     "unfolded_length": sum(run.unfolded_length for run in runs) / probe_count,
                     "nan_rate": sum(run.undefined for run in runs) / probe_count})
    return made, rows
