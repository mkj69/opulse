"""The published target puzzles have finite, reproducible solution sets."""

import json
from collections import Counter

import pytest

from tools.challenge_target import OUTPUT, RECIPES, SEED, _check_rules, check_answer, generate, search


def _load():
    return json.loads(OUTPUT.read_text(encoding="utf-8"))


def test_published_data_is_reproducible():
    data = _load()
    assert OUTPUT.read_text(encoding="utf-8") == json.dumps(
        generate(), ensure_ascii=False, indent=2) + "\n"
    assert (data["schema"], data["mode"], data["group"], data["seed"]) == (
        "opulse.challenge-mode/1", "target", "create", SEED)
    rows = data["challenges"]
    assert len(rows) == len(RECIPES) == 12
    assert [r["id"] for r in rows] == [f"target-{i:02d}" for i in range(1, 13)]
    assert Counter(r["level"] for r in rows) == {"easy": 4, "medium": 5, "hard": 3}
    assert len({r["rules"][0]["text"] for r in rows}) == 12


def test_every_solution_and_fresh_exhaustive_count():
    for row in _load()["challenges"]:
        assert 1 <= len(row["rules"]) <= 3
        assert 4 <= len(row["numbers"]) <= 6
        assert len(set(row["numbers"])) == len(row["numbers"])
        assert all(type(n) is int and 1 <= n <= 10 for n in row["numbers"])
        assert set(row["allowed"]) == {r["symbol"] for r in row["rules"]} | (
            set(row["allowed"]) & {"+", "-", "*"})
        assert 10 <= row["target"] <= 95
        assert row["verified"] is True
        assert row["why"].endswith(".") and row["why_zh"].endswith("。")
        _check_rules(row["rules"])
        check_answer(row, row["solution"])
        fresh = search(row)[row["target"]]
        assert row["solutions_count"] == len(fresh)
        assert any(expr == row["solution"] for expr, _, _ in fresh)
        if row["level"] == "hard":
            assert 1 <= len(fresh) <= 3
            assert all(uses_custom for _, uses_custom, _ in fresh)
        elif row["level"] == "medium":
            assert len(fresh) <= 6
        else:
            assert len(fresh) <= 10


def test_answer_rejects_reused_card_and_disallowed_operator():
    row = _load()["challenges"][0]
    with pytest.raises(AssertionError):
        check_answer(row, "(7 ◆ (7 + 3))")
    with pytest.raises(AssertionError):
        check_answer(row, "(7 * 5)")


@pytest.mark.parametrize("text", [
    "a ◆ b = { a + (b * 1) }",
    "a ◆ b = { a + 0 }",
    "a ◆ b = { a - a }",
    "a ◆ b = { a * 2 }",
    "a ◆ b = { a + b }",
    "a ◆ b = { - (- (a + b)) }",
])
def test_quality_filter_rejects_inert_or_unused_parts(text):
    with pytest.raises(AssertionError):
        _check_rules([{"symbol": "◆", "text": text}])
