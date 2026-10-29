"""Bounded search and laws of operators with three or more arguments."""

import random

import pytest
from conftest import INITIAL_OPERATORS

from opulse.bench.check import answer_from_prompt, base_registry
from opulse.bench.context import SEARCH_RULE, rules_text
from opulse.cli.main import main
from opulse.config import Settings, Symbols
from opulse.core import NAN, Operator, OperatorRegistry
from opulse.definition.ast import render_definition
from opulse.definition.codegen import compile_definition, registry_resolver
from opulse.definition.parser import DefinitionParser, DefinitionSyntaxError
from opulse.expression.nodes import Call, Number
from opulse.expression.render import ExpressionRenderer
from opulse.generation.pipeline import OperatorFactory
from opulse.language.narrate import narrate
from opulse.runtime import PythonRuntime
from opulse.runtime.cython_backend import CythonRuntime
from opulse.solver.properties import PropertyChecker, properties_for
from opulse.solver.smt import check_module, module
from opulse.solver.z3_encode import NotExpressible, Z3Encoder, evaluate_concrete
from opulse.trace.reducer import Reducer
from opulse.verify import Oracle, verify_trace
from opulse.verify.steps import check_steps


def define(registry, text, symbol="⊕", arity=2, symbols=None):
    symbols = symbols or Symbols()
    op = Operator(f"search{len(registry)}", symbol, arity, definition=text)
    parser = DefinitionParser(symbols, registry)
    definition = parser.parse(text)
    code = compile_definition(definition, op.func_id, registry_resolver(registry, op))
    op.op_compute_func, op.op_count_func = code.compute, code.count
    op.dependencies = list(code.dependencies)
    registry.add(op)
    return op, parser, definition


def test_search_roundtrip_and_invalid_syntax():
    registry = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
    text = "a ⊕ b = { search(i, 4, (i + a) == b) }"
    _, parser, definition = define(registry, text)
    assert parser.parse(render_definition(definition, Symbols())) == definition
    custom = Symbols(left_paren="[", right_paren="]", argument_separator="|")
    parser = DefinitionParser(custom, registry)
    written = "a ⊗ b = { search[i| 3| i == [a + b]] }"
    assert render_definition(parser.parse(written), custom) == "a ⊗ b = { search[i| 3| i == a + b] }"
    with pytest.raises(DefinitionSyntaxError):
        parser.parse("a ⊗ b = { search[i| 3| i == c] }")
    with pytest.raises(ValueError):
        Symbols(operand_names=("a", "b", "search"))


def test_search_index_is_local_to_its_expression():
    registry = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
    symbols = Symbols(left_operand="i", right_operand="a")
    op, _, _ = define(registry, "i ⊕ a = { search(i, 2, i == a) + i }", symbols=symbols)
    assert PythonRuntime(registry).compute(op)(7, 1) == 8
    assert Oracle(registry, symbols).evaluate(op, (7, 1)).value == 8


def test_search_short_circuits_and_aborts_on_undefined_comparison():
    registry = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
    op, _, _ = define(registry,
                      "a ⊕ b = { search(i, 4, i == a or (b / (i - i)) == 0) }")
    runtime, oracle = PythonRuntime(registry), Oracle(registry)
    assert runtime.evaluate(op)(0, 3) == (0, 0, 0)
    assert runtime.evaluate(op)(1, 3) == (NAN, 2, 2)
    assert oracle.evaluate(op, (1, 3)).value is NAN
    assert evaluate_concrete(Z3Encoder(oracle), op, (1, 3)) is NAN


def test_search_reference_z3_smt_and_trace():
    registry = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
    op, parser, _ = define(registry, "a ⊕ b = { search(i, 4, (i + a) == b) }")
    runtime, oracle = PythonRuntime(registry), Oracle(registry)
    encoder = Z3Encoder(oracle)
    for args, expected, count in [((2, 2), 0, 1), ((2, 4), 2, 3), ((2, 8), NAN, 5),
                                  ((NAN, 2), NAN, 1)]:
        value, base_ops, calls = runtime.evaluate(op)(*args)
        reference = oracle.evaluate(op, args)
        assert (value, base_ops, calls) == (reference.value, reference.base_ops, reference.calls)
        assert value is expected if expected is NAN else value == expected
        assert base_ops == count
        assert evaluate_concrete(encoder, op, args) is expected if expected is NAN else \
            evaluate_concrete(encoder, op, args) == expected
    text = module(op, encoder)
    check_module(text, op, encoder)
    trace = Reducer(registry, runtime, parser).reduce(Call(op, (Number(2), Number(4))))
    assert trace.value == 2
    assert "i=0: False" in trace.steps[0].condition
    assert "i=2: True" in trace.steps[0].condition
    verify_trace(trace, oracle)
    assert "i=2: True" in narrate(trace, ExpressionRenderer(Symbols()), "en")
    report = check_steps(Call(op, (Number(2), Number(4))), ["2"], parser, registry, oracle, 2)
    assert report.final_correct and report.single_steps == 1


def test_search_compiled_cython_matches_reference(tmp_path):
    pytest.importorskip("Cython", reason="Compiled runtime checks require Cython")
    registry = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
    op, _, _ = define(registry, "a ⊕ b = { search(i, 4, (i + a) == b) }")
    cython = CythonRuntime(registry, tmp_path / "build", jobs=1)
    oracle = Oracle(registry)
    for args in ((2, 2), (2, 4), (2, 8), (NAN, 2)):
        reference = oracle.evaluate(op, args)
        assert cython.evaluate(op)(*args) == (reference.value, reference.base_ops, reference.calls)


def test_search_prompt_rederivation_and_rule():
    registry = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
    op, _, _ = define(registry, "a ⊕ b = { search(i, 4, (i + a) == b) }")
    rules = rules_text(["add"], Settings().semantics.build())
    prompt = ("Rules:\n" + rules + "\n" + SEARCH_RULE.format(nan="NaN") +
              "\n\nDefinitions:\n" + op.definition + "\n\nWhat is the value of `2 ⊕ 4`?")
    task = {"family": "compute", "prompt": prompt, "definitions": [op.definition],
            "expression": "2 ⊕ 4"}
    assert answer_from_prompt(task, base_registry(registry)) == 2
    with pytest.raises(ValueError, match="search rule"):
        answer_from_prompt({**task, "prompt": prompt.replace(SEARCH_RULE.format(nan="NaN") + "\n", "")},
                           base_registry(registry))


def test_large_written_search_is_not_encoded():
    registry = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
    op, _, _ = define(registry, "a ⊕ b = { search(i, 33, i == a) }")
    encoder = Z3Encoder(Oracle(registry))
    assert not encoder.expressible(op)
    with pytest.raises(NotExpressible):
        encoder.apply(op, [])
    with pytest.raises(NotExpressible):
        module(op, encoder)


def test_search_generation_is_opt_in():
    registry = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
    settings = Settings.from_dict({"recursion": {"search_enabled": True, "search_bound": 4}})
    factory = OperatorFactory(settings, registry, random.Random(3))
    drafts = [factory._draft("simple_definition", 0) for _ in range(30)]
    assert any("search(" in render_definition(d.definition, settings.symbols) for d in drafts)
    for seed in range(50):  # the drawn names consume the rng, so find a seed that accepts a search
        generated_factory = OperatorFactory(settings, registry, random.Random(seed))
        generated = generated_factory.generate("simple_definition", 0)
        if "search(" in generated.definition:
            break
    assert "search(" in generated.definition
    args = (2, 3, 4)[:generated.n_ary]
    reference = generated_factory.oracle.evaluate(generated, args)
    assert generated_factory.runtime.evaluate(generated)(*args) == (
        reference.value, reference.base_ops, reference.calls)
    assert all("search(" not in render_definition(d.definition, Symbols()) for d in
               [OperatorFactory(Settings(), registry, random.Random(3))._draft("simple_definition", 0)])
    with pytest.raises(ValueError, match="search_bound"):
        OperatorFactory(Settings.from_dict({"recursion": {"search_enabled": True, "search_bound": 33}}),
                        registry)


def test_nary_laws():
    registry = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
    symmetric, _, _ = define(registry, "⊕(a, b, c) = { a, if a == b and b == c; 0, else }", arity=3)
    asymmetric, _, _ = define(registry, "⊗(a, b, c) = { a - (b + c) }", symbol="⊗", arity=3)
    checker = PropertyChecker(Z3Encoder(Oracle(registry)), timeout_ms=1000)
    assert properties_for(3) == ("symmetric", "idempotent")
    assert checker.check(symmetric, "symmetric").status == "proved"
    assert checker.check(asymmetric, "symmetric").status == "refuted"
    assert checker.check(symmetric, "idempotent").status == "proved"
    assert checker.check(asymmetric, "idempotent").status == "refuted"
    four, _, _ = define(registry,
                        "⊛(a, b, c, d) = { a, if a == b and b == c and c == d; 0, else }",
                        symbol="⊛", arity=4)
    assert checker.check(four, "symmetric").status == "proved"
    assert checker.check(four, "idempotent").status == "proved"


def test_operator_cli_switches(tmp_path, monkeypatch):
    from opulse.cli import operators

    seen = {}
    real_factory = operators.OperatorFactory

    def factory(settings, registry, rng, **kwargs):
        seen["settings"] = settings
        return real_factory(settings, registry, rng, **kwargs)

    monkeypatch.setattr(operators, "OperatorFactory", factory)
    monkeypatch.setattr(operators, "build_layers", lambda *args, **kwargs: None)
    assert main(["operators", "--out", str(tmp_path / "ops.jsonl"), "--layers", "0",
                 "--arity-weights", "1:0.2,2:0.3,3:0.5", "--recursion-style", "direct",
                 "--search", "--search-bound", "5"]) == 0
    settings = seen["settings"]
    assert settings.operators.arity_weights == {1: 0.2, 2: 0.3, 3: 0.5}
    assert settings.recursion.style == "direct"
    assert settings.recursion.search_enabled and settings.recursion.search_bound == 5


@pytest.mark.parametrize("config", [
    {"recursion": {"search_enabled": True, "search_bound": 4}},
    {"operators": {"arity_weights": {1: 0.3, 2: 0.3, 3: 0.4}}},
])
def test_step_counter_matches_reducer(config):
    from opulse.definition.parser import DefinitionParser
    from opulse.expression.generator import ExpressionGenerator, OperatorPool
    from opulse.generation.pipeline import build_layers
    from opulse.runtime import PythonRuntime
    from opulse.trace.count import count_steps
    from opulse.trace.reducer import Reducer

    settings = Settings.from_dict(config)
    registry = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
    build_layers(OperatorFactory(settings, registry, random.Random(5)), [6, 4])
    runtime = PythonRuntime(registry, settings.semantics.build())
    reducer = Reducer(registry, runtime, DefinitionParser(settings.symbols, registry))
    generator = ExpressionGenerator(settings.expressions, random.Random(1))
    pool = OperatorPool.from_registry(registry)
    for _ in range(40):
        tree = generator.tree(pool, max_depth=3, atoms="numbers")
        trace = reducer.reduce(tree)
        if not trace.truncated:
            assert count_steps(reducer, tree) == len(trace.steps)
