"""The published equiv rulebooks reproduce every verdict and witness."""

from __future__ import annotations

import itertools
import json
import re
from collections import Counter

from opulse.config import Symbols
from opulse.core import BRANCH, NAN, SIMPLE, Operator, OperatorRegistry, Semantics
from opulse.core.starting_sets import starting_registry
from opulse.expression.nodes import from_ast
from opulse.solver.equivalence import EquivalenceChecker
from opulse.solver.z3_encode import Z3Encoder
from opulse.verify import Oracle
from tools.challenge_equiv import DOMAIN, OUTPUT, SEED, generate


def _checker(row):
    registry = OperatorRegistry(starting_registry())
    for index, rule in enumerate(row["rules"]):
        text = rule["text"]
        assert text.startswith(f"a {rule['symbol']} b = {{")
        op = Operator(f"published_equiv_{index}", rule["symbol"], 2,
                      definition=text, definition_type=BRANCH if ";" in text else SIMPLE,
                      op_compute_func=f"def op_published_equiv_{index}(a, b):\n    return 0\n",
                      op_count_func=f"def op_count_published_equiv_{index}(a, b):\n    return 0\n")
        registry.add(op)
    oracle = Oracle(registry, Symbols(), Semantics("exact", None))
    checker = EquivalenceChecker(Z3Encoder(oracle), timeout_ms=2_000, small_range=2)
    nodes = tuple(from_ast(oracle.parser.parse_expr(row[key], expression_mode=True), registry)
                  for key in ("left", "right"))
    return checker, nodes


def _shape(row):
    # Ignore symbol choice and literal parameters when checking structural variety.
    symbols = sorted((rule["symbol"] for rule in row["rules"]), key=len, reverse=True)
    result = " | ".join([*(rule["text"] for rule in row["rules"]), row["left"], row["right"]])
    for symbol in symbols:
        result = result.replace(symbol, "OP")
    return re.sub(r"(?<![\w])\d+(?![\w])", "N", result)


def test_schema_counts_and_distinct_puzzles():
    payload = json.loads(OUTPUT.read_text(encoding="utf-8"))
    assert {key: payload[key] for key in ("schema", "mode", "group", "seed")} == {
        "schema": "opulse.challenge-mode/1", "mode": "equiv", "group": "reason", "seed": SEED}
    rows = payload["challenges"]
    assert [row["id"] for row in rows] == [f"equiv-{n:02d}" for n in range(1, 13)]
    assert Counter(row["level"] for row in rows) == {"easy": 4, "medium": 5, "hard": 3}
    assert Counter(row["same"] for row in rows) == {True: 6, False: 6}
    assert len({_shape(row) for row in rows}) == 12
    rule_shapes = [re.sub(r"(?<!\w)-?\d+(?!\w)", "N",
                          rule["text"].split("{", 1)[1])
                   for row in rows for rule in row["rules"]]
    assert len(set(rule_shapes)) == len(rule_shapes)
    assert len({row["why"] for row in rows}) == 12
    assert len({row["why_zh"] for row in rows}) == 12
    assert len({(witness["left"], witness["right"])
                for row in rows if (witness := row["counterexample"])}) == 6
    assert len({tuple(row["counterexample"]["inputs"])
                for row in rows if row["counterexample"]}) == 6
    for row in rows:
        assert set(row) == {"id", "level", "why", "why_zh", "rules", "left",
                            "right", "domain", "same", "proof", "counterexample", "verified", "atoms"}
        assert row["verified"] is True
        assert isinstance(row["same"], bool)
        assert row["domain"] == DOMAIN == [-5, 5]
        assert row["proof"] in ("z3", "range")
        assert row["why"].endswith(".") and row["why_zh"].endswith("。")
        assert row["rules"] and all(set(rule) == {"symbol", "text", "hint"} and rule["hint"]
                                    for rule in row["rules"])
        assert (row["counterexample"] is None) == row["same"]
        if row["counterexample"]:
            assert set(row["counterexample"]) == {"inputs", "left", "right"}
            assert len(row["counterexample"]["inputs"]) == 2


def test_all_published_claims_against_reference_interpreter():
    rows = json.loads(OUTPUT.read_text(encoding="utf-8"))["challenges"]
    for row in rows:
        checker, (left, right) = _checker(row)
        for rule in row["rules"]:
            body = rule["text"].split("{", 1)[1].rsplit("}", 1)[0].strip()
            compact = re.sub(r"\s+", "", body)
            assert not re.search(r"(?:\*1(?!\d)|\+0(?!\d)|-0(?!\d)|/1(?!\d)|a-a|b-b|--)", compact)
            assert not re.fullmatch(r"[ab][+*\-/][ab]", compact)
            operator = checker.oracle.registry.find(rule["symbol"], 2)
            samples = {(a, b): checker.oracle.evaluate(operator, (a, b)).value
                       for a, b in itertools.product(range(-5, 6), repeat=2)}
            assert any(samples[a, b] != samples[c, b]
                       for a, c, b in itertools.product(range(-5, 6), repeat=3))
            assert any(samples[a, b] != samples[a, c]
                       for a, b, c in itertools.product(range(-5, 6), repeat=3))
        differing = []
        lo, hi = row["domain"]
        for a, b in itertools.product(range(lo, hi + 1), repeat=2):
            lv = checker.value(left, {"a": a, "b": b})
            rv = checker.value(right, {"a": a, "b": b})
            assert lv is not NAN and rv is not NAN
            assert abs(lv) <= 100 and abs(rv) <= 100
            if lv != rv:
                differing.append((a, b, lv, rv))
        assert bool(differing) != row["same"]
        if row["same"]:
            if row["proof"] == "z3":
                assert checker.check(left, right).status == "proved"
        else:
            assert all(max(abs(a), abs(b)) > 2 for a, b, _, _ in differing)
            witness = row["counterexample"]
            assert (witness["inputs"][0], witness["inputs"][1], witness["left"], witness["right"]) in differing
            assert checker.check(left, right).status == "refuted"


def test_generator_is_byte_reproducible():
    published = OUTPUT.read_bytes()
    generated = (json.dumps(generate(SEED), ensure_ascii=False, indent=2) + "\n").encode()
    assert published == generated
    assert generate(SEED) == generate(SEED)
