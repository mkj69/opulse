"""Turn a curriculum choice into the row formats used by the verl and TRL examples."""

from __future__ import annotations

from opulse.bench.reward import rl_record
from opulse.env.curriculum import CurriculumChoice, CurriculumSampler


def next_verl_row(sampler: CurriculumSampler, *, split: str = "train",
                  operators: str | None = None, config: str | None = None) -> tuple[CurriculumChoice, dict]:
    """Return one exact reward row for the verl single turn data pipeline."""
    choice, task = sampler.sample()
    row = rl_record(task, split=split, operators=operators, config=config)
    row["extra_info"]["difficulty_cell"] = choice.cell.to_dict()
    return choice, row


def next_trl_row(sampler: CurriculumSampler, *, operators: str = "",
                 config: str = "") -> tuple[CurriculumChoice, dict]:
    """Return one row with the columns expected by examples/trl/bridge.py."""
    choice, task = sampler.sample()
    record = rl_record(task)
    return choice, {"prompt": record["prompt"],
                    "ground_truth": record["reward_model"]["ground_truth"],
                    "operators": operators, "config": config,
                    "difficulty_cell": choice.cell.to_dict()}


def observe_reward(sampler: CurriculumSampler, choice: CurriculumChoice, reward: float) -> dict:
    """Record the exact reward after the learner has answered the sampled task."""
    return sampler.observe(reward > 0, choice=choice)
