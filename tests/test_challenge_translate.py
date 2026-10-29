"""Published cross-world translate puzzles and their seeded oracle checks."""

import json
from collections import Counter

from opulse.core.presets import register_preset
from opulse.core.registry import OperatorRegistry
from opulse.core.semantics import NAN
from opulse.verify import Oracle
from opulse.worlds.perm import Permutation, register_perm
from tools.challenge_translate import (CASES, OUT, SEED, _atoms, _encode, _expr,
                                       _misreadings, build)


def _key(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def test_translate_contract_and_unique_answers():
    data = json.loads(OUT.read_text(encoding="utf-8"))
    assert set(data) == {"schema", "mode", "group", "seed", "challenges"}
    assert (data["schema"], data["mode"], data["group"], data["seed"]) == (
        "opulse.challenge-mode/1", "translate", "induce", SEED)
    puzzles = data["challenges"]
    assert len(puzzles) == 12
    assert Counter(row["level"] for row in puzzles) == {"easy": 4, "medium": 5, "hard": 3}
    assert [row["id"] for row in puzzles] == [f"translate-{i:02d}" for i in range(1, 13)]
    assert len({row["skeleton"] for row in puzzles}) == 12
    assert len({_key(row["target"]["answer"]) for row in puzzles}) == 12
    assert len({_key(row["rules"]) for row in puzzles}) == 12
    for row in puzzles:
        assert set(row) == {"id", "level", "why", "why_zh", "rules", "source_world",
                            "target_world", "skeleton", "source", "target", "verified", "atoms"}
        assert row["verified"] is True
        assert row["why"].endswith(".") and row["why_zh"].endswith("。")
        assert row["rules"] and all(set(rule) == {"symbol", "text", "hint"}
                                    and all(rule.values()) for rule in row["rules"])
        assert set(row["source"]) == {"expression", "inputs", "output"}
        assert set(row["target"]) == {"expression", "inputs", "answer", "options"}
        assert len(row["source"]["inputs"]) == len(row["target"]["inputs"]) == 2
        assert len(row["target"]["options"]) in (3, 4)
        options = [_key(value) for value in row["target"]["options"]]
        assert len(options) == len(set(options))
        assert options.count(_key(row["target"]["answer"])) == 1
        for side, world in (("source", row["source_world"]), ("target", row["target_world"])):
            for value in (*row[side]["inputs"],
                          row[side]["output" if side == "source" else "answer"]):
                assert value["t"] in ({"str", "int"} if world in ("strings", "clock") else
                                      {"list", "int"} if world == "lists" else {"perm", "int"})


def test_translate_regeneration_checks_interpreter_and_skeleton():
    # build() reconstructs every target from the exported source skeleton,
    # checks both structural hashes, and evaluates both answers with Oracle.
    expected = json.dumps(build(), ensure_ascii=False, indent=2) + "\n"
    assert OUT.read_text(encoding="utf-8") == expected


def _decode(value):
    if value["t"] == "list":
        return tuple(_decode(item) for item in value["v"])
    if value["t"] == "perm":
        return Permutation(value["v"])
    return value["v"]


def test_every_distractor_is_a_local_misreading():
    register_preset("strings")
    register_preset("lists")
    register_perm(5)
    rows = json.loads(OUT.read_text(encoding="utf-8"))["challenges"]
    for row, case in zip(rows, CASES, strict=True):
        target, tree = row["target_world"], case[2]
        registry = OperatorRegistry(_atoms(target, tree))
        oracle = Oracle(registry)
        args = tuple(_decode(value) for value in row["target"]["inputs"])
        foils = set()
        for changed in _misreadings(tree):
            value = oracle.evaluate_expr(_expr(changed, registry, target),
                                         {"a": args[0], "b": args[1]}).value
            if value is not NAN:
                foils.add(_key(_encode(target, value)))
        answer = _key(row["target"]["answer"])
        assert all(_key(value) in foils for value in row["target"]["options"]
                   if _key(value) != answer), row["id"]
        assert _decode(row["target"]["answer"]) not in args, row["id"]
        if target == "lists":
            assert all(0 <= number <= 9 for arg in args for number in arg)
