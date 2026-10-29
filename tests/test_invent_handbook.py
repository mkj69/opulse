"""Prompt grounded invention and handbook tasks."""

import copy
import json
import random
import re

import pytest

from opulse.bench.check import base_registry, check_tasks
from opulse.bench.families import common
from opulse.bench.families.invent import bounded_recursion, reduction
from opulse.bench.reward import compute_score, rl_record
from opulse.bench.score import score_response
from opulse.bench.tasks import BenchBuilder
from opulse.cli.main import main
from opulse.config import Settings
from opulse.core.registry import OperatorRegistry
from opulse.definition import ast
from opulse.generation.recursive import REC, RecursiveSpec, recursive_draft


@pytest.fixture(scope="module")
def registry_path(tmp_path_factory):
    path = tmp_path_factory.mktemp("invent") / "operators.jsonl"
    assert main(["operators", "--out", str(path), "--layers", "10", "6", "3", "--seed", "6"]) == 0
    return path


@pytest.fixture(scope="module")
def registry(registry_path):
    return OperatorRegistry.from_jsonl(registry_path)


def build(registry, family, count, seed=0, **options):
    builder = BenchBuilder(Settings(), registry, random.Random(seed), min_definitions=0)
    return [task.to_dict() for task in builder.tasks(family, count, **options)]


def check(registry, tasks):
    settings = Settings()
    return check_tasks(tasks, base_registry(registry), settings.symbols, settings.semantics.build())


def test_invent_reference_partial_reward_and_determinism(registry):
    tasks = build(registry, "invent", 4, seed=2, invent_k=2, problems=6)
    assert tasks == build(registry, "invent", 4, seed=2, invent_k=2, problems=6)
    assert check(registry, tasks) == []
    arities = [t["axes"]["arity"] for t in tasks]
    assert len(set(arities)) >= 2
    assert max(arities.count(arity) for arity in set(arities)) - min(
        arities.count(arity) for arity in set(arities)) <= 1
    task = next(t for t in tasks if len(t["answer"]) == 2)
    full = score_response(task, "Answer: " + task["answer_text"])
    partial = score_response(task, "Answer: " + task["answer"][0])
    assert full["score"] == 1 and all(p["equivalent"] for p in full["proposals"])
    assert 0 < partial["score"] < 1
    assert score_response(task, "Answer: none")["score"] == 0
    truth = rl_record(task)["reward_model"]["ground_truth"]
    assert compute_score("opulse", "Answer: " + task["answer"][0], truth) == partial["score"]


def test_invent_invalid_proposals_and_prompt_tampering(registry):
    task = build(registry, "invent", 1, seed=1)[0]
    definition = task["answer"][0]
    assert score_response(task, "Answer: " + definition + " || " + definition)["reason"] == "too many definitions"
    wrong_arity = "§ a = { a + 1 }" if task["axes"]["arity"] == "binary" else "a § b = { a + b }"
    assert score_response(task, "Answer: " + wrong_arity)["reason"] == "invalid definition"
    lhs = {"binary": "a § b", "prefix unary": "§ a", "postfix unary": "a §"}[task["axes"]["arity"]]
    assert score_response(task, f"Answer: {lhs} = {{ unknown a }}")["reason"] == "invalid definition"
    assert score_response(task, f"Answer: {lhs} = {{ {lhs} }}")["reason"] == "invalid definition"
    assert score_response(task, "reasoning without a final line")["score"] == 0
    assert score_response(task, "Answer: " + definition)["score"] == 1
    tampered = copy.deepcopy(task)
    tampered["prompt"] = tampered["prompt"].replace("1. ", "2. ", 1)
    assert check(registry, [tampered])
    tampered = copy.deepcopy(task)
    tampered["axes"]["reference_reduction"] += 1
    assert check(registry, [tampered])
    tampered = copy.deepcopy(task)
    tampered["prompt"] = re.sub(r"  - .*\n", "", tampered["prompt"], count=1)
    assert check(registry, [tampered])


def test_rewriter_matches_repeated_variables_and_takes_positive_savings():
    pattern = ast.Definition(ast.Apply("§", (ast.Var("a"),), "prefix"),
                             (ast.Branch(ast.Apply("+", (ast.Var("a"), ast.Var("a")))),))
    same = ast.Apply("+", (ast.Num(3), ast.Num(3)))
    different = ast.Apply("+", (ast.Num(3), ast.Num(4)))
    assert reduction([same, different], [pattern]) == 1
    assert reduction([same], []) == 0


def test_only_bounded_recursive_template_is_accepted(registry):
    settings = Settings()
    visible = common.text_registry([], base_registry(registry), settings.symbols, settings.semantics.build())
    callee = visible.registry.find("+", 2)
    spec = RecursiveSpec("§", 1, "prefix", callee, "a", 3, (REC, "a"), ast.Var("a"))
    definition = recursive_draft(spec, settings.symbols).definition
    assert bounded_recursion(definition, visible, settings.symbols)
    unsafe = ast.Definition(definition.lhs, (ast.Branch(ast.Apply("§", (ast.Var("a"),), "prefix")),))
    assert not bounded_recursion(unsafe, visible, settings.symbols)


def test_handbook_positions_answers_files_and_determinism(registry, tmp_path):
    inline = build(registry, "handbook", 8, seed=3, handbook_size=12)
    assert inline == build(registry, "handbook", 8, seed=3, handbook_size=12)
    assert check(registry, inline) == []
    assert all(len(t["definitions"]) == 12 and t["axes"]["handbook_size"] == 12 for t in inline)
    assert len({tuple(t["axes"]["needed_positions"]) for t in inline}) > 1
    assert all(score_response(t, "Answer: " + t["answer_text"])["correct"] for t in inline)
    external = build(registry, "handbook", 2, seed=3, handbook_size=12, handbook_dir=tmp_path)
    assert check(registry, external) == []
    for task in external:
        assert "Read handbook file:" in task["prompt"] and "\nHandbook:\n" not in task["prompt"]
    file = tmp_path / "handbook-000000.txt"
    original = file.read_text(encoding="utf-8")
    file.write_text(original.replace("1. ", "2. ", 1), encoding="utf-8")
    assert check(registry, external)


def test_handbook_prompt_and_axis_tampering(registry):
    task = build(registry, "handbook", 1, seed=4, handbook_size=12)[0]
    changed = copy.deepcopy(task)
    changed["axes"]["needed_positions"] = []
    assert check(registry, [changed])
    changed = copy.deepcopy(task)
    changed["prompt"] = changed["prompt"].replace("1. ", "2. ", 1)
    assert check(registry, [changed])
    changed = copy.deepcopy(task)
    changed["answer"] = 123456789
    assert check(registry, [changed])


def test_cli_build_choices_and_external_handbook(registry_path, tmp_path):
    invent = tmp_path / "invent.jsonl"
    handbook = tmp_path / "handbook.jsonl"
    directory = tmp_path / "texts"
    assert main(["bench", "build", "--operators", str(registry_path), "--out", str(invent),
                 "--family", "invent", "--count", "1", "--min-definitions", "0",
                 "--invent-k", "2", "--invent-problems", "5", "--seed", "2"]) == 0
    assert main(["bench", "build", "--operators", str(registry_path), "--out", str(handbook),
                 "--family", "handbook", "--count", "1", "--handbook-size", "12",
                 "--handbook-needed", "2", "--handbook-dir", str(directory), "--seed", "2"]) == 0
    assert main(["bench", "check", "--operators", str(registry_path), "--tasks", str(invent)]) == 0
    assert main(["bench", "check", "--operators", str(registry_path), "--tasks", str(handbook)]) == 0
    assert (directory / "handbook-000000.txt").exists()
    for tasks in (invent, handbook):
        responses = tmp_path / f"{tasks.stem}-responses.jsonl"
        summary = tmp_path / f"{tasks.stem}-summary.json"
        assert main(["bench", "run", "--tasks", str(tasks), "--out", str(responses), "--reference"]) == 0
        assert main(["bench", "score", "--tasks", str(tasks), "--responses", str(responses),
                     "--out", str(summary)]) == 0
        assert json.loads(summary.read_text(encoding="utf-8"))["accuracy"] == 1


def test_invent_names_call_form_shapes():
    from opulse.bench.families.invent import LIMIT, shape_label

    assert shape_label(2, None) == "binary" and shape_label(1, "postfix") == "postfix unary"
    assert shape_label(3, None) == "3-argument"
    assert LIMIT.search("Propose up to 2 new 3-argument definitions with fresh").group(2) == "3-argument"
