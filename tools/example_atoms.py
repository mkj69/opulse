"""Atom legend entries for published puzzles, taken from the world presets.

The rulebook is the source of truth for which atoms a puzzle actually uses.
Comparison tests are included because they control the displayed branch rules.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORLD_DATA = ROOT / "docs/assets/data/worlds"

COMPARISONS = {
    "<": ("less_than", "a < b tests whether a is smaller than b.", "a < b 检验 a 是否小于 b。", "2 < 3 = true"),
    "<=": ("at_most", "a <= b tests whether a is at most b.", "a <= b 检验 a 是否不大于 b。", "2 <= 2 = true"),
    ">": ("greater_than", "a > b tests whether a is larger than b.", "a > b 检验 a 是否大于 b。", "3 > 2 = true"),
    ">=": ("at_least", "a >= b tests whether a is at least b.", "a >= b 检验 a 是否不小于 b。", "3 >= 3 = true"),
    "==": ("equal", "a == b tests whether a equals b.", "a == b 检验 a 是否等于 b。", "3 == 3 = true"),
}
ATOMIC_ATOMS = {
    "succ": {"symbol": "⁺", "name": "succ", "plain": "a ⁺ is a plus one.",
             "plain_zh": "a ⁺ 是 a 加一。",
             "example": {"expression": "4 ⁺", "inputs": [{"t": "int", "v": 4}],
                         "output": {"t": "int", "v": 5}}},
}


def _catalogue(world: str) -> list[dict]:
    path = WORLD_DATA / f"{world}.json"
    if not path.is_file():
        path = WORLD_DATA / "integer.json"
    return json.loads(path.read_text(encoding="utf-8"))["atoms"]


def _definitions(row: dict) -> list[str]:
    texts = [r["text"] for r in row.get("rules", ()) if isinstance(r, dict) and " = {" in r.get("text", "")]
    for key in ("reference_definition", "reference", "text", "left", "right", "source", "target"):
        value = row.get(key)
        if isinstance(value, dict):
            value = value.get("text")
        if isinstance(value, str) and " = {" in value:
            texts.append(value)
    for key in ("rule", "edit", "variant"):
        value = row.get(key)
        if isinstance(value, dict):
            texts.extend(v for v in value.values() if isinstance(v, str) and " = {" in v)
    return list(dict.fromkeys(texts))


def atom_entries(row: dict, world: str = "integer") -> list[dict]:
    """Return the exact atom metadata required by the page legend."""
    definitions = _definitions(row)
    if row.get("kind") == "induce":
        preset = json.loads((WORLD_DATA / f"{world}.json").read_text(encoding="utf-8"))
        operators = {operator["name"]: operator["definition"]
                     for operator in preset["operators"]}
        visited = set()
        for text in definitions:
            body = text.split("= {", 1)[-1]
            for symbol, definition in operators.items():
                if symbol not in visited and re.search(re.escape(symbol) + r"(?![₀-₉])", body):
                    visited.add(symbol)
                    definitions.append(definition)
    bodies = " ".join(text.split("= {", 1)[1] for text in definitions)
    bodies += " " + " ".join(row.get("allowed", ()))
    worlds = sorted({world, row.get("source_world", world), row.get("target_world", world)})
    catalog = {**ATOMIC_ATOMS,
               **{atom["name"]: atom for name in worlds for atom in _catalogue(name)}}
    used = []
    for atom in catalog.values():
        symbol = atom["symbol"]
        if atom["name"] == "neg" and not re.search(
            r"(?:^|[({;,])\s*-\s*(?:[A-Za-z(\d#&])", bodies.strip()
        ):
            continue
        if atom["name"] == "sub" and not re.search(
            r"(?:[A-Za-z0-9)\]])\s+-\s+(?:[A-Za-z0-9(\[#&])", bodies
        ):
            continue
        if symbol in bodies or re.search(rf"\b{re.escape(atom['name'])}\b", bodies):
            used.append({key: atom[key] for key in ("symbol", "name", "plain", "plain_zh", "example")})
    # The input world can contain an atom with the same glyph as a derived
    # operator; count it only when its name is explicitly present in a rulebook.
    for rule in row.get("rules", ()):
        if not isinstance(rule, dict) or " = {" in rule.get("text", ""):
            continue
        for atom in catalog.values():
            if rule.get("symbol") == atom["symbol"] and atom["name"] not in {item["name"] for item in used}:
                used.append({key: atom[key] for key in ("symbol", "name", "plain", "plain_zh", "example")})
    for symbol, (name, plain, plain_zh, example) in COMPARISONS.items():
        if re.search(rf"(?<![<>=]){re.escape(symbol)}(?![<>=])", bodies):
            used.append({"symbol": symbol, "name": name, "plain": plain,
                         "plain_zh": plain_zh, "example": example})
    return sorted({entry["name"]: entry for entry in used}.values(), key=lambda entry: entry["name"])


def annotate(document: dict, world: str = "integer") -> dict:
    for row in document["challenges"]:
        row["atoms"] = atom_entries(row, world)
    return document
