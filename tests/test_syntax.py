"""Spec section 8 / obligation 8: parsing, notation and render-parse round trips."""

import random

import pytest
from conftest import INITIAL_OPERATORS

from opulse.config import Settings, Symbols
from opulse.core import BINARY, POSTFIX, PREFIX, Operator, OperatorRegistry
from opulse.definition import ast
from opulse.definition.ast import render_definition
from opulse.definition.parser import DefinitionParser, DefinitionSyntaxError
from opulse.expression.generator import ExpressionGenerator, OperatorPool
from opulse.expression.nodes import Call, from_ast
from opulse.expression.numerals import NumeralWriter
from opulse.expression.render import ExpressionRenderer
from opulse.generation.pipeline import OperatorFactory, build_layers
from opulse.generation.priority import assign_priorities
from opulse.generation.symbols import NAMED_SETS, uniquely_decodable

S = Symbols()
NEG = lambda x: ast.Apply("-", (x,), PREFIX)


def with_ops(*ops):
    registry = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
    for i, (symbol, n_ary, position) in enumerate(ops):
        registry.add(Operator(func_id=f"x{i}", symbol=symbol, n_ary=n_ary, unary_position=position,
                              definition="d", op_compute_func="c", op_count_func="n"))
    return registry


def test_unseparated_unary_operators_split():
    """``&-1`` was read as one symbol ``&-``."""
    parser = DefinitionParser(S)
    assert parser.parse_expr("&-1") == ast.Apply("&", (NEG(ast.Num(1)),), PREFIX)
    assert parser.parse_expr("- - a") == NEG(NEG(ast.Var("a")))


def test_prefix_and_postfix_on_one_operand():
    """``(-9⊽⋐)`` could not be parsed."""
    parser = DefinitionParser(S, with_ops(("⊽⋐", 1, POSTFIX), ("⩟", BINARY, None)))
    definition = parser.parse("a ⩟ b = { (-9⊽⋐) , if a > 8 ; b, else }")
    assert definition.branches[0].expr == NEG(ast.Apply("⊽⋐", (ast.Num(9),), POSTFIX))
    assert parser.parse_expr("- a @ $") == NEG(ast.Apply("$", (ast.Apply("@", (ast.Var("a"),), POSTFIX),), POSTFIX))


def test_base_marked_numerals_in_definitions():
    """Numerals written in another base inside a definition use ``#A``-style markers."""
    registry = with_ops(("⊽⋐", 1, POSTFIX), ("⩟", BINARY, None))
    hexa = registry.base_marker(16).symbol
    octal = registry.base_marker(8).symbol
    parser = DefinitionParser(S, registry)
    text = f"a ⩟ b = {{ (- {hexa}A ⊽⋐), if a > {octal}17; b, else }}"
    definition = parser.parse(text)
    assert definition.branches[0].expr == NEG(ast.Apply("⊽⋐", (ast.Num(10, 16),), POSTFIX))
    assert definition.branches[0].condition.right == ast.Num(15, 8)
    writer = NumeralWriter(registry, Settings().numerals.digits)
    rendered = render_definition(definition, S, writer.write)
    assert parser.parse(rendered) == definition


def test_ambiguous_split_is_an_error_not_a_guess():
    parser = DefinitionParser(S, with_ops(("⊕", BINARY, None), ("⊗", 1, PREFIX), ("⊕⊗", 1, PREFIX)))
    with pytest.raises(DefinitionSyntaxError, match="more than one way"):
        parser.parse_expr("a ⊕⊗ b")
    assert parser.parse_expr("a ⊕ ⊗ b") == ast.Apply("⊕", (ast.Var("a"), ast.Apply("⊗", (ast.Var("b"),), PREFIX)))


def test_sardinas_patterson():
    assert uniquely_decodable({"+", "-", "⊕", "⊗⊗"})
    assert not uniquely_decodable({"⊕", "⊗", "⊕⊗"})
    assert not uniquely_decodable({"ab", "a", "bc", "c"})  # ab|c == a|bc
    assert uniquely_decodable({"0", "10", "110"})


@pytest.mark.parametrize("bad", ["a ⊕ b = { a, if }", "(a + b) ⊕ b = { a }", "a ⊕ b = { a ; }",
                                 "a ⊕ b = { c }", "a ⊕ b = { a } trailing"])
def test_syntax_errors(bad):
    with pytest.raises(DefinitionSyntaxError):
        DefinitionParser(S).parse(bad)


def test_conditions_and_parenthesised_comparisons():
    parser = DefinitionParser(S)
    cond = parser.parse_condition("not (a < 1 or (a + b) > 2) and b == 0")
    assert isinstance(cond, ast.And) and isinstance(cond.left, ast.Not)
    assert cond.left.operand.right.left == ast.Apply("+", (ast.Var("a"), ast.Var("b")))


CUSTOM = {
    "symbols": {"left_operand": "x", "right_operand": "y", "left_paren": "[", "right_paren": "]",
                "equals": ":=", "nan": "Undef"},
    "expressions": {"variables": ["x", "y"]},
    "operators": {"partial_probability": 0.3},
}


GREEK = {"operators": {"naming": "legacy", "symbol_sets": ["greek"], "symbol_max_len": 2}}


@pytest.mark.parametrize("raw", [{}, CUSTOM, {**CUSTOM, "recursion": {"style": "direct"}}, GREEK,
                                 {**CUSTOM, **GREEK}])
def test_generated_operators_round_trip_under_any_notation(raw):
    """Other symbol sets (brackets, letters) generate and parse correctly."""
    settings = Settings.from_dict(raw)
    registry = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
    factory = OperatorFactory(settings, registry, random.Random(4))
    build_layers(factory, [12, 8, 5])
    parser = DefinitionParser(settings.symbols, registry)
    generated = [op for op in registry if op.definition]
    if settings.operators.naming == "legacy":
        assert uniquely_decodable({op.symbol for op in registry if op.is_base is None})
    for op in generated:
        definition = parser.parse(op.definition)
        assert render_definition(definition, settings.symbols) == op.definition
        if "symbols" in raw:
            assert "(" not in op.definition and " a " not in f" {op.definition} "
        if raw.get("operators", {}).get("symbol_sets") == ["greek"]:
            assert set(op.symbol) <= set(NAMED_SETS["greek"])  # Greek capitals unlike Latin letters


def test_expression_text_parses_back_with_priorities():
    settings = Settings()
    registry = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
    factory = OperatorFactory(settings, registry, random.Random(9))
    build_layers(factory, [12, 8])
    assign_priorities(registry, random.Random(1), max_levels=5)
    parser = DefinitionParser(settings.symbols, registry)
    renderer = ExpressionRenderer(settings.symbols, NumeralWriter(registry, settings.numerals.digits))
    generator = ExpressionGenerator(settings.expressions, random.Random(2))
    pool = OperatorPool.from_registry(registry)
    checked = 0
    for _ in range(300):
        tree = generator.tree(pool)
        if not isinstance(tree, Call):
            continue
        for text in (renderer.minimal(tree), renderer.full(tree)):
            back = from_ast(parser.parse_expr(text, expression_mode=True), registry)
            assert back == tree, text
        checked += 1
    assert checked > 200
