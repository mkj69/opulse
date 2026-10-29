"""Logic atoms, generated forms, and the exported browser data."""

import random
from itertools import product
from pathlib import Path

from world_contract import check_showcase

from opulse.bench.check import base_registry, check_tasks
from opulse.bench.tasks import BenchBuilder
from opulse.config import Settings, Symbols
from opulse.core.operator import BRANCH, RECURSIVE, SIMPLE, Operator
from opulse.core.presets import PRESETS, register_preset
from opulse.core.primitives import atom_records
from opulse.core.registry import OperatorRegistry
from opulse.core.semantics import NAN, Semantics
from opulse.definition.parser import DefinitionParser
from opulse.expression.nodes import Call, Number
from opulse.expression.render import ExpressionRenderer
from opulse.generation.pipeline import OperatorFactory, build_layers
from opulse.runtime import PythonRuntime
from opulse.solver.z3_encode import Z3Encoder, evaluate_concrete
from opulse.trace import Reducer
from opulse.verify import Oracle
from opulse.verify.records import verify_trace
from opulse.verify.steps import check_steps
from opulse.worlds.logic import export_world_showcase


def logic_registry():
    register_preset("logic")
    return OperatorRegistry(Operator.from_dict(row) for row in atom_records(PRESETS["logic"]))


def test_logic_atoms_are_typed_and_encodable():
    registry = logic_registry()
    oracle = Oracle(registry)
    encoder = Z3Encoder(oracle)
    atoms = [op for op in registry if op.result_type == "bool"]
    assert len(atoms) == 6
    for atom in atoms:
        assert atom.parameter_types == ("bool",) * atom.n_ary
        for args in product((False, True), repeat=atom.n_ary):
            expected = oracle.evaluate(atom, args).value
            assert isinstance(expected, bool)
            assert evaluate_concrete(encoder, atom, args) is expected
    assert Semantics().operations()["logic_and"](True, 1) is NAN


def test_logic_generated_pipeline_and_granularity():
    registry = logic_registry()
    settings = Settings.load(Path(__file__).resolve().parents[1] / "configs/presets/logic.yaml")
    factory = OperatorFactory(settings, registry, random.Random(40))
    build_layers(factory, [8, 4], (0.4, 0.4, 0.2))
    generated = [op for op in registry if op.definition]
    assert {op.definition_type for op in generated} == {SIMPLE, BRANCH, RECURSIVE}
    oracle = Oracle(registry)
    runtime = PythonRuntime(registry)
    parser = DefinitionParser(Symbols(), registry)
    renderer = ExpressionRenderer(Symbols())
    recursive = next(op for op in generated if op.definition_type == RECURSIVE)
    assert recursive.parameter_types == ("bool", "int")
    assert oracle.evaluate(recursive, (True, 4)).value is NAN
    for a, b in product((False, True), range(-3, 4)):
        expected = oracle.evaluate(recursive, (a, b))
        assert runtime.evaluate(recursive)(a, b) == (expected.value, expected.base_ops, expected.calls)
        assert evaluate_concrete(Z3Encoder(oracle), recursive, (a, b)) is expected.value

    tree = Call(recursive, (Number(True), Number(3)))
    for depth in (None, 1, 2):
        trace = Reducer(registry, runtime, parser, max_depth=depth).reduce(tree)
        assert not trace.truncated
        verify_trace(trace, oracle)
        lines = [renderer.full(step.expression_after) for step in trace.steps]
        report = check_steps(tree, lines, parser, registry, oracle,
                             oracle.evaluate(recursive, (True, 3)).value)
        assert report.final_correct and report.first_error is None

    builder = BenchBuilder(settings, registry, random.Random(32), max_depth=2,
                           answer_format="steps", max_answer_share=1)
    tasks = [task.to_dict() for task in builder.tasks("compute", 4)]
    assert not check_tasks(tasks, base_registry(registry))


def test_logic_showcase_contract(tmp_path):
    data = export_world_showcase("logic", tmp_path / "logic.json")
    check_showcase(data, tmp_path)
    for operator in data["operators"]:
        assert operator["truth_table"] and operator["circuit"]["nodes"]
        assert len(operator["truth_table"]) in (2, 4, 9, 18, 81)
