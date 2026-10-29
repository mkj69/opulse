"""Custom reward function for verl 0.9.1."""

from __future__ import annotations

from opulse.bench.reward import compute_score as opulse_compute_score


def compute_score(data_source: str, solution_str: str, ground_truth,
                  extra_info: dict | None = None) -> float:
    """Score a verl response using the mode stored in extra_info."""
    return opulse_compute_score(data_source, solution_str, ground_truth, extra_info)
