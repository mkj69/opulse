"""Generate the interpreter-checked storyboard data for the explainer.

Every value, step and branch shown in the video comes from the Playground's ``Workspace``,
the same engine the site runs in the browser. Scenes read only ``data.json``.
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path
import sys

from opulse.playground import Workspace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# The three definition kinds, one per scene, each built only from atoms shown before it.
RULES = {
    "squares": "a ◆ b = { (a * a) + (b * b) }",
    "distance": "a ▲ b = { a - b, if a >= b; b - a, else }",
    "power": "a ★ b = { 1, if b <= 0; a * (a ★ (b - 1)), else }",
}
# (symbol, name, form, example) for the atoms scene. Every atom used later is here.
ATOMS = [
    ("+", "add", "binary", "3 + 4"),
    ("-", "subtract", "binary", "9 - 4"),
    ("*", "multiply", "binary", "6 * 7"),
    ("%", "remainder", "binary", "17 % 5"),
    ("@", "reverse digits", "postfix", "12@"),
    ("&", "digit sum", "prefix", "&47"),
]
# (id, seconds, English caption, Chinese caption). Title and end cards carry their own copy.
SCENES = [
    ("title", 6, "", ""),
    ("atoms", 8, "Start with a few atoms: small operations you choose.",
     "从少数原子开始：你选择的基本运算。"),
    ("substitution", 10, "Substitution: a new operator is written with the atoms.",
     "代入：用原子写出一个新运算符。"),
    ("branch", 9, "Choice: a test picks which case to use.",
     "选择：由一个测试决定使用哪种情况。"),
    ("recursion", 11, "Recursion: an operator calls itself until a base case.",
     "递归：运算符调用自身，直到基本情况。"),
    ("layers", 13, "Each layer builds on the ones below. Concepts without limit.",
     "每一层都建立在下层之上。概念可以无限扩展。"),
    ("checked", 10, "Every step is checked by the interpreter.",
     "每一步都由解释器检验。"),
    ("six_angles", 12, "Six ways to test reasoning.", "从六个角度检验推理。"),
    ("new_material", 11, "The same structure works in any world.", "同一结构可以用于不同世界。"),
    ("end", 6, "", ""),
]
# The poster is the title card once it is fully revealed.
POSTER = {"scene": "title", "offset": 5.5}

STEP_KEYS = ("kind", "symbol", "operator_kind", "before", "focus", "after", "new",
             "output", "depth", "branch_index")


def _workspace() -> Workspace:
    return Workspace("\n".join(RULES.values()))


def _step(step: dict) -> dict:
    out = {key: step[key] for key in STEP_KEYS}
    if step.get("branches"):
        out["branches"] = [{"condition": b["condition"], "substituted": b.get("substituted"),
                            "truth": b["truth"], "body": b["body"]} for b in step["branches"]]
    return out


def _run(ws: Workspace, expression: str) -> dict:
    result = ws.evaluate(expression)
    assert result["agrees"] and not result["truncated"], expression
    return {"expression": expression, "value": result["value"],
            "steps": [_step(s) for s in result["steps"]]}


def build_data() -> dict:
    ws = _workspace()
    atoms = []
    for symbol, name, form, example in ATOMS:
        atoms.append({"symbol": symbol, "name": name, "form": form, "example": example,
                      "value": ws.evaluate(example)["value"]})
    substitution = _run(ws, "3 ◆ 4")
    branch = [_run(ws, "7 ▲ 3"), _run(ws, "3 ▲ 7")]
    recursion = _run(ws, "2 ★ 4")
    # Values of 2 ★ b for b = 0 .. 4: the fold back from the base case.
    recursion["fold"] = [ws.evaluate(f"2 ★ {b}")["value"] for b in range(5)]
    checked = _run(ws, "(3 ◆ 4) ▲ 30")
    last = checked["steps"][-1]
    # A plausible wrong final step (a model that subtracts the wrong way round or slips).
    checked["wrong"] = {"index": len(checked["steps"]) - 1, "after": "15",
                        "correct": last["after"]}

    assert [a["value"] for a in atoms] == ["7", "5", "42", "2", "21", "11"]
    assert substitution["value"] == "25"
    assert [b["value"] for b in branch] == ["4", "4"]
    assert [b["steps"][0]["branch_index"] for b in branch] == [1, 2]
    assert recursion["value"] == "16" and recursion["fold"] == ["1", "2", "4", "8", "16"]
    assert checked["value"] == "5" and len(checked["steps"]) == 6

    cursor = 0
    scenes = []
    for scene_id, length, en, zh in SCENES:
        scenes.append({"id": scene_id, "start": cursor, "end": cursor + length,
                       "caption": en, "caption_zh": zh})
        cursor += length
    data = {"duration": cursor, "scenes": scenes, "poster": POSTER, "rules": RULES,
            "atoms": atoms, "substitution": substitution, "branch": branch,
            "recursion": recursion, "checked": checked}
    # Scene-specific data lives in data_<key>.py modules with a build() -> dict function.
    for module in sorted(HERE.glob("data_*.py")):
        key = module.stem.removeprefix("data_")
        assert key not in data, key
        data[key] = importlib.import_module(module.stem).build()
    return data


def main() -> None:
    target = HERE / "data.json"
    target.write_text(json.dumps(build_data(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(target)


if __name__ == "__main__":
    main()
