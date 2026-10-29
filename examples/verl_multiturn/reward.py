"""Score verl tool rollouts from the exact TextEnv step rewards."""

from __future__ import annotations


def compute_score(data_source: str, solution_str: str, ground_truth,
                  extra_info: dict | None = None) -> float:
    """Sum the tool rewards attached to one multi turn rollout by verl."""
    if data_source != "opulse_env":
        raise ValueError(f"unexpected data source: {data_source}")
    rewards = (extra_info or {}).get("tool_rewards", [])
    if not isinstance(rewards, (list, tuple)):
        raise TypeError("tool_rewards must be a sequence")
    return float(sum(rewards))
