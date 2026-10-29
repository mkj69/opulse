"""Check the published Describe puzzles against their stated meanings."""

import itertools
import json
from collections import Counter

import pytest

from tools.challenge_describe import (
    DOMAIN, MEANINGS, OUTPUT, SEED, SPECS, check_rule_quality, check_site_rules, generate, values,
)


def test_published_file_and_coverage():
    raw = OUTPUT.read_bytes()
    document = json.loads(raw)
    expected = generate()
    assert document == expected
    assert raw == (json.dumps(expected, ensure_ascii=False, indent=2) + "\n").encode()
    assert {key: document[key] for key in ("schema", "mode", "group", "seed")} == {
        "schema": "opulse.challenge-mode/1", "mode": "describe",
        "group": "describe", "seed": SEED,
    }
    rows = document["challenges"]
    assert [row["id"] for row in rows] == [f"describe-{i:02d}" for i in range(1, 13)]
    assert Counter(row["level"] for row in rows) == {"easy": 4, "medium": 5, "hard": 3}
    assert Counter(row["direction"] for row in rows) == {"name": 6, "write": 6}
    assert len({spec.phenomenon for spec in SPECS}) == 12
    assert all(row["why"].endswith(".") and row["why_zh"].endswith("。")
               and row["verified"] is True for row in rows)


def test_each_description_and_distractor_has_a_distinct_meaning():
    rows = json.loads(OUTPUT.read_text(encoding="utf-8"))["challenges"]
    for spec, row in zip(SPECS, rows):
        domain = tuple(row["domain"])
        assert domain == spec.domain
        assert row["reference"] == spec.reference
        assert row["symbol"] == spec.reference.split(" = ", 1)[0].split()[1]
        assert row["arity"] == 2
        assert [rule["text"] for rule in row["rules"]] == list(spec.rules)
        check_rule_quality((*spec.rules, row["reference"]), domain)
        truth = values((*spec.rules, row["reference"]), domain)
        assert all(type(value) is int and abs(value) <= 100 for value in truth)
        if spec.direction == "name":
            assert row["rule"] == {"symbol": row["symbol"], "text": row["reference"]}
            assert len(row["options"]) == len(row["options_zh"]) == 4
            assert len(row["option_notes"]) == len(row["option_notes_zh"]) == 4
            assert row["answer_format"] == "Option: <n>"
            option_values = [values((*spec.rules, option.meaning), domain)
                             for option in spec.options]
            assert len(set(option_values)) == 4
            assert [i for i, candidate in enumerate(option_values) if candidate == truth] == [row["answer_index"]]
            for i, option in enumerate(spec.options):
                assert row["options_zh"][i] == option.zh
                if i != row["answer_index"]:
                    assert row["options"][i] == option.en
                    assert row["option_notes"][i] == option.note
                    assert row["option_notes_zh"][i] == option.note_zh
        else:
            assert row["description"] == spec.description
            assert row["description_zh"] == spec.description_zh
            assert row["answer_format"] == "Rule: <definition line>"
            intended = MEANINGS[spec.phenomenon]
            assert truth == tuple(intended(a, b) for a, b in itertools.product(
                range(domain[0], domain[1] + 1), repeat=2))
            assert all(values((*spec.rules, alternative), domain) != truth
                       for alternative in spec.misreadings)


def test_boundary_and_product_examples():
    assert DOMAIN == (0, 9)
    rows = json.loads(OUTPUT.read_text(encoding="utf-8"))["challenges"]
    by_id = {row["id"]: row for row in rows}
    threshold = by_id["describe-04"]
    assert values((threshold["reference"],), (4, 4)) == (8,)
    product = by_id["describe-10"]
    assert [MEANINGS["product minus count"](3, b) for b in range(6)] == [0, 2, 4, 6, 8, 10]
    assert product["domain"] == [0, 5]


@pytest.mark.parametrize("rule", [
    "a ★ b = { (a * 1) + b }",
    "a ★ b = { a + 0, if a > b; b, else }",
    "a ★ b = { a + b }",
    "a ★ b = { (b - a) }",
    "a ★ b = { a * 2 }",
    "a ★ b = { (a - a) + b }",
])
def test_quality_filter_rejects_bad_rules(rule):
    with pytest.raises(AssertionError):
        check_rule_quality((rule,), DOMAIN)


@pytest.mark.parametrize(("mode", "index", "key", "rule"), [
    ("describe", 1, "reference", "a ◇ b = { a, if a >= b; b, else }"),
    ("equiv", 1, "rules", "a ◇ b = { a + b, if a + b <= 10; 10, else }"),
    ("induce", 4, "reference_definition", "a ◇ b = { a + b, if b % 2 == 0; a - b, else }"),
])
def test_site_filter_rejects_unreserved_families(mode, index, key, rule):
    from pathlib import Path

    path = Path("docs/assets/data/challenge") / f"{mode}.json"
    rows = json.loads(path.read_text(encoding="utf-8"))["challenges"]
    if key == "rules":
        rows[index][key][0]["text"] = rule
    else:
        rows[index][key] = rule
    with pytest.raises(AssertionError):
        check_site_rules(rows, mode)


def test_site_filter_rejects_other_modes_duplicate():
    from pathlib import Path

    path = Path("docs/assets/data/challenge/equiv.json")
    rows = json.loads(path.read_text(encoding="utf-8"))["challenges"]
    rows[0]["rules"][0]["text"] = "a ★ b = { (a + b) / 2 }"
    with pytest.raises(AssertionError):
        check_site_rules(rows, "equiv")
