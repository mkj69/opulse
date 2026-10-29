"""Grid atoms and their typed end-to-end pipeline."""

import random

import pytest
from world_contract import check_showcase

from opulse.bench.check import (
    base_registry,
    check_tasks,
    prompt_registry,
    prompt_signatures,
)
from opulse.bench.tasks import BenchBuilder
from opulse.config import Settings, Symbols
from opulse.core.operator import BRANCH, RECURSIVE, SIMPLE
from opulse.core.semantics import NAN, Semantics
from opulse.core.types import matches, type_of
from opulse.definition.parser import DefinitionParser
from opulse.expression.nodes import Call, Number, from_ast
from opulse.expression.render import ExpressionRenderer
from opulse.generation.pipeline import OperatorFactory
from opulse.runtime import PythonRuntime
from opulse.solver.z3_encode import NotExpressible, Z3Encoder
from opulse.trace.reducer import Reducer
from opulse.verify import Oracle
from opulse.verify.steps import check_steps
from opulse.worlds.grid import (
    GRID_ATOMS,
    count,
    crop,
    encode_value,
    export_world_showcase,
    fill,
    grid,
    make_registry,
    overlay,
    recolour,
    reflect_h,
    reflect_v,
    rotate,
    text,
    translate,
    transpose,
)


def test_grid_atoms_and_bounds():
    make_registry()
    value = grid(((0, 1, 0), (2, 0, 3)))
    assert str(type_of(value)) == "grid"
    assert text(value) == "010\n203"
    assert rotate(value) == ((2, 0), (0, 1), (3, 0))
    assert reflect_h(value) == ((0, 1, 0), (3, 0, 2))
    assert reflect_v(value) == ((2, 0, 3), (0, 1, 0))
    assert transpose(value) == ((0, 2), (1, 0), (0, 3))
    assert translate(value, 1, axis=1, wrap=True) == ((0, 0, 1), (3, 2, 0))
    assert translate(value, -1, axis=1, wrap=True) == ((1, 0, 0), (0, 3, 2))
    assert translate(value, 1, axis=0, wrap=False) == ((0, 0, 0), (0, 1, 0))
    assert translate(value, 3, axis=0, wrap=False) == ((0, 0, 0), (0, 0, 0))
    assert recolour(value, 13) == ((0, 3, 0), (2, 0, 3))
    assert overlay(value, ((4, 0, 0), (0, 5, 0))) == ((4, 1, 0), (2, 5, 3))
    assert crop(((0, 0, 0), (0, 2, 0), (0, 3, 0))) == ((2,), (3,))
    assert crop(((0, 0),)) == ((0,),)
    assert count(value, 0) == 3
    assert fill(value, 4) == ((4, 1, 4), (2, 4, 3))
    assert len(GRID_ATOMS) == 14
    with pytest.raises(ValueError):
        grid(((0, 10),))
    with pytest.raises(ValueError):
        grid(((0,) * 11,))
    assert not matches(((0,), (1, 2)), "grid")
    semantics = Semantics().operations()
    assert semantics["grid_overlay"](value, ((1,),)) is NAN
    assert semantics["grid_recolour"](value, 100) is NAN
    assert semantics["grid_fill"](value, -1) is NAN
    assert semantics["grid_count"](value, 10) is NAN


def _generated():
    registry = make_registry()
    factory = OperatorFactory(Settings(), registry, random.Random(34))
    generated = []
    for kind, layer in ((SIMPLE, 0), (BRANCH, 0), (RECURSIVE, 1)):
        operator = factory.generate(kind, layer)
        factory.add(operator)
        generated.append(operator)
    return registry, generated


def test_generation_reference_derivations_and_granularity():
    registry, generated = _generated()
    runtime = PythonRuntime(registry)
    oracle = Oracle(registry)
    parser = DefinitionParser(Symbols(), registry)
    value = ((0, 1), (2, 0), (0, 3))
    for operator in generated:
        args = (value, 2) if operator.n_ary == 2 else (value,)
        result = oracle.evaluate(operator, args)
        assert runtime.evaluate(operator)(*args) == (result.value, result.base_ops, result.calls)
        tree = Call(operator, tuple(Number(arg) for arg in args))
        for max_depth in (None, 1, 2):
            trace = Reducer(registry, runtime, parser, max_depth=max_depth).reduce(tree)
            assert not trace.truncated
            assert trace.value == result.value
            lines = [ExpressionRenderer(Symbols()).full(step.expression_after) for step in trace.steps]
            report = check_steps(tree, lines, parser, registry, oracle, result.value)
            assert report.final_correct and report.first_error is None


def test_benchmark_prompt_and_z3_boundary():
    registry, generated = _generated()
    builder = BenchBuilder(Settings(), registry, random.Random(23), max_depth=2,
                           answer_format="steps", max_answer_share=1)
    tasks = [task.to_dict() for task in builder.tasks("compute", 3)]
    assert len(tasks) == 3
    assert not check_tasks(tasks, base_registry(registry))
    first = tasks[0]
    assert "grid" in first["prompt"]
    assert "Grid inputs in expression order (rows of digits):" in first["prompt"]
    parsed = prompt_registry(first["definitions"], base_registry(registry),
                             signatures=prompt_signatures(first["prompt"]))
    tree = from_ast(parsed.parser.parse_expr(first["expression"], expression_mode=True), parsed.registry)
    trace = Reducer(parsed.registry, PythonRuntime(parsed.registry), parsed.parser).reduce(tree)
    lines = [ExpressionRenderer(Symbols()).full(step.expression_after) for step in trace.steps]
    answer = tuple(tuple(row) for row in first["answer"])
    assert check_steps(tree, lines, parsed.parser, parsed.registry,
                       parsed.oracle, answer).final_correct
    encoder = Z3Encoder(Oracle(registry))
    assert not encoder.expressible(generated[0])
    with pytest.raises(NotExpressible):
        encoder.variables(generated[0])


def test_showcase_from_real_reductions(tmp_path):
    data = export_world_showcase("grid", tmp_path / "grid.json")
    check_showcase(data, tmp_path)
    assert data["dimension"] == "vision"
    sizes = {(len(example["inputs"][0]["v"]), len(example["inputs"][0]["v"][0]))
             for op in data["operators"] for example in op["examples"] if example["inputs"][0]["t"] == "grid"}
    assert len(sizes) >= 5 and max(max(size) for size in sizes) >= 8
    assert encode_value(((0, 3), (1, 1))) == {"t": "grid", "v": [[0, 3], [1, 1]]}
