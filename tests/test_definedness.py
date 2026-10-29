"""The optional definedness atom across the execution and prompt paths."""

import random

import pytest
from conftest import INITIAL_OPERATORS

from opulse.bench.check import answer_from_prompt, base_registry, check_tasks
from opulse.bench.context import rules_text
from opulse.cli.main import main
from opulse.config import Settings, Symbols
from opulse.core import NAN, Operator, OperatorRegistry, Semantics
from opulse.core.primitives import enable_definedness
from opulse.definition import ast
from opulse.definition.codegen import compile_definition, registry_resolver
from opulse.definition.parser import DefinitionParser
from opulse.expression.generator import ExpressionGenerator
from opulse.expression.nodes import Call, Number, iter_calls
from opulse.generation.drafts import branch_draft
from opulse.generation.pipeline import OperatorFactory
from opulse.runtime import PythonRuntime
from opulse.solver.smt import evaluate_module, export, module
from opulse.solver.z3_encode import Z3Encoder, evaluate_concrete
from opulse.trace import Reducer
from opulse.verify import Oracle, verify_trace
from opulse.verify.steps import check_steps


def _world():
    registry = OperatorRegistry()
    enable_definedness(registry)
    operator = Operator(func_id="branchdefined", symbol="◇", n_ary=1, unary_position="postfix",
                        definition="a ◇ = { 7, if defined a == 0; a, else }")
    parser = DefinitionParser(Symbols(), registry)
    code = compile_definition(parser.parse(operator.definition), operator.func_id,
                              registry_resolver(registry, operator))
    operator.op_compute_func, operator.op_count_func = code.compute, code.count
    registry.add(operator)
    return registry, operator


def test_disabled_by_default_and_enabled_by_settings_and_cli(tmp_path):
    assert not Settings().operators.definedness
    registry = OperatorRegistry()
    enable_definedness(registry)
    enable_definedness(registry)
    assert len(registry) == 1
    settings = Settings.from_dict({"operators": {"definedness": True}})
    assert settings.operators.definedness
    configured = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
    OperatorFactory(settings, configured, random.Random(1))
    assert configured.find("defined", 1, "prefix") is not None
    out = tmp_path / "ops.jsonl"
    assert main(["operators", "--initial", str(INITIAL_OPERATORS), "--out", str(out), "--layers", "8",
                 "--proportions", "0", "1", "0", "--seed", "4", "--enable-definedness"]) == 0
    generated = OperatorRegistry.from_jsonl(out)
    assert generated.find("defined", 1, "prefix") is not None
    parser = DefinitionParser(Symbols(), generated)
    definitions = [parser.parse(op.definition) for op in generated if op.definition]
    assert any(any(app.symbol == "defined" for app in ast.iter_applications(branch.expr))
               for definition in definitions for branch in definition.branches)
    assert any(any(app.symbol == "defined" for app in ast.iter_applications(branch.condition))
               for definition in definitions for branch in definition.branches if branch.condition)


def test_definedness_in_reference_compiled_trace_and_steps():
    registry, operator = _world()
    atom = registry.find("defined", 1, "prefix")
    semantics = Semantics("exact", 1)
    assert semantics.operations()["defined"](NAN) == 0
    assert semantics.operations()["defined"](500) == 1
    oracle = Oracle(registry, semantics=semantics)
    runtime = PythonRuntime(registry, semantics)
    assert oracle.evaluate(atom, (NAN,)).value == runtime.compute(atom)(NAN) == 0
    for value, expected in [(NAN, 7), (0, 0), (1, 1)]:
        assert oracle.evaluate(operator, (value,)).value == expected
        assert runtime.compute(operator)(value) == expected
        assert runtime.evaluate(operator)(value)[0] == expected
    parser = DefinitionParser(Symbols(), registry)
    start = Call(atom, (Number(NAN),))
    trace = Reducer(registry, runtime, parser).reduce(start)
    assert trace.value == 0
    verify_trace(trace, oracle)
    assert check_steps(start, ["0"], parser, registry, oracle, 0).final_correct
    branch_start = Call(operator, (Number(NAN),))
    branch_trace = Reducer(registry, runtime, parser).reduce(branch_start)
    assert branch_trace.value == 7
    verify_trace(branch_trace, oracle)
    assert check_steps(branch_start, ["7"], parser, registry, oracle, 7).final_correct


def test_definedness_in_cython_runtime(tmp_path):
    pytest.importorskip("Cython")
    from opulse.runtime.cython_backend import CythonRuntime

    registry, operator = _world()
    runtime = CythonRuntime(registry, tmp_path / "cython", jobs=1)
    assert runtime.compute(operator)(NAN) == 7
    assert runtime.compute(operator)(4) == 4


def test_definedness_in_z3_and_smt_export():
    registry, operator = _world()
    atom = registry.find("defined", 1, "prefix")
    encoder = Z3Encoder(Oracle(registry))
    for value, expected in [(NAN, 0), (0, 1), (12, 1)]:
        assert evaluate_concrete(encoder, atom, (value,)) == expected
    for value, expected in [(NAN, 7), (0, 0), (12, 12)]:
        assert evaluate_concrete(encoder, operator, (value,)) == expected
    exported = export(operator, encoder)
    assert exported is not None
    assert evaluate_module(module(operator, encoder), operator, [(NAN,), (0,), (12,)]) == [7, 0, 12]
    assert evaluate_module(module(atom, encoder), atom, [(NAN,), (0,)]) == [0, 1]


def test_definedness_in_generated_conditions_and_prompt_check():
    registry, operator = _world()
    settings = Settings.from_dict({"operators": {"definedness": True}})
    bodies = ExpressionGenerator(settings.expressions, random.Random(3)).definition_bodies(
        OperatorRegistry([registry.find("defined", 1, "prefix")]), 0, 1, ("a",))
    assert any(call.operator.symbol == "defined" for call in iter_calls(bodies[0]))
    body = Number(2)
    drafts = [branch_draft("⊕", 1, "postfix", [body, Number(3)], settings.operators,
                           settings.symbols, random.Random(seed), "defined", "/") for seed in range(20)]
    draft = next(draft for draft in drafts if "defined" in str(draft.definition))
    assert "defined" in str(draft.definition)
    prompt = ("Rules:\n" + rules_text(["defined"], Semantics()) + "\n\nDefinitions:\n" +
              operator.definition + "\n\nWhat is the value of `NaN ◇`?")
    task = {"id": "defined", "family": "compute", "context": "full", "prompt": prompt,
            "definitions": [operator.definition], "expression": "NaN ◇", "answer": 7,
            "answer_text": "7"}
    assert answer_from_prompt(task, base_registry(registry)) == 7
    assert check_tasks([task], base_registry(registry)) == []
    task["prompt"] = prompt.replace("  - defined a is 1 if a is an integer and 0 if a is NaN.\n", "")
    assert check_tasks([task], base_registry(registry))
