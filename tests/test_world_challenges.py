"""Published Challenge data is complete and independently regenerated with checked traces."""

import json
import re
from collections import Counter
from pathlib import Path

import pytest

from opulse.worlds.curation import _cancelled_constant
from tools.world_challenge_induce import _quality
from tools.world_challenges import IDEAS, PLAN, WORLDS, build_action, build_regular

ROOT = Path(__file__).resolve().parents[1] / "docs/assets/data/worlds"


def _key(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


@pytest.mark.parametrize("world", WORLDS)
def test_published_challenges_have_playable_contract(world):
    data = json.loads((ROOT / world / "challenge.json").read_text(encoding="utf-8"))
    assert data["schema"] == "opulse.world-challenge/1"
    assert data["world"] == world
    assert len(data["challenges"]) == 6
    puzzles = data["challenges"][:5]
    assert Counter(p["level"] for p in puzzles) == {"easy": 2, "medium": 2, "hard": 1}
    assert [p["id"] for p in puzzles] == [f"{world}-c{i}" for i in range(1, 6)]
    assert [(p["rules"][0]["symbol"], p["idea"]) for p in puzzles] == list(PLAN[world])
    assert all(p["idea"] in IDEAS for p in puzzles)
    assert len({p["idea"] for p in puzzles}) == 5
    assert len({p["rules"][0]["symbol"] for p in puzzles}) == 5
    assert len({p["why"] for p in puzzles}) == 5
    assert len({p["why_zh"] for p in puzzles}) == 5
    # Every Logic operator returns bool: five distinct value answers are
    # mathematically impossible there, but all other worlds must have them.
    if world == "logic":
        assert len({_key(p["answer"]) for p in puzzles}) == 3
        assert {p["answer"]["t"] for p in puzzles} == {"bool", "nan"}
    else:
        assert len({_key(p["answer"]) for p in puzzles}) == 5
    assert len({(p["rules"][0]["symbol"], p["question"]["expression"]) for p in puzzles}) == 5
    for puzzle in puzzles:
        assert puzzle["verified"] is True
        assert puzzle["question"]["expression"] and puzzle["question"]["inputs"]
        assert isinstance(puzzle["why"], str) and puzzle["why"].endswith(".")
        assert isinstance(puzzle["why_zh"], str) and any("\u4e00" <= c <= "\u9fff" for c in puzzle["why_zh"])
        assert puzzle["why_zh"].endswith("。")
        assert len(puzzle["why"]) >= 65
        assert all(set(rule) == {"symbol", "text", "plain", "layer"} and rule["plain"]
                   for rule in puzzle["rules"])
        assert all(not _cancelled_constant(rule["text"]) for rule in puzzle["rules"])
        for candidate in (puzzle, puzzle["variant"]):
            assert 3 <= len(candidate["options"]) <= 4
            assert len({_key(x) for x in candidate["options"]}) == len(candidate["options"])
            assert sum(_key(x) == _key(candidate["answer"]) for x in candidate["options"]) == 1
            answer_types = {puzzle["answer"]["t"], puzzle["variant"]["answer"]["t"], "nan"}
            assert all(x["t"] in answer_types for x in candidate["options"])
            assert candidate["steps"] and candidate["steps"][-1].get("value") == candidate["answer"]
            assert all({"expr", "rule"} <= set(step) <=
                       ({"expr", "rule", "value"} if world == "action" else
                        {"expr", "rule", "rule_zh", "kind", "focus", "gate", "value"})
                       and step["expr"] and step["rule"] for step in candidate["steps"])
            if world != "action":
                assert all(step["focus"] and step["gate"] and step["rule_zh"]
                           for step in candidate["steps"])
            assert len(candidate["options"]) == len(candidate["option_notes"])
            assert all(bool(note) == (option != candidate["answer"])
                       for option, note in zip(candidate["options"], candidate["option_notes"]))
            assert all("highlighted rule edit" not in note for note in candidate["option_notes"])
        assert len(puzzle["options"]) == len(puzzle["option_notes"])
        assert all(bool(note) == (option != puzzle["answer"])
                   for option, note in zip(puzzle["options"], puzzle["option_notes"]))
        assert all(len(note) >= 25 for note in puzzle["option_notes"] if note)
        variant = puzzle["variant"]
        assert variant["rule_index"] == 0
        assert variant["before"] == puzzle["rules"][0]["text"]
        assert variant["before"] != variant["after"] and variant["plain_after"]
        assert not _cancelled_constant(variant["after"])
        assert not re.search(r"\(\s*-\s*([ab])\s*\)\s*-\s*\(\s*-\s*\1\s*\)", variant["after"])
        assert _key(variant["answer"]) != _key(puzzle["answer"])
        values = [puzzle["answer"], variant["answer"], *puzzle["options"], *variant["options"]]
        assert all(value["t"] != "int" or abs(value["v"]) <= 100 for value in values)
        alternate = puzzle["options"].index(variant["answer"])
        assert puzzle["rules"][0]["symbol"] in puzzle["option_notes"][alternate]
        if world == "grid":
            assert all("[[" not in step["expr"] and "[[" not in step["rule"]
                       for candidate in (puzzle, variant) for step in candidate["steps"])
        if world == "pitch":
            assert all("[[" not in step["expr"] and "[[" not in step["rule"]
                       for candidate in (puzzle, variant) for step in candidate["steps"])


def test_no_worlds_repeat_the_same_main_operator_and_question():
    puzzles = [puzzle for world in WORLDS
               for puzzle in json.loads((ROOT / world / "challenge.json").read_text(encoding="utf-8"))["challenges"][:5]]
    pairs = [(puzzle["rules"][0]["symbol"], puzzle["question"]["expression"])
             for puzzle in puzzles]
    assert len(pairs) == len(set(pairs))
    assert len({puzzle["why"] for puzzle in puzzles}) == 60
    assert len({puzzle["why_zh"] for puzzle in puzzles}) == 60


@pytest.mark.parametrize("world", WORLDS)
def test_induce_challenge_has_representative_checked_pairs(world):
    data = json.loads((ROOT / world / "challenge.json").read_text(encoding="utf-8"))
    puzzle = data["challenges"][5]
    assert puzzle["id"] == f"{world}-c6"
    assert puzzle["kind"] == "induce" and puzzle["idea"] == "induction"
    assert len(puzzle["examples"]) in (3, 4)
    assert all(pair["inputs"] and pair["output"]["t"] != "nan" for pair in puzzle["examples"])
    assert len({_key(pair["output"]) for pair in puzzle["examples"]}) >= 2
    assert puzzle["query"]["inputs"]
    assert 3 <= len(puzzle["query"]["options"]) <= 4
    assert len({_key(option) for option in puzzle["query"]["options"]}) == len(puzzle["query"]["options"])
    assert sum(option == puzzle["answer"] for option in puzzle["query"]["options"]) == 1
    assert puzzle["reference_definition"]["text"] and puzzle["reference_definition"]["plain"]
    assert puzzle["reference_definition"]["plain_zh"] and puzzle["why"] and puzzle["why_zh"]
    assert puzzle["identifiable"]["checked_against"] > 0
    if world == "grid":
        assert all(pair["inputs"][0]["t"] == pair["output"]["t"] == "grid" for pair in puzzle["examples"])
    if world == "pitch":
        assert all(pair["output"]["t"] == "melody" for pair in puzzle["examples"])
    if world == "perm":
        assert all(pair["output"]["t"] == "perm" for pair in puzzle["examples"])


@pytest.mark.parametrize("definition", [
    "a ◇ b = { a * 1 + b }", "a ◇ b = { a + 0 + b }",
    "a ◇ b = { a - 0 + b }", "a ◇ b = { a / 1 + b }",
    "a ◇ b = { (a - a) + b }", "a ◇ b = { 0 + a + b }",
    "a ◇ b = { - (- a) + b }", "a ◇ b = { a + 2 }",
    "a ◇ b = { a + b }",
])
def test_induce_filter_rejects_trivial_or_unused_rules(definition):
    with pytest.raises(ValueError):
        _quality(definition, [(2, 3), (4, 5)], [5, 9], "integer")


def test_world_specific_boundaries_are_real():
    def puzzles(world):
        return json.loads((ROOT / world / "challenge.json").read_text(encoding="utf-8"))["challenges"]

    assert puzzles("clock")[1]["answer"] == {"t": "int", "v": 8}  # -4 wraps on the 12-position dial
    assert puzzles("strings")[3]["question"]["inputs"][1] == {"t": "str", "v": ""}
    assert puzzles("lists")[3]["question"]["inputs"][0] == {"t": "list", "v": []}
    for world in ("logic", "rel"):
        assert puzzles(world)[3]["idea"] == "edge"
        assert puzzles(world)[3]["answer"] == {"t": "nan"}
    assert puzzles("grid")[3]["idea"] == "symmetry"
    assert puzzles("grid")[3]["answer"] == {"t": "grid", "v": [[1, 3], [2, 0]]}
    action = puzzles("action")
    assert "front_water = True" in action[2]["steps"][1]["rule"]
    assert "front_wall = True" in action[3]["steps"][1]["rule"]
    assert action[2]["answer"] != action[3]["answer"]


@pytest.mark.parametrize("world", WORLDS)
def test_published_challenges_replay_checked_generator(world):
    """The generator calls verify_trace (or action.check_steps) for both derivations."""
    published = json.loads((ROOT / world / "challenge.json").read_text(encoding="utf-8"))
    rebuilt = build_action() if world == "action" else build_regular(world)
    assert rebuilt == published
