"""The TRL adapter can be graded without installing TRL or datasets."""

import json
import sys
import types

import pytest
from conftest import INITIAL_OPERATORS

from examples.trl.bridge import (
    dataset_from_tasks,
    outcome_reward,
    progress_reward,
    rows_from_tasks,
    steps_reward,
)

TASK = {
    "id": "compute-000001", "family": "compute", "prompt": "Evaluate (1 + 2) * (3 + 4).",
    "answer": 21, "format": "steps", "expression": "(1 + 2) * (3 + 4)",
    "definitions": [], "axes": {"naming": "symbols"},
}


def test_dataset_rows_and_optional_dataset_import(tmp_path, monkeypatch):
    path = tmp_path / "tasks.jsonl"
    path.write_text(json.dumps(TASK) + "\n", encoding="utf-8")

    class FakeDataset:
        @staticmethod
        def from_list(rows):
            return rows

    monkeypatch.setitem(sys.modules, "datasets", types.SimpleNamespace(Dataset=FakeDataset))
    rows = dataset_from_tasks(path, INITIAL_OPERATORS)
    assert rows == rows_from_tasks([TASK], INITIAL_OPERATORS)
    assert rows[0]["prompt"] == [{"role": "user", "content": TASK["prompt"]}]
    assert json.loads(rows[0]["ground_truth"])["answer"] == 21
    assert rows[0]["operators"] == str(INITIAL_OPERATORS.resolve())


def test_trl_reward_signature_and_values():
    row = rows_from_tasks([TASK], INITIAL_OPERATORS)[0]
    prompt = row["prompt"]
    full = "= 3 * (3 + 4)\n= 3 * 7\n= 21\nAnswer: 21"
    partial = "= 3 * (3 + 4)"
    completions = [[{"role": "assistant", "content": text}] for text in
                   (full, "Answer: 99", partial, "Answer: 21")]
    kwargs = {key: [row[key]] * len(completions) for key in ("ground_truth", "operators", "config")}
    kwargs.update(completion_ids=[[1]] * len(completions), trainer_state=object())
    prompts = [prompt] * len(completions)

    assert outcome_reward(prompts=prompts, completions=completions, **kwargs) == [1.0, 0.0, 0.0, 1.0]
    assert steps_reward(prompts=prompts, completions=completions, **kwargs) == [1.0, 0.0, 0.25, 0.5]
    assert progress_reward(prompts=prompts, completions=completions, **kwargs) == [1.0, 0.0, 1 / 6, 0.5]


def test_step_reward_requires_operators_and_matching_columns():
    row = rows_from_tasks([TASK])[0]
    with pytest.raises(ValueError, match="operators"):
        steps_reward([row["prompt"]], ["Answer: 21"], ground_truth=[row["ground_truth"]])
    with pytest.raises(ValueError, match="one value per completion"):
        outcome_reward([row["prompt"]], ["Answer: 21"], ground_truth=[])
