"""The published large puzzles can be solved from their displayed rules alone."""

import json
import re
import subprocess
import sys
from dataclasses import replace
from difflib import SequenceMatcher

import pytest

from opulse.config import Settings
from opulse.core import Operator, OperatorRegistry
from opulse.core.starting_sets import starting_registry
from opulse.definition import ast
from opulse.expression.nodes import Call, from_ast
from opulse.expression.render import ExpressionRenderer
from opulse.trace.tree import build_tree, flatten
from opulse.verify import verify_trace
from tools.challenge_expert import OUTPUT, ROOT, compiled_world, generate


def published_world(row, settings, variant=False):
    operators = [replace(op) for op in starting_registry()]
    for i, rule in enumerate(row["rules"]):
        text = row["variant"]["after"] if variant and i == row["variant"]["rule_index"] else rule["text"]
        left = text.split("=", 1)[0].strip().split()
        if len(left) == 3:
            symbol, arity, position = left[1], 2, None
        elif left[0] == "a":
            symbol, arity, position = left[1], 1, "postfix"
        else:
            symbol, arity, position = left[0], 1, "prefix"
        operators.append(Operator(f"published{i}", symbol, arity, position,
                                  recursive_layer=rule["layer"], definition=text,
                                  definition_type="simple_definition"))
    registry = OperatorRegistry(operators)
    oracle, runtime, parser = compiled_world(registry, settings)
    question = from_ast(parser.parse_expr(row["question"], expression_mode=True), registry)
    return registry, oracle, runtime, parser, question


@pytest.fixture(scope="module")
def document():
    return json.loads(OUTPUT.read_text(encoding="utf-8"))


def test_levels_and_counts(document):
    assert document["schema"] == "opulse.challenge/1"
    rows = document["challenges"]
    assert [row["id"] for row in rows] == ([f"expert-{i:02d}" for i in range(1, 11)] +
                                             [f"master-{i:02d}" for i in range(1, 11)])
    assert [row["level"] for row in rows] == ["expert"] * 10 + ["master"] * 10
    assert {row["set"]["name"] for row in rows} == {"int10", "int100"}
    assert all(row["set"]["operators"] == (10 if row["level"] == "expert" else 100)
               for row in rows)
    assert all(row["set"]["seed"] == (101 if row["level"] == "expert" else 102)
               for row in rows)
    assert all(row["set"]["command"].startswith("python -m opulse.cli.main operators ")
               for row in rows)
    assert len({row["question"] for row in rows}) == 20


def test_variety_and_difficulty(document):
    expert, master = (document["challenges"][:10], document["challenges"][10:])
    for tier in (expert, master):
        counts = [row["step_count"] for row in tier]
        assert counts == sorted(counts)
        assert len({row["parameters"]["target"] for row in tier}) == 10
        assert len({(row["parameters"]["target"], row["answer"]) for row in tier}) == 10
    assert {row["parameters"].get("shape", "direct") for row in expert} == {
        "direct", "nested", "sum"}
    assert {row["parameters"]["nested_arg"] for row in expert
            if row["parameters"].get("shape") == "nested"} == {0, 1}
    numeric_inputs = [tuple(re.findall(r"(?<![0-9₀-₉])[0-9]+(?![0-9₀-₉])", row["question"]))
                      for row in expert]
    assert len(set(numeric_inputs)) >= 7
    assert len({row["answer"] for row in master}) == 10
    assert min(max(rule["layer"] for rule in row["rules"]) for row in master) >= 3
    assert max(max(rule["layer"] for rule in row["rules"]) for row in master) == 6
    assert {len(row["parameters"]["inputs"]) for row in master} == {1, 2}


def test_every_trace_and_closure(document):
    settings = Settings.load(ROOT / "configs/default.yaml")
    for row in document["challenges"]:
        rules = row["rules"]
        assert rules and [r["layer"] for r in rules] == sorted(r["layer"] for r in rules)
        assert all(r["hint"] and "\n" not in r["hint"] for r in rules)
        registry, oracle, runtime, parser, question = published_world(row, settings)
        defined = {op.symbol for op in registry if op.definition}
        seen = set()
        pending = [call.symbol for call in ast.iter_applications(parser.parse_expr(row["question"], expression_mode=True))
                   if call.symbol in defined]
        while pending:
            symbol = pending.pop()
            if symbol in seen:
                continue
            seen.add(symbol)
            operator = next(op for op in registry if op.definition and op.symbol == symbol)
            definition = parser.parse(operator.definition)
            for branch in definition.branches:
                applications = list(ast.iter_applications(branch.expr))
                if branch.condition is not None:
                    applications += list(ast.iter_applications(branch.condition))
                for call in applications:
                    assert registry.find(call.symbol, call.n_ary, call.unary_position) is not None
                    if call.symbol in defined:
                        pending.append(call.symbol)
        assert seen == {r["symbol"] for r in rules}

        for changed in (False, True):
            if changed:
                registry, oracle, runtime, parser, question = published_world(row, settings, True)
            expected = row["variant"] if changed else row
            root = build_tree(question, registry, runtime, parser, max_nodes=3000)
            assert root.value == expected["answer"]
            for key, trace in (("steps", flatten(root)),
                               ("coarse_steps", flatten(root, max_depth=1))):
                verify_trace(trace, oracle)
                assert len(trace.steps) == expected["step_count" if key == "steps" else "coarse_step_count"]
                assert expected[key][0] == {"expr": row["question"], "rule": None}
                assert expected[key][1:] == [
                            {"expr": ExpressionRenderer(settings.symbols).full(step.expression_after),
                             "rule": step.operator.symbol} for step in trace.steps]
            low, high = (25, 250) if row["level"] == "expert" else (100, 5000)
            assert low <= expected["step_count"] <= high
            assert isinstance(expected["answer"], int) and not isinstance(expected["answer"], bool)
            if row["level"] == "expert":
                assert abs(expected["answer"]) <= 200
        variant = row["variant"]
        assert variant["answer"] != row["answer"]
        assert variant["before"] == rules[variant["rule_index"]]["text"]
        assert sum(a["text"] != (variant["after"] if i == variant["rule_index"] else a["text"])
                   for i, a in enumerate(rules)) == 1
        edits = [edit for edit in SequenceMatcher(None, variant["before"], variant["after"]).get_opcodes()
                 if edit[0] != "equal"]
        assert len(edits) == 1
        _, start, end, new_start, new_end = edits[0]
        assert max(end - start, new_end - new_start) <= 2
        assert rules[variant["rule_index"]]["layer"] < max(r["layer"] for r in rules)
        main_call = question.args[0] if row["parameters"].get("shape") == "sum" else question
        assert isinstance(main_call, Call)
        assert rules[variant["rule_index"]]["symbol"] != main_call.operator.symbol


def test_reproducible(document, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    index = json.loads((ROOT / "docs/assets/data/scales/index.json").read_text())
    specs = {item["name"]: item for scale in index["scales"]
             for item in scale["sets"] if item["name"] in {"int10", "int100"}}
    for name in ("int10", "int100"):
        if name == "int10":
            command = document["challenges"][0]["set"]["command"].split()
            filename = "int10.seed101.jsonl"
        else:
            command = specs[name]["generation_command"].split()
            filename = "int100.jsonl"
        command[command.index("--out") + 1] = str(cache / filename)
        subprocess.run([sys.executable, *command[1:]], cwd=ROOT, check=True, capture_output=True)
    expected = json.dumps(generate(cache), ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    assert OUTPUT.read_text(encoding="utf-8") == expected
