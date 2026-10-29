"""Shared publication checks for all Challenge generators."""

from __future__ import annotations

import re
from collections import Counter, defaultdict

COUNTS = {"easy": 8, "medium": 14, "hard": 8, "expert": 10, "master": 10, "legend": 3}
STEP_LIMITS = {"easy": (4, 8), "medium": (7, 16), "hard": (10, 17),
               "expert": (25, 250), "master": (100, 5000), "legend": (20_000, 300_000)}
NUMBER = re.compile(r"(?<![₀-₉\w])\d+(?![₀-₉\w])")
ONE_UNIT = re.compile(r"one.unit|off.by.(?:exactly.)?one|(?:by (?:exactly )?|exactly )one", re.I)


def structural_key(row: dict) -> str:
    """Pair the main custom operator with the number-free expression tree."""
    question = NUMBER.sub("N", row["question"])
    symbols = sorted((rule["symbol"] for rule in row["rules"]), key=len, reverse=True)
    pattern = re.compile("|".join(re.escape(symbol) for symbol in symbols))
    matches = list(pattern.finditer(question))
    assert matches, row["id"]
    depth = 0
    depths = []
    for char in question:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        depths.append(depth)
    main = min(matches, key=lambda match: (depths[match.start()], match.start())).group()
    return main + " | " + pattern.sub("OP", question)


def structures(row: dict) -> set[str]:
    rules = row["rules"]
    symbols = [rule["symbol"] for rule in rules]
    texts = [rule["text"] for rule in rules]
    result = set()
    direct_calls = sum(row["question"].count(symbol) for symbol in symbols)
    if direct_calls > 1 or any(
        other in rule["text"].split("=", 1)[1]
        for rule in rules for other in symbols if other != rule["symbol"]
    ):
        result.add("composition")
    if any(" if " in text and ";" in text for text in texts):
        result.add("branch")
    if any(rule["symbol"] in rule["text"].split("=", 1)[1] for rule in rules):
        result.add("recursion")
    if any(len(text.split("=", 1)[0].split()) == 2 or "= { - (" in text for text in texts):
        result.add("unary")
    return result


def validate_tier(rows: list[dict]) -> None:
    assert rows
    level = rows[0]["level"]
    assert all(row["level"] == level for row in rows)
    assert len(rows) == COUNTS[level]
    assert len({structural_key(row) for row in rows}) == len(rows)
    assert set().union(*(structures(row) for row in rows)) == {
        "composition", "branch", "recursion", "unary"
    }, level
    answers = Counter(row["answer"] for row in rows)
    assert max(answers.values()) <= 2, level
    if level in ("expert", "master"):
        assert all(abs(row["answer"] - row["variant"]["answer"]) >= 3 for row in rows), level
        assert len({row["parameters"]["target"] for row in rows}) == 10
    if level == "expert":
        assert all(answers[value] <= 2 for value in (0, 1, 10))
        assert len(answers) >= 7
    for row in rows:
        assert isinstance(row["answer"], int) and not isinstance(row["answer"], bool)
        assert row["answer"] != row["variant"]["answer"]
        low, high = STEP_LIMITS[level]
        assert low <= row["step_count"] <= high, row["id"]
        assert low <= row["variant"]["step_count"] <= high, row["id"]
        if level in ("expert", "master"):
            assert row["variant"].get("rule_id"), row["id"]
        if abs(row["answer"] - row["variant"]["answer"]) == 1:
            assert ONE_UNIT.search(row["why"]), row["id"]
        traps = row.get("trap_answers", {})
        assert not traps or any(value != row["answer"] for value in traps.values()), row["id"]
        for field, ending in (("why", "."), ("why_zh", "。")):
            note = row.get(field, "")
            assert isinstance(note, str) and len(note.strip()) >= (35 if field == "why" else 24), row["id"]
            assert note.endswith(ending), row["id"]
            assert "Same question, different rulebook" not in note
            if field == "why":
                assert len(note.split()) <= 30, row["id"]
    assert len({row["why"] for row in rows}) == len(rows)
    assert len({row["why_zh"] for row in rows}) == len(rows)


def validate_global(rows: list[dict]) -> None:
    assert len(rows) == 53
    assert len({row["id"] for row in rows}) == len(rows)
    assert len({structural_key(row) for row in rows}) == len(rows)
    assert len({row["why"] for row in rows}) == len(rows)
    assert len({row["why_zh"] for row in rows}) == len(rows)
    edited_pairs = [(row["set"]["name"], row["variant"].get("rule_id", row["variant"]["before"]),
                     tuple(sorted((row["answer"], row["variant"]["answer"]))))
                    for row in rows if row["level"] in ("expert", "master")]
    assert len(set(edited_pairs)) == len(edited_pairs)
    tiers = defaultdict(list)
    for row in rows:
        tiers[row["level"]].append(row)
    assert {level: len(items) for level, items in tiers.items()} == COUNTS
    small = ("easy", "medium", "hard")
    assert sum(row["question"].lstrip().startswith(("-", "+", "#", "&"))
               for row in rows if row["level"] in small) <= 3
    for level in small:
        assert sum(row["question"].lstrip().startswith(("-", "+", "#", "&"))
                   for row in tiers[level]) <= 2
    for items in tiers.values():
        validate_tier(items)
