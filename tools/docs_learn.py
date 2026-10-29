"""Build the small, interpreter-checked examples for the Learn page.

Run ``PYTHONPATH=src python3 tools/docs_learn.py``. ``--check`` compares the
committed data with a fresh evaluation without writing it.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from opulse.playground import run_json

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/assets/data/learn.json"

# Deliberately selected textbook-sized cases. The three worlds deliberately
# share a shape to show transfer across materials.
CASES = [
    ("atoms", "", "(3 + 4) * 2", "", "4 * 3", "atom"),
    ("substitution", "a ◆ b = { (a + b) * 2 }", "3 ◆ 4", "", "5 ◆ 1", "substitution"),
    ("layers", "a ◆ b = { (a + b) * 2 }\na ♣ b = { (a ◆ b) - a }", "3 ♣ 4", "", "5 ♣ 2", "layers"),
    ("branch_equal", "a ▲ b = { a - b, if a >= b; b - a, else }", "3 ▲ 3", "", "4 ▲ 4", "boundary"),
    ("recursion", "a ★ b = { 0, if b <= 0; (a ★ (b - 1)) + a, else }", "2 ★ 3", "", "3 ★ 4", "recursion"),
    ("prefix", "◇ a = { (a * a) + a }", "◇ 4", "", "◇ 3", "prefix"),
    ("postfix", "a ♠ = { (a * 2) + 1 }", "4 ♠", "", "3 ♠", "postfix"),
    ("call", "⊙(a, b, c) = { (a + b) - c }", "⊙(4, 3, 2)", "", "⊙(3, 5, 4)", "call"),
    ("strings", "a ◆ b = { (a ⊕ b) ⇥ }", '"sun" ◆ "day"', "strings", '"red" ◆ "wood"', "transfer"),
    ("lists", "a ◆ b = { (a ⊞ b) ⌄ }", "[1, 2] ◆ [3, 4]", "lists", "[2, 5] ◆ [7]", "transfer"),
    ("grid", "a ◆ = { (a ↻) ↻ }", "[[1, 2], [3, 4]] ◆", "grid", "[[1, 2, 3], [4, 5, 6]] ◆", "transfer"),
    ("next", "a ◈ b = { a, if a >= b; b, else }", "4 ◈ 7", "", "7 ◈ 4", "choice"),
]


def quality_filter(rule: str, expression: str, mode: str) -> None:
    """Reject common generated-puzzle defects before asking the interpreter."""
    if re.search(r"(?:\*|/)\s*1\b|\+\s*0\b|-\s*0\b|\*\s*0\b|0\s*\*|\(\s*a\s*-\s*a\s*\)", rule):
        raise ValueError("identity arithmetic")
    if re.search(r"-\s*\(\s*-", rule):
        raise ValueError("double negation")
    for line in rule.splitlines():
        lhs, body = line.split("=", 1)
        if re.fullmatch(r"\s*\{\s*(?:[abc]\s+[^\s{}]+\s+[abc]|[^\s{}]+\s+[abc]|[abc]\s+[^\s{}]+)\s*\}\s*", body):
            raise ValueError("pure alias")
        for parameter in re.findall(r"\b[abc]\b", lhs):
            if not re.search(rf"\b{parameter}\b", body):
                raise ValueError(f"unused parameter {parameter}")
        if mode not in {"recursion", "transfer"} and len(body) > 100:
            raise ValueError("rule too long for a first lesson")
    for number in re.findall(r"(?<!\w)-?\d+(?!\w)", expression):
        if abs(int(number)) > 9:
            raise ValueError("input outside human-sized range")


def evaluate(rule: str, expression: str, world: str) -> dict:
    result = json.loads(run_json(rule, expression, world=world))
    if not result.get("ok"):
        raise ValueError(f"{expression}: {result.get('error')}")
    if result.get("value") == "NaN" or not result.get("agrees") or result.get("truncated"):
        raise ValueError(f"unverified or undefined result: {expression}")
    if not result.get("steps"):
        raise ValueError(f"missing steps: {expression}")
    value = result["value"]
    if world == "" and abs(int(value)) > 100:
        raise ValueError(f"answer outside human-sized range: {expression}")
    return {"value": value, "steps": result["steps"]}


def build() -> list[dict]:
    assert len(CASES) == 12
    rows = []
    fingerprints = set()
    for id_, rule, expression, world, exercise, mode in CASES:
        quality_filter(rule, expression, mode)
        quality_filter(rule, exercise, mode)
        if rule and mode != "transfer":
            # Compare each case's new rule; a layered case may cite an earlier
            # rule as context, while the world trio intentionally shares shape.
            body = rule.splitlines()[-1].split("=", 1)[1]
            fingerprint = re.sub(r"\d+", "#", re.sub(r"\s+", "", body))
            if fingerprint in fingerprints:
                raise ValueError(f"near-copy of an earlier rule: {id_}")
            fingerprints.add(fingerprint)
        rows.append({"id": id_, "rule": rule, "expression": expression, "world": world,
                     "mode": mode, **evaluate(rule, expression, world),
                     "exercise": {"expression": exercise, **evaluate(rule, exercise, world)}})
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    data = json.dumps(build(), ensure_ascii=False, indent=2) + "\n"
    if args.check:
        if OUT.read_text(encoding="utf-8") != data:
            raise SystemExit("Learn data differs from interpreter output")
        print("12 Learn examples and exercises verified")
    else:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(data, encoding="utf-8")
        print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
