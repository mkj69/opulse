"""Permutation values across generation, checking, and presentation data."""

import json
import random

import pytest
from world_contract import check_showcase

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
from opulse.solver.z3_encode import Z3Encoder
from opulse.trace import Reducer
from opulse.verify import Oracle
from opulse.verify.records import audit_record, verify_trace
from opulse.verify.steps import check_steps
from opulse.worlds.perm import (
    Permutation,
    apply,
    compose,
    export_world_showcase,
    inverse,
    reverse,
    rotate_left,
    rotate_right,
    swap,
)


def registry(cards=5):
    register_preset("perm", cards=cards)
    return OperatorRegistry(
        Operator.from_dict(row) for row in atom_records(PRESETS["perm"], seed=32)
    )


def test_permutation_atoms_and_order():
    register_preset("perm")
    p = Permutation((1, 2, 0, 4, 3))
    q = Permutation((1, 0, 2, 3, 4))
    assert compose(p, q) != compose(q, p)
    assert compose(p, inverse(p)) == Permutation(range(5))
    assert rotate_right(rotate_left(p)) == p
    assert reverse(reverse(p)) == p
    assert swap(p, 1 * 5 + 4) == Permutation((4, 2, 0, 1, 3))
    assert swap(p, 25) is NAN
    assert apply(p, 2) == 0
    assert apply(p, -1) is NAN
    with pytest.raises(ValueError):
        Permutation((0, 0, 1))
    ops = Semantics().operations()
    assert ops["rotate_left"](list(p)) is NAN
    assert ops["rotate_left"](p) == rotate_left(p)


def test_configurable_size_and_persisted_atoms(tmp_path):
    registry(7).to_jsonl(tmp_path / "perm.jsonl")
    loaded = OperatorRegistry.from_jsonl(tmp_path / "perm.jsonl")
    p = Permutation(range(7))
    assert loaded.find("⤺", 1, "postfix").parameter_types == ("perm[7]",)
    assert Oracle(loaded).evaluate(loaded.find("⤺", 1, "postfix"), (p,)).value == rotate_left(p)
    parser = DefinitionParser(Symbols(), loaded)
    assert parser.parse_expr("P[0, 1, 2, 3, 4, 5, 6] ⤺")


def test_generation_trace_bench_and_solver_status():
    ops = registry()
    settings = Settings.from_dict({"recursion": {"style": "direct", "direct_bound": 3}})
    build_layers(OperatorFactory(settings, ops, random.Random(32)), [8, 5])
    generated = [op for op in ops if op.definition]
    assert {op.definition_type for op in generated} == {
        "simple_definition", "branch_definition", "recursive_definition"
    }
    oracle = Oracle(ops)
    runtime = PythonRuntime(ops)
    renderer = ExpressionRenderer(Symbols())
    p = Permutation((1, 2, 0, 4, 3))
    for depth in (None, 1):
        recursive = next(op for op in generated if op.definition_type == "recursive_definition")
        tree = Call(recursive, (Number(p), Number(2)))
        trace = Reducer(ops, runtime, DefinitionParser(Symbols(), ops), max_depth=depth).reduce(tree)
        assert not trace.truncated
        verify_trace(trace, oracle)
        assert runtime.evaluate(recursive)(p, 2)[0] == oracle.evaluate(recursive, (p, 2)).value
        lines = [renderer.full(step.expression_after) for step in trace.steps]
        report = check_steps(tree, lines, DefinitionParser(Symbols(), ops), ops, oracle, trace.value)
        assert report.final_correct and report.first_error is None
    assert not Z3Encoder(oracle).expressible(ops.find("⤨", 2))
    assert not Z3Encoder(oracle).expressible(ops.find("≋", 2))
    assert not Z3Encoder(oracle).expressible(recursive)
    record = json.loads(json.dumps(next(ExpressionDataset(
        settings, ops, runtime, random.Random(4), cot="en"
    ).records(1))))
    assert not audit_record(record, ops, oracle, settings, runtime)

    tasks = [task.to_dict() for task in BenchBuilder(
        settings, ops, random.Random(1), max_depth=2, answer_format="steps"
    ).tasks("compute", 3)]
    assert not check_tasks(tasks, base_registry(ops))
    for task in tasks:
        assert score_response(task, "Answer: " + task["answer_text"])["correct"]
        prompt = prompt_registry(task["definitions"], base_registry(ops),
                                 signatures=prompt_signatures(task["prompt"]))
        tree = from_ast(prompt.parser.parse_expr(task["expression"], expression_mode=True),
                        prompt.registry)
        trace = Reducer(prompt.registry, PythonRuntime(prompt.registry), prompt.parser).reduce(tree)
        lines = [renderer.full(step.expression_after) for step in trace.steps]
        answer = Permutation(task["answer"]) if task["answer_text"].startswith("P[") else task["answer"]
        assert check_steps(tree, lines, prompt.parser, prompt.registry,
                           prompt.oracle, answer).final_correct


def test_showcase_contract_and_card_values(tmp_path):
    data = export_world_showcase("perm", tmp_path / "perm.json")
    check_showcase(data, tmp_path)
    values = [example["output"] for op in data["operators"] for example in op["examples"]]
    assert any(value["t"] == "perm" for value in values) and any(value["t"] == "nan" for value in values)
