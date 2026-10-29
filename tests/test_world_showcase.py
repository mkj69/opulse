"""The published world data stays reproducible and independently loadable."""

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from world_contract import check_showcase

from opulse.worlds.showcase import _inert_atoms, export_world_showcase

PUBLISHED = Path(__file__).resolve().parents[1] / "docs/assets/data/worlds"
WORLDS = ("successor", "integer", "clock", "bits", "strings", "lists", "logic", "perm", "rel", "grid", "pitch")


def test_inert_atom_count_uses_the_atom_input_not_the_final_result():
    atom = SimpleNamespace(definition=None)
    helper = SimpleNamespace(definition="a")
    def step(operator, before, after):
        return SimpleNamespace(kind="eval", operator=operator,
                               before=SimpleNamespace(args=(SimpleNamespace(value=before),)), output=after)

    trace = SimpleNamespace(steps=[step(atom, "Ab", "Ab"), step(atom, "Ab", "ab"),
                                   step(helper, "ab", "ab")])
    assert _inert_atoms(trace) == 1


def test_lowercase_after_append_changes_the_first_example():
    data = json.loads((PUBLISHED / "strings.json").read_text(encoding="utf-8"))
    row = next(row for row in data["operators"]
               if row["plain"] == "Append b to a, then turn it into lowercase.")
    assert any(value["t"] == "str" and any(char.isupper() for char in value["v"])
               for value in row["examples"][0]["inputs"])
    index = data["operators"].index(row)
    steps = json.loads((PUBLISHED / "strings" / "steps" / str(data["seed"]) /
                        f"{index}.json").read_text(encoding="utf-8"))[0]
    assert steps[1]["value"] != steps[2]["value"]


def test_world_challenge_tab_is_wired_after_more():
    assets = PUBLISHED.parent.parent
    core = (assets / "js/worlds/core.js").read_text(encoding="utf-8")
    tasks = (assets / "js/worlds/tasks.js").read_text(encoding="utf-8")
    challenge = (assets / "js/worlds/challenge.js").read_text(encoding="utf-8")
    css = (assets / "css/worlds.css").read_text(encoding="utf-8")
    assert 'loadScript("tasks").then(() => loadScript("challenge"))' in core
    assert 'fetchJSON(data.world + "/challenge.json")' in core
    assert 'tab.available(data)' in core
    assert 'id: "more"' in tasks and 'id: "challenge"' in challenge
    assert 'available: data => !!data.challenge' in challenge
    for feature in ("owc-picker", "owc-rule", "owc-option", "owc-step", "owc-variant",
                    "localStorage", "renderStep", "motionReduced", "aria-label"):
        assert feature in challenge
    assert 'why.textContent = textFor(puzzle, "why")' in challenge
    assert 'why.hidden = false' in challenge
    assert 'card.append(first, why, variantStage)' in challenge
    assert "@media (max-width: 700px)" in css
    assert ".owc-options { grid-template-columns: repeat(2, minmax(0, 1fr)); }" in css
    chinese = PUBLISHED.parents[3] / "docs_zh/assets"
    if chinese.is_dir():  # the public export has no Chinese site
        for path in ("js/worlds/core.js", "js/worlds/tasks.js", "js/worlds/challenge.js", "css/worlds.css"):
            assert (assets / path).read_bytes() == (chinese / path).read_bytes()


@pytest.mark.parametrize("world", (*WORLDS, "action"))
def test_world_challenge_starter_records(world):
    path = PUBLISHED / world / "challenge.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["schema"] == "opulse.world-challenge/1" and data["world"] == world
    mirror = PUBLISHED.parents[3] / "docs_zh/assets/data/worlds" / world / "challenge.json"
    if mirror.parents[3].is_dir():  # the public export has no Chinese site
        assert mirror.read_bytes() == path.read_bytes()
    assert len(data["challenges"]) == 6
    assert [puzzle["id"] for puzzle in data["challenges"]] == [f"{world}-c{i}" for i in range(1, 7)]
    for puzzle in data["challenges"][:5]:
        assert puzzle["id"].startswith(world + "-c") and puzzle["level"] in {"easy", "medium", "hard"}
        assert puzzle["idea"] and puzzle["why"] and puzzle["why_zh"]
        assert puzzle["rules"] and puzzle["question"]["inputs"]
        assert len(puzzle["options"]) in (3, 4)
        assert len(puzzle["option_notes"]) == len(puzzle["options"])
        assert sum(value == puzzle["answer"] for value in puzzle["options"]) == 1
        assert puzzle["steps"] and all(step["expr"] and step["rule"] for step in puzzle["steps"])
        assert puzzle["steps"][-1]["value"] == puzzle["answer"]
        variant = puzzle["variant"]
        assert puzzle["rules"][variant["rule_index"]]["text"] == variant["before"] != variant["after"]
        assert len(variant["options"]) in (3, 4)
        assert sum(value == variant["answer"] for value in variant["options"]) == 1
        assert variant["steps"] and all(step["expr"] and step["rule"] for step in variant["steps"])
        assert variant["steps"][-1]["value"] == variant["answer"]
    induced = data["challenges"][5]
    assert induced["kind"] == "induce" and induced["idea"] == "induction"
    assert induced["level"] in {"easy", "medium", "hard"}
    assert induced["why"] and induced["why_zh"]
    assert len(induced["examples"]) >= 3
    assert all(example["inputs"] and "output" in example for example in induced["examples"])
    assert induced["query"]["inputs"]
    assert len(induced["query"]["options"]) in (3, 4)
    assert sum(option == induced["answer"] for option in induced["query"]["options"]) == 1
    assert induced["reference_definition"]["text"]
    assert induced["reference_definition"]["plain"] and induced["reference_definition"]["plain_zh"]
    assert induced["identifiable"]["checked_against"] >= 1


def _check_local_names(data):
    names = [row["name"] for row in data["operators"]]
    assert len(names) == len(set(names))
    digits = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
    assert [int(re.search(r"[₀-₉]+$", name).group().translate(digits)) for name in names] == list(
        range(1, len(names) + 1))
    allowed = set(names) | {atom["symbol"] for atom in data["atoms"]}
    assert all(row["interest"]["nearest"] in allowed | {None} for row in data["operators"])


def test_clock_showcase_is_reproducible(tmp_path):
    first = export_world_showcase("clock", tmp_path / "one" / "clock.json")
    second = export_world_showcase("clock", tmp_path / "two" / "clock.json")
    assert (tmp_path / "one" / "clock.json").read_bytes() == (tmp_path / "two" / "clock.json").read_bytes()
    assert first["modulus"] == 12 and first == second
    check_showcase(first, tmp_path / "one")
    published = json.loads((PUBLISHED / "clock.json").read_text())
    assert {key: value for key, value in first.items() if key not in {"metrics", "seeds"}} == {
        key: value for key, value in published.items() if key not in {"metrics", "seeds"}}
    assert first["metrics"]["behaviours"] == published["metrics"]["behaviours"]


@pytest.mark.parametrize("world", WORLDS)
def test_published_showcases_keep_the_contract(world):
    data = json.loads((PUBLISHED / f"{world}.json").read_text(encoding="utf-8"))
    check_showcase(data, PUBLISHED)
    _check_local_names(data)
    assert len(data["seeds"]) == 3
    for seed in data["seeds"][1:]:
        other = json.loads((PUBLISHED / seed["file"]).read_text(encoding="utf-8"))
        assert other["seed"] == seed["seed"] and other["operators"] != data["operators"]
        check_showcase(other, PUBLISHED)
        _check_local_names(other)
    total = sum(path.stat().st_size for path in (PUBLISHED / world).rglob("*.json"))
    assert total + (PUBLISHED / f"{world}.json").stat().st_size < 5_000_000


@pytest.mark.parametrize("world", (*WORLDS, "action"))
def test_curated_operators_and_complete_atoms(world):
    data = json.loads((PUBLISHED / f"{world}.json").read_text(encoding="utf-8"))
    grown = {row["name"]: row for row in data["operators"]}
    assert all(row.get("interest") is not None for row in grown.values())
    curated = data["curated"]
    assert 8 <= len(curated) <= 24
    assert len(curated) == len(set(curated)) and set(curated) <= grown.keys()
    assert {grown[name]["kind"] for name in curated} == {"composition", "branching", "recursion"}
    assert sum(data["curation_rejected"].values()) + len(curated) + data["curation_not_selected"] == len(grown)
    for name in curated:
        row = grown[name]
        assert row["plain"] and len(row["plain"].split()) <= 22
        assert any(example["output"]["t"] != "nan" for example in row["examples"])
        assert row["interest"] is not None
        if world != "action":
            from opulse.worlds.curation import _cancelled_constant, _contrived_plain

            assert not _cancelled_constant(row["definition"] + " " + row["plain"])
            assert not _contrived_plain(world, row)
        else:
            assert any(example["output"] != example["inputs"][0] for example in row["examples"])
    assert data["atoms"]
    # Several worlds deliberately overload a glyph at different arities.
    assert len({(atom["symbol"], atom["arity"], atom["signature"])
                for atom in data["atoms"]}) == len(data["atoms"])
    if world == "action":
        assert len(data["atoms"]) == 12  # six actions and six observations
    for atom in data["atoms"]:
        assert all(key in atom for key in ("symbol", "name", "arity", "signature", "plain",
                                          "plain_zh", "example"))
        assert atom["arity"] == len(atom["example"]["inputs"])
        assert atom["example"]["output"]
        assert atom["example"]["output"]["t"] != "nan"
        if world == "perm":
            for value in [*atom["example"]["inputs"], atom["example"]["output"]]:
                if value["t"] == "perm":
                    assert len(value["v"]) == 5


@pytest.mark.parametrize("world", WORLDS)
def test_curated_behaviours_are_varied_and_use_their_inputs(world):
    from collections import Counter

    from opulse.worlds.curation import _numeric_shape, _points_by_signature, _sample, _uses_every_argument
    from opulse.worlds.showcase_tasks import prepare

    data = json.loads((PUBLISHED / f"{world}.json").read_text(encoding="utf-8"))
    built = prepare(world, data["seed"])
    assert {(atom["symbol"], atom["arity"]) for atom in data["atoms"]} == {
        (op.symbol, op.n_ary) for op in built.tools.registry if op.definition is None}
    by_name = {built.name(op): op for op in built.ordered}
    groups = _points_by_signature([op for op in built.tools.registry if op.definition is None] +
                                  built.ordered, built.spec, built.tools)
    tables = {}
    shapes = {}
    for atom in built.tools.registry:
        if atom.definition is None:
            tables.setdefault((tuple(atom.parameter_types), atom.result_type), set()).add(
                _sample(atom, built.spec, built.oracle, groups[tuple(atom.parameter_types)])[1])
    for name in data["curated"]:
        op = by_name[name]
        points, outputs = _sample(op, built.spec, built.oracle, groups[tuple(op.parameter_types)])
        counts = Counter(outputs)
        assert len(counts) > 1 and counts["NaN"] < len(outputs)
        assert len(outputs) < 8 or max(counts.values()) / len(outputs) < 0.85
        assert _uses_every_argument(points, outputs, op.n_ary)
        key = (tuple(op.parameter_types), op.result_type)
        assert outputs not in tables.setdefault(key, set())
        tables[key].add(outputs)
        shape = _numeric_shape(outputs)
        if shape is not None:
            assert shape not in shapes.setdefault(key, set())
            shapes[key].add(shape)
