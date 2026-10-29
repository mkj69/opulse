"""Typed atoms, generated definitions, traces, prompts, and step grading."""

import json
import random

import pytest

from opulse.bench.check import (
    base_registry,
    check_tasks,
    prompt_registry,
    prompt_signatures,
)
from opulse.bench.score import score_response
from opulse.bench.tasks import BenchBuilder
from opulse.config import Settings, Symbols
from opulse.core.operator import Operator
from opulse.core.presets import PRESETS, register_preset
from opulse.core.primitives import atom_records
from opulse.core.registry import OperatorRegistry
from opulse.core.semantics import NAN, Semantics
from opulse.definition.parser import DefinitionParser
from opulse.expression.dataset import ExpressionDataset
from opulse.expression.nodes import Call, Number, from_ast
from opulse.expression.render import ExpressionRenderer
from opulse.generation.pipeline import OperatorFactory, build_layers
from opulse.runtime import PythonRuntime
from opulse.solver.z3_encode import Z3Encoder, evaluate_concrete
from opulse.trace import Reducer
from opulse.verify import Oracle
from opulse.verify.records import audit_record, verify_trace
from opulse.verify.steps import check_steps


@pytest.mark.parametrize(
    "world,atom,args,want,limited",
    [
        ("strings", "⊕", ("ab", "c"), "abc", Semantics(max_string_length=2)),
        ("lists", "⊞", ((1, 2), (3,)), (1, 2, 3), Semantics(max_list_length=2)),
    ],
)
def test_typed_pipeline(world, atom, args, want, limited):
    register_preset(world)
    registry = OperatorRegistry(
        Operator.from_dict(row) for row in atom_records(PRESETS[world], seed=18)
    )
    base = registry.find(atom, 2)
    assert (
        Semantics().operations()[{"⊕": "str_concat", "⊞": "list_append"}[atom]](*args)
        == want
    )
    assert (
        limited.operations()[{"⊕": "str_concat", "⊞": "list_append"}[atom]](*args)
        is NAN
    )
    assert evaluate_concrete(Z3Encoder(Oracle(registry)), base, args) == want

    settings = Settings()
    factory = OperatorFactory(settings, registry, random.Random(18))
    build_layers(factory, [2, 2])
    generated = [op for op in registry if op.definition]
    assert len(generated) == 4
    assert any(op.definition_type == "recursive_definition" for op in generated)
    runtime = PythonRuntime(registry)
    oracle = Oracle(registry)
    recursive = next(
        op for op in generated if op.definition_type == "recursive_definition"
    )
    value = "abc" if world == "strings" else (1, 2, 3)
    expected = oracle.evaluate(recursive, (value, 2))
    assert runtime.evaluate(recursive)(value, 2) == (
        expected.value,
        expected.base_ops,
        expected.calls,
    )
    if world == "lists":
        assert oracle.evaluate(recursive, (list(value), 2)).value == expected.value
        assert runtime.evaluate(recursive)(list(value), 2)[0] == expected.value
    assert oracle.evaluate(recursive, (value, 9)).value is NAN

    tree = Call(recursive, (Number(value), Number(2)))
    reducer = Reducer(registry, runtime, DefinitionParser(Symbols(), registry))
    trace = reducer.reduce(tree)
    assert not trace.truncated
    verify_trace(trace, oracle)
    renderer = ExpressionRenderer(Symbols())
    lines = [renderer.full(step.expression_after) for step in trace.steps]
    report = check_steps(
        tree,
        lines,
        DefinitionParser(Symbols(), registry),
        registry,
        oracle,
        expected.value,
    )
    assert report.final_correct and report.first_error is None

    dataset = ExpressionDataset(
        settings, registry, runtime, random.Random(29), cot="en"
    )
    record = json.loads(json.dumps(next(dataset.records(1))))
    assert not audit_record(record, registry, oracle, settings, runtime)

    builder = BenchBuilder(
        settings, registry, random.Random(23), max_depth=2, answer_format="steps"
    )
    tasks = [task.to_dict() for task in builder.tasks("compute", 3)]
    assert not check_tasks(tasks, base_registry(registry))
    task = tasks[0]
    prompt_ops = prompt_registry(
        task["definitions"],
        base_registry(registry),
        signatures=prompt_signatures(task["prompt"]),
    )
    parsed = prompt_ops.parser.parse_expr(task["expression"], expression_mode=True)
    start = from_ast(parsed, prompt_ops.registry)
    prompt_trace = Reducer(
        prompt_ops.registry, PythonRuntime(prompt_ops.registry), prompt_ops.parser
    ).reduce(start)
    prompt_lines = [renderer.full(step.expression_after) for step in prompt_trace.steps]
    answer = (
        NAN
        if task["answer"] is None
        else tuple(task["answer"])
        if isinstance(task["answer"], list)
        else task["answer"]
    )
    prompt_report = check_steps(
        start,
        prompt_lines,
        prompt_ops.parser,
        prompt_ops.registry,
        prompt_ops.oracle,
        answer,
    )
    assert prompt_report.final_correct and prompt_report.first_error is None
    assert score_response(task, f"Answer: {task['answer_text']}")["correct"]


def test_typed_literals_and_type_error():
    register_preset("strings")
    registry = OperatorRegistry(
        Operator.from_dict(row) for row in atom_records(PRESETS["strings"])
    )
    parser = DefinitionParser(Symbols(), registry)
    assert parser.parse_expr('"a b" ⊕ "c"')
    assert parser.parse_expr("true")
    assert parser.parse_expr("[[1, 2]]").value == ((1, 2),)
    assert Semantics().operations()["str_concat"](4, "x") is NAN
    assert not score_response({"family": "compute", "answer": True}, "Answer: 1")[
        "correct"
    ]
    from opulse.definition.typecheck import check_definition

    invalid = parser.parse("a ◇ b = { a ⊕ 2 }")
    operator = Operator(
        func_id="bad",
        symbol="◇",
        n_ary=2,
        parameter_types=("str", "str"),
        result_type="str",
        definition="a ◇ b = { a ⊕ 2 }",
    )
    from opulse.definition.codegen import registry_resolver

    with pytest.raises(TypeError):
        check_definition(invalid, operator, registry_resolver(registry, operator))
