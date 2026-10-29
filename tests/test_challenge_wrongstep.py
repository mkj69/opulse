"""Publication checks for the seeded first-wrong-step Challenge data."""

from __future__ import annotations

import json
import re
from collections import Counter

from tools.challenge_quality import structural_key
from tools.audit_examples import normalize_rule, recurring_family, trivial_template
from tools.challenge_wrongstep import CASES, OUTPUT, generate


def test_wrongstep_schema_and_unique_answers():
    data = json.loads(OUTPUT.read_text(encoding="utf-8"))
    assert set(data) == {"schema", "mode", "group", "seed", "challenges"}
    assert (data["schema"], data["mode"], data["group"]) == (
        "opulse.challenge-mode/1", "wrongstep", "execute")
    rows = data["challenges"]
    assert len(rows) == 12
    assert Counter(row["level"] for row in rows) == {"easy": 4, "medium": 5, "hard": 3}
    assert [row["id"] for row in rows] == [f"wrongstep-{i:02d}" for i in range(1, 13)]
    assert len({row["wrong_index"] for row in rows}) == 12
    assert len({structural_key(row) for row in rows}) == 12
    assert len({tuple(rule["text"] for rule in row["rules"]) for row in rows}) == 12
    assert len({row["why"] for row in rows}) == 12
    assert len({row["why_zh"] for row in rows}) == 12

    for row in rows:
        assert set(row) == {"id", "level", "why", "why_zh", "rules", "question",
                            "steps", "wrong_index", "wrong_reason", "wrong_reason_zh",
                            "correct_expr", "verified", "atoms"}
        assert row["verified"] is True
        assert row["why"].endswith(".") and row["why_zh"].endswith("。")
        assert row["wrong_reason"].endswith(".")
        assert row["wrong_reason_zh"].endswith("。")
        assert row["rules"] and all(set(rule) == {"symbol", "text", "hint"}
                                    and all(rule.values()) for rule in row["rules"])
        assert 6 <= len(row["steps"]) - 1 <= 25
        assert row["steps"][0] == {"expr": row["question"], "rule": None}
        assert all(set(step) == {"expr", "rule"} for step in row["steps"])
        assert all(step["rule"] for step in row["steps"][1:])
        assert 1 <= row["wrong_index"] < len(row["steps"]) - 1
        assert row["steps"][row["wrong_index"]]["expr"] != row["correct_expr"]
        assert len({step["expr"] for step in row["steps"]}) == len(row["steps"])


def test_reader_explanations_omit_runtime_terms():
    data = json.loads(OUTPUT.read_text(encoding="utf-8"))
    for row in data["challenges"]:
        reader_text = " ".join(row[key] for key in ("why", "why_zh", "wrong_reason", "wrong_reason_zh"))
        assert not re.search(r"\b(?:abort|overflow|undefined|evaluation)\b", reader_text, re.I)


def test_reserved_families_and_templates_are_excluded():
    rows = json.loads(OUTPUT.read_text(encoding="utf-8"))["challenges"]
    templates = Counter()
    for row in rows:
        atoms = tuple(atom["symbol"] for atom in row["atoms"])
        for rule in row["rules"]:
            template = normalize_rule(rule["text"], blind=True, atom_symbols=atoms)
            assert recurring_family(template) is None
            if not trivial_template(template):
                templates[template] += 1
    assert max(templates.values()) <= 3


def test_wrongstep_reproducible_and_interpreter_verified():
    # generate() independently builds and verifies the correct full trace,
    # checks that the mistaken rewrite changes the reference value, then
    # verifies the entire continuation from the mistaken expression.
    expected = (json.dumps(generate(), ensure_ascii=False, indent=2,
                           allow_nan=False) + "\n").encode()
    assert OUTPUT.read_bytes() == expected
    assert {case.error for case in CASES} == {"off_by_one", "swapped", "atom", "wrong_branch"}
    bodies = [body for case in CASES for _, body, _ in case.rules]
    assert len(set(bodies)) == len(bodies)
    assert all(abs(int(row["steps"][-1]["expr"])) <= 100
               for row in json.loads(OUTPUT.read_text(encoding="utf-8"))["challenges"])
