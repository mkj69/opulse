"""Recheck exported task claims with the reference interpreters."""

import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from opulse.core.registry import OperatorRegistry
from opulse.core.semantics import NAN
from opulse.core.types import same_value
from opulse.expression.nodes import from_dict
from opulse.solver.holes import HoleSolver
from opulse.verify import Oracle
from opulse.worlds import showcase_tasks as tasks
from opulse.worlds.action import decode as action_decode
from opulse.worlds.action import encode as action_encode
from opulse.worlds.action import generate_skills, run_skill
from opulse.worlds.present import alias

PUBLISHED = Path(__file__).resolve().parents[1] / "docs/assets/data/worlds"


@pytest.mark.parametrize("name", ["successor", "integer", "clock", "bits", "strings", "lists",
                                  "logic", "perm", "rel", "grid", "pitch", "action"])
def test_published_expressions_are_defined(name):
    data = json.loads((PUBLISHED / name / "tasks.json").read_text(encoding="utf-8"))
    assert data["expressions"]
    assert all(item["value"]["t"] != "nan" for item in data["expressions"])


def _decode(value):
    if value is None or value["t"] == "nan":
        return NAN
    if value["t"] == "list":
        return tuple(_decode(item) for item in value["v"])
    return value["v"]


def _fixture(world, path):
    shutil.copyfile(PUBLISHED / f"{world}.json", path / f"{world}.json")
    return tasks.export_tasks(world, path)


@pytest.mark.parametrize("name", ["integer", "clock", "strings"])
def test_integer_and_typed_tasks(tmp_path, name):
    data = _fixture(name, tmp_path)
    world = tasks.prepare(name)
    by_name = {world.name(op): op for op in world.ordered}
    folder = tmp_path / name / "tasks"
    assert data["expressions"] and data["holes"]
    if name == "clock":
        assert world.encoder is None

    for item in data["expressions"]:
        reverse = {shown: symbol for symbol, shown in world.tools.names.items()}
        tree = from_dict(tasks._rename_tree(item["tree"], reverse), world.tools.registry)
        value = world.value(tree)
        assert world.enc(value, tree.operator.result_type) == item["value"]
        source = alias(item["expression"], reverse)
        parsed = world.tools.parser.parse_expr(source, expression_mode=True)
        assert world.enc(world.oracle.evaluate_expr(parsed, {}).value, tree.operator.result_type) == item["value"]
        granular = json.loads((folder / f"{item['id']}.json").read_text())
        assert len(granular) == 3
        for steps in granular:
            assert steps and steps[-1]["value"] == item["value"]

    for item in data["holes"]:
        reverse = {shown: symbol for symbol, shown in world.tools.names.items()}
        tree = from_dict(tasks._rename_tree(item["tree"], reverse), world.tools.registry)
        target = _decode(item["target"])
        detail = json.loads((folder / f"{item['id']}.json").read_text())
        candidates = detail["candidates"]
        hits = []
        for raw_x, raw_value in candidates:
            x = _decode(raw_x)
            try:
                value = world.value(tree, {"x": x})
            except Exception:  # noqa: BLE001
                value = NAN
            if raw_value is None:
                assert value is NAN
            else:
                assert world.enc(value, tree.operator.result_type) == raw_value
            if value is not NAN and same_value(value, target):
                hits.append(raw_x)
        if item["check"]["method"] == "z3":
            found = HoleSolver(world.encoder, world.oracle).solve(tree, target)
            assert found.complete
            assert [world.enc(x, "int") for x in found.values] == item["solutions"]
        else:
            assert hits == item["solutions"]
            if item["check"]["method"] == "range":
                lo, hi = item["check"]["range"]
                assert [_decode(row[0]) for row in candidates] == list(range(lo, hi + 1))

    for row in data["laws"]["rows"]:
        op = by_name[row["name"]]
        for law, cell in row["cells"].items():
            if "counterexample" not in cell:
                continue
            counter = cell["counterexample"]
            point = tuple(_decode(item["value"]) for item in counter["inputs"])
            element = _decode(cell["element"]) if "element" in cell else None
            left, right = tasks._sides(world, op, law, point, element)
            assert not same_value(left, right)
            assert world.enc(left, op.result_type) == counter["left_value"]
            assert world.enc(right, op.result_type) == counter["right_value"]

    for item in data["equivalence"]:
        if "counterexample" not in item:
            continue
        counter = item["counterexample"]
        point = tuple(_decode(cell["value"]) for cell in counter["inputs"])
        if item["kind"] == "operators":
            first, second = (by_name[row["name"]] for row in item["definitions"])
            left = world.oracle.evaluate(first, point).value
            right = world.oracle.evaluate(second, point).value
            assert world.enc(left, first.result_type) == counter["left_value"]
            assert world.enc(right, second.result_type) == counter["right_value"]
            assert not same_value(left, right)

    for item in data["edit"]:
        low = by_name[item["operator"]]
        reverse = {shown: symbol for symbol, shown in world.tools.names.items()}
        definition = alias(item["after"], reverse)
        registry = OperatorRegistry(replace(op, definition=definition) if op.func_id == low.func_id else op
                                    for op in world.tools.registry)
        edited = Oracle(registry, world.tools.settings.symbols, world.oracle.semantics)
        for row in item["rows"]:
            op = by_name[row["name"]]
            # Each row is a concrete call. Evaluate its argument expressions.
            source = alias(row["expression"], reverse)
            parsed = world.tools.parser.parse_expr(source, expression_mode=True)
            from opulse.expression.nodes import from_ast

            tree = from_ast(parsed, world.tools.registry)
            values = tuple(world.value(arg) for arg in tree.args)
            before = world.oracle.evaluate(op, values).value
            after = edited.evaluate(registry.get(op.func_id), values).value
            assert world.enc(before, op.result_type) == row["before"]
            assert world.enc(after, op.result_type) == row["after"]


def test_action_tasks(tmp_path):
    data = _fixture("action", tmp_path)
    skills = generate_skills()
    library = {skill.name: skill for skill in skills}
    folder = tmp_path / "action" / "tasks"
    assert data["expressions"] and data["holes"] and data["edit"]

    for item in data["expressions"]:
        state = action_decode(item["first"])
        for name in item["operators"]:
            state = run_skill(name, state, library, unfold=False)[0]
        assert action_encode(state) == item["value"]
        granular = json.loads((folder / f"{item['id']}.json").read_text())
        assert len(granular) == 3
        for steps in granular:
            assert steps and steps[-1]["value"] == item["value"]

    for item in data["holes"]:
        detail = json.loads((folder / f"{item['id']}.json").read_text())
        hits = []
        for raw_x, raw_value in detail["candidates"]:
            if item["x_kind"] == "skill":
                value = run_skill(raw_x["v"], action_decode(item["start"]), library, unfold=False)[0]
            else:
                name = item["expression"].split("(", 1)[0]
                value = run_skill(name, action_decode(raw_x), library, unfold=False)[0]
            assert action_encode(value) == raw_value
            if raw_value == item["target"]:
                hits.append(raw_x)
        assert hits == item["solutions"]

    for row in data["laws"]["rows"]:
        for law, cell in row["cells"].items():
            if "counterexample" not in cell:
                continue
            counter = cell["counterexample"]
            state = action_decode(counter["inputs"][0]["value"])
            once = run_skill(row["name"], state, library, unfold=False)[0] if row["name"] in library else None
            if once is None:
                from opulse.worlds.action import apply_atom

                once = apply_atom(row["name"], state)
                twice = apply_atom(row["name"], once) if once is not NAN else NAN
            else:
                twice = run_skill(row["name"], once, library, unfold=False)[0] if once is not NAN else NAN
            right = once if law == "idempotent" else state
            assert action_encode(twice) == counter["left_value"]
            assert action_encode(right) == counter["right_value"]
            assert counter["left_value"] != counter["right_value"]

    for item in data["equivalence"]:
        if "counterexample" not in item:
            continue
        state = action_decode(item["counterexample"]["inputs"][0]["value"])
        names = [part["name"] for part in item["definitions"]]
        left, right = (run_skill(name, state, library, unfold=False)[0] for name in names)
        assert action_encode(left) == item["counterexample"]["left_value"]
        assert action_encode(right) == item["counterexample"]["right_value"]
        assert not same_value(left, right)

    for item in data["edit"]:
        from opulse.worlds.action import Skill

        changed = Skill.from_record({**library[item["operator"]].record()})
        assert changed.definition() == item["before"]
        edited_skill = next(skill for skill in [replace(changed, first=changed.second, second=changed.first),
                                                replace(changed, bound=changed.bound + 2),
                                                replace(changed, expected=(not changed.expected)
                                                        if isinstance(changed.expected, bool) else changed.expected,
                                                        first=changed.second, second=changed.first)]
                            if skill.definition() == item["after"])
        edited = {**library, item["operator"]: edited_skill}
        for row in item["rows"]:
            state = action_decode(row["input"])
            before = run_skill(row["name"], state, library, unfold=False)[0]
            after = run_skill(row["name"], state, edited, unfold=False)[0]
            assert action_encode(before) == row["before"]
            assert action_encode(after) == row["after"]


def test_operator_list_must_match_browser(tmp_path):
    for name in ("integer", "action"):
        data = json.loads((PUBLISHED / f"{name}.json").read_text())
        data["operators"][0]["definition"] += " changed"
        (tmp_path / f"{name}.json").write_text(json.dumps(data))
        with pytest.raises(ValueError, match="operators that differ"):
            tasks.export_tasks(name, tmp_path)
        assert not (tmp_path / name / "tasks.json").exists()
