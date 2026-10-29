import random

import pytest

from opulse.config import Symbols
from opulse.core import BINARY, POSTFIX, PREFIX, RECURSIVE, UNARY, Operator
from opulse.definition import ast
from opulse.definition.ast import render_definition
from opulse.definition.codegen import (
    UnknownOperatorError,
    compile_definition,
    registry_resolver,
)
from opulse.definition.parser import DefinitionParser, DefinitionSyntaxError
from opulse.runtime import PythonRuntime
from opulse.verify import Oracle, check_operator

SYMBOLS = Symbols()


@pytest.fixture
def parser():
    return DefinitionParser(SYMBOLS)


@pytest.mark.parametrize(
    "text",
    [
        "a ⊕ b = { (a + 3) * b, if a < 10 and b >= 2; (-5), else }",
        "⋮ a = { a, if a % 7 == 0; & (⋮ ((a % 7) - 1)), if a % 7 > 0; & (⋮ ((a % 7) + 1)), if a % 7 < 0 }",
        "a ⇽ = { (a ⇽) - 1 }",
        "a ⊕ b = { a, if not (a < 1 or b > 2); b, else }",
    ],
)
def test_render_parse_round_trip(parser, text):
    definition = parser.parse(text)
    assert parser.parse(render_definition(definition, SYMBOLS)) == definition


def test_parser_builds_expected_tree(parser):
    definition = parser.parse("a ⊕ = { - (a @), if a > 1; 0, else }")
    assert definition.lhs == ast.Apply("⊕", (ast.Var("a"),), POSTFIX)
    first = definition.branches[0]
    assert first.expr == ast.Apply("-", (ast.Apply("@", (ast.Var("a"),), POSTFIX),), PREFIX)
    assert first.condition == ast.Compare(ast.Var("a"), ">", ast.Num(1))
    assert definition.branches[1].is_else


def test_negative_constant_is_negation(parser):
    assert parser.parse_expr("(-5)") == ast.negate(-5) == ast.Apply("-", (ast.Num(5),), PREFIX)
    with pytest.raises(ValueError):
        ast.Num(-1)


def test_syntax_errors_are_reported(parser):
    with pytest.raises(DefinitionSyntaxError):
        parser.parse("a ⊕ b = { a, if }")
    with pytest.raises(DefinitionSyntaxError):
        parser.parse("(a + b) ⊕ b = { a }")


def _compile(registry, parser, text, func_id, symbol, n_ary, position=None):
    operator = Operator(func_id=func_id, symbol=symbol, n_ary=n_ary, unary_position=position,
                        definition=text, definition_type=RECURSIVE)
    code = compile_definition(parser.parse(text), func_id, registry_resolver(registry, operator))
    operator.op_compute_func, operator.op_count_func = code.compute, code.count
    operator.dependencies = list(code.dependencies)
    return operator


def test_simple_definition_compiles_and_counts(registry, parser):
    op = _compile(registry, parser, "a ⊕ b = { (a + 3) * b }", "plus3", "⊕", BINARY)
    runtime = PythonRuntime(registry)
    runtime.load(op)
    assert runtime.compute(op)(2, 4) == 20
    assert runtime.count(op)(2, 4) == 2
    plus, times = registry.find("+", BINARY), registry.find("*", BINARY)
    assert set(op.dependencies) == {plus.func_id, times.func_id}


def test_atom_branch_counts_zero(registry, parser):
    """Spec section 5: a branch returning a constant or variable contributes 0 base operations."""
    op = _compile(registry, parser, "a ⊕ b = { 7, if a > b; a + b, else }", "atom", "⊕", BINARY)
    runtime = PythonRuntime(registry)
    runtime.load(op)
    assert runtime.evaluate(op)(5, 1) == (7, 0, 0)
    assert runtime.evaluate(op)(1, 5) == (6, 1, 1)


def test_condition_operations_are_counted(registry, parser):
    op = _compile(registry, parser, "a ⊕ b = { a, if (a + b) > 3; b, else }", "cond", "⊕", BINARY)
    runtime = PythonRuntime(registry)
    runtime.load(op)
    assert runtime.evaluate(op)(5, 1) == (5, 1, 1)


def test_undefined_cases(registry, parser):
    """Spec section 4: zero divisor, NaN in a comparison and no matching branch give NaN."""
    from opulse.core import NAN

    op = _compile(registry, parser, "a ⊕ b = { a / b, if a > 0; (a / b) + 1, if (a / b) < 0 }", "nan", "⊕", BINARY)
    runtime = PythonRuntime(registry)
    runtime.load(op)
    assert runtime.compute(op)(4, 0) is NAN          # division by zero in the body
    assert runtime.compute(op)(-4, 0) is NAN         # NaN in the second comparison
    assert runtime.compute(op)(-4, -1) is NAN        # no branch matches (a <= 0 and a / b >= 0)
    assert runtime.compute(op)(-4, 1) == -3
    oracle = Oracle(registry)
    oracle.include(op)
    assert not check_operator(op, runtime.evaluate(op), oracle, random.Random(0))


def test_unknown_operator_is_rejected(registry, parser):
    with pytest.raises(UnknownOperatorError):
        compile_definition(parser.parse("a ⊕ b = { a ⊗ b }"), "x", registry_resolver(registry))


def test_unbound_variable_is_rejected(registry, parser):
    with pytest.raises(ValueError):
        compile_definition(parser.parse("⊕ a = { a + b }"), "x", registry_resolver(registry))


RECURSIVE_CASES = [
    ("⋮ a = { a, if a % 7 == 0; & (⋮ ((a % 7) - 1)), if a % 7 > 0; & (⋮ ((a % 7) + 1)), if a % 7 < 0 }",
     "⋮", UNARY, PREFIX),
    ("a ⇽ = { 5, if a % 6 == 0; a - (((a % 6) - 1) ⇽), if a % 6 > 0; a - (((a % 6) + 1) ⇽), if a % 6 < 0 }",
     "⇽", UNARY, POSTFIX),
    (("a ⊗ b = { a, if b % 5 == 0; (a ⊗ ((b % 5) - 1)) * (a ⊗ ((b % 5) - 1)), if b % 5 > 0; "
      "(b ⊗ ((b % 5) + 1)) - a, if b % 5 < 0 }"), "⊗", BINARY, None),
]


@pytest.mark.parametrize("text, symbol, n_ary, position", RECURSIVE_CASES)
def test_compiled_recursion_matches_reference_interpreter(registry, parser, text, symbol, n_ary, position):
    op = _compile(registry, parser, text, "rec", symbol, n_ary, position)
    runtime = PythonRuntime(registry)
    runtime.load(op)
    oracle = Oracle(registry)
    oracle.include(op)
    assert not check_operator(op, runtime.evaluate(op), oracle, random.Random(0), random_trials=300)


def test_shared_recursive_call_is_evaluated_once(registry, parser):
    text, symbol, n_ary, position = RECURSIVE_CASES[2]
    op = _compile(registry, parser, text, "rec", symbol, n_ary, position)
    positive_branch = op.op_compute_func.split("if t")[2].split("if t")[0]
    assert positive_branch.count("_e_rec(") == 1      # value computed once ...
    assert positive_branch.count("_o += r") == 2       # ... but counted for both occurrences


def test_complexity_matches_legacy_values(registry, parser):
    """Recompute (L, E) for legacy simple/branch operators and compare with the stored numbers."""
    import json

    from conftest import LEGACY_OPERATORS_1K

    if LEGACY_OPERATORS_1K is None or not LEGACY_OPERATORS_1K.is_file():
        pytest.skip("legacy operator fixture is unavailable")

    from opulse.core import OperatorRegistry
    from opulse.definition.complexity import definition_complexity

    with LEGACY_OPERATORS_1K.open(encoding="utf-8") as source:
        legacy = OperatorRegistry(Operator.from_dict(json.loads(line)) for line in source)
    checked = 0
    for op in legacy:
        if op.definition_type not in ("simple_definition", "branch_definition"):
            continue
        got = definition_complexity(parser.parse(op.definition), registry_resolver(legacy))
        assert (got.max_path_depth, got.max_edge_count) == (op.max_path_depth, op.max_edge_count), op.definition
        checked += 1
    assert checked > 900
