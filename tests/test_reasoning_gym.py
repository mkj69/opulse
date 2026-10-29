"""Reasoning Gym interface, also usable without the optional package."""

import importlib.util
import sys
from types import ModuleType

import pytest
from conftest import INITIAL_OPERATORS

from opulse.cli.main import main
from opulse.integrations.reasoning_gym import OpulseConfig, OpulseDataset


@pytest.fixture(scope="module")
def operators(tmp_path_factory):
    path = tmp_path_factory.mktemp("reasoning_gym") / "operators.jsonl"
    assert main(["operators", "--out", str(path), "--layers", "10", "6", "3", "--seed", "4"]) == 0
    return path


def test_import_without_reasoning_gym():
    if importlib.util.find_spec("reasoning_gym") is not None:
        pytest.skip("Reasoning Gym is installed")
    assert issubclass(OpulseDataset, object)
    assert len(OpulseDataset(OpulseConfig(size=3))) == 3


def test_registration_when_interface_is_available(monkeypatch):
    import opulse.integrations.reasoning_gym as adapter

    package = ModuleType("reasoning_gym")
    package.__path__ = []
    dataset_module = ModuleType("reasoning_gym.dataset")
    dataset_module.ProceduralDataset = type("ProceduralDataset", (), {
        "__init__": lambda self, config, seed=None, size=500: setattr(self, "config", config),
    })
    factory = ModuleType("reasoning_gym.factory")
    factory.DATASETS = {}
    factory.register_dataset = lambda name, dataset_cls, config_cls: factory.DATASETS.update(
        {name: (dataset_cls, config_cls)})
    for name, module in (("reasoning_gym", package), ("reasoning_gym.dataset", dataset_module),
                         ("reasoning_gym.factory", factory)):
        monkeypatch.setitem(sys.modules, name, module)
    spec = importlib.util.spec_from_file_location("opulse.integrations._rg_registration_test", adapter.__file__)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    dataset_cls, config_cls = factory.DATASETS["opulse"]
    assert issubclass(dataset_cls, dataset_module.ProceduralDataset)
    assert config_cls is module.OpulseConfig


@pytest.mark.parametrize("family", ["compute", "hole", "contrast"])
def test_indexed_tasks_and_exact_scoring(operators, family):
    hole = family == "hole"
    size = 2 if hole else 4
    config = OpulseConfig(operators=str(INITIAL_OPERATORS if hole else operators), seed=17, size=size,
                          family=family, max_depth=1 if hole else 2,
                          min_definitions=0 if hole else 1, max_definitions=0 if hole else 4)
    dataset = OpulseDataset(config)
    first = dataset[0]
    assert first == dataset[0]
    assert len(dataset) == size
    assert len(list(dataset)) == size
    assert first["metadata"]["source_dataset"] == "opulse"
    assert first["metadata"]["task"]["axes"]["expression_depth"] <= 3
    assert first["question"] == first["metadata"]["task"]["prompt"]
    assert dataset.score_answer(f"Answer: {first['answer']}", first) == 1.0
    assert dataset.score_answer("Answer: definitely wrong", first) == 0.0
    assert dataset.score_answer(None, first) == 0.0
    with pytest.raises(IndexError):
        dataset[size]
    if family == "contrast":
        second = dataset[1]
        assert first["metadata"]["task"]["expression"] == second["metadata"]["task"]["expression"]
        assert first["answer"] != second["answer"]
        assert first["metadata"]["task"]["axes"]["pair"] == second["metadata"]["task"]["axes"]["pair"] == 0
        assert dataset[2]["metadata"]["task"]["axes"]["pair"] == 1


@pytest.mark.parametrize("family", ["compute", "contrast"])
def test_step_format_uses_opulse_rewrite_checker(operators, family):
    from opulse.config import Settings
    from opulse.core.registry import OperatorRegistry
    from opulse.definition.parser import DefinitionParser
    from opulse.expression.nodes import from_ast
    from opulse.expression.render import ExpressionRenderer
    from opulse.runtime import PythonRuntime
    from opulse.trace import Reducer

    dataset = OpulseDataset(OpulseConfig(operators=str(operators), seed=31,
                                         size=2 if family == "contrast" else 1,
                                         family=family, format="steps", max_depth=2))
    entry = dataset[0]
    task = entry["metadata"]["task"]
    registry = OperatorRegistry.from_jsonl(operators)
    parser = DefinitionParser(Settings().symbols, registry)
    tree = from_ast(parser.parse_expr(task["expression"], expression_mode=True), registry)
    trace = Reducer(registry, PythonRuntime(registry), parser).reduce(tree)
    renderer = ExpressionRenderer(Settings().symbols)
    lines = [f"= {renderer.full(step.expression_after)}" for step in trace.steps]
    full = "\n".join(lines + [f"Answer: {entry['answer']}"])
    assert dataset.score_answer(full, entry) == 1.0
    assert dataset.score_answer(f"Answer: {entry['answer']}", entry) == 0.5
    assert dataset.score_answer("= 987654321\n" + full, entry) < 1.0


def test_config_validation_and_factory_safe_defaults():
    for options in ({"family": "hole", "format": "steps"}, {"family": "contrast", "size": 3},
                    {"max_depth": 0}, {"min_definitions": 2, "max_definitions": 1}):
        with pytest.raises(ValueError):
            OpulseDataset(OpulseConfig(**options))
    with pytest.raises(ValueError, match="operators"):
        OpulseDataset(OpulseConfig(size=1))[0]
