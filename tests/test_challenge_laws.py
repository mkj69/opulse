"""Validate the published Law Hunter data against the displayed rulebooks."""

from __future__ import annotations

import itertools
import json
from collections import Counter
from pathlib import Path

import pytest

from opulse.bench.families import common
from opulse.bench.families.law import law_sides
from opulse.config import Symbols
from opulse.definition import ast
from tools.challenge_laws import DOMAIN, SEED, SEMANTICS, SPECS, base_registry, build, quality_signature

DATA = Path(__file__).resolve().parents[1] / "docs/assets/data/challenge/laws.json"
LAWS = {"commutative", "associative", "idempotent", "left identity", "right identity",
        "involution", "absorbing"}


def test_published_laws_are_reproducible_and_unique():
    text = DATA.read_text(encoding="utf-8")
    data = json.loads(text)
    assert data == build()
    assert text == json.dumps(build(), ensure_ascii=False, indent=2) + "\n"
    assert data["schema"] == "opulse.challenge-mode/1"
    assert (data["mode"], data["group"], data["seed"]) == ("laws", "reason", SEED)
    rows = data["challenges"]
    assert len(rows) == 12
    assert [row["id"] for row in rows] == [f"laws-{n:02d}" for n in range(1, 13)]
    assert Counter(row["level"] for row in rows) == {"easy": 4, "medium": 5, "hard": 3}
    assert Counter(row["holds"] for row in rows) == {True: 6, False: 6}
    assert {row["law"] for row in rows} == LAWS
    assert len({row["symbol"] for row in rows}) == 12
    assert len({row["statement"] for row in rows}) == 12
    assert len({row["why"] for row in rows}) == 12
    assert len({row["why_zh"] for row in rows}) == 12
    assert len({tuple(rule["text"] for rule in row["rules"]) for row in rows}) == 12
    assert len({quality_signature(spec) for spec in SPECS}) == 12
    assert len({(row["law"], row["holds"],
                 tuple(row["counterexample"]["inputs"]) if row["counterexample"] else ())
                for row in rows}) == 12
    for row in rows:
        assert set(row) == {"id", "level", "why", "why_zh", "rules", "symbol", "law",
                            "statement", "holds", "proof", "counterexample", "domain", "verified", "atoms"}
        assert row["verified"] is True and row["proof"] == "range"
        assert row["domain"] == DOMAIN
        assert row["why"].endswith(".") and row["why_zh"].endswith("。")
        assert all(set(rule) == {"symbol", "text", "hint"} and rule["hint"] for rule in row["rules"])
        assert row["symbol"] == row["rules"][-1]["symbol"]


def test_each_law_is_exhaustive_over_its_stated_domain():
    rows = json.loads(DATA.read_text(encoding="utf-8"))["challenges"]
    symbols = Symbols()
    for row in rows:
        ops = common.text_registry([rule["text"] for rule in row["rules"]], base_registry(),
                                   symbols, SEMANTICS)
        target = ops.registry.find(row["symbol"], 1, "prefix")
        unary = target is not None
        if not unary:
            target = ops.registry.find(row["symbol"], 2)
        assert target is not None
        law = "left_absorbing" if row["law"] == "absorbing" else row["law"].replace(" ", "_")
        element = None
        if row["law"] in ("left identity", "right identity", "absorbing"):
            # The stated element is the constant in the first law side.
            first = row["statement"].split(" = ", 1)[0]
            tokens = first.split()
            element = int(tokens[0] if row["law"] != "right identity" else tokens[-1])
        sides = law_sides(law, row["symbol"], target.n_ary,
                          target.unary_position, element)
        assert sides is not None
        rendered = [ast.render_expr(side, symbols) for side in sides]
        assert row["statement"] == " = ".join(rendered)
        left, right = (common.expression(ops, part) for part in rendered)
        variables = common.variables_in(left, right)
        failures = {}
        lo, hi = row["domain"]
        for point in itertools.product(range(lo, hi + 1), repeat=len(variables)):
            differs, lv, rv = common.violates(ops, left, right, dict(zip(variables, point)))
            assert all(type(value) is int and abs(value) <= 100 for value in (lv, rv))
            if differs:
                failures[point] = (common.json_value(lv), common.json_value(rv))
        assert row["holds"] is (not failures), row["id"]
        if row["holds"]:
            assert row["counterexample"] is None
        else:
            example = row["counterexample"]
            assert set(example) == {"inputs", "left", "right"}
            point = tuple(example["inputs"])
            assert point in failures
            assert (example["left"], example["right"]) == failures[point]
            assert any(abs(value) >= 3 for value in point)
            assert all(tuple([simple] * len(variables)) not in failures for simple in (0, 1))


@pytest.mark.parametrize("rules", [
    [("◈", "a ◈ b = { (a * 1) + b }", "")],
    [("◈", "a ◈ b = { a + 2 }", "")],
    [("⊙", "a ⊙ b = { a + b }", ""), ("◈", "a ◈ b = { a ⊙ b }", "")],
])
def test_quality_filter_rejects_degenerate_rules(rules):
    with pytest.raises(AssertionError):
        quality_signature({"rules": rules})
