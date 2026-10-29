"""Seeded property checks across Opulse's independent reference paths."""

import random
from dataclasses import replace

import pytest

hypothesis = pytest.importorskip("hypothesis")
from conftest import INITIAL_OPERATORS
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from opulse.bench.check import answer_from_prompt, base_registry
from opulse.bench.score import score_response
from opulse.bench.tasks import BenchBuilder
from opulse.config import Settings
from opulse.core import NAN, OperatorRegistry
from opulse.core.types import same_value
from opulse.definition.ast import render_definition
from opulse.definition.parser import DefinitionParser
from opulse.expression.aliases import AliasMap, aliased_registry
from opulse.expression.generator import ExpressionGenerator, OperatorPool
from opulse.expression.nodes import Call, Number, from_ast, literal_form, to_ast
from opulse.expression.numerals import NumeralWriter
from opulse.expression.render import ExpressionRenderer
from opulse.generation.interest import Fingerprinter
from opulse.generation.pipeline import OperatorFactory, build_layers
from opulse.runtime import PythonRuntime
from opulse.solver.z3_encode import Z3Encoder, evaluate_concrete
from opulse.trace import Reducer
from opulse.verify import Oracle, VerificationError, verify_trace
from opulse.verify.steps import check_steps


@pytest.fixture(scope="module")
def worlds():
    """Two independently generated sets, reused by all examples."""
    result = []
    for seed in (7, 19):
        config = Settings()
        registry = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
        build_layers(OperatorFactory(config, registry, random.Random(seed)), [7, 4])
        result.append((config, registry))
    return result


@pytest.mark.slow
@pytest.mark.parametrize("naming", ["shape_index", "legacy"])
@pytest.mark.parametrize("notation", [
    {},
    {"left_operand": "x", "right_operand": "y", "left_paren": "[", "right_paren": "]",
     "equals": ":=", "nan": "Undef"},
    {"operand_names": ["x", "y", "z"], "argument_separator": "|"},
])
def test_definition_round_trip_every_naming_and_notation(naming, notation):
    config = Settings.from_dict({"operators": {"naming": naming}, "symbols": notation})
    registry = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
    build_layers(OperatorFactory(config, registry, random.Random(12)), [4])
    parser = DefinitionParser(config.symbols, registry)
    writer = NumeralWriter(registry, config.numerals.digits)
    for op in registry:
        if op.definition is None:
            continue
        definition = parser.parse(op.definition)
        for layout in ("compact", "piecewise"):
            rendered = render_definition(definition, config.symbols, writer.write,
                                         layout=layout, min_length=0)
            assert parser.parse(rendered) == definition


@settings(max_examples=35, deadline=None)
@given(st.integers(min_value=0, max_value=10_000), st.integers(min_value=0, max_value=1))
def test_expression_round_trip(worlds, seed, world_index):
    config, registry = worlds[world_index]
    tree = ExpressionGenerator(config.expressions, random.Random(seed)).tree(OperatorPool.from_registry(registry))
    parser = DefinitionParser(config.symbols, registry)
    renderer = ExpressionRenderer(config.symbols, NumeralWriter(registry, config.numerals.digits))
    for text in (renderer.full(tree), renderer.minimal(tree)):
        assert from_ast(parser.parse_expr(text, expression_mode=True), registry) == tree


def _case(worlds, world_index, operator_index, a, b):
    config, registry = worlds[world_index]
    defined = [op for op in registry if op.definition is not None]
    op = defined[operator_index % len(defined)]
    args = (a, b)[:op.n_ary]
    tree = literal_form(Call(op, tuple(Number(x) for x in args)), registry)
    return config, registry, op, args, tree


@pytest.mark.slow
@settings(max_examples=28, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(st.integers(0, 1), st.integers(0, 100), st.integers(-8, 8), st.integers(-8, 8),
       st.one_of(st.none(), st.integers(0, 3)), st.booleans(), st.booleans())
def test_random_trace_is_verified_and_reaches_interpreter(worlds, world_index, operator_index,
                                                          a, b, depth, known, nested):
    config, registry, _, _, tree = _case(worlds, world_index, operator_index, a, b)
    if nested:
        tree = Call(registry.find("+", 2), (tree, Number(abs(b))))
    oracle = Oracle(registry)
    reducer = Reducer(registry, PythonRuntime(registry), DefinitionParser(config.symbols, registry),
                      max_depth=depth, expand=lambda op: op.definition is not None and
                      (not known or (op.recursive_layer or 0) >= 1))
    trace = reducer.reduce(tree)
    assert not trace.truncated
    verify_trace(trace, oracle)
    assert same_value(trace.value, oracle.evaluate_expr(to_ast(tree), {}).value)


@pytest.mark.slow
@settings(max_examples=18, deadline=None)
@given(st.integers(0, 1), st.integers(0, 100), st.integers(-5, 5), st.integers(-5, 5),
       st.integers(0, 100), st.sampled_from(["after", "kind", "index"]))
def test_any_selected_trace_step_rejects_tampering(worlds, world_index, operator_index, a, b,
                                                    step_index, field):
    config, registry, _, _, tree = _case(worlds, world_index, operator_index, a, b)
    oracle = Oracle(registry)
    trace = Reducer(registry, PythonRuntime(registry), DefinitionParser(config.symbols, registry),
                    max_depth=2).reduce(tree)
    verify_trace(trace, oracle)
    index = step_index % len(trace.steps)
    step = trace.steps[index]
    wrong = Number(0 if not isinstance(step.after, Number) or step.after.value != 0 else 1)
    damaged = replace(trace, steps=list(trace.steps))
    # Minimal metadata repro: changing only kind to "bogus" used to pass verify_trace.
    change = {"after": wrong, "kind": "bogus", "index": step.index + 1}[field]
    damaged.steps[index] = replace(step, **{field: change})
    with pytest.raises(VerificationError):
        verify_trace(damaged, oracle)


@pytest.mark.slow
@settings(max_examples=16, deadline=None)
@given(st.integers(0, 1), st.integers(0, 100), st.integers(-5, 5), st.integers(-5, 5))
def test_step_grader_reference_full_credit_and_wrong_final_never_full(worlds, world_index,
                                                                       operator_index, a, b):
    config, registry, _, _, tree = _case(worlds, world_index, operator_index, a, b)
    parser = DefinitionParser(config.symbols, registry)
    oracle = Oracle(registry)
    trace = Reducer(registry, PythonRuntime(registry), parser).reduce(tree)
    assert not trace.truncated
    lines = [ExpressionRenderer(config.symbols).full(step.expression_after) for step in trace.steps]
    report = check_steps(tree, lines, parser, registry, oracle, trace.value)
    assert report.final_correct and report.credit == 1.0
    wrong = 0 if trace.value is NAN or trace.value != 0 else 1
    bad = check_steps(tree, [*lines[:-1], str(wrong)], parser, registry, oracle, trace.value)
    assert not bad.final_correct and bad.credit < 1.0


@settings(max_examples=60, deadline=None)
@given(st.one_of(st.integers(-100_000, 100_000), st.none()),
       st.integers(-100_000, 100_000),
       st.sampled_from(["Answer: {}", "answer: {}.", "**Answer:** {}", "答案：{}", "Answer: `{}`"]),
       st.sampled_from(["NaN", "nan", "NAN", "NaN.", " NaN "]))
def test_bench_never_accepts_wrong_values(answer, candidate, wrapper, nan_spelling):
    wrong = candidate if candidate != answer else candidate + 1
    for text in (str(wrong), nan_spelling if answer is not None else str(wrong)):
        assert not score_response({"family": "compute", "answer": answer}, wrapper.format(text))["correct"]


@pytest.mark.slow
@settings(max_examples=12, deadline=None)
@given(st.integers(0, 1), st.integers(0, 100), st.integers(-8, 8), st.integers(-8, 8))
def test_prompt_only_answer_equals_stored_answer(worlds, world_index, operator_index, a, b):
    config, registry, _, _, tree = _case(worlds, world_index, operator_index, a, b)
    task = BenchBuilder(config, registry, random.Random(1), allow_nan=True)._compute(tree, 0)
    assert task is not None
    value = answer_from_prompt(task.to_dict(), base_registry(registry), config.symbols)
    assert same_value(value, NAN if task.answer is None else task.answer)


@pytest.mark.slow
@settings(max_examples=18, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(st.integers(0, 1), st.integers(0, 100), st.integers(-6, 6), st.integers(-6, 6))
def test_z3_agrees_with_interpreter_when_expressible(worlds, world_index, operator_index, a, b):
    _, registry, op, args, _ = _case(worlds, world_index, operator_index, a, b)
    oracle = Oracle(registry)
    encoder = Z3Encoder(oracle)
    if not encoder.expressible(op):
        return
    got = evaluate_concrete(encoder, op, args)
    assert same_value(got, oracle.evaluate(op, args).value)


@pytest.mark.slow
@settings(max_examples=12, deadline=None)
@given(st.integers(0, 1), st.integers(0, 100))
def test_behaviour_fingerprint_survives_renaming(worlds, world_index, operator_index):
    config, registry = worlds[world_index]
    alias = AliasMap.build(registry, random.Random(42), style="pseudo", symbols=config.symbols)
    renamed = aliased_registry(registry, alias)
    op = [item for item in registry if item.definition][operator_index % len([item for item in registry
                                                                               if item.definition])]
    renamed_op = renamed.get(op.func_id)
    fingerprinter = Fingerprinter(config.interest)
    original_oracle, renamed_oracle = Oracle(registry), Oracle(renamed)
    original = fingerprinter.values(op, lambda *args: original_oracle.evaluate(op, args).value)
    copied = fingerprinter.values(renamed_op, lambda *args: renamed_oracle.evaluate(renamed_op, args).value)
    assert fingerprinter.codes(original).tolist() == fingerprinter.codes(copied).tolist()
