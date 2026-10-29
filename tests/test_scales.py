"""Focused checks of the published scale examples."""

from __future__ import annotations

import json
import math
import shlex
from pathlib import Path

import pytest

from opulse.config import Settings
from opulse.core import OperatorRegistry
from opulse.core.operator import Operator
from opulse.core.presets import register_for_symbol
from opulse.definition.parser import DefinitionParser
from opulse.expression.nodes import Call, Number
from opulse.trace.tree import build_tree, flatten
from opulse.verify import Oracle, verify_trace

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs/assets/data/scales"
pytestmark = pytest.mark.skipif(not DATA.exists(), reason="scale data is absent")


def load_example(scale: str, example_id: str):
    path = DATA / scale / f"{example_id}.json"
    assert path.stat().st_size <= 2_000_000
    data = json.loads(path.read_text())
    assert data["schema"] == "opulse.scale-example/1"
    nodes = [None] * sum(item["end"] - item["start"] for item in data["chunks"])
    strings_by_node = [None] * len(nodes)
    total = path.stat().st_size
    for chunk in data["chunks"]:
        chunk_path = path.parent / chunk["file"]
        size = chunk_path.stat().st_size
        assert size == chunk["bytes"] <= 2_000_000
        payload = json.loads(chunk_path.read_text())
        rows = payload["nodes"]
        assert isinstance(payload["strings"], list)
        assert len(rows) == chunk["end"] - chunk["start"]
        nodes[chunk["start"]:chunk["end"]] = rows
        strings_by_node[chunk["start"]:chunk["end"]] = [payload["strings"]] * len(rows)
        total += size
    assert total <= 6_000_000
    assert all(node is not None for node in nodes)
    assert data["chunks"][-1]["file"].endswith("/root.json")
    assert "strings" not in data
    return data, nodes, strings_by_node


def count(nodes, operators, root: int, limit: int) -> int:
    memo = {}
    stack = [(root, False)]
    while stack:
        index, done = stack.pop()
        if index in memo:
            continue
        if not done:
            stack.append((index, True))
            for step in nodes[index]["steps"]:
                if step[2] >= 0 and operators[step[1]]["layer"] >= limit:
                    stack.append((step[2], False))
        else:
            memo[index] = sum(memo[step[2]] if step[2] >= 0
                              and operators[step[1]]["layer"] >= limit else 1
                              for step in nodes[index]["steps"])
    return memo[root]


def test_all_published_examples():
    index = json.loads((DATA / "index.json").read_text())
    assert (DATA / "index.json").stat().st_size <= 2_000_000
    assert index["schema"] == "opulse.scales/1"
    assert [row["key"] for row in index["scales"]] == ["s10", "s100", "s1000", "s10000"]
    assert [row["name"] for row in index["scales"][-1]["sets"]] == ["int10000b", "str10000"]
    assert sum(path.stat().st_size for path in DATA.rglob("*.json")) <= 30_000_000
    for scale in index["scales"]:
        closures = {}
        for set_row in scale["sets"]:
            command = shlex.split(set_row["generation_command"])
            assert command[:4] == ["python", "-m", "opulse.cli.main", "operators"]
            assert not Path(command[command.index("--config") + 1]).is_absolute()
            assert not Path(command[command.index("--out") + 1]).is_absolute()
            assert "--dedup" in set_row["generation_command"]
            assert f"--seed {set_row['seed']}" in set_row["generation_command"]
            if set_row["name"] == "int1000":
                assert set_row["config"] == "configs/large.yaml"
            if set_row["name"] == "int10000b":
                assert set_row["config_overrides"] == {
                    "operators.safety_timeout_ms": 600000, "operators.degenerate_budget": 60}
                assert "large_safe60.yaml" in set_row["generation_command"]
            if set_row["name"] == "str10000":
                assert set_row["seed"] == 211
        for summary in scale["examples"]:
            data, nodes, strings_by_node = load_example(scale["key"], summary["id"])
            header = data["header"]
            assert header["scale"] == scale["key"]
            assert header["id"] == summary["id"]
            assert header["closure_size"] == sum(header["closure_by_layer"].values())
            assert header["verification"]["nodes_verified"] == len(nodes)
            assert header["verification"]["full_trace_verified"] is True
            assert header["verification"]["per_layer_counts_checked"] == list(range(header["layer"] + 2))
            assert header["verification"]["verified_with"] == (
                "opulse.verify.verify_trace on the flattened fully unfolded trace and verify_tree on every node")
            rows = header["cut_table"]
            assert [row["L"] for row in rows] == list(range(header["layer"] + 2))
            assert all(rows[i]["steps"] >= rows[i + 1]["steps"] for i in range(len(rows) - 1))
            assert rows[0]["steps"] == header["verification"]["full_trace_steps"]
            assert rows[-1]["steps"] == summary["coarse_steps"]
            assert rows[header["middle_cut"]]["steps"] == summary["middle_steps"]
            midpoint = (math.log(rows[0]["steps"]) + math.log(rows[-1]["steps"])) / 2
            assert header["middle_cut"] == min(
                range(len(rows)), key=lambda limit: (abs(math.log(rows[limit]["steps"]) - midpoint), -limit))
            assert all("priority" in op and "associativity" in op and "position" in op
                       for op in data["operators"])
            defined_ids = {op["id"] for op in data["operators"] if op["definition"] is not None}
            target_id = next(op["id"] for op in data["operators"] if op["symbol"] == header["target"])
            for chosen_id, chosen_ids, full in closures.get(summary["set"], []):
                assert not (max(summary["full_steps"], full) <= 1.05 * min(summary["full_steps"], full)
                            and (target_id in chosen_ids or chosen_id in defined_ids))
                if scale["key"] in ("s1000", "s10000"):
                    assert len(defined_ids & chosen_ids) < 0.95 * len(defined_ids | chosen_ids)
            closures.setdefault(summary["set"], []).append((target_id, defined_ids, summary["full_steps"]))
            if scale["key"] == "s10000":
                assert summary["full_steps"] >= 10_000
                assert header["layer"] >= next(
                    row["number_of_layers"] for row in scale["sets"] if row["name"] == summary["set"]) - 2
            for row in rows:
                assert count(nodes, data["operators"], data["root"], row["L"]) == row["steps"]
            for node_index, node in enumerate(nodes):
                strings = strings_by_node[node_index]
                assert count(nodes, data["operators"], node_index, 0) == node["full"]
                assert node["full"] >= len(node["steps"])
                assert all(0 <= text_id < len(strings) for text_id in
                           [*node["inputs"], node["value"]])
                for step in node["steps"]:
                    assert len(step) == 7
                    assert step[0] in (0, 1, 2)
                    assert 0 <= step[1] < len(data["operators"])
                    assert step[2] == -1 or 0 <= step[2] < len(nodes)
                    assert all(0 <= text_id < len(strings) for text_id in step[3:5])
                    assert step[5] is None or 0 <= step[5] < len(strings)


class _ReferenceRuntime:
    def __init__(self, oracle):
        self.oracle = oracle

    def compute(self, operator):
        return lambda *args: self.oracle.evaluate(operator, args).value


@pytest.mark.parametrize("scale", ["s10", "s100"])
def test_small_example_against_reference(scale):
    index = json.loads((DATA / "index.json").read_text())
    record = next(row for row in index["scales"] if row["key"] == scale)
    summary = next(row for row in record["examples"] if row["world"] == "integer")
    data, nodes, strings_by_node = load_example(scale, summary["id"])
    operators = []
    for row in data["operators"]:
        if row["definition"] is None:
            register_for_symbol(row["symbol"], row["parameter_types"], None,
                                row["arity"], row["position"], row["result_type"])
        operators.append(Operator(func_id=row["id"], symbol=row["symbol"], n_ary=row["arity"],
                                  unary_position=row["position"], recursive_layer=row["layer"],
                                  priority=row["priority"], associativity_direction=row["associativity"],
                                  definition=row["definition"], parameter_types=tuple(row["parameter_types"]),
                                  result_type=row["result_type"], op_compute_func="reference",
                                  op_count_func="reference"))
    registry = OperatorRegistry(operators)
    settings = Settings.load(ROOT / "configs/default.yaml")
    oracle = Oracle(registry, settings.symbols, settings.semantics.build())
    target = next(op for op in registry if op.symbol == data["header"]["target"])
    raw_inputs = nodes[data["root"]]["steps"][0][2]
    assert raw_inputs >= 0
    inputs = [json.loads(strings_by_node[raw_inputs][text_id])
              for text_id in nodes[raw_inputs]["inputs"]]
    expression = Call(target, tuple(Number(value) for value in inputs))
    parser = DefinitionParser(settings.symbols, registry)
    tree = build_tree(expression, registry, _ReferenceRuntime(oracle), parser)
    trace = flatten(tree)
    verify_trace(trace, oracle)
    assert len(trace.steps) == data["header"]["verification"]["full_trace_steps"]
    assert str(trace.value) == data["header"]["value"]
