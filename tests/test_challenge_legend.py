"""Fast published-data checks; regeneration is opt-in because it verifies six full traces."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from itertools import combinations
from pathlib import Path

import pytest

from opulse.config import Settings
from opulse.core import OperatorRegistry
from opulse.core.operator import Operator
from opulse.core.presets import register_for_symbol
from opulse.definition.parser import DefinitionParser
from opulse.expression.nodes import Call, Number, from_ast
from opulse.verify import Oracle
from opulse.verify.steps import check_steps

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs/assets/data/challenge"


def load_dag(ref):
    assert ref["format"] == "opulse.scale-example/1"
    path = DATA / ref["path"] / "index.json"
    dag = json.loads(path.read_text())
    assert dag["schema"] == "opulse.scale-example/1"
    assert dag["chunks"][-1]["file"] == "root.json"
    nodes = []
    total = path.stat().st_size
    for chunk in dag["chunks"]:
        assert chunk["start"] == len(nodes)
        file = path.parent / chunk["file"]
        assert file.is_file() and file.stat().st_size == chunk["bytes"] <= 2_000_000
        payload = json.loads(file.read_text())
        assert len(payload["nodes"]) == chunk["end"] - chunk["start"]
        assert isinstance(payload["strings"], list)
        nodes.extend(payload["nodes"])
        total += file.stat().st_size
    assert dag["root"] == len(nodes)-1
    memo = {}
    def count(index):
        if index not in memo:
            memo[index] = sum(count(step[2]) if step[2] >= 0 else 1
                              for step in nodes[index]["steps"])
            assert memo[index] == nodes[index]["full"]
        return memo[index]
    assert count(dag["root"]) == ref["count"]
    assert dag["header"]["verification"]["full_trace_verified"] is True
    assert dag["header"]["verification"]["full_trace_steps"] == ref["count"]
    return dag, total


def interpreter(dag):
    operators = []
    for row in dag["operators"]:
        if row["definition"] is None:
            register_for_symbol(row["symbol"], row["parameter_types"], None,
                                row["arity"], row["position"], row["result_type"])
        operators.append(Operator(func_id=row["id"], symbol=row["symbol"], n_ary=row["arity"],
                                  unary_position=row["position"], recursive_layer=row["layer"],
                                  priority=row["priority"], associativity_direction=row["associativity"],
                                  definition=row["definition"], parameter_types=tuple(row["parameter_types"]),
                                  result_type=row["result_type"], op_compute_func="reference",
                                  op_count_func="reference"))
    registry = OperatorRegistry(operators)
    settings = Settings.load(ROOT / "configs/large.yaml")
    return registry, DefinitionParser(settings.symbols, registry), Oracle(
        registry, settings.symbols, settings.semantics.build())


def question_shape(node):
    if not isinstance(node, Call):
        return 0, set(), 0
    children = [question_shape(arg) for arg in node.args]
    defined = node.operator.definition is not None
    return (1 + sum(count for count, _, _ in children),
            ({node.operator.symbol} if defined and 6 <= node.operator.recursive_layer <= 9 else set()).union(
                *(symbols for _, symbols, _ in children)),
            (1 if defined else 0) + max((depth for _, _, depth in children), default=0))


def high_defined_depth(node):
    if not isinstance(node, Call):
        return 0
    high = node.operator.definition is not None and 6 <= node.operator.recursive_layer <= 9
    return int(high) + max((high_defined_depth(arg) for arg in node.args), default=0)


def question_parts(node):
    """Return visible defined operators and subtrees with at least two calls."""
    operators, subtrees = set(), set()
    def visit(part):
        if isinstance(part, Number):
            return ("number", part.value), 0
        children = [visit(arg) for arg in part.args]
        key = (part.operator.func_id, tuple(child for child, _ in children))
        calls = 1 + sum(count for _, count in children)
        if part.operator.definition is not None:
            operators.add(part.operator.func_id)
        if calls >= 2:
            subtrees.add(key)
        return key, calls
    visit(node)
    return operators, subtrees


def test_legend_questions_have_no_shared_multicall_subexpressions():
    rows = json.loads((DATA / "legend.json").read_text())["challenges"]
    parts = []
    for row in rows:
        dag, _ = load_dag(row["steps_ref"])
        registry, parser, _ = interpreter(dag)
        start = from_ast(parser.parse_expr(row["question"], expression_mode=True, strict=True), registry)
        parts.append((row["id"], *question_parts(start)))
    for (left_id, left_ops, left_subtrees), (right_id, right_ops, right_subtrees) in combinations(parts, 2):
        assert len(left_ops & right_ops) <= 1, (left_id, right_id)
        assert not left_subtrees & right_subtrees, (left_id, right_id)


def test_published_legend():
    data = json.loads((DATA / "legend.json").read_text())
    assert data["schema"] == "opulse.challenge/1"
    rows = data["challenges"]
    assert 3 <= len(rows) <= 5
    assert [row["id"] for row in rows] == [f"legend-{i:02d}" for i in range(1, len(rows)+1)]
    for row, (symbol, old, new) in zip(rows, (
        ("▲₃₀₆", "a < 29", "a <= 29"),
        ("♣₂₁₉", "- 77, if", "- 78, if"),
        ("△₃", "a + a", "a - a"),
    )):
        variant = row["variant"]
        assert row["rules"][variant["rule_index"]]["symbol"] == symbol
        assert variant["before"].count(old) == 1
        assert variant["after"] == variant["before"].replace(old, new, 1)
    for row in rows:
        assert row["level"] == "legend" and row["verified"] is True
        assert row["set"]["name"] == "int1000" and row["set"]["operators"] == 1000
        assert row["set"]["seed"] == 103 and "--dedup" in row["set"]["command"]
        assert len(row["rules"]) >= 100
        assert [rule["layer"] for rule in row["rules"]] == sorted(rule["layer"] for rule in row["rules"])
        assert all({"symbol", "text", "hint", "layer"} <= rule.keys() for rule in row["rules"])
        total = 0
        for version in (row, row["variant"]):
            dag, size = load_dag(version["steps_ref"])
            total += size
            assert version["step_count"] == version["steps_ref"]["count"] >= 20_000
            assert version["step_count"] <= 300_000
            assert version["coarse_step_count"] == len(version["coarse_steps"])-1 < 40
            assert version["coarse_steps"][0] == {"expr": row["question"], "rule": None}
            assert version["coarse_steps"][-1]["expr"] == str(version["answer"])
            assert dag["header"]["expression"] == row["question"]
            registry, parser, oracle = interpreter(dag)
            start = from_ast(parser.parse_expr(row["question"], expression_mode=True, strict=True), registry)
            assert start.operator.symbol == {"legend-01": "+", "legend-02": "*",
                                             "legend-03": "♧₉₆₈"}[row["id"]]
            if row["id"] == "legend-03":
                assert high_defined_depth(start) >= 3
            applications, high_symbols, defined_depth = question_shape(start)
            assert applications >= 6
            assert len(high_symbols) >= 4
            assert defined_depth >= 3
            definitions = {op.symbol: op.definition for op in registry if op.definition is not None}
            edited_symbol = row["rules"][row["variant"]["rule_index"]]["symbol"]
            for rule in row["rules"]:
                expected = (row["variant"]["after"] if version is row["variant"]
                            and rule["symbol"] == edited_symbol else rule["text"])
                assert definitions[rule["symbol"]] == expected
            report = check_steps(start, [step["expr"] for step in version["coarse_steps"][1:]],
                                 parser, registry, oracle, version["answer"])
            assert report.first_error is None, report.errors
            assert report.derivation_correct and report.valid_steps == report.steps
        assert total == row["data_bytes"] < 4_000_000
        variant = row["variant"]
        assert variant["verified"] is True and variant["answer"] != row["answer"]
        assert 1 <= row["rules"][variant["rule_index"]]["layer"] <= 3
        assert variant["before"] == row["rules"][variant["rule_index"]]["text"]
        assert variant["before"] != variant["after"]
        assert 100 <= variant["affected_rules"] <= len(row["rules"])
        assert abs(variant["answer"] - row["answer"]) >= 3
        symbols = [rule["symbol"] for rule in row["rules"]]
        pattern = re.compile("|".join(re.escape(symbol) for symbol in
                                      sorted(symbols, key=len, reverse=True)))
        dependencies = {rule["symbol"]: set(pattern.findall(rule["text"].split("=", 1)[1]))
                        for rule in row["rules"]}
        affected = {row["rules"][variant["rule_index"]]["symbol"]}
        while True:
            expanded = affected | {symbol for symbol, deps in dependencies.items() if deps & affected}
            if expanded == affected:
                break
            affected = expanded
        assert variant["affected_rules"] == len(affected)


@pytest.mark.slow
@pytest.mark.skipif(os.getenv("RUN_SLOW_LEGEND") != "1", reason="full trace regeneration is opt-in")
def test_legend_regenerates_byte_for_byte():
    subprocess.run([sys.executable, str(ROOT / "tools/challenge_legend.py"), "--check",
                    "--cache", os.getenv("OPULSE_SCALES_CACHE", "/tmp/opulse_scales")],
                   cwd=ROOT, check=True)
