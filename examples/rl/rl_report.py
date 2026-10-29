"""Tables comparing GRPO runs (Opulse tasks vs. a familiar-arithmetic control) for the docs.

    python examples/rl/rl_report.py --markdown docs/snippets/rl_results.md

Reads the transfer evaluations written by eval_transfer.py in outputs/rl.
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

RL = Path(__file__).resolve().parents[2] / "outputs" / "rl"
RUNS = {"before training": None, "Opulse tasks, seed 0": "q06b_run2", "Opulse tasks, seed 1": "q06b_run3",
        "familiar arithmetic (control)": "q06b_control"}
SEEDS = (11, 31, 47, 59)


def load(path: Path) -> dict:
    return json.loads(path.read_text())["results"]


def pct(x: float) -> str:
    return f"{100 * x:.1f}"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--markdown", type=Path, default=None)
    args = p.parse_args()
    transfer = {label: load(RL / (run or "q06b_run2") / ("transfer_step200.json" if run else "transfer_base.json"))
                for label, run in RUNS.items()}
    panel = {label: load(RL / f"panel_{ {None: 'base', 'q06b_run2': 'run2', 'q06b_run3': 'run3', 'q06b_control': 'control'}[run]}.json")
             for label, run in RUNS.items()}

    def pooled(results: dict, prefix: str) -> float:
        names = [prefix] + [f"{prefix}_{s}" for s in SEEDS[1:]]
        right = sum(sum(results[n]["correct"].values()) for n in names)
        return right / sum(results[n]["n"] for n in names)

    lines = ["| Training (200 steps) | Opulse small, 4 held-out sets | Opulse mid, 4 held-out sets | "
             "small, no definitions | GSM8K | SVAMP |", "|---|---|---|---|---|---|"]
    for label, r in transfer.items():
        lines.append(f"| {label} | {pct(pooled(r, 'small'))} | {pct(pooled(r, 'mid'))} | {pct(r['small_none']['accuracy'])} "
                     f"| {pct(r['gsm8k']['accuracy'])} | {pct(r['svamp']['accuracy'])} |")
    lines += ["", "| Training (200 steps) | 1 definition | 2–3 definitions | 4–8 definitions | contrast pairs, both right |",
              "|---|---|---|---|---|"]
    for label, r in panel.items():
        cells = [pct(statistics.mean(r[f"{c}_{s}"]["accuracy"] for s in SEEDS)) for c in ("d1", "d3", "d8")]
        both = total = 0
        for s in SEEDS:
            pairs: dict = {}
            for task_id, ok in r[f"contrast_{s}"]["correct"].items():
                pairs.setdefault(task_id[:-1], []).append(ok)
            both += sum(all(v) for v in pairs.values())
            total += len(pairs)
        lines.append(f"| {label} | " + " | ".join(cells) + f" | {pct(both / total)} |")
    text = "\n".join(lines) + "\n"
    print(text)
    if args.markdown:
        args.markdown.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
