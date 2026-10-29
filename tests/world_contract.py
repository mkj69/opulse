"""Checks every world showcase meets: names, sentences, examples, derivation files, sizes."""

import json
import re
from pathlib import Path

GENERIC = ("Apply the composition shown", "Use the first branch whose condition holds",
           "按定义中的组合式", "定义中的操作")


def check_showcase(data: dict, root: Path, min_operators: int = 85) -> None:
    operators = data["operators"]
    assert len(operators) >= min_operators
    assert {op["kind"] for op in operators} == {"composition", "branching", "recursion"}
    assert {op["layer"] for op in operators} >= {0, 1, 2}
    names = [op["name"] for op in operators]
    assert len(set(names)) == len(names)
    assert all(re.search(r"[₀-₉]+$", name) for name in names)
    assert len({name[0] for name in names[:8]}) >= 2
    atoms = {atom["symbol"] for atom in data["atoms"]}
    assert not {name[0] for name in names} & atoms
    assert sum(op["featured"] for op in operators) == 5 and all(op["featured"] for op in operators[:5])
    assert all(atom["plain_zh"] and atom["example"]["output"] for atom in data["atoms"])
    assert data["domain"] and data["settings"] and data["why"]["en"] and data["metrics"]["behaviours"] > 0
    varied_cases = varied_depths = branches = recursions = 0
    for index, op in enumerate(operators):
        assert op["plain"] and op["plain_zh"] and not any(text in op["plain"] + op["plain_zh"] for text in GENERIC)
        examples = op["examples"]
        assert 1 <= len(examples) <= (10 if op["featured"] else 3)
        steps = json.loads((root / data["steps"] / f"{index}.json").read_text(encoding="utf-8"))
        assert len(steps) == len(examples) and all(steps)
        if op["kind"] == "branching":
            branches += 1
            varied_cases += len({example["case"] for example in examples[:3]}) > 1
        if op["kind"] == "recursion":
            recursions += 1
            varied_depths += len({example["depth"] for example in examples[:3]}) > 1
    assert varied_cases >= 0.6 * branches and varied_depths >= 0.8 * recursions
    size = sum(path.stat().st_size for path in (root / data["steps"]).glob("*.json"))
    assert size < 2_500_000
