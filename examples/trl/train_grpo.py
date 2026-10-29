"""Train GRPO on an Opulse benchmark JSONL file with TRL 1.16.0.

Example: python examples/trl/train_grpo.py tasks.jsonl MODEL output_dir
"""

from __future__ import annotations

import argparse
from pathlib import Path

from bridge import dataset_from_tasks, outcome_reward, progress_reward, steps_reward


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tasks", type=Path)
    parser.add_argument("model", help="model ID or local model directory")
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--reward", choices=("outcome", "steps", "progress"), default="outcome")
    parser.add_argument("--operators", type=Path, help="operator JSONL, required for step rewards")
    parser.add_argument("--config", type=Path, help="Opulse settings for a custom operator set")
    parser.add_argument("--max-steps", type=int, default=100)
    args = parser.parse_args(argv)
    if args.reward != "outcome" and not args.operators:
        parser.error("step and progress rewards require --operators")

    from trl import GRPOConfig, GRPOTrainer

    reward = {"outcome": outcome_reward, "steps": steps_reward, "progress": progress_reward}[args.reward]
    dataset = dataset_from_tasks(args.tasks, args.operators, args.config)
    config = GRPOConfig(output_dir=str(args.output_dir), max_steps=args.max_steps,
                        per_device_train_batch_size=4, num_generations=4, remove_unused_columns=False)
    trainer = GRPOTrainer(model=args.model, reward_funcs=reward, args=config, train_dataset=dataset)
    trainer.train()
    trainer.save_model()


if __name__ == "__main__":
    main()
