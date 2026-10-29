"""Published induce puzzles are reproducible, discriminating, and readable."""

import itertools
import json
import random
import re
from collections import Counter

import pytest

from opulse.bench.families import common
from tools.challenge_induce import (
    BASE,
    MIRROR,
    OUTPUT,
    SEED,
    SEMANTICS,
    SYMBOLS,
    candidate_differences,
    generate,
    quality_filter,
    verify_row,
)


def _load():
    return json.loads(OUTPUT.read_text(encoding="utf-8"))


def _ops(row):
    ops = common.text_registry(row["known"] + [row["reference_definition"]], BASE, SYMBOLS, SEMANTICS)
    target = next(item for item in ops.registry if item.symbol == row["symbol"] and item.definition)
    return ops, target


def test_schema_quality_variety_and_answers():
    data = _load()
    assert set(data) == {"schema", "mode", "group", "seed", "challenges"}
    assert (data["schema"], data["mode"], data["group"], data["seed"]) == (
        "opulse.challenge-mode/1", "induce", "induce", SEED)
    rows = data["challenges"]
    assert len(rows) == 12
    assert [row["id"] for row in rows] == [f"induce-{i:02d}" for i in range(1, 13)]
    assert Counter(row["level"] for row in rows) == {"easy": 4, "medium": 5, "hard": 3}
    assert len({tuple(query["answer"] for query in row["queries"]) for row in rows}) == 12
    assert len({text.split(" = ", 1)[1] for row in rows
                for text in row["known"] + [row["reference_definition"]]}) == sum(
                    1 + len(row["known"]) for row in rows)
    shapes, functions = set(), set()
    for row in rows:
        assert set(row) == {"id", "level", "why", "why_zh", "rules", "atoms", "known", "symbol",
                            "examples", "queries", "reference_definition", "domain", "identifiable", "verified"}
        assert row["why"].endswith(".") and row["why_zh"].endswith("。")
        assert 5 <= len(row["examples"]) <= 8 and len(row["queries"]) == 3
        assert len({tuple(item["inputs"]) for item in row["examples"] + row["queries"]}) == (
            len(row["examples"]) + 3)
        verify_row(row)
        ops, target = _ops(row)
        lo, hi = row["domain"]
        values = tuple(ops.oracle.evaluate(target, point).value for point in itertools.product(
            range(lo, hi + 1), repeat=target.n_ary))
        assert all(isinstance(value, int) and abs(value) <= 100 for value in values)
        signature = (target.n_ary, values)
        assert signature not in functions
        functions.add(signature)
        shape = re.sub(r"\b\d+\b", "N", row["reference_definition"])
        for symbol in [row["symbol"], *(rule["symbol"] for rule in row["rules"])]:
            shape = shape.replace(symbol, "OP")
        assert shape not in shapes
        shapes.add(shape)


def test_examples_rule_out_library_alternatives():
    for index, row in enumerate(_load()["challenges"], 1):
        ops, target = _ops(row)
        lo, hi = row["domain"]
        points = list(itertools.product(range(lo, hi + 1), repeat=target.n_ary))
        values = [ops.oracle.evaluate(target, point).value for point in points]
        known = [item for item in ops.registry if item.definition in row["known"]]
        alternatives, checked = candidate_differences(
            ops, target, points, values, random.Random(SEED + index), known)
        examples = {points.index(tuple(example["inputs"])) for example in row["examples"]}
        assert all(diff.intersection(examples) for diff in alternatives), row["id"]
        assert row["identifiable"]["checked_against"] == checked
        assert row["identifiable"]["distinguishable"] == len(alternatives)


def test_bad_data_is_detected():
    row = _load()["challenges"][2].copy()
    row["queries"] = [dict(item) for item in row["queries"]]
    row["queries"][0]["answer"] += 1
    with pytest.raises(AssertionError):
        verify_row(row)


def test_byte_reproducible():
    expected = json.dumps(generate(), ensure_ascii=False, indent=2) + "\n"
    assert OUTPUT.read_text(encoding="utf-8") == expected
    if MIRROR.parent.is_dir():
        assert MIRROR.read_text(encoding="utf-8") == expected


@pytest.mark.parametrize("definition", [
    "a ★ b = { (a * b) * 1 }",
    "a ★ b = { (a + b) + 0 }",
    "a ★ b = { (a - a) + b }",
    "a ★ b = { a * 2 }",
    "a ★ b = { a ◇ b }",
])
def test_quality_filter_rejects_silly_rules(definition):
    helper = "a ◇ b = { a + b }"
    ops = common.text_registry([helper, definition], BASE, SYMBOLS, SEMANTICS)
    with pytest.raises(AssertionError):
        quality_filter(definition, "★", ops)
