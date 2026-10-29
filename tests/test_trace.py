import random

import pytest

from opulse.config import Settings
from opulse.definition.parser import DefinitionParser
from opulse.expression.evaluator import Evaluator
from opulse.expression.generator import ExpressionGenerator, OperatorPool
from opulse.expression.nodes import Call, Number
from opulse.expression.render import ExpressionRenderer
from opulse.generation.pipeline import OperatorFactory, build_layers
from opulse.runtime import PythonRuntime
from opulse.trace import Reducer
from opulse.verify import Oracle, verify_trace


@pytest.fixture(scope="module")
def world():
    from conftest import INITIAL_OPERATORS

    from opulse.core import OperatorRegistry

    registry = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
    factory = OperatorFactory(Settings(), registry, random.Random(21))
    build_layers(factory, [15, 10, 6])
    return registry, factory.runtime


def test_reduction_reaches_the_evaluated_value(world):
    registry, runtime = world
    reducer = Reducer(registry, runtime, DefinitionParser(Settings().symbols))
    oracle = Oracle(registry)
    generator = ExpressionGenerator(Settings().expressions, random.Random(0))
    pool = OperatorPool.from_registry(registry)
    checked = 0
    for _ in range(60):
        tree = generator.tree(pool)
        if not isinstance(tree, Call):
            continue
        trace = reducer.reduce(tree)
        if trace.truncated:  # longer than the step limit: nothing to compare
            continue
        assert trace.value is Evaluator(runtime).evaluate(tree).value or \
            trace.value == Evaluator(runtime).evaluate(tree).value
        verify_trace(trace, oracle)
        for step in trace.steps:
            assert step.kind in (("expand", "undefined") if step.operator.definition else ("eval",))
        checked += 1
    assert checked > 30


def test_recursive_operator_unfolds_step_by_step(world):
    registry, runtime = world
    recursive = next(op for op in registry if op.definition_type == "recursive_definition" and op.n_ary == 1)
    tree = Call(recursive, (Number(5),))
    trace = Reducer(registry, runtime, DefinitionParser(Settings().symbols)).reduce(tree)
    expansions = [s for s in trace.steps if s.operator is recursive]
    modulus = int(recursive.definition.split("%")[1].split("==")[0])
    assert len(expansions) == 5 % modulus + 1  # 5%m, ..., 1, then the base case
    assert expansions[-1].branch_index == 0
    assert trace.value == runtime.compute(recursive)(5)


def test_partial_unfolding_evaluates_deep_layers_directly(world):
    registry, runtime = world
    deep = next(op for op in registry if (op.recursive_layer or 0) == 2 and op.n_ary == 2)
    tree = Call(deep, (Number(3), Number(4)))
    shallow = Reducer(registry, runtime, DefinitionParser(Settings().symbols),
                      expand=lambda op: op.definition is not None and op.recursive_layer >= 2)
    trace = shallow.reduce(tree)
    assert trace.value == runtime.compute(deep)(3, 4)
    assert all(step.kind == "eval" for step in trace.steps[1:] if (step.operator.recursive_layer or 0) < 2)


def test_steps_render_readably(world):
    registry, runtime = world
    renderer = ExpressionRenderer(Settings().symbols)
    branchy = next(op for op in registry if op.definition_type == "branch_definition")
    tree = Call(branchy, tuple(Number(7) for _ in range(branchy.n_ary)))
    trace = Reducer(registry, runtime, DefinitionParser(Settings().symbols)).reduce(tree)
    first = trace.steps[0]
    assert first.kind == "expand" and renderer.full(first.before) == renderer.full(tree)
    assert first.condition is None or "7" in first.condition


def test_verify_trace_checks_each_step_locally(registry):
    """Review finding: a false local step hidden by ``0 * …`` was accepted."""
    from dataclasses import replace

    import pytest

    from opulse.config import Symbols
    from opulse.definition.parser import DefinitionParser
    from opulse.expression.nodes import Call, Number
    from opulse.runtime import PythonRuntime
    from opulse.trace import Reducer
    from opulse.verify import Oracle, VerificationError, verify_trace

    plus, times = registry.find("+", 2), registry.find("*", 2)
    source = Call(times, (Number(0), Call(plus, (Number(1), Number(2)))))
    reducer = Reducer(registry, PythonRuntime(registry), DefinitionParser(Symbols(), registry))
    oracle = Oracle(registry)
    verify_trace(reducer.reduce(source), oracle)  # the real trace passes

    trace = reducer.reduce(source)
    trace.steps[0] = replace(trace.steps[0], after=Number(99), expression_after=Call(times, (Number(0), Number(99))))
    with pytest.raises(VerificationError, match="rewrite has value 99"):
        verify_trace(trace, oracle)

    trace = reducer.reduce(source)
    trace.steps[1] = replace(trace.steps[1], expression_before=source)
    with pytest.raises(VerificationError, match="does not continue"):
        verify_trace(trace, oracle)


def test_granularity_depth_and_known_operators(world):
    """Coarser solutions have fewer steps, reach the same value and pass the same checks."""
    registry, runtime = world
    parser = DefinitionParser(Settings().symbols)
    oracle = Oracle(registry)
    generator = ExpressionGenerator(Settings().expressions, random.Random(7))
    pool = OperatorPool.from_registry(registry)
    compared = 0
    while compared < 15:
        tree = generator.tree(pool)
        if not isinstance(tree, Call):
            continue
        full = Reducer(registry, runtime, parser).reduce(tree)
        if full.truncated:
            continue
        lengths = []
        for depth in (None, 2, 1, 0):
            trace = Reducer(registry, runtime, parser, max_depth=depth).reduce(tree)
            verify_trace(trace, oracle)
            assert trace.value is full.value or trace.value == full.value
            assert all(step.depth <= depth for step in trace.steps if depth is not None and step.kind == "expand")
            lengths.append(len(trace.steps))
        assert lengths == sorted(lengths, reverse=True)
        assert all(step.kind == "eval" for step in Reducer(registry, runtime, parser, max_depth=0).reduce(tree).steps)
        known = Reducer(registry, runtime, parser, expand=lambda op: (op.recursive_layer or 0) >= 1).reduce(tree)
        verify_trace(known, oracle)
        assert not any(step.kind == "expand" and (step.operator.recursive_layer or 0) < 1 for step in known.steps)
        compared += 1


def test_cot_granularity_cli(tmp_path):
    import json

    from opulse.cli.main import main

    ops = tmp_path / "ops.jsonl"
    assert main(["operators", "--out", str(ops), "--layers", "8", "4", "--seed", "2"]) == 0
    counts = {}
    for name, extra in (("full", []), ("depth1", ["--cot-depth", "1"]), ("known", ["--cot-known-layers", "1"])):
        out = tmp_path / f"{name}.jsonl"
        assert main(["expressions", "--operators", str(ops), "--out", str(out), "--count", "6", "--seed", "1",
                     "--cot", "en", *extra]) == 0
        records = [json.loads(line) for line in out.read_text().splitlines()]
        counts[name] = sum(r["cot"].count("\n\n") for r in records)
        if name != "full":
            assert any("known operator" in r["cot"] for r in records) or counts[name] <= counts["full"]
    assert counts["depth1"] <= counts["full"] and counts["known"] <= counts["full"]


def test_verify_trace_requires_the_branch_body(registry):
    """Review finding: an expand step that jumps straight to the value was accepted."""
    from dataclasses import replace

    from opulse.config import Symbols
    from opulse.core import BINARY, SIMPLE, Operator
    from opulse.definition.parser import DefinitionParser
    from opulse.verify import VerificationError

    op = Operator("vtb", "⊕", BINARY, definition="a ⊕ b = { a + b }", definition_type=SIMPLE)
    op.op_compute_func = "def op_vtb(a, b):\n    return a + b\n"
    op.op_count_func = "def op_count_vtb(a, b):\n    return 1\n"
    registry.add(op)
    reducer = Reducer(registry, PythonRuntime(registry), DefinitionParser(Symbols(), registry))
    oracle = Oracle(registry)
    trace = reducer.reduce(Call(op, (Number(2), Number(3))))
    verify_trace(trace, oracle)
    shortcut = replace(trace.steps[0], after=Number(5), expression_after=Number(5))
    trace.steps[:] = [shortcut]
    with pytest.raises(VerificationError, match="not the body of branch"):
        verify_trace(trace, oracle)
