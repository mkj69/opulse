"""Export the published layer-0 atom glossary from the world showcases.

The showcases are built from the preset registries and already carry the Playground/
Worlds descriptions and checked examples. Run ``python3 tools/docs_atoms.py`` after
updating them, or ``python3 tools/docs_atoms.py --check`` in CI.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAMES = {
    "triangle": "signed triangular number", "digitsum": "signed digit sum",
    "popcount": "one-bit count", "reverse": "reverse decimal digits",
    "neg": "negation", "add": "addition", "sub": "subtraction",
    "mul": "multiplication", "div": "division", "mod": "remainder",
}


def value_text(value: dict) -> str:
    kind = value.get("t")
    if kind == "nan":
        return "NaN"
    if kind == "str":
        return json.dumps(value["v"], ensure_ascii=False)
    if kind == "bool":
        return "true" if value["v"] else "false"
    if kind == "int":
        return str(value["v"])
    return json.dumps(value.get("v", value), ensure_ascii=False, separators=(",", ":"))


def export(world: str) -> str:
    source = ROOT / "docs/assets/data/worlds" / f"{world}.json"
    atoms = json.loads(source.read_text(encoding="utf-8"))["atoms"]
    result = {}
    for atom in atoms:
        symbol = atom["symbol"]
        arity = len(atom["params"])
        # The same glyph denotes binary subtraction and prefix negation.
        key = "- (unary)" if symbol == "-" and arity == 1 else symbol
        signature = " × ".join(param["type"] for param in atom["params"]) + " → " + atom["result_type"]
        checked = atom["example"]
        result[key] = {
            "name": NAMES.get(atom["name"], atom["name"].replace("_", " ")),
            "arity": arity,
            "signature": signature,
            "plain": atom["plain"],
            "plain_zh": atom.get("plain_zh", atom["plain"]),
            "example": checked["expression"] + " = " + value_text(checked["output"]),
        }
    return json.dumps(result, ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    worlds = sorted(path.stem for path in (ROOT / "docs/assets/data/worlds").glob("*.json")
                    if path.stem != "index")
    check = sys.argv[1:] == ["--check"]
    for site in ("docs", "docs_zh"):
        if check and not (ROOT / site).is_dir():
            continue  # The public export contains only the English site.
        output = ROOT / site / "assets/data/atoms"
        if not check:
            output.mkdir(parents=True, exist_ok=True)
        for world in worlds:
            target = output / f"{world}.json"
            content = export(world)
            if check:
                if not target.exists() or target.read_text(encoding="utf-8") != content:
                    print(f"stale: {target}", file=sys.stderr)
                    return 1
            else:
                target.write_text(content, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
