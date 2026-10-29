"""Verified examples and real generated-set counts for the layers scene."""

import json
from pathlib import Path

from opulse.playground import Workspace


ASSETS = Path(__file__).resolve().parents[2] / "docs/assets/data"
BASE = [
    "a ◆ b = { (a * a) + (b * b) }",
    "a ▲ b = { a - b, if a >= b; b - a, else }",
    "a ★ b = { 1, if b <= 0; a * (a ★ (b - 1)), else }",
]
ADDED = [
    {"symbol": "◇", "layer": 2, "kind": "simple", "name": "squared distance",
     "calls": ["▲", "★"], "definition": "a ◇ b = { (a ▲ b) ★ 2 }", "expression": "3 ◇ 4"},
    {"symbol": "✦", "layer": 2, "kind": "simple", "name": "gap between the squares",
     "calls": ["★", "▲"], "definition": "a ✦ b = { (a ★ 2) ▲ (b ★ 2) }", "expression": "2 ✦ 7"},
    {"symbol": "⬡", "layer": 3, "kind": "simple", "name": "twice the product",
     "calls": ["◆", "◇", "-"], "definition": "a ⬡ b = { (a ◆ b) - (a ◇ b) }", "expression": "3 ⬡ 4"},
]


def _read(relative):
    return json.loads((ASSETS / relative).read_text(encoding="utf-8"))


def build():
    workspace = Workspace("\n".join(BASE + [item["definition"] for item in ADDED]))
    examples = []
    for item in ADDED:
        result = workspace.evaluate(item["expression"])
        assert result["agrees"] and not result["truncated"]
        examples.append({**item, "value": result["value"]})
    assert [item["value"] for item in examples] == ["1", "45", "24"]
    assert [workspace.evaluate(expression)["value"] for expression in
            ("3 ◆ 4", "3 ◇ 4", "(3 ◆ 4) - (3 ◇ 4)")] == ["25", "1", "24"]

    index = _read("scales/index.json")
    sets = []
    for scale, name in (("s1000", "int1000"), ("s10000", "int10000b")):
        entry = next(row for row in index["scales"] if row["key"] == scale)
        metadata = next(row for row in entry["sets"] if row["name"] == name)
        growth = _read(f"scales_growth/{name}.json")
        layers = [{"layer": row["layer"], "count": row["count"], "kinds": row["kinds"]}
                  for row in growth["layers"]]
        assert growth["size"] == metadata["size"] == sum(row["count"] for row in layers)
        assert [row["count"] for row in layers] == metadata["layers"]
        kinds = {kind: sum(row["kinds"][kind] for row in layers)
                 for kind in ("simple", "branch", "recursive")}
        assert all(sum(row["kinds"].values()) == row["count"] for row in layers)
        assert kinds == {kind: metadata["funnel"]["accepted"][f"{kind}_definition"]
                         for kind in kinds}
        sets.append({"name": name, "total": growth["size"], "kinds": kinds, "layers": layers})

    granularity = _read("granularity_anim.json")
    assert len(granularity["layers"]) == 3
    return {"examples": examples, "sets": sets,
            "granularity": {"layers": granularity["layers"]}}
