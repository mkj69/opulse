"""Resolved expression trees preserve arity, variables, and literal semantics."""

import pytest

from opulse.core import NAN, OperatorRegistry
from opulse.definition import ast
from opulse.expression.nodes import (
    Call,
    Number,
    Variable,
    depth,
    from_ast,
    from_dict,
    has_variable,
    iter_calls,
    literal_form,
    map_operators,
    to_ast,
    to_dict,
)
from opulse.verify import Oracle


def test_nested_tree_tracks_variables_and_rejects_wrong_arity(registry):
    add = registry.find("+", 2)
    with pytest.raises(ValueError, match="takes 2 argument"):
        Call(add, (Number(1),))

    tree = Call(add, (Number(2), Call(add, (Variable("x"), Number(3)))))
    assert has_variable(tree)
    assert not has_variable(Call(add, (Number(2), Number(3))))
    assert depth(tree) == 3
    assert list(iter_calls(tree)) == [tree.args[1], tree]
    assert from_dict(to_dict(tree), registry) == tree


def test_negative_literal_uses_registered_negation(registry):
    add = registry.find("+", 2)
    tree = Call(add, (Number(-4, base=16), Number(2)))
    normalized = literal_form(tree, registry)
    neg = registry.find("-", 1, "prefix")
    assert normalized == Call(add, (Call(neg, (Number(4, base=16),)), Number(2)))
    assert Oracle(registry).evaluate_expr(to_ast(normalized), {}).value == -2

    without_neg = OperatorRegistry([add])
    with pytest.raises(ValueError, match="negative number needs"):
        literal_form(Number(-4), without_neg)


def test_nan_variable_and_operator_swap_round_trip(registry):
    add = registry.find("+", 2)
    sub = registry.find("-", 2)
    tree = Call(add, (Number(5), Number(2)))
    swapped = map_operators(tree, lambda op: sub if op is add else op)
    assert Oracle(registry).evaluate_expr(to_ast(tree), {}).value == 7
    assert Oracle(registry).evaluate_expr(to_ast(swapped), {}).value == 3
    assert from_dict(to_dict(Number(NAN)), registry) == Number(NAN)
    assert from_ast(ast.NaN(), registry) == Number(NAN)
    assert from_dict(to_dict(Variable("x")), registry) == Variable("x")
    with pytest.raises(LookupError, match="no operator"):
        from_ast(ast.Apply("unknown", (ast.Num(1),), "prefix"), registry)
