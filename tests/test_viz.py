"""The report and wizard must preserve generated data and loadable settings."""

import json
import re

import pytest

from opulse.analysis.graph import dependency_graph, to_dot, topological_layers
from opulse.cli.main import main
from opulse.config import Settings
from opulse.core import OperatorRegistry


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    path = tmp_path_factory.mktemp("viz") / "operators.jsonl"
    assert main(["operators", "--out", str(path), "--layers", "4", "3", "--seed", "5"]) == 0
    return path


def test_graph_contains_valid_dependencies_and_dot_symbols(generated):
    registry = OperatorRegistry.from_jsonl(generated)
    graph = dependency_graph(registry)
    ids = {node["func_id"] for node in graph["nodes"]}
    assert set().union(*map(set, topological_layers(graph))) == ids
    for edge in graph["edges"]:
        assert edge["source"] in ids and edge["target"] in ids
        op = registry.get(edge["source"])
        assert edge["target"] in op.dependencies or edge["source"] == edge["target"]
    assert all(edge["source"] == edge["target"] or edge["target"] in registry.get(edge["source"]).dependencies
               for edge in graph["edges"])
    dot = to_dot(graph)
    assert all(json.dumps(op.symbol, ensure_ascii=False) in dot for op in registry)


def test_graph_rejects_nonself_cycle():
    graph = {"nodes": [{"func_id": "a"}, {"func_id": "b"}],
             "edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "a"}]}
    with pytest.raises(ValueError, match="cycle"):
        topological_layers(graph)


def test_viz_writes_embedded_data_and_dot(generated, tmp_path):
    expr = tmp_path / "expressions.jsonl"
    assert main(["expressions", "--operators", str(generated), "--out", str(expr),
                 "--count", "3", "--seed", "4"]) == 0
    out = tmp_path / "report"
    assert main(["viz", "--operators", str(generated), "--expressions", str(expr),
                 "--out", str(out)]) == 0
    html = (out / "index.html").read_text()
    embedded = re.search(r'<script id="report-data" type="application/json">(.*?)</script>', html, re.DOTALL)
    assert embedded
    payload = json.loads(embedded.group(1))
    from opulse.canary import CANARY

    assert payload["meta"]["canary"] == CANARY
    assert CANARY in (out / "graph.dot").read_text()
    assert len(payload["graph"]["nodes"]) == len(OperatorRegistry.from_jsonl(generated))
    assert len(payload["expressions"]) == 3
    assert payload["statistics"]["expressions"]["count"] == 3
    assert (out / "graph.dot").exists()


def test_wizard_answers_round_trip_and_reject_invalid(tmp_path):
    answers = {"semantics": {"mode": "exact", "bound": 10000},
               "symbols": {"left_operand": "x", "right_operand": "y", "left_paren": "[",
                           "right_paren": "]", "equals": ":=", "nan": "Undef"},
               "numerals": {"max_base": 12},
               "operators": {"symbol_sets": ["suits", "arrows"], "max_if_branches": 4,
                             "partial_probability": 0.2},
               "recursion": {"style": "direct", "direct_bound": 4},
               "expressions": {"variables": ["x", "y"], "max_depth": 2},
               "layers": [5, 3]}
    answer_path = tmp_path / "answers.json"
    answer_path.write_text(json.dumps(answers))
    output = tmp_path / "settings.yaml"
    assert main(["wizard", "--answers", str(answer_path), "--out", str(output)]) == 0
    from opulse.canary import CANARY

    assert output.read_text().startswith(f"# {CANARY}\n")
    assert Settings.load(output) == Settings.from_dict({k: v for k, v in answers.items() if k != "layers"})
    assert "--layers 5 3" in output.read_text()
    answers["recursion"] = {"style": "unknown"}
    answer_path.write_text(json.dumps(answers))
    invalid_out = tmp_path / "invalid.yaml"
    assert main(["wizard", "--answers", str(answer_path), "--out", str(invalid_out)]) == 2
    assert not invalid_out.exists()
