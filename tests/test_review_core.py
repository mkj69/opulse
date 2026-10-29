"""Regressions from the core and generated-recursion reviews."""

import pytest

from opulse.config import Symbols
from opulse.core import Operator
from opulse.core.primitives import register_primitive, unregister_primitive
from opulse.core.semantics import Semantics
from opulse.definition import ast
from opulse.definition.codegen import compile_definition, registry_resolver
from opulse.definition.interpreter import EngineError
from opulse.definition.parser import DefinitionParser
from opulse.runtime import PythonRuntime
from opulse.verify import Oracle


def _defined(registry, func_id, symbol, text, *, position="postfix"):
    op = Operator(func_id, symbol, 1, position, definition=text,
                  definition_type="recursive_definition")
    parser = DefinitionParser(Symbols(), registry)
    code = compile_definition(parser.parse(text), func_id, registry_resolver(registry, op))
    op.op_compute_func, op.op_count_func = code.compute, code.count
    registry.add(op)
    return op


def _chain(registry, bound=1200):
    text = f"a ⇽ = {{ 0, if a == 0; (a - 1) ⇽, if a > 0 and a <= {bound} }}"
    return _defined(registry, "reviewchain", "⇽", text)


def test_interpreter_permitted_depth_500(registry):
    op = _chain(registry, 500)
    oracle = Oracle(registry)
    oracle.interpreter.max_depth = 500
    assert oracle.evaluate(op, (500,)).value == 0


def test_memo_depth_independent_of_history(registry):
    op = _chain(registry, 2)
    oracle = Oracle(registry)
    oracle.interpreter.max_depth = 1
    assert oracle.evaluate(op, (1,)).value == 0
    with pytest.raises(EngineError, match="recursion deeper than 1"):
        oracle.evaluate(op, (2,))


def test_forget_invalidates_dependents(registry):
    f = _defined(registry, "reviewf", "⇽", "a ⇽ = { a + 1 }")
    _defined(registry, "reviewg", "⋰", "a ⋰ = { a ⇽ }")
    h = _defined(registry, "reviewh", "⋱", "a ⋱ = { a ⋰ }")
    oracle = Oracle(registry)
    assert oracle.evaluate(h, (1,)).value == 2
    f.definition = "a ⇽ = { a - 1 }"
    oracle.forget(f)
    assert oracle.evaluate(h, (1,)).value == 0


@pytest.mark.parametrize("symbol", ["if", "a", ">", "a+b"])
def test_register_rejects_unparseable_symbol(symbol):
    try:
        with pytest.raises(ValueError):
            register_primitive("review_bad_symbol", symbol, lambda a: a, rule="Identity.")
    finally:
        unregister_primitive("review_bad_symbol")


def test_register_rejects_ambiguous_alphabet():
    try:
        with pytest.raises(ValueError):
            register_primitive("review_ambiguous", "++", lambda a, b: a + b,
                               n_ary=2, position=None, rule="Add.")
    finally:
        unregister_primitive("review_ambiguous")


@pytest.mark.parametrize("kwargs", [{"compute": 42}, {"priority": "high"}, {"z3": 42}])
def test_register_rejects_invalid_arguments(kwargs):
    options = {"compute": lambda a: a, "priority": None, "z3": None} | kwargs
    try:
        with pytest.raises((TypeError, ValueError)):
            register_primitive("review_bad_arg", "⊛", options.pop("compute"),
                               rule="Identity.", **options)
    finally:
        unregister_primitive("review_bad_arg")


@pytest.mark.parametrize("bound", [1.5, float("nan"), True])
def test_semantics_rejects_noninteger_bound(bound):
    with pytest.raises(ValueError, match="bound"):
        Semantics("exact", bound)


def test_large_literal_round_trip_and_compile(registry):
    digits = "1" + "0" * 4300
    parser = DefinitionParser(Symbols(), registry)
    number = parser.parse_expr(digits)
    assert ast.render_expr(number, Symbols()) == digits
    op = _defined(registry, "reviewlarge", "⇽", f"a ⇽ = {{ {digits} }}")
    runtime = PythonRuntime(registry, Semantics("exact", None))
    assert runtime.compute(op)(0) == number.value


def test_compiled_and_reference_direct_depth_1200(registry):
    op = _chain(registry)
    oracle = Oracle(registry)
    runtime = PythonRuntime(registry)
    compiled = runtime.evaluate(op)(1200)
    expected = oracle.evaluate(op, (1200,))
    assert expected.value == 0
    assert compiled == (expected.value, expected.base_ops, expected.calls)
