"""TRL 1.16.0 GRPO recipe using one Opulse environment per rollout.

    python examples/trl_multiturn/train.py --operators ops.jsonl --model MODEL

Running this script starts training. Importing it does not.
"""

from __future__ import annotations

import argparse

if __package__:
    from .environment import make_env_factory
else:
    from environment import make_env_factory

INSTRUCTION = ("Call the act tool with one QUERY or SUBMIT action at a time. "
               "Read each tool response before choosing the next action. "
               "Stop calling the tool when the episode ends.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operators", required=True)
    parser.add_argument("--settings")
    parser.add_argument("--env", choices=("blackbox", "selfplay"), default="blackbox")
    parser.add_argument("--model", required=True)
    parser.add_argument("--episodes", type=int, default=128)
    parser.add_argument("--turn-budget", type=int, default=20)
    parser.add_argument("--output-dir", default="outputs/trl_multiturn")
    args = parser.parse_args()
    if args.episodes < 1:
        parser.error("--episodes must be positive")

    from datasets import Dataset
    from trl import GRPOConfig, GRPOTrainer

    dataset = Dataset.from_dict({
        "prompt": [[{"role": "user", "content": INSTRUCTION}] for _ in range(args.episodes)],
        "seed": list(range(args.episodes)),
    })
    factory = make_env_factory(args.operators, args.settings, env=args.env,
                               turn_budget=args.turn_budget)
    trainer = GRPOTrainer(
        model=args.model,
        args=GRPOConfig(output_dir=args.output_dir,
                        max_tool_calling_iterations=args.turn_budget),
        train_dataset=dataset,
        environment_factory=factory,
    )
    trainer.train()


if __name__ == "__main__":
    main()
