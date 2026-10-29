"""Published Challenge shorten data is reproducible and exhaustively checked."""

import itertools
import json
import re
from collections import Counter

import pytest

from opulse.bench.families import common
from opulse.playground import challenge_steps, challenge_steps_json, check_equivalent
from tools.challenge_shorten import BASE, OUTPUT, SEED, SEMANTICS, SYMBOLS, generate, quality_filter, verify_row


def _load():
    return json.loads(OUTPUT.read_text(encoding="utf-8"))


def _shape(row):
    text = " | ".join(rule["text"] for rule in row["rules"])
    for index, symbol in enumerate(rule["symbol"] for rule in row["rules"]):
        text = text.replace(symbol, f"OP{index}")
    return re.sub(r"\b\d+\b", "N", text)


def _function_signature(row):
    texts = [rule["text"] for rule in row["rules"][:-1]] + [row["reference"]]
    ops = common.text_registry(texts, BASE, SYMBOLS, SEMANTICS)
    operator = next(op for op in ops.registry if op.symbol == row["symbol"])
    return row["arity"], tuple(
        common.json_value(ops.oracle.evaluate(operator, args).value)
        for args in itertools.product(range(-2, 3), repeat=row["arity"])
    )


def test_schema_variety_and_verification():
    data = _load()
    assert set(data) == {"schema", "mode", "group", "seed", "challenges"}
    assert (data["schema"], data["mode"], data["group"], data["seed"]) == (
        "opulse.challenge-mode/1", "shorten", "create", SEED)
    rows = data["challenges"]
    assert len(rows) == 12
    assert [row["id"] for row in rows] == [f"shorten-{i:02d}" for i in range(1, 13)]
    assert Counter(row["level"] for row in rows) == {"easy": 4, "medium": 5, "hard": 3}
    assert len({_shape(row) for row in rows}) == 12
    assert len({_function_signature(row) for row in rows}) == 12
    assert len({row["reference"] for row in rows}) == 12
    all_rules = [rule["text"] for row in rows for rule in row["rules"]]
    assert len(all_rules) == len(set(all_rules))
    for row in rows:
        assert set(row) == {"id", "level", "why", "why_zh", "rules", "symbol", "text",
                            "size", "reference_size", "steps", "budget_steps", "reference_steps",
                            "inputs", "reference", "domain", "arity", "verified", "atoms"}
        assert row["why"].endswith(".") and row["why_zh"].endswith("。")
        assert row["arity"] in (1, 2, 3, 4)
        assert 5 <= len(row["inputs"]) <= 8
        assert row["reference_steps"] <= row["budget_steps"] < row["steps"]
        assert row["size"] > 0 and row["reference_size"] > 0
        rules = [rule["text"] for rule in row["rules"]]
        original = challenge_steps("\n".join(rules), row["text"], row["inputs"])
        reference = challenge_steps("\n".join(rules), row["reference"], row["inputs"])
        assert original["parse_error"] is reference["parse_error"] is None
        assert original["total"] == row["steps"]
        assert reference["total"] == row["reference_steps"]
        assert check_equivalent("\n".join(rules), row["symbol"], row["reference"],
                                row["domain"])["equivalent"] is True
        assert len(original["per_input"]) == len(row["inputs"])
        assert [entry["inputs"] for entry in original["per_input"]] == row["inputs"]
        verify_row(row)


def test_reference_error_is_caught():
    row = next(row for row in _load()["challenges"] if row["id"] == "shorten-08").copy()
    row["reference"] = row["reference"].replace("a + 2", "a + 3")
    with pytest.raises(AssertionError):
        verify_row(row)


def test_byte_reproducible():
    expected = json.dumps(generate(), ensure_ascii=False, indent=2) + "\n"
    assert OUTPUT.read_text(encoding="utf-8") == expected


def test_steps_entry_point_reports_errors_and_preserves_sample_multiplicity():
    rules = "a ◇ b = { (a * b) + (a * b) }"
    answer = "a ◇ b = { (a * b) * 2 }"
    points = [[2, 3], [2, 3], [0, 4]]
    result = challenge_steps(rules, answer, points)
    assert result == {"total": 6, "per_input": [
        {"inputs": point, "steps": 2} for point in points], "parse_error": None}
    assert json.loads(challenge_steps_json(rules, answer, json.dumps(points))) == result
    assert challenge_steps(rules, "a ◇ b = { a + }", points)["parse_error"]
    assert challenge_steps(rules, answer, [[1]])["parse_error"]
    assert challenge_steps(rules, answer, [])["parse_error"]


@pytest.mark.parametrize("text", [
    "a ◇ b = { (a * b) + 0 }",
    "a ◇ b = { (a * b) * 1 }",
    "a ◇ b = { (a * b) - (a * b) }",
    "a ◇ b = { - (- (a + b)) }",
    "a ◇ b = { a * 2 }",
    "a ◇ b = { a ♣ b }",
])
def test_quality_filter_rejects_silly_rules(text):
    definitions = ["a ♣ b = { (a * 2) + b }", text]
    ops = common.text_registry(definitions, BASE, SYMBOLS, SEMANTICS)
    with pytest.raises(AssertionError):
        quality_filter(ops.parser.parse(text), {"◇", "♣"})
