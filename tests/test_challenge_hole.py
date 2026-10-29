"""Recheck the published hole mode against the reference interpreter."""

import json
from collections import Counter

from opulse.bench.check import prompt_registry
from opulse.config import Settings
from opulse.core.starting_sets import starting_registry
from opulse.expression.nodes import from_ast
from opulse.expression.render import ExpressionRenderer
from opulse.solver.holes import HoleSolver
from tools.challenge_hole import DOMAIN, OUTPUT, ROOT, SEED, check_rule_quality, generate, shape
from tools.audit_examples import normalize_rule, recurring_family, trivial_template


def test_schema_variety_and_reproducibility():
    raw = OUTPUT.read_bytes()
    document = json.loads(raw)
    expected = generate()
    assert document == expected
    assert raw == (json.dumps(expected, ensure_ascii=False, indent=2) + "\n").encode()
    assert {key: document[key] for key in ("schema", "mode", "group", "seed")} == {
        "schema": "opulse.challenge-mode/1", "mode": "hole", "group": "reason", "seed": SEED}
    rows = document["challenges"]
    assert len(rows) == 12
    assert [row["id"] for row in rows] == [f"hole-{i:02d}" for i in range(1, 13)]
    assert Counter(row["level"] for row in rows) == {"easy": 4, "medium": 5, "hard": 3}
    assert len({row["answer"] for row in rows}) == 12
    assert len({row["why"] for row in rows}) == 12
    assert len({row["why_zh"] for row in rows}) == 12
    assert len({tuple(rule["text"] for rule in row["rules"]) for row in rows}) == 12


def test_reservation_and_template_limit():
    rows = json.loads(OUTPUT.read_text(encoding="utf-8"))["challenges"]
    templates = Counter()
    reserved = []
    for row in rows:
        atoms = tuple(atom["symbol"] for atom in row["atoms"])
        for rule in row["rules"]:
            template = normalize_rule(rule["text"], blind=True, atom_symbols=atoms)
            if not trivial_template(template):
                templates[template] += 1
            if family := recurring_family(template):
                reserved.append((row["id"], family))
    assert max(templates.values()) <= 3
    assert reserved == [("hole-03", "a + (b * #)")]


def test_each_scan_and_unique_solution():
    rows = json.loads(OUTPUT.read_text(encoding="utf-8"))["challenges"]
    settings = Settings.load(ROOT / "configs/default.yaml")
    shapes = set()
    for row in rows:
        assert set(row) == {"id", "level", "why", "why_zh", "rules", "question", "target",
                            "domain", "answer", "scan", "unique", "verified", "atoms"}
        assert row["verified"] is True and row["unique"] is True
        assert row["why"].endswith(".") and row["why_zh"].endswith("。")
        assert all(set(rule) == {"symbol", "text", "hint"} and rule["hint"] for rule in row["rules"])
        check_rule_quality(row["rules"])
        lo, hi = row["domain"]
        assert (lo, hi) == DOMAIN and lo <= row["answer"] <= hi
        ops = prompt_registry([rule["text"] for rule in row["rules"]], starting_registry(),
                              settings.symbols, settings.semantics.build(), variables=("x",))
        ast = ops.parser.parse_expr(row["question"], expression_mode=True)
        expr = from_ast(ast, ops.registry)
        assert ExpressionRenderer(settings.symbols).full(expr) == row["question"]
        structure = shape(expr)
        assert structure not in shapes
        shapes.add(structure)
        assert row["question"].count("x") == 1
        assert row["scan"] == [
            {"x": x, "value": ops.oracle.evaluate_expr(ast, {"x": x}).value}
            for x in range(lo, hi + 1)
        ]
        assert all(type(item["value"]) is int and abs(item["value"]) <= 100 for item in row["scan"])
        assert row["target"] == row["scan"][row["answer"] - lo]["value"]
        assert [item["x"] for item in row["scan"] if item["value"] == row["target"]] == [row["answer"]]
        solutions = HoleSolver(None, ops.oracle, fallback_domain=DOMAIN).solve(expr, row["target"])
        assert solutions.unique and solutions.domain == DOMAIN
        assert solutions.values == [row["answer"]]
