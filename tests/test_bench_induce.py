"""Induce tasks distinguish candidate rules and grade prediction and definition separately."""

import itertools
import json

import pytest

from opulse.bench.score import score_response
from opulse.cli.main import main
from opulse.core.primitives import CUSTOM, unregister_primitive
from opulse.core.registry import OperatorRegistry
from opulse.core.types import same_value
from opulse.verify import Oracle
from opulse.worlds.showcase import world_spec


@pytest.fixture(scope="module")
def integer_task(tmp_path_factory):
    folder = tmp_path_factory.mktemp("induce_integer")
    operators = folder / "operators.jsonl"
    assert main(["operators", "--out", str(operators), "--layers", "10", "6", "3", "--seed", "4"]) == 0
    path = folder / "tasks.jsonl"
    args = ["bench", "build", "--operators", str(operators), "--out", str(path),
            "--family", "induce", "--count", "1", "--seed", "1"]
    assert main(args) == 0
    first = path.read_bytes()
    assert main(args) == 0
    assert path.read_bytes() == first
    return json.loads(path.read_text()), operators, path


def test_identifiable_against_compatible_operators(integer_task):
    task, path, _ = integer_task
    assert 2 <= task["axes"]["body_size"] <= 6
    registry = OperatorRegistry.from_jsonl(path)
    oracle = Oracle(registry)
    hidden = next(op for op in registry if op.definition == task["reference_definition"])
    examples = [tuple(row["inputs"]) for row in task["examples"]]
    points = list(itertools.product(*(task["input_range"][kind] for kind in task["parameter_types"])))
    checked = 0
    for other in registry:
        if other.definition is None or other.func_id == hidden.func_id:
            continue
        if (other.n_ary, other.unary_position, other.parameter_types, other.result_type) != (
                hidden.n_ary, hidden.unary_position, hidden.parameter_types, hidden.result_type):
            continue
        differs = any(not same_value(oracle.evaluate(hidden, point).value,
                                     oracle.evaluate(other, point).value) for point in points)
        if differs:
            checked += 1
            assert any(not same_value(oracle.evaluate(hidden, point).value,
                                      oracle.evaluate(other, point).value) for point in examples)
    assert task["identifiable"]["checked_against"] >= checked > 0
    assert 6 <= len(task["examples"]) <= 10
    assert all(row["inputs"] not in [example["inputs"] for example in task["examples"]]
               for row in task["queries"])


def test_public_integer_example_is_generated_and_readable(tmp_path):
    from opulse.bench.families import common
    from opulse.config import Symbols
    from opulse.core.semantics import Semantics
    from opulse.core.starting_sets import starting_registry

    symbols = Symbols()
    ops = common.text_registry(["a ◆ b = { (a * 2) + b }"], starting_registry(),
                               symbols, Semantics(bound=None))
    operators = tmp_path / "operators.jsonl"
    ops.registry.to_jsonl(operators)
    path = tmp_path / "tasks.jsonl"
    assert main(["bench", "build", "--operators", str(operators), "--out", str(path),
                 "--family", "induce", "--count", "1", "--seed", "11"]) == 0
    task = json.loads(path.read_text())
    assert task["known"] == []
    assert task["axes"]["body_size"] == 2
    assert task["reference_definition"] == "a ◆ b = { (a * 2) + b }"
    assert [(row["inputs"], row["output"]) for row in task["examples"]] == [
        ([3, 3], 9), ([-2, 2], -2), ([-2, 1], -3), ([3, 0], 6), ([2, 4], 8), ([-2, 3], -1)]
    assert task["queries"] == [{"inputs": [-4, 3]}, {"inputs": [4, -3]}, {"inputs": [-1, 1]}]
    assert task["query_outputs"] == [-5, 5, -1]
    assert task["identifiable"]["distinguishable"] == 5


def test_grading_parts_and_cli(integer_task, tmp_path):
    task, operators, tasks = integer_task
    reference = score_response(task, "Answer: " + task["answer_text"])
    assert reference["correct"] and reference["queries_correct"] == len(task["queries"])
    assert reference["definition_parses"] and reference["definition_matches_examples"]
    assert reference["definition_equivalent"] in ("proved", "checked on range")
    wrong = score_response(task, "Answer: 999\n999\n999\n" + task["reference_definition"])
    assert not wrong["correct"] and wrong["queries_correct"] == 0
    assert wrong["definition_equivalent"] in ("proved", "checked on range")
    bad_definition = score_response(task, "Answer: " + "\n".join(
        task["answer_text"].splitlines()[:3] + ["not a definition"]))
    assert bad_definition["queries_correct"] == 3 and not bad_definition["definition_parses"]
    assert main(["bench", "check", "--tasks", str(tasks), "--operators", str(operators)]) == 0
    replies = tmp_path / "replies.jsonl"
    replies.write_text(json.dumps({"id": task["id"], "response": "Answer: " + task["answer_text"]}) + "\n")
    summary = tmp_path / "summary.json"
    assert main(["bench", "score", "--tasks", str(tasks), "--responses", str(replies),
                 "--out", str(summary)]) == 0
    assert json.loads(summary.read_text())["induce"]["definition_parses"] == 1


def test_answer_modes(integer_task, tmp_path):
    _, operators, _ = integer_task
    for mode in ("predict", "define"):
        path = tmp_path / f"{mode}.jsonl"
        assert main(["bench", "build", "--operators", str(operators), "--out", str(path),
                     "--family", "induce", "--count", "1", "--seed", "1", "--answer", mode]) == 0
        task = json.loads(path.read_text())
        assert score_response(task, "Answer: " + task["answer_text"])["correct"]
        assert not score_response(task, "Answer: definitely invalid")["correct"]


def test_z3_refutes_a_rule_that_only_matches_the_stated_range(integer_task):
    original, _, _ = integer_task
    task = json.loads(json.dumps(original))
    lhs = task["reference_definition"].split(" = ", 1)[0]
    task["reference_definition"] = f"{lhs} = {{ a + b }}"
    task["known"] = []
    task["known_types"] = []
    task["answer_mode"] = "define"
    for row in task["examples"]:
        row["output"] = sum(row["inputs"])
    task["query_outputs"] = [sum(row["inputs"]) for row in task["queries"]]
    verdict = score_response(task, f"Answer: {lhs} = {{ a + b, if a <= 4; 0, else }}")
    assert verdict["definition_parses"] and verdict["definition_matches_examples"]
    assert verdict["definition_equivalent"] == "refuted with a counterexample"
    assert verdict["counterexample"]["a"] > 4
    assert not verdict["correct"]


def test_unary_hidden_rule(integer_task, tmp_path):
    _, operators, _ = integer_task
    path = tmp_path / "unary.jsonl"
    assert main(["bench", "build", "--operators", str(operators), "--out", str(path),
                 "--family", "induce", "--count", "1", "--seed", "4"]) == 0
    task = json.loads(path.read_text())
    assert task["arity"] == 1 and len(task["examples"]) == 6 and len(task["queries"]) == 3
    assert score_response(task, "Answer: " + task["answer_text"])["correct"]


@pytest.mark.parametrize("world", ["strings", "lists", "grid", "pitch", "perm", "rel", "logic", "clock"])
def test_worlds(world, tmp_path):
    registered = set(CUSTOM)
    try:
        _settings, registry, _ = world_spec(world).build()
        operators = tmp_path / "operators.jsonl"
        registry.to_jsonl(operators)
        config = tmp_path / "config.json"
        config.write_text(json.dumps({"preset": world}))
        path = tmp_path / "tasks.jsonl"
        assert main(["bench", "build", "--operators", str(operators), "--config", str(config),
                     "--out", str(path), "--family", "induce", "--count", "1", "--seed", "4"]) == 0
        task = json.loads(path.read_text())
        assert task["world"] == world
        assert task["atoms"] and task["input_range"]
        assert score_response(task, "Answer: " + task["answer_text"])["correct"]
    finally:
        for name in set(CUSTOM) - registered:
            unregister_primitive(name)
