"""Write two interpreter-checked Challenge UI fixtures per new mode.

This is temporary page data. Full mode generators may replace these files.
Existing files are never overwritten.
"""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from opulse.playground import run

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/assets/data/challenge"
SEED = 20261026


def value(definitions: str, expression: str, world: str | None = None):
    result = run(definitions, expression, world=world)
    assert result["ok"] and result.get("agrees") is True, (expression, result.get("error"))
    raw = result["value"]
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return raw


def rule(symbol: str, text: str, hint: str) -> dict:
    return {"symbol": symbol, "text": text, "hint": hint}


def record(mode, number, level, why, why_zh, rules, **fields):
    return dict(id=f"{mode}-{number:02d}", level=level, why=why,
                why_zh=why_zh, rules=rules, **fields, verified=True)


def save(mode, group, items):
    path = OUT / f"{mode}.json"
    if path.exists():
        return
    data = {"schema": "opulse.challenge-mode/1", "mode": mode, "group": group,
            "seed": SEED, "challenges": items}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_wrongstep():
    compute = json.loads((OUT / "challenges.json").read_text(encoding="utf-8"))["challenges"]
    items = []
    for i, source in enumerate(compute[:2], 1):
        steps = deepcopy(source["steps"])
        wrong_index = min(4, len(steps) - 1)
        correct = steps[wrong_index]["expr"]
        steps = steps[:wrong_index + 1]
        steps[-1]["expr"] = str(value("\n".join(r["text"] for r in source["rules"]), source["question"]) + i)
        items.append(record("wrongstep", i, "easy", "The last line skips a needed rewrite.",
                            "末行跳过了一次必要的改写。", source["rules"],
                            question=source["question"], steps=steps, wrong_index=wrong_index,
                            wrong_reason="The displayed value does not follow from the previous line.",
                            correct_expr=correct, correct_steps=source["steps"]))
    save("wrongstep", "execute", items)


def build_hole():
    items = []
    specs = [
        ("a ◇ b = { a * 2 + b }", "x ◇ 3", [-3, 3], 1, "Doubling x moves the target in steps of two.", "x 翻倍后，结果每次相差二。"),
        ("a ✧ b = { a * a - b }", "x ✧ 4", [0, 5], 3, "The square would have two signs without the domain limit.", "平方通常对应正负两个数，范围限制排除了一个。"),
    ]
    for i, (definition, question, domain, answer, why, why_zh) in enumerate(specs, 1):
        scan = [{"x": x, "value": value(definition, question.replace("x", str(x)))} for x in range(domain[0], domain[1] + 1)]
        target = next(row["value"] for row in scan if row["x"] == answer)
        assert [row["x"] for row in scan if row["value"] == target] == [answer]
        symbol = definition.split()[1]
        items.append(record("hole", i, "easy", why, why_zh, [rule(symbol, definition, "Apply the displayed arithmetic.")],
                            question=question + " = " + str(target), target=target, domain=domain,
                            answer=answer, scan=scan, unique=True))
    save("hole", "reason", items)


def build_equiv():
    specs = [
        ("a ♢ b = { a + b + 1 }", "a ♢ b", "b ♢ a", True, None,
         "The extra one does not disturb symmetry.", "额外加一仍然保持交换对称。"),
        ("a ▷ b = { a - 2 * b }", "a ▷ b", "b ▷ a", False, [1, 2],
         "Reversing operands changes the doubled term.", "交换输入后，被加倍的项也变了。"),
    ]
    items = []
    for i, (definition, left, right, same, witness, why, why_zh) in enumerate(specs, 1):
        outcomes = [(a, b, value(definition, left.replace("a", str(a)).replace("b", str(b))),
                     value(definition, right.replace("a", str(a)).replace("b", str(b))))
                    for a in range(-3, 4) for b in range(-3, 4)]
        assert all(x[2] == x[3] for x in outcomes) == same
        cex = None
        if witness:
            a, b = witness
            row = next(x for x in outcomes if x[:2] == (a, b))
            assert row[2] != row[3]
            cex = {"inputs": witness, "left": row[2], "right": row[3]}
        items.append(record("equiv", i, "easy", why, why_zh, [rule(definition.split()[1], definition, "Compare both orders.")],
                            left=left, right=right, domain=[-3, 3], same=same, proof="range", counterexample=cex))
    save("equiv", "reason", items)


def build_ripple():
    specs = [
        ("a ◆ b = { a + b }", "a ◆ b = { a - b }", ["2 ◆ 3", "2 + 3", "5 ◆ 0", "4 * 2", "(1 ◆ 2) + 3"],
         "The rule edit affects calls to ◆ except where b is zero.", "规则变化会影响 ◆，但 b 为零时结果相同。"),
        ("a ✦ b = { a * b }", "a ✦ b = { a + b }", ["2 ✦ 3", "2 * 3", "2 ✦ 2", "0 + 4", "(1 ✦ 4) + 1"],
         "Multiplication and addition sometimes happen to agree.", "乘法和加法有时恰好得到相同结果。"),
    ]
    items = []
    for i, (before, after, expressions, why, why_zh) in enumerate(specs, 1):
        rows = []
        for expr in expressions:
            old, new = value(before, expr), value(after, expr)
            rows.append({"expr": expr, "before": old, "after": new, "changed": old != new})
        assert any(row["changed"] for row in rows) and any(not row["changed"] for row in rows)
        symbol = before.split()[1]
        items.append(record("ripple", i, "easy", why, why_zh, [rule(symbol, before, "Follow the changed definition.")],
                            edit={"rule_index": 0, "before": before, "after": after}, input=[2, 3], items=rows))
    save("ripple", "reason", items)


def build_laws():
    specs = [
        ("a ⊙ b = { a + b + 2 }", "commutative", "a ⊙ b = b ⊙ a", True, None,
         "Adding a fixed offset still permits swapping inputs.", "加上固定偏移后仍可交换输入。"),
        ("a ⊘ b = { a - b + 1 }", "commutative", "a ⊘ b = b ⊘ a", False, [2, 4],
         "The subtraction reverses sign when inputs swap.", "交换输入后，减法项会变号。"),
    ]
    items = []
    for i, (definition, law, statement, holds, witness, why, why_zh) in enumerate(specs, 1):
        symbol = definition.split()[1]
        def pair(a, b):
            return value(definition, f"{a} {symbol} {b}"), value(definition, f"{b} {symbol} {a}")
        assert all((lambda p: p[0] == p[1])(pair(a, b)) for a in range(-3, 4) for b in range(-3, 4)) == holds
        cex = None
        if witness:
            left, right = pair(*witness)
            assert left != right
            cex = {"inputs": witness, "left": left, "right": right}
        items.append(record("laws", i, "easy", why, why_zh, [rule(symbol, definition, "Check both input orders.")],
                            symbol=symbol, law=law, statement=statement, holds=holds, proof="range",
                            counterexample=cex, domain=[-3, 3]))
    save("laws", "reason", items)


def build_deadbranch():
    specs = [
        ("a ☀ b = { a + b, if a > a; a - b, else }", "The strict comparison a > a is impossible.",
         "严格比较 a > a 不可能成立。", "Self comparison cannot be strictly greater."),
        ("a ☾ b = { a * b, if b < b; a + b, else }", "The strict comparison b < b is impossible.",
         "严格比较 b < b 不可能成立。", "Self comparison cannot be strictly smaller."),
    ]
    items = []
    for i, (definition, reason, reason_zh, why) in enumerate(specs, 1):
        symbol = definition.split()[1]
        for a in range(-3, 4):
            for b in range(-3, 4):
                expected = a - b if i == 1 else a + b
                assert value(definition, f"{a} {symbol} {b}") == expected
        items.append(record("deadbranch", i, "easy", why, reason_zh, [rule(symbol, definition, "Test the condition.")],
                            rule_index=0, branches=[{"text": definition.split("{")[1].split(";")[0].strip(), "dead": True},
                                                    {"text": definition.split(";")[1].split("}")[0].strip(), "dead": False}],
                            reason=reason, proof="range"))
    save("deadbranch", "reason", items)


def encoded(value_):
    if isinstance(value_, list):
        return {"t": "list", "v": [encoded(v) for v in value_]}
    return {"t": "int", "v": value_}


def build_translate():
    assert value("", "2 + 3") == 5
    assert value("", "[2] ⊞ [3]", "lists") == [2, 3]
    assert value("", "[1, 2] ⊞ [4]", "lists") == [1, 2, 4]
    items = [
        record("translate", 1, "easy", "The operation changes material but keeps the two-leaf tree.",
               "运算材料变了，但两片叶子的树形没有变。",
               [rule("+", "a + b is integer addition.", "Combine two numbers."),
                rule("⊞", "a ⊞ b joins two lists.", "Keep their order.")],
               source_world="integer", target_world="lists", skeleton="left ◇ right",
               source={"expression": "2 + 3", "inputs": [encoded(2), encoded(3)], "output": encoded(5)},
               target={"expression": "[2] ⊞ [3]", "inputs": [encoded([2]), encoded([3])],
                       "answer": encoded([2, 3]), "options": [encoded([3, 2]), encoded([2, 3]), encoded([5])]}),
        record("translate", 2, "easy", "The left subtree is a list, not a single number.",
               "左侧子树是列表，不是单个数字。",
               [rule("⊞", "a ⊞ b joins two lists.", "Keep their order."),
                rule("+", "a + b is integer addition.", "Combine two numbers.")],
               source_world="lists", target_world="integer", skeleton="(left ◇ middle) ◇ right",
               source={"expression": "[1] ⊞ [2] ⊞ [4]", "inputs": [encoded([1]), encoded([2]), encoded([4])], "output": encoded([1, 2, 4])},
               target={"expression": "1 + 2 + 4", "inputs": [encoded(1), encoded(2), encoded(4)],
                       "answer": encoded(7), "options": [encoded(6), encoded(7), encoded(8)]}),
    ]
    assert value("", "1 + 2 + 4") == 7
    save("translate", "induce", items)


def build_induce():
    specs = [
        ("a ♧ b = { a + b }", "a ★ b = { (a ♧ b) * 2 }", [[1, 2], [2, 3]], [[4, 1], [0, 3]],
         "A doubled sum can look like a larger constant from one example.", "只看一个例子时，翻倍求和可能被误认作加常数。"),
        ("a ♤ b = { a - b }", "a ☆ b = { (a ♤ b) * 3 }", [[5, 1], [2, 4]], [[3, 2], [0, 2]],
         "Negative outputs expose the subtraction before scaling.", "负数输出揭示了先相减再放大的顺序。"),
    ]
    items = []
    for i, (base, definition, known, queries, why, why_zh) in enumerate(specs, 1):
        symbol = definition.split()[1]
        def example(pair, answer_key):
            a, b = pair
            return {"inputs": pair, answer_key: value(base + "\n" + definition, f"{a} {symbol} {b}")}
        items.append(record("induce", i, "easy", why, why_zh, [rule(base.split()[1], base, "Use this known operation.")],
                            atoms=["+", "-", "*"], known=[base], examples=[example(x, "output") for x in known],
                            queries=[example(x, "answer") for x in queries], reference_definition=definition,
                            domain=[-3, 3]))
    save("induce", "induce", items)


def build_shorten():
    specs = [
        ("a ✚ b = { (a + b) + 0 }", "a ✚ b = { a + b }", "Adding zero hides a simpler single operation.",
         "多余的加零掩盖了一次运算即可完成的定义。"),
        ("a ✶ b = { (a * b) * 1 }", "a ✶ b = { a * b }", "Multiplying by one spends an unnecessary operation.",
         "多余的乘一浪费了一次运算。"),
    ]
    items = []
    for i, (verbose, short, why, why_zh) in enumerate(specs, 1):
        symbol = verbose.split()[1]
        for a in range(-3, 4):
            for b in range(-3, 4):
                assert value(verbose, f"{a} {symbol} {b}") == value(short, f"{a} {symbol} {b}")
        items.append(record("shorten", i, "easy", why, why_zh, [rule(symbol, verbose, "Remove the neutral step.")],
                            symbol=symbol, text=verbose, size=2, budget=1, reference=short,
                            domain=[-3, 3], arity=2))
    save("shorten", "create", items)


if __name__ == "__main__":
    build_wrongstep()
    build_hole()
    build_equiv()
    build_ripple()
    build_laws()
    build_deadbranch()
    build_translate()
    build_induce()
    build_shorten()
