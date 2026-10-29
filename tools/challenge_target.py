"""Build finite Countdown-style target puzzles with the reference interpreter.

Search grammar: leaves are distinct given number cards; internal nodes are binary
operators from ``allowed``. Search considers at most ``size_limit`` applications,
all orders and parenthesizations, and deduplicates commutative mirror images.
The finite card set and operation limit make the search exhaustive without a
numerical cutoff. ``solutions_count`` counts distinct canonical expressions.
"""

from __future__ import annotations

import itertools
import json
import re
import sys
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from opulse.bench.families import common
from opulse.config import Symbols
from opulse.core.semantics import Semantics
from opulse.core.starting_sets import starting_registry
from opulse.definition import ast
from tools.challenge_shorten import quality_filter
from tools.audit_examples import Puzzle
from tools.example_registry import ExampleRegistry

OUTPUT = ROOT / "docs/assets/data/challenge/target.json"
SEED = 20261027
SYMBOLS = Symbols()
SEMANTICS = Semantics(bound=None)
BASE = starting_registry()

# A rule and a number-card set for each distinct puzzle-book mechanism.
# The selected target is the rarest interesting reachable result.
RECIPES = (
    ("easy", "◆", "a ◆ b = { (a * b) + (a - b) }", [2, 3, 5, 7], ["◆", "+"], 2,
     "◆ adds the signed gap to a product; swapping the cards changes that gap.",
     "◆ 把带方向的差加到乘积上；交换数字牌会改变这个差。"),
    ("easy", "◇", "a ◇ b = { (a * b) - (a $) }", [2, 4, 6, 9], ["◇", "-"], 2,
     "◇ subtracts the one-bit count of its left input from the product.",
     "◇ 从乘积中减去左参数的二进制置位数。"),
    ("easy", "♣", "a ♣ b = { a - b, if a >= b; (b - a) * 2, else }", [2, 3, 6, 8], ["♣", "+"], 2,
     "♣ doubles the distance only when the left card is smaller.",
     "♣ 只在左边的数字牌较小时，才把两数间的距离加倍。"),
    ("easy", "♠", "a ♠ b = { (# a) + b }", [2, 4, 6, 8], ["♠", "-"], 2,
     "♠ adds the triangular total of the left card to the right card.",
     "♠ 把左边数字牌的三角数加到右边的数字牌上。"),
    ("medium", "●", "a ● b = { a + b, if a + b <= 10; (a + b) - 10, else }", [3, 4, 7, 9], ["●", "-"], 3,
     "● removes ten from a sum above ten, so crossing the boundary changes the result.",
     "● 在和超过十时减去十；越过边界会改变计算结果。"),
    ("medium", "△", "a △ b = { a * b, if (a + b) % 2 == 0; a + b, else }", [2, 5, 7, 9], ["△", "+"], 3,
     "△ multiplies pairs with an even sum and adds pairs with an odd sum.",
     "△ 在两数之和为偶数时相乘，为奇数时相加。"),
    ("medium", "☆", "a ☆ b = { (a * a) - (b * b) }", [2, 3, 5, 9], ["☆", "+"], 3,
     "☆ takes the difference of two squares; reversing the cards changes its sign.",
     "☆ 求两个平方的差；交换数字牌会改变结果的正负号。"),
    ("medium", "⬡", "a ⬡ b = { (a * b) % 10 }", [2, 4, 7, 8], ["⬡", "+"], 3,
     "⬡ keeps the last digit of 2 times 8: six; adding 7 then reaches thirteen.",
     "⬡ 取 2 乘 8 的个位数，得到 6；再加 7 得到 13。"),
    ("medium", "⊙", "a ⊙ b = { (a + b) + a, if a <= b; (a + b) + b, else }", [2, 3, 6, 9], ["⊙", "-"], 3,
     "⊙ adds the smaller input twice; pairing different cards changes the bonus.",
     "⊙ 将较小的参数加两次；换一组数字牌，额外增加的数也会变。"),
    ("hard", "✦", "a ✦ b = { (a + b) * (a + b) }", [3, 5, 7, 9], ["✦", "-"], 3,
     "✦ squares 3 plus 5 to make 64; subtract the remaining 7 and 9 to reach 48.",
     "✦ 把 3 与 5 的和平方得到 64；再减去剩余的 7 和 9，得到 48。"),
    ("hard", "⊛", "a ⊛ b = { a * b, if a > b; a + b, else }", [2, 4, 5, 9], ["⊛", "+"], 3,
     "Both chosen pairs multiply because the larger card is on the left; reversing a pair would add.",
     "两组运算都把较大的牌放在左边，因此会相乘；将一组换序就会改为相加。"),
    ("hard", "◈", "a ◈ b = { (a * b) - (a + b) }", [2, 3, 7, 8], ["◈", "+"], 3,
     "◈ removes both inputs from their product; nesting changes the next pair.",
     "◈ 从乘积中减去两个参数；嵌套运算会改变下一对数字。"),
)


def _ops(rules):
    return common.text_registry([r["text"] for r in rules], BASE, SYMBOLS, SEMANTICS)


def _check_rules(rules):
    assert 1 <= len(rules) <= 3
    ops = _ops(rules)
    for rule in rules:
        definition = ops.parser.parse(rule["text"])
        assert definition.lhs.symbol == rule["symbol"]
        quality_filter(definition, {r["symbol"] for r in rules})
        if len(definition.branches) == 1:
            body = definition.branches[0].expr
            assert not (isinstance(body, ast.Apply) and body.symbol in {"+", "-", "*"}
                        and body.args == definition.lhs.args), "base-operation alias"
        # Both arguments must matter on small positive inputs.
        operator = next(op for op in ops.registry if op.symbol == rule["symbol"])
        values = {(a, b): ops.oracle.evaluate(operator, (a, b)).value
                  for a, b in itertools.product(range(1, 6), repeat=2)}
        assert any(values[a, 2] != values[a, 3] for a in range(1, 6))
        assert any(values[2, b] != values[3, b] for b in range(1, 6))
        assert all(type(v) is int and abs(v) <= 100 for v in values.values())


def _expression_nodes(node):
    if isinstance(node, ast.Num):
        yield node
    elif isinstance(node, ast.Apply):
        yield node
        for arg in node.args:
            yield from _expression_nodes(arg)
    else:
        raise AssertionError(node)


def check_answer(row, expression):
    """Parse, check card and operator usage, then evaluate with the oracle."""
    ops = _ops(row["rules"])
    parsed = ops.parser.parse_expr(expression, expression_mode=True)
    leaves = [n.value for n in _expression_nodes(parsed) if isinstance(n, ast.Num)]
    calls = [n for n in _expression_nodes(parsed) if isinstance(n, ast.Apply)]
    assert Counter(leaves) <= Counter(row["numbers"])
    assert 1 <= len(calls) <= row["size_limit"]
    assert all(n.n_ary == 2 and n.symbol in row["allowed"] for n in calls)
    assert any(n.symbol in {r["symbol"] for r in row["rules"]} for n in calls)
    assert ops.oracle.evaluate_expr(parsed, {}).value == row["target"]


def search(row):
    """Return all reachable targets and their canonical expression strings."""
    numbers = row["numbers"]
    ops = _ops(row["rules"])
    by_symbol = {name: next(op for op in ops.registry if op.symbol == name and op.n_ary == 2)
                 for name in row["allowed"]}
    custom = {r["symbol"] for r in row["rules"]}
    commutative = {"+", "*", "♣", "♠", "●", "△", "✦", "◈"}  # ◈ is symmetric.

    @lru_cache(None)
    def apply(symbol, left, right):
        value = ops.oracle.evaluate(by_symbol[symbol], (left, right)).value
        return value if type(value) is int else None

    states = {1 << i: {(n, str(n), False)} for i, n in enumerate(numbers)}
    for size in range(2, min(len(numbers), row["size_limit"] + 1) + 1):
        for mask in range(1, 1 << len(numbers)):
            if mask.bit_count() != size:
                continue
            found = set()
            sub = (mask - 1) & mask
            while sub:
                other = mask ^ sub
                if other and sub in states and other in states:
                    for left, right in itertools.product(states[sub], states[other]):
                        lv, lt, lc = left
                        rv, rt, rc = right
                        for symbol in row["allowed"]:
                            if symbol in commutative and lt > rt:
                                continue
                            # No inert or self-cancelling arithmetic in displayed solutions.
                            if symbol == "*" and (lv in (0, 1) or rv in (0, 1)):
                                continue
                            if symbol == "+" and (lv == 0 or rv == 0):
                                continue
                            if symbol == "-" and (rv == 0 or lt == rt):
                                continue
                            value = apply(symbol, lv, rv)
                            if value is None:
                                continue
                            found.add((value, f"({lt} {symbol} {rt})", lc or rc or symbol in custom))
                sub = (sub - 1) & mask
            states[mask] = found
    results = defaultdict(set)
    for mask, entries in states.items():
        if 2 <= mask.bit_count() <= row["size_limit"] + 1:
            for value, expression, uses_custom in entries:
                results[value].add((expression, uses_custom, mask.bit_count() - 1))
    return results


def _select(row):
    results = search(row)
    level = row["level"]
    max_count = {"easy": 10, "medium": 6, "hard": 3}[level]
    min_size = {"easy": 1, "medium": 2, "hard": 3}[level]
    if row["id"] in {"target-01", "target-04"}:  # Their insight needs a second move.
        min_size = 2
    candidates = []
    for target, solutions in results.items():
        if not 10 <= target <= 95 or not 1 <= len(solutions) <= max_count:
            continue
        if level == "hard" and any(not used for _, used, _ in solutions):
            continue
        eligible = sorted((size, expr) for expr, used, size in solutions
                          if used and size >= min_size)
        if row["id"] == "target-08":
            def wraps(expr):
                return any(int(a) * int(b) >= 10 for a, b in
                           re.findall(r"(\d+) ⬡ (\d+)", expr))
            eligible = [(size, expr) for size, expr in eligible if wraps(expr)]
        if not eligible:
            continue
        # Prefer a nontrivial target with very few answers and a full-size solution.
        candidates.append((len(solutions), -eligible[-1][0], abs(target - 50), target, eligible[0][1]))
    assert candidates, row["id"]
    _, _, _, target, solution = min(candidates)
    row["target"] = target
    row["solution"] = solution
    row["solutions_count"] = len(results[target])
    check_answer(row, solution)
    return row


def generate():
    rows = []
    exclusions = ExampleRegistry("docs/assets/data/challenge/target.json")
    for index, (level, symbol, text, numbers, allowed, limit, why, why_zh) in enumerate(RECIPES, 1):
        row = {"id": f"target-{index:02d}", "level": level, "why": why,
               "why_zh": why_zh, "rules": [{"symbol": symbol, "text": text}],
               "numbers": numbers, "allowed": allowed, "size_limit": limit,
               "target": None, "solution": None, "solutions_count": None, "verified": True}
        _check_rules(row["rules"])
        row = _select(row)
        exclusions.reserve(Puzzle("docs/assets/data/challenge/target.json", row["id"],
                                  "create", tuple(rule["text"] for rule in row["rules"]),
                                  "", "", tuple(sorted(row["numbers"]))))
        rows.append(row)
    assert Counter(r["level"] for r in rows) == {"easy": 4, "medium": 5, "hard": 3}
    assert len({r["target"] for r in rows}) >= 8
    signatures = []
    for row in rows:
        ops = _ops(row["rules"])
        operator = next(op for op in ops.registry if op.symbol == row["rules"][0]["symbol"])
        signatures.append(tuple(ops.oracle.evaluate(operator, pair).value
                                for pair in itertools.product(range(1, 5), repeat=2)))
    assert len(set(signatures)) == len(rows), "duplicate rule behavior"
    from tools.example_atoms import annotate
    return annotate({"schema": "opulse.challenge-mode/1", "mode": "target", "group": "create",
                     "seed": SEED, "challenges": rows})


def main():
    OUTPUT.write_text(json.dumps(generate(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
