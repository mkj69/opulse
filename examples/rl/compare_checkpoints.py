"""Compare checkpoint evaluations from eval_transfer.py problem by problem.

    python examples/rl/compare_checkpoints.py runs/grpo --markdown results.md

Reads ``transfer_<checkpoint>.json`` files and reports, per task set, accuracy at every
checkpoint and the change from ``base`` to the last checkpoint with an exact McNemar p-value.
Opulse sets of the same tier are also pooled.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path


def mcnemar(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("directory", type=Path)
    p.add_argument("--markdown", type=Path, default=None)
    args = p.parse_args()

    def step(path: Path) -> int:
        match = re.search(r"step(\d+)", path.stem)
        return int(match.group(1)) if match else 0

    runs = {path.stem.replace("transfer_", ""): json.loads(path.read_text())["results"]
            for path in sorted(args.directory.glob("transfer_*.json"), key=step)}
    names = list(runs)
    first, last = names[0], names[-1]
    sets = list(runs[first])
    groups = {"opulse small, 4 held-out sets": [s for s in sets if s == "small" or re.fullmatch(r"small_\d+", s)],
              "opulse mid, 4 held-out sets": [s for s in sets if s == "mid" or re.fullmatch(r"mid_\d+", s)]}
    rows = []
    for label, members in [(s, [s]) for s in sets] + list(groups.items()):
        cells = []
        for name in names:
            right = sum(sum(runs[name][s]["correct"].values()) for s in members)
            total = sum(runs[name][s]["n"] for s in members)
            cells.append(100 * right / total)
        b = c = 0
        for s in members:
            before, after = runs[first][s]["correct"], runs[last][s]["correct"]
            b += sum(before[i] and not after[i] for i in before)
            c += sum(after[i] and not before[i] for i in before)
        rows.append((label, cells, b, c, mcnemar(b, c)))
    lines = ["| Task set | " + " | ".join(names) + f" | {first} → {last}: lost / gained | p |",
             "|---|" + "---|" * (len(names) + 2)]
    for label, cells, b, c, pval in rows:
        lines.append(f"| {label} | " + " | ".join(f"{x:.1f}" for x in cells) + f" | {b} / {c} | {pval:.2g} |")
    text = "\n".join(lines) + "\n"
    print(text)
    if args.markdown:
        args.markdown.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
