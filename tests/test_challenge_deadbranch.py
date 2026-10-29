"""Published deadbranch puzzles have one provably dead and otherwise live branch."""

import copy
import itertools
import json
import re
from collections import Counter

import pytest

from opulse.analysis.coverage import selected_branch
from opulse.core import BRANCH, SIMPLE, Operator, OperatorRegistry, Semantics
from opulse.core.starting_sets import starting_registry
from opulse.solver.static import reachable_branches
from opulse.solver.z3_encode import Z3Encoder
from opulse.verify import Oracle
from tools.challenge_deadbranch import OUTPUT, SEED, SPECS, _make_world, _quality_check, build


def _document():
    return json.loads(OUTPUT.read_text(encoding="utf-8"))


def _world(row):
    operators = []
    for i, rule in enumerate(row["rules"]):
        left = rule["text"].split("=", 1)[0].strip()
        if left.startswith("a "):
            arity, position = 2, None
        elif "(" in left:
            arity, position = 3, None
        else:
            arity, position = 1, "prefix"
        operators.append(
            Operator(
                f"published_deadbranch_{row['id']}_{i}",
                rule["symbol"],
                arity,
                position,
                definition=rule["text"],
                definition_type=BRANCH if ";" in rule["text"] else SIMPLE,
            )
        )
    oracle = Oracle(
        OperatorRegistry([*starting_registry(), *operators]), semantics=Semantics()
    )
    for helper in operators[: row["rule_index"]]:
        oracle.include(helper)
    return operators[row["rule_index"]], oracle


def test_schema_uniqueness_and_reproducibility():
    doc = _document()
    assert {key: doc[key] for key in ("schema", "mode", "group", "seed")} == {
        "schema": "opulse.challenge-mode/1",
        "mode": "deadbranch",
        "group": "reason",
        "seed": SEED,
    }
    rows = doc["challenges"]
    assert len(rows) == 12
    assert [r["id"] for r in rows] == [f"deadbranch-{i:02d}" for i in range(1, 13)]
    assert Counter(r["level"] for r in rows) == {"easy": 4, "medium": 5, "hard": 3}
    assert len({tuple(rule["text"] for rule in row["rules"]) for row in rows}) == 12
    assert (
        len(
            {
                row["branches"][
                    next(i for i, b in enumerate(row["branches"]) if b["dead"])
                ]["text"]
                for row in rows
            }
        )
        == 12
    )
    # Erase the chosen glyphs and constants: the underlying rule layouts still differ.
    layouts = []
    for row in rows:
        texts = " || ".join(rule["text"] for rule in row["rules"])
        for rule in row["rules"]:
            texts = texts.replace(rule["symbol"], "OP")
        layouts.append(re.sub(r"\d+", "N", texts))
    assert len(set(layouts)) == 12
    for row in rows:
        assert set(row) == {
            "id",
            "level",
            "why",
            "why_zh",
            "rules",
            "rule_index",
            "branches",
            "reason",
            "reason_zh",
            "proof",
            "verified",
            "atoms",
        }
        assert row["verified"] is True and row["proof"] == "z3"
        assert all(
            isinstance(row[key], str) and row[key].strip()
            for key in ("why", "why_zh", "reason", "reason_zh")
        )
        assert 0 <= row["rule_index"] < len(row["rules"])
        assert all(
            set(rule) == {"symbol", "text", "hint"} and all(rule.values())
            for rule in row["rules"]
        )
        assert sum(branch["dead"] is True for branch in row["branches"]) == 1
        assert all(
            set(branch) == {"text", "dead"}
            and branch["text"]
            and type(branch["dead"]) is bool
            for branch in row["branches"]
        )
        body = (
            row["rules"][row["rule_index"]]["text"].split("{", 1)[1].rsplit("}", 1)[0]
        )
        assert [part.strip() for part in body.split(";")] == [
            b["text"] for b in row["branches"]
        ]
    assert (
        json.dumps(build(), ensure_ascii=False, indent=2) + "\n"
    ).encode() == OUTPUT.read_bytes()


def test_reader_explanations_omit_runtime_terms():
    for row in _document()["challenges"]:
        reader_text = " ".join(row[key] for key in ("why", "why_zh", "reason", "reason_zh"))
        assert not re.search(r"\b(?:abort|overflow|undefined|evaluation)\b", reader_text, re.I)


def test_published_rules_are_verified_independently():
    for row in _document()["challenges"]:
        operator, oracle = _world(row)
        _quality_check(
            {"dead": next(i for i, b in enumerate(row["branches"]) if b["dead"]),
             "arity": operator.n_ary},
            [(rule["text"], rule["hint"]) for rule in row["rules"]],
            operator,
            oracle,
        )
        branches = oracle._definition_of(operator).branches
        assert len(branches) == len(row["branches"])
        got = reachable_branches(operator, Z3Encoder(oracle))
        assert got == [
            "dead" if b["dead"] else "reachable" for b in row["branches"][:-1]
        ]
        assert branches[-1].condition is None
        witnessed = set()
        for args in itertools.product(range(-12, 13), repeat=operator.n_ary):
            index = selected_branch(operator, args, oracle)
            if index is not None and type(oracle.evaluate(operator, args).value) is int:
                witnessed.add(index)
            if len(witnessed) == len(branches) - 1:
                break
        assert witnessed == {i for i, b in enumerate(row["branches"]) if not b["dead"]}


@pytest.mark.parametrize(
    ("number", "rule", "replacement", "rejection"),
    [
        (1, 0,
         "@S@ a = { a + 0, if a % 6 == 0; a - 1, if a % 3 == 0 and a % 2 == 0; a * 2, if a < 0; a, else }",
         "no-op arithmetic"),
        (11, 0, "a @H@ b = { a + b }", "pure alias"),
        (12, 0, "a @H@ b = { a + 2, if b > 0; a + 2, else }", "ignored input"),
    ],
)
def test_quality_filter_rejects_weak_rules(number, rule, replacement, rejection):
    spec = copy.deepcopy(SPECS[number - 1])
    spec["rules"][rule] = (replacement, spec["rules"][rule][1])
    rendered, operator, oracle = _make_world(spec, number, ("◇", "◆"))
    with pytest.raises(AssertionError, match=rejection):
        _quality_check(spec, rendered, operator, oracle)
