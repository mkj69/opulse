"""Short, streaming description of data just written by a generation command."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


def _depth(tree: dict) -> int:
    children = [tree[key] for key in ("left_expr", "right_expr", "unary_expr") if key in tree]
    children.extend(tree.get("args", ()))
    return 1 + max((_depth(child) for child in children), default=0)


def print_data_summary(path: Path) -> None:
    """Show actual answers and depths without changing the generated JSONL."""
    answers: Counter[str] = Counter()
    depths: Counter[int] = Counter()
    total = undefined = 0
    with path.open(encoding="utf-8") as source:
        for line in source:
            if not line.strip():
                continue
            row = json.loads(line)
            total += 1
            answer = row.get("result") if "result" in row else row.get("answer")
            if row.get("undefined", answer is None) or answer is None:
                undefined += 1
            else:
                answers[json.dumps(answer, ensure_ascii=False, sort_keys=True)] += 1
            depth = (row.get("axes") or {}).get("expression_depth")
            if depth is None and "tree" in row:
                depth = _depth(row["tree"])
            if isinstance(depth, int):
                depths[depth] += 1
    defined = sum(answers.values())
    top = answers.most_common(5)
    values = ", ".join(f"{key[:40]}: {count}" for key, count in top) or "none"
    most_common = top[0][1] / defined if defined else 0.0
    top_two = sum(count for _, count in top[:2]) / defined if defined else 0.0
    depth_text = ", ".join(f"{depth}: {count}" for depth, count in sorted(depths.items())) or "none"
    print(f"Data summary ({total} records): top answers {values}; most common {most_common:.1%}; "
          f"NaN {undefined / total if total else 0:.1%}.")
    print(f"Depth histogram: {depth_text}.")
    if defined >= 10 and top_two > 0.30:
        print(f"Warning: the two most common answers make up {top_two:.1%} of defined answers. "
              "Use --max-answer-share 0.2 to spread answers; inspect more with opulse audit-data.")
