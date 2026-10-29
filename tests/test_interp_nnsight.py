"""Exact labels and optional nnsight tracing on a cached tiny model."""

import json

import numpy as np
import pytest
from conftest import INITIAL_OPERATORS

pytest.importorskip("nnsight")
pytest.importorskip("torch")
pytest.importorskip("transformers")

from opulse.config import Settings
from opulse.core.registry import OperatorRegistry
from opulse.integrations.nnsight import (
    align_task,
    collect,
    counterfactual,
    load_model,
    patch,
    probe,
)


@pytest.fixture(scope="module")
def setup():
    model, tokenizer = load_model("hf-internal-testing/tiny-random-LlamaForCausalLM", "cpu")
    base = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
    expression = "2 ⊕ (3 + 4)"
    prompt = ("Rules:\n  - a + b is integer addition.\n\nDefinitions:\n"
              "a ⊕ b = { a + b }\n\nWhat is the value of `2 ⊕ (3 + 4)`?\nAnswer:")
    task = {"id": "compute-0", "family": "compute", "context": "full", "prompt": prompt,
            "expression": expression, "definitions": ["a ⊕ b = { a + b }"], "answer": 9}
    return model, tokenizer, base, Settings(), task


def test_alignment(setup):
    _, tokenizer, base, settings, task = setup
    rows = align_task(task, base, settings, tokenizer)
    assert {tuple(r["path"]): r["value"] for r in rows} == {
        (): 9, (0,): 2, (1,): 7, (1, 0): 3, (1, 1): 4}
    for row in rows:
        a, b = row["char_span"]
        assert task["prompt"][a:b] == row["text"]
        assert row["token_span"][0] <= row["position"] < row["token_span"][1]
    assert rows[0]["internal_steps"][-1]["value"] == 9


def test_defined_call_inside_branch_condition(setup):
    _, tokenizer, base, settings, _ = setup
    definitions = ["a ⊕ b = { a + b }", "a ⊗ b = { a, if (a ⊕ b) > 5; b, else }"]
    task = {"id": "branch-0", "family": "compute", "context": "full",
            "prompt": "Rules:\n\nDefinitions:\n" + "\n".join(definitions)
            + "\n\nWhat is the value of `2 ⊗ 5`?",
            "expression": "2 ⊗ 5", "definitions": definitions, "answer": 2}
    root = align_task(task, base, settings, tokenizer)[0]
    assert root["value"] == 2
    assert root["internal_steps"][0]["branch_index"] == 0
    assert root["internal_steps"][0]["condition"] is not None


def test_collection_shapes(setup, tmp_path):
    from opulse.canary import CANARY

    model, tokenizer, base, settings, task = setup
    report = collect([task], base, settings, model, tokenizer, [0, 1], tmp_path)
    bundle = np.load(tmp_path / "activations.npz")
    assert report["observations"] == 8
    assert bundle["activations"].shape[:2] == (8, 2)
    assert bundle["canary"].item() == CANARY
    metadata = [json.loads(line) for line in (tmp_path / "metadata.jsonl").read_text().splitlines()]
    assert all(row["meta"]["canary"] == CANARY for row in metadata)
    assert sum(row["site"] == "reduction_step" for row in metadata) == 2


def test_probe_operator_split():
    rng = np.random.default_rng(7)
    values = np.arange(-8, 8)
    x = np.stack([values, values * 2, np.ones(len(values))], axis=1)
    activations = np.stack([x + rng.normal(0, 0.01, x.shape), x], axis=1)
    rows = [{"site": "subexpression", "operator_id": "left" if i % 2 else "right",
             "value": int(v), "depth": i % 3} for i, v in enumerate(values)]
    result = probe(activations, rows, [-2, 2], seed=1)
    assert not set(result["train_operators"]) & set(result["test_operators"])
    assert len(result["layers"]) == 2
    assert result["layers"][1]["overall"]["mae"] < 3


def test_counterfactual_and_patch(setup, tmp_path):
    from opulse.canary import CANARY

    model, tokenizer, base, settings, task = setup
    pair = counterfactual(task, base, settings, tokenizer)
    assert pair is not None
    assert pair.clean_answer == 9 and pair.changed_answer == 10
    assert pair.clean_value == 9 and pair.changed_value == 10
    report = patch([task], base, settings, model, tokenizer, [0], tmp_path)
    assert report["patches"] == 1
    assert all(json.loads(line)["meta"]["canary"] == CANARY
               for line in (tmp_path / "patches.jsonl").read_text().splitlines())
    assert json.loads((tmp_path / "summary.json").read_text())["meta"]["canary"] == CANARY
