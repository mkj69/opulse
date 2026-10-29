"""Convert Opulse tasks and adapt their exact rewards for TRL GRPOTrainer.

The optional ``datasets`` dependency is imported only when creating a Dataset.
"""

from __future__ import annotations

import json
from pathlib import Path

from opulse.bench.reward import compute_score, rl_record


def rows_from_tasks(tasks: list[dict], operators: Path | None = None,
                    config: Path | None = None) -> list[dict]:
    """Return rows with a conversational prompt and the columns needed by rewards."""
    rows = []
    for task in tasks:
        record = rl_record(task)
        rows.append({
            "prompt": record["prompt"],
            "ground_truth": record["reward_model"]["ground_truth"],
            "operators": str(operators.resolve()) if operators else "",
            "config": str(config.resolve()) if config else "",
        })
    return rows


def dataset_from_tasks(path: Path, operators: Path | None = None, config: Path | None = None):
    """Read benchmark JSONL and return a ``datasets.Dataset`` for GRPOTrainer."""
    from datasets import Dataset

    tasks = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not tasks:
        raise ValueError(f"no benchmark tasks in {path}")
    return Dataset.from_list(rows_from_tasks(tasks, operators, config))


def _completion_text(completion) -> str:
    if isinstance(completion, str):
        return completion
    if isinstance(completion, list) and completion:
        content = completion[-1].get("content")
        if isinstance(content, str):
            return content
    raise ValueError("expected text or conversational assistant completion")


def _rewards(mode: str, prompts, completions, **kwargs) -> list[float]:
    truths = kwargs["ground_truth"]
    operators = kwargs.get("operators", [""] * len(completions))
    configs = kwargs.get("config", [""] * len(completions))
    if not (len(prompts) == len(completions) == len(truths) == len(operators) == len(configs)):
        raise ValueError("reward columns must have one value per completion")
    rewards = []
    for completion, truth, operator_path, config_path in zip(completions, truths, operators, configs, strict=True):
        task = json.loads(truth) if isinstance(truth, str) else truth
        if mode != "outcome" and task.get("format") == "steps" and not operator_path:
            raise ValueError("step rewards require an operators file")
        info = {"reward_mode": mode, "operators": operator_path, "config": config_path}
        rewards.append(compute_score("opulse", _completion_text(completion), task, info))
    return rewards


def outcome_reward(prompts, completions, **kwargs) -> list[float]:
    """One reward per completion: 1 for the exact final answer, else 0."""
    return _rewards("outcome", prompts, completions, **kwargs)


def steps_reward(prompts, completions, **kwargs) -> list[float]:
    """Mean of final answer credit and checked single rewrite credit."""
    return _rewards("steps", prompts, completions, **kwargs)


def progress_reward(prompts, completions, **kwargs) -> list[float]:
    """Mean of final answer credit and reference derivation progress."""
    return _rewards("progress", prompts, completions, **kwargs)
