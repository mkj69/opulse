"""Display aliases must survive parsing without changing interpreter results."""

import random
import re
from dataclasses import fields, is_dataclass, replace

import pytest

from opulse.config import Settings, Symbols
from opulse.core import Operator, OperatorRegistry
from opulse.definition import ast
from opulse.definition.parser import DefinitionParser
from opulse.expression.aliases import (
    ARITHMETIC_WORDS,
    AliasMap,
    _english_words,
    _hints_arithmetic,
    alias_tree,
    aliased_registry,
    pseudo_words,
)
from opulse.expression.nodes import Call, Number, from_ast
from opulse.expression.render import ExpressionRenderer
from opulse.generation.pipeline import OperatorFactory, build_layers
from opulse.verify import Oracle


@pytest.fixture(scope="module")
def grown_registry():
    from conftest import INITIAL_OPERATORS

    registry = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
    build_layers(OperatorFactory(Settings(), registry, random.Random(7)), [8, 4])
    return registry


def test_pseudo_words_are_distinct_and_pronounceable():
    symbols = Symbols(left_operand="bavu", right_operand="tiri", nan="Moro")
    words = pseudo_words(1000, random.Random(3), symbols=symbols)
    assert len(words) == len(set(words)) == 1000
    assert all(re.fullmatch(r"(?:[bcdfghjklmnpqrstvwxyz][aeiou]){2,3}", w) for w in words)
    assert not set(words) & {"if", "else", "and", "or", "not", "bavu", "tiri", "Moro"}
    assert pseudo_words(1000, random.Random(3), symbols=symbols) == words


def test_english_names_exclude_arithmetic_and_are_invertible(grown_registry):
    words = _english_words()
    assert 1900 <= len(words) <= 2200
    assert len(words) == len(set(words))
    aliases = AliasMap.build(grown_registry, random.Random(11), style="english")
    assert len(aliases.symbol_to_word) == 12
    assert len(set(aliases.symbol_to_word.values())) == 12
    assert not set(aliases.word_to_symbol) & ARITHMETIC_WORDS
    assert not any(_hints_arithmetic(word) for word in aliases.word_to_symbol)
    assert all(aliases.symbol_to_word[key] == word for word, key in aliases.word_to_symbol.items())
    with pytest.raises(ValueError, match="alias style"):
        AliasMap.build(grown_registry, random.Random(0), style="invalid")


def _restore_names(node, aliases):
    """Undo only surface Apply names, so AST comparisons still check every branch."""
    if isinstance(node, ast.Apply):
        key = aliases.word_to_symbol.get(node.symbol)
        return ast.Apply(key[0] if key else node.symbol,
                         tuple(_restore_names(arg, aliases) for arg in node.args), node.unary_position)
    if isinstance(node, tuple):
        return tuple(_restore_names(item, aliases) for item in node)
    if is_dataclass(node):
        return replace(node, **{f.name: _restore_names(getattr(node, f.name), aliases)
                                for f in fields(node)})
    return node


@pytest.mark.parametrize("style", ["pseudo", "english"])
def test_definition_and_expression_round_trips(grown_registry, style):
    aliases = AliasMap.build(grown_registry, random.Random(13), style=style)
    display = aliased_registry(grown_registry, aliases)
    original_parser = DefinitionParser(Symbols(), grown_registry)
    parser = DefinitionParser(Symbols(), display)
    renderer = ExpressionRenderer(Symbols())
    assert len(display) == len(grown_registry)
    for op in grown_registry:
        named = display.get(op.func_id)
        if op.definition is None:
            assert named.symbol == op.symbol
            continue
        assert _restore_names(parser.parse(named.definition), aliases) == original_parser.parse(op.definition)
    plus = grown_registry.find("+", 2)
    for op in grown_registry:
        if op.is_base is not None:
            assert display.get(op.func_id).symbol == op.symbol
            continue
        inner = Call(op, tuple(Number(i + 1) for i in range(op.n_ary)))
        tree = Call(plus, (inner, Number(3)))
        named = alias_tree(tree, display)
        for render in (renderer.full, renderer.minimal):
            text = render(named)
            assert from_ast(parser.parse_expr(text, expression_mode=True), display) == named


def test_aliased_oracle_agrees_on_boundaries(grown_registry):
    aliases = AliasMap.build(grown_registry, random.Random(2))
    display = aliased_registry(grown_registry, aliases)
    original_oracle, named_oracle = Oracle(grown_registry), Oracle(display)
    bound = Settings().semantics.bound
    inputs = (-bound, -1, 0, 1, bound)
    for op in grown_registry:
        if op.is_base is not None:
            continue
        for left in inputs:
            for args in ((left,),) if op.n_ary == 1 else ((left, right) for right in inputs):
                assert named_oracle.evaluate(display.get(op.func_id), args) == original_oracle.evaluate(op, args)


def test_custom_operand_and_nan_spellings_are_respected(grown_registry):
    symbols = Symbols(left_operand="x", right_operand="y", nan="Undefined")
    op = Operator(func_id="custom", symbol="⊕", n_ary=2,
                  definition="x ⊕ y = { x + y, if x != Undefined; Undefined, else }")
    registry = OperatorRegistry([base for base in grown_registry if base.definition is None] + [op])
    aliases = AliasMap.build(registry, random.Random(1), symbols=symbols)
    display = aliased_registry(registry, aliases)
    named = display.get("custom")
    parsed = DefinitionParser(symbols, display).parse(named.definition)
    assert parsed.lhs.symbol == named.symbol
    assert "Undefined" in named.definition
    assert not set(aliases.word_to_symbol) & {"x", "y", "Undefined"}


@pytest.mark.parametrize("word", ["if", "else", "and", "or", "not", "a", "b", "NaN", "custom"])
def test_registered_word_collision_is_clear(word):
    symbols = Symbols()
    registry = OperatorRegistry([Operator(func_id="bad", symbol=word, n_ary=2)])
    with pytest.raises(ValueError, match="conflicts with a keyword, operand, or NaN"):
        DefinitionParser(symbols, registry, variables=("custom",))
    parser = DefinitionParser(symbols, OperatorRegistry(), variables=("custom",))
    with pytest.raises(ValueError, match="conflicts with a keyword, operand, or NaN"):
        parser.add(registry.get("bad"))
