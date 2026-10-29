"""Step-format results of the outcome-reward and step-reward GRPO runs.

    python examples/rl/steps_report.py --markdown docs/snippets/rl_steps_results.md

For each model, over four held-out operator sets: final-answer accuracy, complete derivations
(every line a checked single rewrite ending at the right value), and the mean step credit.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from opulse.cli.bench import step_checker_for, summarize  # noqa: E402
from opulse.cli.operators import DEFAULT_CONFIG  # noqa: E402

S = ROOT / "outputs" / "rl" / "steps"
OPS = {11: ROOT / "outputs/eval/ops.jsonl", 31: ROOT / "outputs/stability/ops_31.jsonl",
       47: ROOT / "outputs/stability/ops_47.jsonl", 59: ROOT / "outputs/stability/ops_59.jsonl"}
MODELS = {"before training": S / "resp_base", "outcome reward": S / "outcome" / "resp_step200",
          "outcome + line-share step reward": S / "stepreward" / "resp_step200",
          "outcome + progress step reward": S / "progress" / "resp_step200"}


def read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--markdown", type=Path, default=None)
    args = p.parse_args()
    checkers = {seed: step_checker_for(path, DEFAULT_CONFIG) for seed, path in OPS.items()}
    lines = ["| Training (200 steps) | Final answer right | Complete derivations | Mean progress | Cut off |",
             "|---|---|---|---|---|"]
    for label, directory in MODELS.items():
        if not directory.exists():
            continue
        n = right = complete = 0
        credit = cut = 0.0
        for seed in OPS:
            tasks = read(S / f"test_steps_{seed}.jsonl")
            responses = read(directory / f"resp_steps_{seed}.jsonl")
            summary = summarize(tasks, responses, checkers[seed])
            k = summary["tasks"]
            n += k
            right += summary["accuracy"] * k
            complete += summary["steps"]["complete_derivations"] * summary["steps"]["graded"]
            by_id = {r["id"]: r for r in responses}
            for task in tasks:
                reply = by_id[task["id"]]
                cut += reply.get("finish_reason") == "length"
                if reply.get("finish_reason") != "length":
                    credit += checkers[seed](task, reply["response"])["progress"]
        lines.append(f"| {label} | {100 * right / n:.1f} | {100 * complete / n:.1f} | {credit / n:.2f} | "
                     f"{100 * cut / n:.1f}% |")
    text = "\n".join(lines) + "\n"
    print(text)
    if args.markdown:
        args.markdown.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
