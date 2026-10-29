"""Regressions from the benchmark review."""

import json

import pytest
from conftest import INITIAL_OPERATORS

from opulse.bench.check import base_registry, check_tasks
from opulse.bench.client import run_tasks
from opulse.bench.context import rules_text
from opulse.bench.score import score_response
from opulse.bench.splits import leakage
from opulse.cli.bench import summarize
from opulse.cli.main import main
from opulse.core.operator import Operator
from opulse.core.registry import OperatorRegistry
from opulse.core.semantics import Semantics


def _task():
    registry = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
    task = {"id": "compute-000000", "family": "compute", "context": "full", "definitions": [],
            "expression": "7 + 8", "answer": 15, "answer_text": "15", "axes": {},
            "prompt": "Rules:\n" + rules_text(["add"], Semantics()) + "\n\nWhat is the value of `7 + 8`?"}
    return task, registry


def test_finding_1_internal_space_is_not_a_number():
    assert not score_response({"answer": 15}, "Answer: 1 5")["correct"]
    assert score_response({"answer": [1, 5]}, "Answer: {1, 5}")["correct"]


def test_finding_3_steps_require_shown_definitions(tmp_path):
    out = tmp_path / "tasks.jsonl"
    operators = tmp_path / "operators.jsonl"
    assert main(["operators", "--out", str(operators), "--layers", "2", "--seed", "4"]) == 0
    with pytest.raises(SystemExit, match="steps.*context|context.*steps"):
        main(["bench", "build", "--operators", str(operators), "--out", str(out),
              "--count", "1", "--format", "steps", "--context", "none"])
    assert not out.exists()


def test_finding_4_cli_checks_holes_and_reports_uncheckable_context(tmp_path, capsys):
    hole = {"id": "hole-000000", "family": "hole", "context": "full", "definitions": [],
            "expression": "x + 1", "answer": 1, "answer_text": "1", "axes": {"search_domain": [-2, 2]},
            "prompt": ("Rules:\n" + rules_text(["add"], Semantics()) +
                       "\n\nFind the integer x with -2 <= x <= 2 such that `x + 1` = 2. "
                       "Exactly one such x exists.")}
    wrong = {**hole, "answer": hole["answer"] + 1, "answer_text": str(hole["answer"] + 1)}
    path = tmp_path / "tasks.jsonl"
    path.write_text(json.dumps(wrong, ensure_ascii=False) + "\n", encoding="utf-8")
    assert main(["bench", "check", "--tasks", str(path), "--operators", str(INITIAL_OPERATORS)]) == 1
    assert hole["id"] in capsys.readouterr().out
    hidden = {**hole, "context": "none", "definitions": [],
              "prompt": hole["prompt"] + "\nDefinitions not given."}
    path.write_text(json.dumps(hidden, ensure_ascii=False) + "\n", encoding="utf-8")
    assert main(["bench", "check", "--tasks", str(path), "--operators", str(INITIAL_OPERATORS)]) == 1
    assert "not checkable from the prompt" in capsys.readouterr().out


def test_finding_5_changed_bound_is_rejected():
    task, registry = _task()
    assert check_tasks([task], base_registry(registry)) == []
    changed = {**task, "prompt": task["prompt"].replace("larger than 2147483647", "larger than 1")}
    assert changed["prompt"] != task["prompt"]
    assert check_tasks([changed], base_registry(registry))


def test_finding_6_answer_text_must_match_answer():
    task, registry = _task()
    changed = {**task, "answer_text": "999"}
    assert check_tasks([changed], base_registry(registry))


def test_finding_7_resume_and_score_reject_a_different_prompt(tmp_path, monkeypatch):
    from opulse.bench import client

    task = {"id": "compute-000000", "prompt": "new question", "answer": 31, "axes": {}}
    out = tmp_path / "responses.jsonl"
    out.write_text(json.dumps({"id": task["id"], "model": "model", "response": "Answer: 15"}) + "\n")
    calls = []

    def fake_chat(base_url, model, prompt, max_tokens, temperature, api_key, extra):
        calls.append(prompt)
        return {"response": "Answer: 31"}

    monkeypatch.setattr(client, "chat", fake_chat)
    assert run_tasks([task], out, "http://localhost/v1", "model", concurrency=1) == 1
    assert calls == [task["prompt"]]
    row = json.loads(out.read_text().splitlines()[0])
    assert summarize([task], [{**row, "prompt_hash": "wrong"}])["accuracy"] == 0.0
    assert summarize([task], [{"id": task["id"], "model": "old", "response": "Answer: 31"}])["accuracy"] == 0.0


def test_finding_8_sampled_behaviour_is_only_a_candidate():
    def one(symbol, definition, fid):
        registry = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
        op = Operator(func_id=fid, symbol=symbol, n_ary=2, definition=definition)
        op.op_compute_func = f"def op_{fid}(a, b):\n    return 0\n"
        op.op_count_func = f"def count_{fid}(a, b):\n    return 0\n"
        registry.add(op)
        return registry

    train = one("♧", "a ♧ b = { 0 }", "constant")
    test = one("♢", "a ♢ b = { 1, if a == 4; 0, else }", "spike")
    report = leakage(train, test)
    assert report["structural"]["shared"] == 0
    assert report["behavioural"]["shared"] == 0
    assert report["behavioural"]["candidates"] == 1
    same_symbol = one("♧", "a ♧ b = { 1, if a == 4; 0, else }", "spike")
    assert leakage(train, same_symbol)["behavioural"]["shared"] == 0
    addition = one("♡", "a ♡ b = { a + b }", "addition")
    reversed_addition = one("♤", "a ♤ b = { b + a }", "reversed")
    assert leakage(addition, reversed_addition)["behavioural"]["shared"] == 1


def test_negative_answer_written_with_a_space_is_read():
    from opulse.bench.score import parse_value

    assert parse_value("- 7") == -7 and parse_value("-7") == -7
    assert parse_value("1 5") is None and parse_value("- 1 5") is None
