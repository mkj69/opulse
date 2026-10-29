"""The verl example writes its schema and uses Opulse's checked rewards."""

import json
from pathlib import Path

import pytest
from conftest import INITIAL_OPERATORS

from examples.verl.prepare_data import prepare_data
from examples.verl.reward import compute_score
from opulse.bench.reward import rl_record


def _task() -> dict:
    return {
        "id": "example-1", "family": "compute", "format": "steps",
        "prompt": "What is the value of `(1 + 2) * (3 + 4)`?",
        "expression": "(1 + 2) * (3 + 4)", "definitions": [],
        "answer": 21, "nan": "NaN", "axes": {"naming": "symbols", "definitions_needed": 0},
    }


def test_parquet_schema_and_record(tmp_path):
    pq = pytest.importorskip("pyarrow.parquet")
    tasks = tmp_path / "tasks.jsonl"
    tasks.write_text(json.dumps(_task()) + "\n", encoding="utf-8")
    out = tmp_path / "train.parquet"
    assert prepare_data(tasks, out, "train", "steps", INITIAL_OPERATORS) == 1

    table = pq.read_table(out)
    assert table.column_names == ["data_source", "prompt", "ability", "reward_model", "extra_info"]
    row = table.to_pylist()[0]
    assert row["data_source"] == "opulse"
    assert row["prompt"] == [{"role": "user", "content": _task()["prompt"]}]
    assert row["ability"] == "opulse-compute"
    assert row["reward_model"]["style"] == "rule"
    assert json.loads(row["reward_model"]["ground_truth"])["answer"] == 21
    assert row["extra_info"]["split"] == "train"
    assert row["extra_info"]["reward_mode"] == "steps"
    assert Path(row["extra_info"]["operators"]) == INITIAL_OPERATORS.resolve()
    assert json.loads(row["extra_info"]["axes"])["naming"] == "symbols"

    outcome_out = tmp_path / "outcome.parquet"
    assert prepare_data(tasks, outcome_out, "val", "outcome") == 1
    outcome_info = pq.read_table(outcome_out).to_pylist()[0]["extra_info"]
    assert outcome_info["reward_mode"] == "outcome"
    assert "operators" not in outcome_info


def test_reward_modes_on_correct_wrong_and_partial_derivations():
    row = rl_record(_task(), operators=str(INITIAL_OPERATORS))
    truth = row["reward_model"]["ground_truth"]
    info = row["extra_info"]
    full = "= 3 * (3 + 4)\n= 3 * 7\n= 21\nAnswer: 21"
    partial = "= 3 * (3 + 4)"
    wrong = "= 123456789\nAnswer: 22"

    assert compute_score("opulse", full, truth, {**info, "reward_mode": "outcome"}) == 1.0
    assert compute_score("opulse", wrong, truth, {**info, "reward_mode": "outcome"}) == 0.0
    assert compute_score("opulse", full, truth, {**info, "reward_mode": "steps"}) == 1.0
    assert compute_score("opulse", wrong, truth, {**info, "reward_mode": "steps"}) == 0.0
    assert compute_score("opulse", full, truth, {**info, "reward_mode": "progress"}) == 1.0
    assert compute_score("opulse", wrong, truth, {**info, "reward_mode": "progress"}) == 0.0
    assert 0 < compute_score("opulse", partial, truth, {**info, "reward_mode": "steps"}) < 0.5
    assert compute_score("opulse", partial, truth, {**info, "reward_mode": "progress"}) == pytest.approx(1 / 6)
    assert compute_score("opulse", "Answer: 21", truth, {**info, "reward_mode": "steps"}) == 0.5


def test_step_mode_requires_operator_file(tmp_path):
    tasks = tmp_path / "tasks.jsonl"
    tasks.write_text(json.dumps(_task()) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="needs --operators"):
        prepare_data(tasks, tmp_path / "train.parquet", "train", "progress")
