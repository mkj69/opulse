"""Write verl rollout rows with deterministic Opulse episode seeds.

    python examples/verl_multiturn/prepare.py --operators ops.jsonl --out train.parquet

The tool config must point to the same operator file and environment options.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from opulse.env import BlackBoxEnv, SelfPlayEnv

INSTRUCTION = ("Use the opulse_step tool once for each action. Pass the entire QUERY or SUBMIT "
               "line as its action argument. Stop calling the tool when the episode ends.")


def rows(operators: str, settings: str | None, env_name: str, first_seed: int, episodes: int,
         turn_budget: int) -> list[dict]:
    """Construct verl rows without disclosing hidden answers in model prompts."""
    if env_name == "blackbox":
        env = BlackBoxEnv.from_files(operators, settings, turn_budget=turn_budget)
    elif env_name == "selfplay":
        env = SelfPlayEnv.from_files(operators, settings, attempts=turn_budget)
    else:
        raise ValueError("env must be blackbox or selfplay")
    result = []
    for seed in range(first_seed, first_seed + episodes):
        observation = env.reset(seed)
        result.append({
            "data_source": "opulse_env",
            "prompt": [{"role": "user", "content": observation + "\n\n" + INSTRUCTION}],
            "ability": f"opulse-{env_name}",
            "reward_model": {"style": "rule", "ground_truth": ""},
            "extra_info": {"seed": seed},
            "tools_kwargs": {"opulse_step": {"create_kwargs": {"seed": seed}}},
        })
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operators", required=True)
    parser.add_argument("--settings")
    parser.add_argument("--env", choices=("blackbox", "selfplay"), default="blackbox")
    parser.add_argument("--first-seed", type=int, default=0)
    parser.add_argument("--episodes", type=int, default=100)
    parser.add_argument("--turn-budget", type=int, default=20)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.episodes < 1:
        parser.error("--episodes must be positive")
    import pandas as pd  # optional dependency for Parquet output

    records = rows(args.operators, args.settings, args.env, args.first_seed, args.episodes,
                   args.turn_budget)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(records).to_parquet(args.out, index=False)


if __name__ == "__main__":
    main()
