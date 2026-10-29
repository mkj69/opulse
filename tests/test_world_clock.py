"""Clock arithmetic agrees across the interpreter, runtime, reducer and solver."""

import shutil

import pytest
from conftest import INITIAL_OPERATORS

from opulse.bench.context import rules_text
from opulse.config import Settings
from opulse.core.operator import SIMPLE, Operator
from opulse.core.registry import OperatorRegistry
from opulse.core.semantics import NAN, Semantics
from opulse.definition.codegen import compile_definition, registry_resolver
from opulse.definition.parser import DefinitionParser
from opulse.expression.nodes import Call, Number
from opulse.expression.render import ExpressionRenderer
from opulse.runtime.python_backend import PythonRuntime
from opulse.solver.z3_encode import NotExpressible, Z3Encoder
from opulse.trace.reducer import Reducer
from opulse.verify import Oracle
from opulse.verify.steps import check_steps


def test_clock_modulus_and_validation():
    settings = Settings.from_dict({"preset": "clock"})
    assert settings.semantics.build().operations()["add"](11, 2) == 1
    assert Settings.from_dict({"preset": "clock", "semantics": {"modulus": 24}}).semantics.modulus == 24
    with pytest.raises(ValueError):
        Semantics("modular")
    with pytest.raises(ValueError):
        Semantics("modular", modulus=1)


def test_clock_backends_and_trace():
    settings = Settings.from_dict({"preset": "clock"})
    semantics = settings.semantics.build()
    registry = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
    oracle = Oracle(registry, settings.symbols, semantics)
    runtime = PythonRuntime(registry, semantics)
    with pytest.raises(NotExpressible):
        Z3Encoder(oracle)
    plus = registry.find("+", 2)
    for args in ((11, 2), (-1, 0), (24, 5), (0, 0)):
        expected = oracle.evaluate(plus, args).value
        assert runtime.compute(plus)(*args) == expected
        trace = Reducer(registry, runtime, oracle.parser).reduce(Call(plus, tuple(Number(x) for x in args)))
        assert trace.value == expected
        lines = [ExpressionRenderer(settings.symbols).full(step.expression_after) for step in trace.steps]
        report = check_steps(trace.source, lines, oracle.parser, registry, oracle, expected)
        assert report.final_correct and report.first_error is None
    div = registry.find("/", 2)
    assert oracle.evaluate(div, (2, 0)).value is NAN
    assert "modulo 12" in rules_text(["add"], semantics)


@pytest.mark.skipif(shutil.which("gcc") is None, reason="needs a C compiler")
def test_clock_cython_cache_uses_modulus(tmp_path):
    pytest.importorskip("Cython")
    from opulse.runtime.cython_backend import CythonRuntime

    registry = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
    op = Operator("clockiso", "⊕", 2, definition="a ⊕ b = { a + b }", definition_type=SIMPLE)
    code = compile_definition(DefinitionParser(Settings().symbols, registry).parse(op.definition),
                              op.func_id, registry_resolver(registry, op))
    op.op_compute_func, op.op_count_func, op.dependencies = code.compute, code.count, list(code.dependencies)
    registry.add(op)
    twelve = CythonRuntime(registry, tmp_path, Semantics("modular", modulus=12), jobs=1)
    twenty_four = CythonRuntime(registry, tmp_path, Semantics("modular", modulus=24), jobs=1)
    assert twelve.compute(op)(11, 5) == 4
    assert twenty_four.compute(op)(11, 5) == 16
