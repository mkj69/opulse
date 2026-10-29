"""Regenerate the two widgets of the blog post (docs/blog/index.md) by running Opulse.

    python tools/blog_visuals.py

The post opens with one generated task: seed 12, `opulse operators --layers 10 6 --check-variety`,
then `opulse bench build --format steps --count 40 --min-definitions 2 --max-definitions 2 --seed 1`,
task compute-000025. This script rebuilds that task and writes

* docs/snippets/vis_blog_unfold.html: its reference reduction, one rewrite per frame;
* docs/snippets/vis_blog_steps.html: the step checker on the reference derivation and on the same
  derivation with the recursion count written wrong on line 2 (the final answer stays 258).

Generated operators are shown with the labels the post uses (◆₁, ◆₂); every value comes from the
library and every grade from the step checker.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from docs_visuals import Engine, num, pre, quiet, trace_payload, write_widget

from opulse.cli.operators import DEFAULT_CONFIG
from opulse.config import Settings
from opulse.core import OperatorRegistry
from opulse.expression.nodes import Number, from_ast
from opulse.trace.reducer import _replace_at
from opulse.verify.steps import check_steps

WORK = ROOT / "outputs" / "blog"
TASK_ID = "compute-000025"
LABELS = {"∏∆¬": "◆₁", "∨∀◆": "◆₂"}


def relabel(text: str) -> str:
    for symbol, label in LABELS.items():
        text = text.replace(symbol, label)
    return text


def write(name: str, kind: str, data: dict, static: str) -> None:
    write_widget(name, kind, json.loads(relabel(json.dumps(data, ensure_ascii=False))), relabel(static))


def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    ops, tasks = WORK / "ops12.jsonl", WORK / "st12.jsonl"
    for path in (ops, tasks):
        path.unlink(missing_ok=True)
    quiet(["operators", "--out", str(ops), "--layers", "10", "6", "--seed", "12", "--check-variety"])
    quiet(["bench", "build", "--operators", str(ops), "--out", str(tasks), "--format", "steps",
           "--count", "40", "--min-definitions", "2", "--max-definitions", "2", "--seed", "1"])
    task = next(t for t in map(json.loads, tasks.open(encoding="utf-8")) if t["id"] == TASK_ID)
    engine = Engine(Settings.load(DEFAULT_CONFIG), OperatorRegistry.from_jsonl(ops))
    tree = from_ast(engine.parser.parse_expr(task["expression"], expression_mode=True), engine.registry)

    data = trace_payload(engine, tree, engine.text(tree))
    write("blog_unfold", "unfold", data, pre("\n= ".join(f["text"] for f in data["frames"])))

    trace = engine.reducer().reduce(tree)
    answer = trace.value
    good = [engine.text(s.expression_after) for s in trace.steps]
    # The slip: on line 2, 31 % 9 is written as 3 instead of 4, so the recursion runs three times.
    step = trace.steps[1]
    slipped = _replace_at(step.expression_before, step.path, Number(3))
    rest = engine.reducer().reduce(slipped)
    bad = good[:1] + [engine.text(slipped)] + [engine.text(s.expression_after) for s in rest.steps]

    def grade(lines: list[str]) -> tuple[list[dict], dict]:
        rows, single = [], 0
        for k in range(1, len(lines) + 1):
            report = check_steps(tree, lines[:k], engine.parser, engine.registry, engine.oracle, answer)
            if report.first_error is not None:
                rows.append({"line": lines[k - 1], "status": "error", "message": report.errors[0]})
                rows += [{"line": t, "status": "skipped"} for t in lines[k:]]
                break
            rows.append({"line": lines[k - 1], "status": "single" if report.single_steps > single else "jump"})
            single = report.single_steps
        final = check_steps(tree, lines, engine.parser, engine.registry, engine.oracle, answer).to_dict()
        return rows, {k: final[k] for k in ("steps", "valid_steps", "first_error", "final_correct",
                                            "single_steps", "credit")}

    good_rows, good_report = grade(good)
    bad_rows, bad_report = grade(bad)
    steps = {"question": engine.text(tree), "answer": num(answer),
             "runs": [{"label": "reference derivation", "rows": good_rows, "report": good_report},
                      {"label": "recursion count written wrong on line 2", "rows": bad_rows,
                       "report": bad_report, "slip": 1, "wrong_answer": num(rest.value)}]}
    write("blog_steps", "steps", steps, pre(
        f"{steps['question']}\n" + "\n".join(f"= {r['line']}   [{r['status']}]" for r in good_rows)
        + "\n\nrecursion count written wrong on line 2:\n"
        + "\n".join(f"= {r['line']}   [{r['status']}{': ' + r['message'] if 'message' in r else ''}]"
                    for r in bad_rows)))
    print(f"answer {answer}; slipped derivation ends at {rest.value}; "
          f"first error {bad_report['first_error']}; {len(good)} reference lines")
    return 0


if __name__ == "__main__":
    sys.exit(main())
