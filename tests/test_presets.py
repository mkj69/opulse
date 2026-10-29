"""Numeric presets use their own atoms throughout generation and checking."""

import json

import pytest

from opulse.cli.main import main
from opulse.config import Settings
from opulse.core.primitives import CUSTOM, atom_records
from opulse.core.registry import OperatorRegistry
from opulse.presets import PRESETS
from opulse.solver.z3_encode import Z3Encoder
from opulse.verify import Oracle


@pytest.mark.parametrize("name", tuple(PRESETS))
def test_preset_pipeline(name, tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text(f"preset: {name}\n")
    operators = tmp_path / "operators.jsonl"
    assert main(["operators", "--preset", name, "--out", str(operators),
                 "--layers", "5", "2", "--seed", "17"]) == 0
    registry = OperatorRegistry.from_jsonl(operators)
    starting = [op for op in registry if op.definition is None]
    assert len(starting) == len(PRESETS[name]["atoms"])
    assert {op.symbol for op in starting} == {row["symbol"] for row in atom_records(PRESETS[name]["atoms"])}
    assert any(op.definition_type == "recursive_definition" for op in registry)
    if name == "bits":
        encoder = Z3Encoder(Oracle(registry))
        assert not encoder.expressible(next(op for op in starting if op.symbol == "∧"))
    expressions = tmp_path / "expressions.jsonl"
    assert main(["expressions", "--config", str(config), "--operators", str(operators),
                 "--out", str(expressions), "--count", "4", "--cot", "en"]) == 0
    assert all(json.loads(line)["cot"] for line in expressions.read_text().splitlines())
    assert main(["verify", "--config", str(config), "--operators", str(operators),
                 "--expressions", str(expressions), "--samples", "10"]) == 0
    tasks = tmp_path / "tasks.jsonl"
    assert main(["bench", "build", "--config", str(config), "--operators", str(operators),
                 "--out", str(tasks), "--count", "2", "--max-depth", "2",
                 "--max-answer-share", "1"]) == 0
    assert main(["bench", "check", "--config", str(config), "--operators", str(operators),
                 "--tasks", str(tasks)]) == 0


def test_preset_settings_can_be_overridden():
    settings = Settings.from_dict({"preset": "bits", "expressions": {"value_max": 7},
                                   "operators": {"condition_max": 9}})
    assert settings.expressions.value_max == 7
    assert settings.operators.condition_max == 9
    assert settings.recursion.style == "bits"
    assert CUSTOM["bit_and"].z3 is None
