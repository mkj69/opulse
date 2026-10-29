"""Check the published scale solve records against the reference interpreter."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import requires_zh_site

from opulse.core import NAN
from opulse.expression.nodes import Call, Number, Variable, to_ast
from tools.check_scales import registry_for

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs/assets/data/scales_solve"


@pytest.mark.parametrize("path", sorted(DATA.glob("*.json")))
def test_published_file(path: Path) -> None:
    row = json.loads(path.read_text())
    assert row["schema"] == "opulse.scales-solve/1"
    assert path.stat().st_size < 1_000_000
    assert row["unique"] and row["complete"]
    assert row["solutions"] == row["hits"] == [row["answer"]]
    assert row["verification"]["full_trace_verified"]
    assert row["verification"]["reverse_complete"]
    assert len(row["scan"]) == row["domain"][1] - row["domain"][0] + 1
    assert row["scan_steps"] == sum(item["steps"] for item in row["scan"])
    assert all(0 < item["steps"] <= row["step_cap"] for item in row["scan"])
    assert row["check_steps"] == row["scan"][row["answer"] - row["domain"][0]]["steps"]
    assert row["reverse"][0]["symbol"] == row["target_operator"]
    assert row["reverse"][0]["unknown_position"] == row["unknown_position"]
    assert row["target_layer"] >= 2
    assert row["check_steps"] > 1
    if row["scale"] != "s10":
        defined = [item["value"] for item in row["scan"] if item["value"] is not None]
        assert len(set(defined)) < len(defined)


@pytest.mark.parametrize("scale", ["s100", "s1000"])
def test_reference_interpreter_and_uniqueness(scale: str) -> None:
    path = DATA / f"{scale}.json"
    row = json.loads(path.read_text())
    # These targets and their dependency closures are in the committed examples.
    example = next(p for p in (ROOT / "docs/assets/data/scales" / scale).glob("*.json")
                   if any(op["id"] == row["target_id"] for op in json.loads(p.read_text())["operators"]))
    _, _, oracle, _ = registry_for(json.loads(example.read_text()), example.parents[1])
    registry = oracle.registry
    expression = Call(registry.get(row["target_id"]),
                      tuple(Variable("x") if i == row["unknown_position"] else Number(value)
                            for i, value in enumerate(row["operator_inputs"])))
    values = []
    for x in range(row["domain"][0], row["domain"][1] + 1):
        result = oracle.evaluate_expr(to_ast(expression), {"x": x}).value
        value = None if result is NAN else result
        values.append({"x": x, "value": value})
    assert values == [{"x": item["x"], "value": item["value"]} for item in row["scan"]]
    assert [item["x"] for item in values if item["value"] == row["target"]] == [row["answer"]]
    assert values[row["answer"] - row["domain"][0]]["value"] == row["check_value"]


def test_snippet_wiring() -> None:
    _check_snippet_wiring("docs")


@requires_zh_site
def test_chinese_snippet_wiring() -> None:
    _check_snippet_wiring("docs_zh")
    assert (ROOT / "docs_zh/snippets/localized_assets/js/scales-solve.js").read_bytes() == (
        ROOT / "docs/assets/js/scales-solve.js").read_bytes()


def _check_snippet_wiring(language):
    snippet = (ROOT / language / "snippets/vis_solve.html").read_text()
    assert 'class="scales-solve"' in snippet
    assert "scales_solve/" in snippet
    assert "scales-solve.js" in snippet
