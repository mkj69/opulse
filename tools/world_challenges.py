"""Build checked, reproducible Challenge tabs from the published seed of each world.

Run with ``PYTHONPATH=src python tools/world_challenges.py [world ...]``.
The showcase is the source of names and short candidate inputs; all answers and
both derivations are recomputed from the reference interpreter before writing.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import sys
from dataclasses import replace
from pathlib import Path

from opulse.core.registry import OperatorRegistry
from opulse.core.semantics import NAN
from opulse.core.types import same_value
from opulse.definition.parser import DefinitionParser
from opulse.expression.nodes import Call, Number, to_ast
from opulse.runtime.python_backend import PythonRuntime
from opulse.trace.reducer import Reducer
from opulse.verify import verify_trace
from opulse.worlds.showcase import _notes
from opulse.worlds.showcase_tasks import _mutations, prepare
from opulse.worlds.present import Describer
from opulse.worlds.curation import _alias, _cancelled_constant
if __package__:
    from .example_atoms import annotate
    from .world_challenge_rationales import CASE_DIGESTS, RATIONALES
    from .world_challenge_induce import build as build_induce_challenge
else:
    from example_atoms import annotate
    from world_challenge_rationales import CASE_DIGESTS, RATIONALES
    from world_challenge_induce import build as build_induce_challenge

ROOT = Path(__file__).resolve().parents[1] / "docs/assets/data/worlds"
WORLDS = ("successor", "integer", "clock", "bits", "strings", "lists", "logic",
          "perm", "rel", "grid", "pitch", "action")
LEVELS = ("easy", "easy", "medium", "medium", "hard")
IDEAS = ("composition", "branch", "recursion", "order", "inverse", "edge", "saturation", "symmetry")
# The order is the teaching sequence. Each operator has a separate reason to be here.
PLAN = {
    "successor": (("♡₉", "composition"), ("♣₁₄", "edge"), ("◆₄", "branch"),
                  ("◆₆", "saturation"), ("■₃", "recursion")),
    "integer": (("■₄", "composition"), ("♢₅", "order"), ("♦₃₇", "branch"),
                ("▼₇", "inverse"), ("♤₃", "recursion")),
    "clock": (("△₁", "order"), ("▽₅", "edge"), ("▽₂", "branch"),
              ("☆₄", "composition"), ("●₃", "recursion")),
    "bits": (("▲₈", "composition"), ("♤₁", "inverse"), ("♠₂₁", "branch"),
             ("♦₅", "edge"), ("♢₃", "recursion")),
    "strings": (("♣₁", "composition"), ("▲₆", "order"), ("♦₂", "branch"),
                ("■₄", "edge"), ("□₇₆", "recursion")),
    "lists": (("■₆", "composition"), ("□₁₀", "order"), ("▲₂₀", "branch"),
              ("☆₄", "edge"), ("▽₃", "recursion")),
    "logic": (("♦₅", "composition"), ("◆₆", "order"), ("△₂", "branch"),
              ("♡₇₂", "edge"), ("▽₄₄", "recursion")),
    "perm": (("♤₁", "composition"), ("▼₄", "order"), ("♣₂", "branch"),
             ("♤₇", "edge"), ("♠₃", "recursion")),
    "rel": (("♤₂", "branch"), ("★₄", "order"), ("●₁", "composition"),
            ("♠₅", "edge"), ("♥₃", "recursion")),
    "grid": (("●₈", "composition"), ("★₄", "order"), ("■₂", "branch"),
             ("●₁₀", "symmetry"), ("♤₄₄", "recursion")),
    "pitch": (("■₆", "composition"), ("♢₅", "order"), ("▲₁₉", "branch"),
              ("●₉", "edge"), ("♠₃", "recursion")),
    "action": (("★₁", "composition"), ("♤₇", "order"), ("□₂", "branch"),
               ("▲₅", "edge"), ("■₃", "recursion")),
}
PREFERRED = {
    ("clock", "▽₅"): "2 ▽₅",
    ("successor", "♡₉"): "♡₉ 2",
    ("successor", "♣₁₄"): "♣₁₄ 0",
    ("successor", "◆₆"): "1 ◆₆",
    ("integer", "♤₃"): "9 ♤₃ (-5)",
    ("integer", "♦₃₇"): "9 ♦₃₇ (-2)",
    ("lists", "▲₂₀"): "[] ▲₂₀",
    ("lists", "☆₄"): "[] ☆₄",
    ("lists", "□₁₀"): "[12, 7] □₁₀ [-4, 0, 6]",
    ("logic", "□₃"): "false □₃ 5",
    ("logic", "♡₇₂"): "false ♡₇₂ 5",
    ("logic", "▽₄₄"): "false ▽₄₄ 3",
    ("logic", "◆₆"): "false ◆₆ true",
    ("bits", "♦₅"): "63 ♦₅ 25",
    ("perm", "♣₂"): "P[1, 0, 2, 3, 4] ♣₂ P[1, 2, 3, 4, 0]",
    ("strings", "■₄"): '"B" ■₄ ""',
    ("strings", "♡₃"): '"" ♡₃ 2',
    ("strings", "□₇₆"): '"" □₇₆ 2',
    ("grid", "■₂"): "[[3, 0, 3], [0, 1, 0]] ■₂ 2",
    ("grid", "●₈"): "[[1, 0], [0, 3]] ●₈ 1",
    ("grid", "●₁₀"): "[[1, 2], [3, 0]] ●₁₀",
    ("grid", "♤₄₄"): "[[1, 2], [3, 0]] ♤₄₄ 3",
    ("rel", "♠₅"): '"Gio" ♠₅',
    ("rel", "♤₂"): '"Hana" ♤₂',
    ("rel", "★₄"): '"Faye" ★₄',
    ("rel", "♥₃"): '"Bo" ♥₃ (-1)',
}
PREFERRED_ARGS = {("integer", "♦₃₇"): (9, -2), ("successor", "♣₁₄"): (0,),
                  ("successor", "◆₆"): (1,), ("grid", "●₈"): (((1, 0), (0, 3)), 1),
                  ("grid", "●₁₀"): (((1, 2), (3, 0)),),
                  ("grid", "♤₄₄"): (((1, 2), (3, 0)), 3)}
PREFERRED_ARGS[("strings", "□₇₆")] = ("", 2)
PREFERRED_ARGS[("logic", "♡₇₂")] = (False, 5)

TEACHING_INPUTS = {
    "successor": ((2,), (0,), (3, 4), (1,), (0, 4)),
    "integer": ((12, 7), (9, 3), (9, -2), (9,), (9, -5)),
    "clock": ((2, 7), (2,), (0, 13), (2,), (2, 5)),
    "bits": ((3,), (5, 5), (2,), (63, 25), (2, 2)),
    "strings": (("b", "B"), ("ab",), ("a", "hello"), ("B", ""), ("", 2)),
    "lists": (((12, 7),), ((12, 7), (-4, 0, 6)), ((),), ((),), ((2, 9), 2)),
    "logic": ((True, True), (False, True), (True, 0), (False, 5), (False, 3)),
    "perm": (((0, 1, 2, 3, 4),), ((0, 1, 2, 3, 4),),
             ((1, 0, 2, 3, 4), (1, 2, 3, 4, 0)), ((1, 2, 3, 4, 0),), ((0, 1, 2, 3, 4), 3)),
    "rel": (("Hana",), ("Faye",), ("Ana",), ("Gio",), ("Bo", -1)),
    "grid": ((((1, 0), (0, 3)), 1), (((2, 0, 0), (2, 0, 0), (2, 2, 0)),),
             (((3, 0, 3), (0, 1, 0)), 2), (((1, 2), (3, 0)),), (((1, 2), (3, 0)), 3)),
    "pitch": ((60,), (60, 2), (60, -4), (60, 2), (60, 2)),
}


def _key(value: dict) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _human_sized(world_name: str, args: tuple, before, after) -> bool:
    """Reject oversized scalar puzzles while leaving size-based worlds intact."""
    if any(type(value) is int and abs(value) > 100 for value in (before, after)):
        return False
    if world_name in {"successor", "integer"}:
        return sum(type(value) is int and abs(value) > 20 for value in args) <= 1
    return True


def _check_rationales(world_name: str, puzzles: list[dict]) -> None:
    cases = [{"question": puzzle["question"], "answer": puzzle["answer"]} for puzzle in puzzles]
    payload = json.dumps(cases, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if hashlib.sha256(payload.encode()).hexdigest() != CASE_DIGESTS[world_name]:
        raise RuntimeError(f"{world_name}: question or answer changed; review its why and why_zh")


def _steps(trace, world) -> list[dict]:
    kinds = {op.func_id: op.result_type for op in world.tools.registry}
    rows = []
    for step in trace.steps:
        note, note_zh = _notes(step, world.tools, kinds)
        row = {"expr": _display_step(world.show(world.tools.renderer.full(step.expression_after)), world.spec.world),
               "rule": _display_step(note, world.spec.world),
               "rule_zh": _display_step(note_zh, world.spec.world),
               "kind": step.kind,
               "focus": _display_step(world.show(world.tools.renderer.full(step.before)), world.spec.world),
               "gate": world.name(step.operator) if step.operator.definition else step.operator.symbol}
        if step.output is not None:
            row["value"] = world.enc(step.output, kinds.get(step.operator.func_id))
        rows.append(row)
    return rows


def _display_step(text: str, world_name: str) -> str:
    """Use the same compact literal notation as the world's browser renderer."""
    if world_name == "grid":
        def grid(match):
            rows = json.loads(match.group())
            return f"▦{len(rows)}×{len(rows[0])}"

        return re.sub(r"\[\[[\d, ]*\](?:, \[[\d, ]*\])*\]", grid, text)
    if world_name == "pitch":
        names = ("C", "C♯", "D", "D♯", "E", "F", "F♯", "G", "G♯", "A", "A♯", "B")

        def melody(match):
            pairs = json.loads(match.group())
            return "⟨" + " ".join(names[p % 12] + str(p // 12 - 1) +
                                  ("" if duration == 1 else f":{duration}")
                                  for p, duration in pairs) + "⟩"

        return re.sub(r"\[\[\d+, \d+\](?:, \[\d+, \d+\])*\]", melody, text)
    return text


def _edit_note(symbol: str, before: str, after: str) -> str:
    """Name the one changed part of a rule for its counterfactual option."""
    if symbol == "▽₅" and "(- (a + 2))" in before + after:
        return ("That would be the answer if ▽₅ increased its second input by two before negation."
                if "(- (a + 2))" in after else
                "That would be the answer if ▽₅ did not increase its second input by two.")
    first = 0
    while first < min(len(before), len(after)) and before[first] == after[first]:
        first += 1
    last = 0
    while last < min(len(before), len(after)) - first and before[-1 - last] == after[-1 - last]:
        last += 1
    old = before[first:len(before) - last if last else len(before)]
    new = after[first:len(after) - last if last else len(after)]
    return f"That would be the answer if {symbol} used {new} instead of {old}."


def _trace(registry, oracle, settings, tree):
    reducer = Reducer(registry, PythonRuntime(registry, settings.semantics.build()),
                      DefinitionParser(settings.symbols, registry), max_steps=100, max_depth=2)
    trace = reducer.reduce(tree)
    if trace.truncated or not same_value(trace.value, oracle.evaluate_expr(to_ast(tree), {}).value):
        raise ValueError("trace does not reach the reference answer")
    verify_trace(trace, oracle)
    return trace


def _options(answer, alternate, source: list[tuple[dict, str]], world, result_type: str,
             alternate_note: str) -> tuple[list[dict], list[str]]:
    options = [answer, alternate]
    notes = ["", alternate_note]
    choice_type = alternate["t"] if answer["t"] == "nan" else answer["t"]
    for candidate, explanation in source:
        if result_type == "bool" and candidate["t"] == "nan":
            continue
        if candidate["t"] not in (choice_type, "nan"):
            continue
        if _key(candidate) not in {_key(x) for x in options}:
            options.append(candidate)
            notes.append(explanation)
        if len(options) == 3:
            break
    if len(options) < 3 and result_type == "bool":
        options.append({"t": "nan"})
        notes.append("These inputs are within the displayed rule's domain, so its Boolean result is defined.")
    if len(options) != 3 or len({_key(x) for x in options}) != 3:
        raise ValueError("three distinct answer choices unavailable")
    # Rotate the correct answer among the positions without any runtime randomness.
    shift = len(world.spec.world) % 3
    return options[shift:] + options[:shift], notes[shift:] + notes[:shift]


def _rules(main: dict, trace, data: dict, world) -> list[dict]:
    lookup = {row["name"]: row for row in data["operators"]}
    lookup.update({row["symbol"]: row for row in data["atoms"]})
    names = [main["name"]]
    for step in trace.steps:
        name = world.name(step.operator) if step.operator.definition is not None else step.operator.symbol
        if name in lookup and name not in names:
            names.append(name)
    rules = []
    for name in names:
        text = lookup[name].get("definition", lookup[name].get("rule", ""))
        plain = lookup[name]["plain"]
        if name != main["name"]:
            # Display an equivalent zero branch in helper rules without asking
            # readers to compute a deliberately cancelling expression.
            text = re.sub(r"\ba\s*-\s*a\b", "0", text)
            plain = plain.replace("subtract a from a", "return zero")
        rules.append({"symbol": name, "text": text, "plain": plain,
                      "layer": lookup[name].get("layer", 0)})
    return rules


def build_regular(world_name: str) -> dict:
    data = json.loads((ROOT / f"{world_name}.json").read_text(encoding="utf-8"))
    world = prepare(world_name, data["seed"])
    by_name = {world.name(op): op for op in world.ordered}
    result = []
    by_row = {row["name"]: (index, row) for index, row in enumerate(data["operators"])}
    for name, idea in PLAN[world_name]:
        index, row = by_row[name]
        if _alias(row) or _cancelled_constant(row["definition"] + " " + row["plain"]):
            raise RuntimeError(f"{world_name}: puzzle rule {name} has a redundant operation")
        op = by_name[row["name"]]
        if any(item["rules"][0]["symbol"] == row["name"] for item in result):
            continue
        parsed = world.oracle._definition_of(op)
        mutations = [(kind, make) for kind, make in _mutations(parsed, random.Random(1000 + index))
                     if kind != "swap_operands"]
        if (world_name, name) == ("clock", "▽₅"):
            mutations.insert(0, ("symbol", lambda: op.definition.replace(
                "(- a) + (- a)", "(- a) + (- (a + 2))")))
        if (world_name, name) == ("integer", "▼₇"):
            mutations.insert(0, ("symbol", lambda: op.definition.replace(
                "(- a) * (- a)", "a * (- a)")))
        if (world_name, name) == ("successor", "♣₁₄"):
            mutations.insert(0, ("symbol", lambda: op.definition.replace(
                "(a ↓) ↑", "(a ↑) ↑")))
        if (world_name, name) == ("logic", "♡₇₂"):
            mutations.insert(0, ("symbol", lambda: op.definition.replace(
                "b <= 3", "b <= 5").replace("b >= - 3", "b >= - 5")))
        # Some worlds compose only unary atoms and have no editable literal or
        # binary call. Replacing one compatible atom is still a one-symbol edit.
        for source in world.tools.registry:
            if source.definition is not None or source.symbol not in op.definition:
                continue
            for target in world.tools.registry:
                if (target.definition is None and target.symbol != source.symbol
                        and target.parameter_types == source.parameter_types
                        and target.result_type == source.result_type):
                    mutations.append(("symbol", lambda s=source.symbol, t=target.symbol:
                                      op.definition.replace(s, t, 1)))
        if not mutations:
            continue
        def candidate_order(example):
            # Prefer a familiar musical register over MIDI 0 when both show
            # the same rule behavior.
            low_note = (world_name == "pitch" and any(
                arg["t"] == "note" and not 60 <= arg["v"] <= 84
                for arg in example["inputs"]))
            return (low_note, len(_key(example["inputs"])), example["expression"])

        preferred = PREFERRED.get((world_name, name))
        examples = list(row["examples"])
        args = TEACHING_INPUTS[world_name][len(result)]
        if world_name == "perm":
            from opulse.worlds.perm import Permutation

            args = tuple(Permutation(arg) if kind.startswith("perm") else arg
                         for arg, kind in zip(args, op.parameter_types))
        tree = Call(op, tuple(Number(arg) for arg in args))
        teaching = {"expression": world.show(world.tools.renderer.full(tree)),
                    "inputs": [world.enc(arg, kind) for arg, kind in zip(args, op.parameter_types)],
                    "output": world.enc(world.oracle.evaluate(op, args).value, op.result_type)}
        examples.insert(0, teaching)
        if (world_name, name) in PREFERRED_ARGS:
            args = PREFERRED_ARGS[(world_name, name)]
            tree = Call(op, tuple(Number(arg) for arg in args))
            examples.insert(0, {"expression": world.show(world.tools.renderer.full(tree)),
                                "inputs": [world.enc(arg, kind) for arg, kind in zip(args, op.parameter_types)],
                                "output": world.enc(world.oracle.evaluate(op, args).value, op.result_type)})
        candidates = sorted(examples, key=lambda example: (
            example is not teaching,
            example["expression"] != preferred if preferred else False, candidate_order(example)))
        chosen = None
        for edit_kind, make in mutations:
            from opulse.bench.families import common

            changed_text = make() if edit_kind == "symbol" else common.render(make(), world.tools.settings.symbols)
            if (world_name, name) == ("integer", "▼₇") and ("(- a) + (- a)" in changed_text or
                                                            "(- a) / (- a)" in changed_text):
                continue
            if (world_name, name) == ("successor", "♣₁₄") and "(a ↓) ↓" in changed_text:
                continue
            if (_cancelled_constant(changed_text) or re.search(
                    r"\(\s*-\s*([ab])\s*\)\s*-\s*\(\s*-\s*\1\s*\)", changed_text)):
                continue
            if world_name == "clock":
                from opulse.definition import ast

                changed_definition = world.tools.parser.parse(changed_text)
                if any(call.symbol == "-" and len(call.args) == 2 and call.args[0] == call.args[1]
                       for branch in changed_definition.branches
                       for call in ast.iter_applications(branch.expr)):
                    continue
            registry = OperatorRegistry(replace(member, definition=changed_text)
                                        if member.func_id == op.func_id else member
                                        for member in world.tools.registry)
            from opulse.verify import Oracle

            changed_oracle = Oracle(registry, world.tools.settings.symbols, world.oracle.semantics)
            changed_op = registry.get(op.func_id)
            for example in candidates:
                try:
                    # Published example inputs retain the world's exact encoding.
                    args = tuple(_decode(arg) for arg in example["inputs"])
                    before = world.oracle.evaluate(op, args).value
                    after = changed_oracle.evaluate(changed_op, args).value
                    if not _human_sized(world_name, args, before, after):
                        continue
                    undefined_edge = (world_name, name) in {
                        ("grid", "♦₅"), ("rel", "♠₅"), ("logic", "♡₇₂")}
                    if same_value(before, after) or after is NAN:
                        continue
                    if (before is NAN) != undefined_edge:
                        continue
                    answer_key = _key(world.enc(before, op.result_type))
                    # Boolean worlds have only two defined answers; this one
                    # cannot satisfy five distinct answer values.
                    if world_name != "logic" and answer_key in {_key(p["answer"]) for p in result}:
                        continue
                    tree = Call(op, tuple(Number(arg) for arg in args))
                    changed_tree = Call(changed_op, tuple(Number(arg) for arg in args))
                    trace = _trace(world.tools.registry, world.oracle, world.tools.settings, tree)
                    variant_trace = _trace(registry, changed_oracle, world.tools.settings, changed_tree)
                    if len(trace.steps) > 35 or len(variant_trace.steps) > 35:
                        continue
                    answer, alternate = world.enc(before, op.result_type), world.enc(after, op.result_type)
                    checked_steps = _steps(trace, world)
                    pool = [(row_step["value"],
                             f"This stops after {world.name(trace_step.operator) if trace_step.operator.definition else trace_step.operator.symbol}; the remaining operations still change it.")
                            for trace_step, row_step in zip(trace.steps[:-1], checked_steps[:-1])
                            if "value" in row_step]
                    pool += [(arg, "This leaves the input unchanged before the later operations finish.")
                             for arg in example["inputs"] if arg["t"] == answer["t"]]
                    pool += [(candidate["output"],
                              f"This is the result for the different input in {candidate['expression'][:70]}.")
                             for candidate in row["examples"] if candidate is not example]
                    pool += [(candidate["output"], f"This uses {other['name']} instead of {name}.")
                             for other in data["operators"][:10] if other["result_type"] == op.result_type
                             for candidate in other["examples"][:3]]
                    original_text = row["definition"]
                    edit_note = _edit_note(name, original_text, world.show(changed_text))
                    reverse_note = _edit_note(name, world.show(changed_text), original_text)
                    options, notes = _options(answer, alternate, pool, world, op.result_type, edit_note)
                    variant_options, variant_notes = _options(
                        alternate, answer, pool, world, op.result_type, reverse_note)
                    changed_plain = Describer(registry, world.tools.names,
                                              DefinitionParser(world.tools.settings.symbols, registry),
                                              world.spec.value_text).describe(changed_op).en
                    chosen = (example, trace, variant_trace, answer, alternate, options,
                              notes, variant_options, variant_notes, changed_text, changed_plain)
                    break
                except (ValueError, TypeError, OverflowError, RecursionError, KeyError):
                    continue
            if chosen:
                break
        if not chosen:
            raise RuntimeError(f"{world_name}: no checked candidate for {name}")
        example, trace, variant_trace, answer, alternate, options, notes, variant_options, variant_notes, changed_text, changed_plain = chosen
        if preferred and example["expression"] != preferred:
            raise RuntimeError(f"{world_name}: expected the teaching input {preferred} for {name}")
        rules = _rules(row, trace, data, world)
        why, why_zh = RATIONALES[world_name][len(result)]
        result.append({"id": f"{world_name}-c{len(result)+1}", "level": LEVELS[len(result)],
                       "idea": idea, "why": why, "why_zh": why_zh, "rules": rules,
                       "question": {"expression": example["expression"], "inputs": example["inputs"]},
                       "answer": answer, "options": options, "option_notes": notes,
                       "steps": checked_steps, "verified": True,
                       "variant": {"rule_index": 0, "before": row["definition"],
                                   "after": world.show(changed_text),
                                   "plain_after": changed_plain,
                                   "answer": alternate, "options": variant_options,
                                   "option_notes": variant_notes,
                                   "steps": _steps(variant_trace, world)}})
    if len(result) != 5:
        raise RuntimeError(f"{world_name}: found only {len(result)} checked puzzles")
    _check_rationales(world_name, result)
    result.append(build_induce_challenge(world_name, ROOT, _decode))
    return annotate({"schema": "opulse.world-challenge/1", "world": world_name,
                     "challenges": result}, world_name)


def _decode(value: dict):
    from opulse.worlds.action import decode as action_decode

    kind = value["t"]
    if kind in ("state", "colour", "direction"):
        return action_decode(value)
    if kind == "nan":
        return NAN
    if kind in ("int", "str", "bool", "entity"):
        return value["v"]
    if kind == "list":
        return tuple(_decode(item) for item in value["v"])
    if kind == "perm":
        from opulse.worlds.perm import Permutation

        return Permutation(value["v"])
    if kind == "melody":
        return tuple((item["p"], item["d"]) for item in value["v"])
    if kind == "grid":
        return tuple(tuple(row) if isinstance(row, list) else row for row in value["v"])
    if kind == "note":
        return value["v"]
    raise ValueError(f"unknown encoding {kind}")


def build_action() -> dict:
    from opulse.worlds.action import ACTION_RULES, check_steps, decode, describe_skill, encode, generate_skills, run_skill

    data = json.loads((ROOT / "action.json").read_text(encoding="utf-8"))
    skills = generate_skills(seed=data["seed"])
    library = {skill.name: skill for skill in skills}
    rows = []
    by_row = {row["name"]: row for row in data["operators"]}
    for name, idea in PLAN["action"]:
        row = by_row[name]
        skill = library[row["name"]]
        changes = []
        if skill.kind == "recursion":
            changes.append(replace(skill, bound=skill.bound + 1))
            changes += [replace(skill, first=atom) for atom in ACTION_RULES if atom != skill.first]
        elif skill.kind == "branch":
            changes += [replace(skill, first=atom) for atom in ACTION_RULES if atom != skill.first]
            changes.append(replace(skill, expected=not skill.expected) if isinstance(skill.expected, bool)
                           else replace(skill, first="turn_left"))
        else:
            changes += [replace(skill, first=atom) for atom in ACTION_RULES if atom != skill.first]
        found = None
        def action_preference(example):
            robot = example["inputs"][0]["v"]["robot"]
            if name == "□₂":
                return (robot["x"], robot["y"], robot["facing"]) != (3, 3, "E")
            if name == "▲₅":
                return (robot["x"], robot["y"], robot["facing"]) != (7, 7, "E")
            return False

        for example in sorted(row["examples"], key=action_preference):
            state = decode(example["inputs"][0])
            answer, steps = run_skill(skill, state, library)
            if (answer is NAN or encode(answer) == encode(state) or len(steps) > 40
                    or not check_steps(skill, state, library, steps)):
                continue
            for altered in changes:
                alternate_library = {**library, skill.name: altered}
                alternate, alternate_steps = run_skill(altered, state, alternate_library)
                if alternate is NAN or encode(answer) == encode(alternate) or len(alternate_steps) > 40:
                    continue
                if _key(encode(answer)) in {_key(p["answer"]) for p in rows}:
                    continue
                assert check_steps(altered, state, alternate_library, alternate_steps)
                found = (example, steps, alternate_steps, encode(answer), encode(alternate), altered)
                break
            if found:
                break
        if not found:
            continue
        example, steps, alternate_steps, answer, alternate, altered = found
        pool = [(step["value"], "This leaves the robot at its starting state before the skill acts."
                 if step["note"].startswith("Unfold") else
                 f"This stops after '{step['note']}' before the skill finishes.")
                for step in steps[:-1]]
        pool += [(other["output"], "This uses a different starting robot position or direction.")
                for other in row["examples"] if other["output"]["t"] == "state"]
        stub = type("W", (), {"spec": type("S", (), {"world": "action"})()})()
        edit_note = _edit_note(skill.name, skill.definition(), altered.definition())
        reverse_note = _edit_note(skill.name, altered.definition(), skill.definition())
        opts, notes = _options(answer, alternate, pool, stub, "state", edit_note)
        variant_opts, variant_notes = _options(alternate, answer, pool, stub, "state", reverse_note)
        rule_names = [skill.name]
        for ref in (skill.first, skill.second, skill.guard):
            if ref and ref not in rule_names:
                rule_names.append(ref)
        rules = []
        for name in rule_names:
            if name in library:
                source = next(item for item in data["operators"] if item["name"] == name)
                rules.append({"symbol": name, "text": source["definition"], "plain": source["plain"],
                              "layer": source["layer"]})
            else:
                source = next(item for item in data["atoms"] if item["name"] == name)
                rules.append({"symbol": source["symbol"], "text": source["rule"],
                              "plain": source["plain"], "layer": 0})
        why, why_zh = RATIONALES["action"][len(rows)]
        rows.append({"id": f"action-c{len(rows)+1}", "level": LEVELS[len(rows)],
                     "idea": idea, "why": why, "why_zh": why_zh, "rules": rules,
                     "question": {"expression": example["expression"], "inputs": example["inputs"]},
                     "answer": answer, "options": opts, "option_notes": notes,
                     "steps": [{"expr": step["expression"], "rule": step["note"], "value": step["value"]}
                               for step in steps], "verified": True,
                     "variant": {"rule_index": 0, "before": skill.definition(),
                                 "after": altered.definition(),
                                 "plain_after": describe_skill(altered)[0],
                                 "answer": alternate, "options": variant_opts,
                                 "option_notes": variant_notes,
                                 "steps": [{"expr": step["expression"], "rule": step["note"], "value": step["value"]}
                                           for step in alternate_steps]}})
    if len(rows) != 5:
        raise RuntimeError(f"action: found only {len(rows)} checked puzzles")
    _check_rationales("action", rows)
    rows.append(build_induce_challenge("action", ROOT, _decode))
    return annotate({"schema": "opulse.world-challenge/1", "world": "action",
                     "challenges": rows}, "action")


def main(names: list[str]) -> None:
    for name in names or WORLDS:
        if name not in WORLDS:
            raise ValueError(name)
        data = build_action() if name == "action" else build_regular(name)
        path = ROOT / name / "challenge.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(name, len(data["challenges"]), flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
