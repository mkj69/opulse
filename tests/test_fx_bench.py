"""Regressions for verified benchmark review findings."""

import json
import random

import pytest
from conftest import INITIAL_OPERATORS

from opulse.bench import client
from opulse.bench.check import answer_from_prompt, base_registry, check_tasks
from opulse.bench.context import rules_text, search_rule
from opulse.bench.families import common
from opulse.bench.families.equivalence import simplify_question
from opulse.bench.tasks import BenchBuilder
from opulse.config import Settings, Symbols
from opulse.core.operator import Operator
from opulse.core.registry import OperatorRegistry
from opulse.core.semantics import Semantics


@pytest.mark.parametrize("body", [
    "search(i, 4, (i + a) == b) + 1",
    "1, if search(i, 4, (i + a) == b) == 2; 0, else",
])
def test_nested_search_requires_prompt_rule(body):
    registry = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
    definition = f"a ⊕ b = {{ {body} }}"
    rule = search_rule("NaN")
    prompt = ("Rules:\n" + rules_text(["add"], Semantics()) + "\n" + rule +
              "\n\nDefinitions:\n" + definition + "\n\nWhat is the value of `1 ⊕ 3`?")
    task = {"family": "compute", "prompt": prompt, "definitions": [definition], "expression": "1 ⊕ 3"}
    assert answer_from_prompt(task, base_registry(registry)) == (1 if body.startswith("1,") else 3)
    with pytest.raises(ValueError, match="search rule"):
        answer_from_prompt({**task, "prompt": prompt.replace(rule + "\n", "")}, base_registry(registry))


def test_law_rejects_only_unsupported_arity():
    registry = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
    op = Operator(func_id="ternary", symbol="⊕", n_ary=3,
                  definition="⊕(a, b, c) = { (a + b) + c }")
    op.op_compute_func = "def op_ternary(a, b, c):\n    return 0\n"
    op.op_count_func = "def op_count_ternary(a, b, c):\n    return 0\n"
    registry.add(op)
    with pytest.raises(ValueError, match="law.*arity 1 or 2"):
        next(BenchBuilder(Settings(), registry, random.Random(0)).tasks("law", 1))


def test_ternary_definition_equivalence_lhs_is_a_parseable_call():
    symbols = Symbols()
    lhs = common.lhs_text("⊕", 3, None, symbols)
    assert lhs == symbols.call("⊕", symbols.operands(3))
    registry = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
    ops = common.text_registry(["⊕(a, b, c) = { (a + b) + c }"], base_registry(registry),
                               symbols, Semantics())
    assert common.expression(ops, lhs).operator.symbol == "⊕"
    question = simplify_question("⊕", "⊗", 3, None, 2, Semantics(), "NaN", symbols)
    assert "`⊗(a, b, c)` = `⊕(a, b, c)`" in question


def test_ternary_equivalence_task_uses_call_form():
    registry = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
    for index, (symbol, definition) in enumerate((
        ("⊕", "⊕(a, b, c) = { (a + b) + c }"),
        ("⊗", "⊗(a, b, c) = { a + (b + c) }"),
    )):
        op = Operator(func_id=f"ternary{index}", symbol=symbol, n_ary=3, definition=definition,
                      definition_type="simple_definition")
        op.op_compute_func = f"def op_ternary{index}(a, b, c):\n    return 0\n"
        op.op_count_func = f"def op_count_ternary{index}(a, b, c):\n    return 0\n"
        registry.add(op)
    task = next(BenchBuilder(Settings(), registry, random.Random(0)).tasks(
        "equivalence", 1, max_attempts=20)).to_dict()
    assert "(a, b, c)" in task["expression"]
    assert check_tasks([task], base_registry(registry)) == []


def test_run_tasks_requeries_changed_model_or_sampling(tmp_path, monkeypatch):
    task = {"id": "q", "prompt": "question"}
    out = tmp_path / "responses.jsonl"
    calls = []

    def fake_chat(base_url, model, prompt, max_tokens, temperature, api_key, extra):
        calls.append((model, temperature))
        return {"response": "new"}

    monkeypatch.setattr(client, "chat", fake_chat)
    old = {"id": "q", "prompt_hash": client.prompt_hash("question"), "response": "old",
           "model": "model-A", "sampling": {"temperature": 0.0, "max_tokens": None}}
    for changes in ({}, {"model": "model-B", "sampling": {"temperature": 0.5, "max_tokens": None}}):
        out.write_text(json.dumps({**old, **changes}) + "\n", encoding="utf-8")
        assert client.run_tasks([task], out, "http://localhost/v1", "model-B", concurrency=1) == 1
        assert json.loads(out.read_text())["response"] == "new"
    assert calls == [("model-B", 0.0), ("model-B", 0.0)]


def test_run_tasks_rejects_duplicate_input_ids(tmp_path, monkeypatch):
    monkeypatch.setattr(client, "chat", lambda *args, **kwargs: pytest.fail("sent duplicate task"))
    out = tmp_path / "responses.jsonl"
    with pytest.raises(ValueError, match="duplicate task id"):
        client.run_tasks([{"id": "q", "prompt": "first"}, {"id": "q", "prompt": "second"}],
                         out, "http://localhost/v1", "model-B", concurrency=2)
    assert not out.exists()
