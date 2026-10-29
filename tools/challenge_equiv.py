"""Publish twelve reproducible, reference-checked equivalence puzzles.

The advertised domain is the inclusive range of each free integer input.  A
``range`` proof checks its Cartesian square exhaustively; a ``z3`` proof is
stronger and covers all integers under the unbounded exact semantics.
"""

from __future__ import annotations

import argparse
import itertools
import json
import random
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from opulse.config import Symbols
from opulse.core import BRANCH, NAN, SIMPLE, Operator, OperatorRegistry, Semantics
from opulse.core.starting_sets import starting_registry
from opulse.expression.nodes import from_ast
from opulse.solver.equivalence import EquivalenceChecker
from opulse.solver.z3_encode import Z3Encoder
from opulse.verify import Oracle

OUTPUT = ROOT / "docs/assets/data/challenge/equiv.json"
SEED = 20261026
DOMAIN = [-5, 5]
SYMBOLS = ("◆", "♣", "◇", "★", "▲", "●", "■", "♥", "♠", "♧", "✦", "⬟", "✧", "⬢")


@dataclass(frozen=True)
class Recipe:
    level: str
    same: bool
    bodies: tuple[str, ...]
    left: str
    right: str
    hints: tuple[str, ...]
    why: str
    why_zh: str


# The six false pairs agree throughout [-2, 2].  Each row illustrates a
# different algebraic identity or a different shape of exceptional input.
RECIPES = (
    Recipe("easy", True, ("(a * b) - a",), "a {s} b", "a * (b - 1)",
           ("Remove one copy of a from the product.",),
           "Subtracting a removes one copy of a from the factor b.",
           "减去一个 a，就等于在乘数 b 中减去一。"),
    Recipe("easy", False, ("a + b, if a <= {t}; a - b, else",),
           "a {s} b", "a + b",
           ("Add below the boundary; subtract above it.",),
           "The rule changes from addition to subtraction only when a crosses the boundary.",
           "只有 a 越过边界时，规则才从加法切换为减法。"),
    Recipe("easy", True, ("a - (b - a)",), "a {s} b", "(2 * a) - b",
           ("Subtract the gap from b back to a.",),
           "Subtracting b minus a leaves two copies of a minus b.",
           "减去 b 减 a 后，留下两份 a 再减 b。"),
    Recipe("easy", False, ("a - b, if b - a <= {t}; (a - b) * 2, else",),
           "a {s} b", "a - b",
           ("Double the signed gap when b is much larger.",),
           "The signed difference is doubled only when b exceeds a by more than the boundary.",
           "只有 b 比 a 大出超过边界的数值时，带符号的差才加倍。"),
    Recipe("medium", True, ("(a + b) * (a - b)",),
           "a {s} b", "(a * a) - (b * b)",
           ("Multiply a sum by the corresponding difference.",),
           "The product of a sum and a difference expands to two squares.",
           "和与差相乘展开后是两个平方之差。"),
    Recipe("medium", False, ("a * b, if a * b <= {t}; (a - 1) * b, else",),
           "a {s} b", "a * b",
           ("Above the limit, use one fewer copy of b.",),
           "Small products agree; above the limit, reducing a by one changes the result by b.",
           "小乘积相同；越过界线后，a 少一会使结果变化一个 b。"),
    Recipe("medium", True, ("(a * b) + (b * a)",),
           "a {s} b", "(2 * a) * b",
           ("Add the product in both input orders.",),
           "Swapping factors leaves the product unchanged, so the two products make twice a times b.",
           "交换乘数不改变乘积，因此两个乘积相加等于 a 乘 b 的两倍。"),
    Recipe("medium", False,
           ("a + b, if (a - b) * (a - b) <= {t}; (a + b) + (a - b), else",),
           "a {s} b", "a + b",
           ("A wide gap adds the signed difference to the sum.",),
           "Nearby inputs keep their sum; a gap beyond the squared boundary adds their signed difference.",
           "两数接近时只取和；差的平方越过边界时，还要加上带符号的差。"),
    Recipe("medium", True, ("(a * a) + (b * b)",),
           "(a {s} b) + ((2 * a) * b)", "(a + b) * (a + b)",
           ("Return the sum of the two squares.",),
           "The missing cross term sits outside the rule, completing the square.",
           "规则内只有两个平方，规则外的交叉项把它补成完整平方。"),
    Recipe("hard", False,
           ("a * b, if a <= {t} or b <= {t}; a + b, else",),
           "a {s} b", "a * b",
           ("Both inputs must cross the boundary before addition replaces multiplication.",),
           "Either small input keeps multiplication; only two large inputs switch to addition.",
           "只要有一个输入较小就仍然相乘；两个输入都较大才改为相加。"),
    Recipe("hard", True, ("((a * b) + a) + b",),
           "(a {s} (b + 2)) + 1", "(a + 1) * (b + 3)",
           ("Count the rectangle and one extra row and column.",),
           "Adding two to b expands the hidden rectangle into factors a plus one and b plus three.",
           "先给 b 加二，隐藏的长方形就能补成 a 加一与 b 加三的乘积。"),
    Recipe("hard", False, ("a * b, if a * b >= -{t}; (a * b) / 2, else",),
           "a {s} b", "a * b",
           ("A sufficiently large negative product is halved toward zero.",),
           "Only a large loss from opposite signs is halved; ordinary products still agree.",
           "异号相乘造成较大负值时才减半；普通乘积仍相同。"),
)


def _world(recipe: Recipe, symbols: tuple[str, ...], thresholds: tuple[int, ...]):
    registry = OperatorRegistry(starting_registry())
    rules = []
    for index, (body, hint) in enumerate(zip(recipe.bodies, recipe.hints)):
        symbol = symbols[index]
        text = f"a {symbol} b = {{ {body.format(s=symbols[0], u=symbols[-1], t=thresholds[0])} }}"
        kind = BRANCH if ";" in body else SIMPLE
        operator = Operator(f"equiv_{index}", symbol, 2, definition=text, definition_type=kind,
                            op_compute_func=f"def op_equiv_{index}(a, b):\n    return 0\n",
                            op_count_func=f"def op_count_equiv_{index}(a, b):\n    return 0\n")
        registry.add(operator)
        rules.append({"symbol": symbol, "text": text, "hint": hint})
    oracle = Oracle(registry, Symbols(), Semantics("exact", None))
    return oracle, rules


def _nodes(oracle: Oracle, recipe: Recipe, symbols: tuple[str, ...]):
    substitutions = {"s": symbols[0], "u": symbols[-1]}
    left = recipe.left.format(**substitutions)
    right = recipe.right.format(**substitutions)
    return left, right, *(from_ast(oracle.parser.parse_expr(text, expression_mode=True), oracle.registry)
                          for text in (left, right))


def _value(checker: EquivalenceChecker, node, a: int, b: int):
    value = checker.value(node, {"a": a, "b": b})
    if value is NAN:
        raise AssertionError("These puzzles must have integer outputs throughout their domain")
    return value


def _signature(text: str, symbols: tuple[str, ...]) -> str:
    for symbol in symbols:
        text = text.replace(symbol, "CUSTOM")
    return re.sub(r"(?<!\w)-?\d+(?!\w)", "N", text)


def _check_rule_quality(oracle: Oracle, rules: list[dict]) -> None:
    """Reject inert arithmetic, aliases, and rules with an inactive input."""
    for rule in rules:
        body = rule["text"].split("{", 1)[1].rsplit("}", 1)[0].strip()
        compact = re.sub(r"\s+", "", body)
        assert not re.search(r"(?:\*1(?!\d)|\+0(?!\d)|-0(?!\d)|/1(?!\d))", compact)
        assert not re.search(r"(?:a-a|b-b|--|-\(-)", compact)
        assert not re.fullmatch(r"[ab](?:[+*\-/])[ab]", compact), body
        assert compact not in ("a", "b")
        if ";" in body:
            first, second = body.split(";", 1)
            assert first.split(", if", 1)[0].strip() != second.split(", else", 1)[0].strip()
        operator = oracle.registry.find(rule["symbol"], 2)
        values = {(a, b): oracle.evaluate(operator, (a, b)).value
                  for a, b in itertools.product(range(DOMAIN[0], DOMAIN[1] + 1), repeat=2)}
        assert any(values[a, b] != values[c, b]
                   for a, c, b in itertools.product(range(DOMAIN[0], DOMAIN[1] + 1), repeat=3))
        assert any(values[a, b] != values[a, c]
                   for a, b, c in itertools.product(range(DOMAIN[0], DOMAIN[1] + 1), repeat=3))


def _generate_once(rng: random.Random, seed: int) -> dict:
    chosen = rng.sample(SYMBOLS, len(RECIPES))
    thresholds = (rng.choice((2, 3)), rng.choice((5, 6)),
                  rng.choice((6, 7)), rng.choice((25, 36)),
                  3, rng.choice((9, 10)))
    false_count = 0
    rows = []
    structures = set()
    rule_shapes = set()
    witness_inputs = set()
    for index, recipe in enumerate(RECIPES, 1):
        names = (chosen[index - 1], chosen[(index + 6) % len(chosen)])
        threshold = thresholds[false_count] if not recipe.same else 0
        if not recipe.same:
            false_count += 1
        oracle, rules = _world(recipe, names, (threshold,))
        _check_rule_quality(oracle, rules)
        left, right, left_node, right_node = _nodes(oracle, recipe, names)
        key = (_signature("|".join(rule["text"] for rule in rules), names),
               _signature(left, names), _signature(right, names))
        assert key not in structures
        structures.add(key)
        for rule in rules:
            shape = _signature(rule["text"].split("{", 1)[1], names)
            assert shape not in rule_shapes
            rule_shapes.add(shape)
        checker = EquivalenceChecker(Z3Encoder(oracle), timeout_ms=2_000, small_range=2)
        differences = []
        for a, b in itertools.product(range(DOMAIN[0], DOMAIN[1] + 1), repeat=2):
            lv, rv = _value(checker, left_node, a, b), _value(checker, right_node, a, b)
            assert abs(lv) <= 100 and abs(rv) <= 100
            if lv != rv:
                differences.append((a, b, lv, rv))
        assert bool(differences) != recipe.same, (index, left, right)
        if differences:
            assert all(max(abs(a), abs(b)) > 2 for a, b, _, _ in differences)
            rng.shuffle(differences)
            choices = [item for item in differences if item[:2] not in witness_inputs]
            assert choices
            a, b, lv, rv = min(choices, key=lambda item: (max(abs(item[0]), abs(item[1])),
                                                        abs(item[0]) + abs(item[1])))
            witness_inputs.add((a, b))
            counterexample = {"inputs": [a, b], "left": lv, "right": rv}
        else:
            counterexample = None
        # The repository's equivalence checker supplies an independent SMT check.
        verdict = checker.check(left_node, right_node)
        if recipe.same:
            assert verdict.status in ("proved", "bounded")
        else:
            assert verdict.status == "refuted"
        rows.append({"id": f"equiv-{index:02d}", "level": recipe.level,
                     "why": recipe.why, "why_zh": recipe.why_zh, "rules": rules,
                     "left": left, "right": right, "domain": DOMAIN,
                     "same": recipe.same, "proof": "z3" if verdict.status == "proved" else "range",
                     "counterexample": counterexample, "verified": True})
    assert len(rows) == 12 and false_count == 6
    assert [r["level"] for r in rows] == ["easy"] * 4 + ["medium"] * 5 + ["hard"] * 3
    assert len({(r["counterexample"]["left"], r["counterexample"]["right"])
                for r in rows if not r["same"]}) == 6
    from tools.challenge_describe import check_site_rules
    check_site_rules(rows, "equiv")
    from tools.example_atoms import annotate
    return annotate({"schema": "opulse.challenge-mode/1", "mode": "equiv", "group": "reason",
                     "seed": seed, "challenges": rows})


def generate(seed: int = SEED) -> dict:
    rng = random.Random(seed)
    for _ in range(64):
        try:
            return _generate_once(rng, seed)
        except AssertionError:
            # A threshold or witness may fail a quality or uniqueness filter.
            # Sample a fresh seeded candidate instead of publishing that set.
            continue
    raise AssertionError("No set of twelve distinct, verified puzzles passed the filters")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--out", type=Path, default=OUTPUT)
    args = parser.parse_args()
    payload = generate(args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
