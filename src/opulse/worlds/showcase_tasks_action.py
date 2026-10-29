"""Task tabs of the action world (see :mod:`opulse.worlds.showcase_tasks`).

The action world grows skills, not operator definitions, so its tasks are built from
:func:`opulse.worlds.action.run_skill`, the reference reducer of skills. Nothing here is a z3
proof: every claim is checked by simulation on the world's generated start states, and each
item says how many states were checked. There is no simplify task, because a skill body has
no helper to inline.
"""

from __future__ import annotations

import itertools
import json
import random
from dataclasses import replace
from pathlib import Path

from opulse.core.semantics import NAN
from opulse.worlds.action import (
    _examples_states,
    apply_atom,
    bounded_equivalence,
    encode,
    generate_skills,
    run_skill,
)

SEED = 36  # the first seed of the action showcase
TASK_SEED = 20261024
GRANULARITIES = (
    {"key": "operator", "en": "one step per skill", "zh": "每个技能一步", "depth": 0},
    {"key": "unfold", "en": "written skills unfolded", "zh": "展开写出的技能", "depth": 1},
    {"key": "full", "en": "every step", "zh": "每一步", "depth": None},
)


def _same(a, b) -> bool:
    return encode(a) == encode(b)


def _apply(names: list[str], state, library):
    for name in names:
        state, _ = run_skill(name, state, library, unfold=False)
    return state


def _text(names: list[str]) -> str:
    text = "s"
    for name in names:
        text = f"{name}({text})"
    return text


def _closure(skill, library) -> set[str]:
    found, stack = set(), [skill.name]
    while stack:
        name = stack.pop()
        if name in found or name not in library:
            continue
        found.add(name)
        stack.extend(ref for ref in (library[name].first, library[name].second) if ref)
    return found


def export_action_tasks(directory: Path, folder: Path) -> dict:
    skills = generate_skills(seed=SEED)
    library = {s.name: s for s in skills}
    states = _examples_states()
    rng = random.Random(TASK_SEED)
    names = [s.name for s in skills]
    check = {"method": "sample", "size": len(states), "unit": "states"}

    # ---------------------------------------------------------------- expressions
    expressions, seen = [], set()
    for size in (2, 2, 3, 3, 3, 4, 4, 2):
        for _ in range(400):
            chain = rng.sample(names[:40], size)
            if tuple(chain) in seen:
                continue
            state = rng.choice(states[:12])
            value = _apply(chain, state, library)
            if value is NAN or _same(value, state):
                continue
            granular = []
            for level in GRANULARITIES:
                current, steps = state, []
                for name in chain:
                    current, more = run_skill(name, current, library, max_unfold_depth=level["depth"])
                    steps += more
                if not _same(current, value):
                    raise AssertionError("an action derivation disagrees with the one step result")
                granular.append(steps)
            if len(granular[-1]) > 220:
                continue
            index = len(expressions)
            (folder / f"expr-{index}.json").write_text(json.dumps(granular, ensure_ascii=False, separators=(",", ":")),
                                                      encoding="utf-8")
            expressions.append({"id": f"expr-{index}", "expression": _text(chain), "value": encode(value),
                                "depth": size, "operators": chain, "first": encode(state),
                                "definitions": [{"name": n, "definition": library[n].definition()} for n in chain],
                                "steps": [len(s) for s in granular], "_chain": chain, "_state": state})
            seen.add(tuple(chain))
            break

    # ---------------------------------------------------------------- holes
    holes = []
    for skill in skills[:40]:
        if len(holes) >= 2:
            break
        outputs = [run_skill(skill, s, library, unfold=False)[0] for s in states]
        for i, out in enumerate(outputs):
            if out is NAN:
                continue
            hits = [j for j, other in enumerate(outputs) if _same(other, out)]
            if len(hits) == 1 and not _same(out, states[i]):
                rows = [[encode(s), encode(o)] for s, o in zip(states, outputs)]
                index = len(holes)
                (folder / f"hole-{index}.json").write_text(json.dumps({"candidates": rows}, separators=(",", ":")),
                                                          encoding="utf-8")
                holes.append({"id": f"hole-{index}", "equation": f"{skill.name}(x) = t", "expression": f"{skill.name}(x)",
                              "target": encode(out), "answer": encode(states[i]), "solutions": [encode(states[i])],
                              "unique": True, "domain": {"kind": "state", "size": len(states)}, "check": check,
                              "summary": False, "x_kind": "state", "tried": len(states), "depth": 1})
                break
    start = states[4]
    for skill in skills[3:60]:
        if len(holes) >= 4:
            break
        target = run_skill(skill, start, library, unfold=False)[0]
        if target is NAN or _same(target, start):
            continue
        outputs = [run_skill(name, start, library, unfold=False)[0] for name in names]
        hits = [n for n, o in zip(names, outputs) if _same(o, target)]
        if len(hits) > 3:
            continue
        rows = [[{"t": "skill", "v": n}, encode(o)] for n, o in zip(names, outputs)]
        index = len(holes)
        (folder / f"hole-{index}.json").write_text(json.dumps({"candidates": rows, "start": encode(start)},
                                                              separators=(",", ":")), encoding="utf-8")
        holes.append({"id": f"hole-{index}", "equation": "x(s) = t", "expression": "x(s)", "start": encode(start),
                      "target": encode(target), "answer": {"t": "skill", "v": skill.name},
                      "solutions": [{"t": "skill", "v": n} for n in hits], "unique": len(hits) == 1,
                      "domain": {"kind": "skill", "size": len(names)},
                      "check": {"method": "all", "size": len(names), "unit": "skills"},
                      "summary": False, "x_kind": "skill", "tried": len(names), "depth": 1})

    # ---------------------------------------------------------------- laws
    def unary(name):
        if name in library:
            return lambda s: run_skill(name, s, library, unfold=False)[0]
        return lambda s: apply_atom(name, s)

    rows = []
    for name in ["turn_left", "pick", *names[:30]]:
        f = unary(name)
        cells = {}
        for law in ("idempotent", "involution"):
            failing = None
            for s in states:
                once = f(s)
                left = f(once) if once is not NAN else NAN
                right = once if law == "idempotent" else s
                if not _same(left, right):
                    failing = (s, left, right)
                    break
            if failing is None:
                cells[law] = {"holds": True, "check": check}
            else:
                s, left, right = failing
                cells[law] = {"holds": False, "check": check, "counterexample": {
                    "inputs": [{"name": "s", "value": encode(s)}],
                    "left": f"{name}({name}(s))", "right": f"{name}(s)" if law == "idempotent" else "s",
                    "left_value": encode(left), "right_value": encode(right)}}
        definition = library[name].definition() if name in library else name
        rows.append({"name": name, "definition": definition, "signature": ["state", "state"], "n_ary": 1,
                     "cells": cells})
    holding = [r for r in rows if any(c["holds"] for c in r["cells"].values())]
    failing = [r for r in rows if r not in holding]
    picked = (holding[:3] + failing[:3])[:6]
    laws = {"laws": ["idempotent", "involution"], "rows": picked}

    # ---------------------------------------------------------------- equivalence
    outputs = {n: [encode(run_skill(n, s, library, unfold=False)[0]) for s in states] for n in names[:60]}
    pairs = []
    for a, b in itertools.combinations(names[:60], 2):
        if library[a].definition().split("=", 1)[1] == library[b].definition().split("=", 1)[1]:
            continue
        agree = sum(x == y for x, y in zip(outputs[a], outputs[b])) / len(states)
        defined = sum(x["t"] != "nan" for x in outputs[a])
        if defined >= len(states) // 2:
            pairs.append((agree, a, b))
    pairs.sort(key=lambda row: -row[0])
    equivalence = []
    for agree, a, b in pairs:
        if len(equivalence) >= 3:
            break
        verdict = bounded_equivalence(library[a], library[b], states, library)
        equal = verdict["equivalent"]
        if equal and any(item["equal"] for item in equivalence):
            continue
        if not equal and agree < 0.6:
            continue
        item = {"left": f"{a}(s)", "right": f"{b}(s)", "kind": "operators", "equal": equal, "check": check,
                "agreement": round(agree, 3),
                "definitions": [{"name": n, "definition": library[n].definition()} for n in (a, b)]}
        if not equal:
            from opulse.worlds.action import decode

            s = decode(verdict["counterexample"])
            item["counterexample"] = {"inputs": [{"name": "s", "value": encode(s)}],
                                      "left_value": encode(run_skill(a, s, library, unfold=False)[0]),
                                      "right_value": encode(run_skill(b, s, library, unfold=False)[0])}
        equivalence.append(item)

    # ---------------------------------------------------------------- contrast
    contrast = []
    for item in expressions:
        if len(contrast) >= 2:
            break
        chain, state = item["_chain"], item["_state"]
        target = chain[-1]
        for other in names[:60]:
            if other in chain or target in _closure(library[other], library):
                continue
            twin = chain[:-1] + [other]
            first, second = _apply(chain, state, library), _apply(twin, state, library)
            if second is NAN or _same(first, second):
                continue
            body = library[other].definition().replace(f"s {other} =", f"s {target} =", 1)
            contrast.append({"expression": item["expression"], "operator": target, "start": encode(state),
                             "a": {"definition": library[target].definition(), "value": encode(first)},
                             "b": {"definition": body, "value": encode(second), "from": other}})
            break

    # ---------------------------------------------------------------- edit
    edit = []
    users = {n: [m for m in names if n != m and n in _closure(library[m], library)] for n in names}
    for low in sorted(names[:50], key=lambda n: -len(users[n])):
        skill = library[low]
        if skill.kind == "branch":
            changed = replace(skill, expected=(not skill.expected) if isinstance(skill.expected, bool)
                              else skill.expected, first=skill.second, second=skill.first)
            kind = ("the two cases swapped", "交换两种情形")
        elif skill.kind == "recursion":
            changed = replace(skill, bound=skill.bound + 2)
            kind = ("the repeat bound raised by two", "重复上限加二")
        else:
            changed = replace(skill, first=skill.second, second=skill.first)
            kind = ("the two parts swapped", "交换前后两部分")
        edited = {**library, low: changed}
        rows = []
        for name in [low, *users[low][:7], *[n for n in names[:20] if n not in users[low] and n != low][:2]]:
            pick = None
            for s in states:
                before = run_skill(name, s, library, unfold=False)[0]
                after = run_skill(name, s, edited, unfold=False)[0]
                if before is not NAN and not _same(before, after):
                    pick = (s, before, after)
                    break
            if pick is None:
                s = states[0]
                pick = (s, run_skill(name, s, library, unfold=False)[0], run_skill(name, s, edited, unfold=False)[0])
            s, before, after = pick
            rows.append({"name": name, "expression": f"{name}(s)", "input": encode(s),
                         "reaches": name == low or name in users[low],
                         "before": encode(before), "after": encode(after), "changed": not _same(before, after)})
        if sum(r["changed"] for r in rows[1:]) >= 2:
            edit.append({"operator": low, "before": skill.definition(), "after": changed.definition(),
                         "edit": "skill", "edit_en": kind[0], "edit_zh": kind[1],
                         "affected_count": len(users[low]), "affected": users[low][:12], "rows": rows})
            break

    for item in expressions:
        item.pop("_chain")
        item.pop("_state")
    return {"world": "action", "seed": SEED, "files": "action/tasks/",
            "granularities": [{k: v for k, v in g.items() if k != "depth"} for g in GRANULARITIES],
            "solver": "simulation", "expressions": expressions, "holes": holes, "laws": laws,
            "equivalence": equivalence, "contrast": contrast, "edit": edit, "simplify": [],
            "notes": {"simplify": {"en": "Action skills contain no helper definitions to expand, so this simplification view does not apply.",
                                   "zh": "行动技能没有可展开的辅助定义，因此这里不适用化简视图。"}}}
