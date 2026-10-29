"""Published ripple answers follow only from the displayed rule texts."""

from __future__ import annotations

import json
import re

from opulse.bench.check import prompt_registry
from opulse.config import Settings
from opulse.core.semantics import NAN
from opulse.core.starting_sets import starting_registry
from opulse.definition import ast
from tools.challenge_ripple import OUTPUT, ROOT, SEED, generate, quality_issues


def document():
    return json.loads(OUTPUT.read_text(encoding="utf-8"))


def test_schema_counts_and_distinct_challenges():
    data = document()
    assert set(data) == {"schema", "mode", "group", "seed", "challenges"}
    assert (data["schema"], data["mode"], data["group"], data["seed"]) == (
        "opulse.challenge-mode/1", "ripple", "reason", SEED)
    rows = data["challenges"]
    assert [row["id"] for row in rows] == [f"ripple-{i:02d}" for i in range(1, 13)]
    assert [row["level"] for row in rows] == ["easy"] * 4 + ["medium"] * 5 + ["hard"] * 3

    rule_sets, structures, answers, masks, explanations = set(), set(), set(), set(), set()
    for row in rows:
        assert set(row) == {"id", "level", "why", "why_zh", "rules", "edit",
                            "input", "items", "verified", "atoms"}
        assert row["verified"] is True
        assert row["why"] and row["why_zh"] and len(row["why_zh"]) > 15
        assert row["why"] not in explanations
        explanations.add(row["why"])
        assert len(row["input"]) == 2 and all(type(x) is int for x in row["input"])
        assert 5 <= len(row["items"]) <= 8
        assert all(set(rule) == {"symbol", "text", "hint"} and rule["hint"]
                   for rule in row["rules"])
        assert all(set(item) == {"expr", "before", "after", "changed"}
                   and type(item["before"]) is int and type(item["after"]) is int
                   and type(item["changed"]) is bool for item in row["items"])
        mask = tuple(item["changed"] for item in row["items"])
        assert sum(mask) >= 2 and len(mask) - sum(mask) >= 2
        assert mask not in masks
        masks.add(mask)
        answer = tuple((item["before"], item["after"]) for item in row["items"])
        assert answer not in answers
        answers.add(answer)
        rule_set = tuple(rule["text"] for rule in row["rules"])
        assert rule_set not in rule_sets
        rule_sets.add(rule_set)

        def normalized(text):
            for index, rule in enumerate(row["rules"]):
                text = text.replace(rule["symbol"], f"@{index}")
            return re.sub(r"\d+", "#", text)

        structure = (tuple(normalized(rule["text"]) for rule in row["rules"]),
                     tuple(normalized(item["expr"]) for item in row["items"]))
        assert structure not in structures
        structures.add(structure)


def test_each_item_against_fresh_reference_interpreters():
    settings = Settings.load(ROOT / "configs/default.yaml")
    for row in document()["challenges"]:
        rules = row["rules"]
        edit = row["edit"]
        assert set(edit) == {"rule_index", "before", "after"}
        assert edit["rule_index"] == 0
        assert edit["before"] == rules[0]["text"] and edit["after"] != edit["before"]
        texts = [rule["text"] for rule in rules]
        changed_texts = texts.copy()
        changed_texts[edit["rule_index"]] = edit["after"]
        worlds = [prompt_registry(candidate, starting_registry(), settings.symbols,
                                  settings.semantics.build())
                  for candidate in (texts, changed_texts)]
        edited_symbol = rules[edit["rule_index"]]["symbol"]
        unchanged_dependent = False
        for item in row["items"]:
            values = []
            for world in worlds:
                expr = world.parser.parse_expr(item["expr"], expression_mode=True, strict=True)
                result = world.oracle.evaluate_expr(expr, {}).value
                assert result is not NAN and type(result) is int
                values.append(result)
            assert values == [item["before"], item["after"]]
            assert item["changed"] == (values[0] != values[1])
            original = worlds[0]
            parsed = original.parser.parse_expr(item["expr"], expression_mode=True, strict=True)
            calls = {call.symbol for call in ast.iter_applications(parsed)}
            reachable = set(calls)
            while True:
                extra = {original.registry.get(dep).symbol
                         for op in original.registry if op.symbol in reachable
                         for dep in op.dependencies}
                if extra <= reachable:
                    break
                reachable |= extra
            if not item["changed"] and edited_symbol in reachable:
                unchanged_dependent = True
        assert unchanged_dependent, row["id"]


def test_generator_is_byte_reproducible():
    expected = json.dumps(generate(), ensure_ascii=False, indent=2) + "\n"
    assert OUTPUT.read_text(encoding="utf-8") == expected


def test_quality_gate_rejects_shortcuts_and_ignored_inputs():
    row = document()["challenges"][0]
    settings = Settings.load(ROOT / "configs/default.yaml")
    texts = [rule["text"] for rule in row["rules"]]
    p, q, r, s = [rule["symbol"] for rule in row["rules"]]
    expression = [item["expr"] for item in row["items"]]

    bad = texts.copy()
    bad[1] = f"{q} a = {{ a {p} 1 }}"
    assert any("pure alias" in issue for issue in quality_issues(
        bad, row["edit"]["after"], expression, settings))

    bad = texts.copy()
    bad[2] = f"a {r} b = {{ (a {p} b) - (a {p} b) }}"
    issues = quality_issues(bad, row["edit"]["after"], expression, settings)
    assert any("trivial arithmetic" in issue for issue in issues)
    assert any("ignores argument" in issue for issue in issues)

    bad = texts.copy()
    bad[3] = f"{s} a = {{ 2 }}"
    assert any("unused parameter" in issue for issue in quality_issues(
        bad, row["edit"]["after"], expression, settings))

    assert any("trivial arithmetic" in issue for issue in quality_issues(
        texts, row["edit"]["after"], [f"(5 {p} 2) * 1"], settings))
