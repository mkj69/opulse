import hashlib
import random

import pytest
from conftest import INITIAL_OPERATORS

from opulse.config import Settings
from opulse.core import OperatorRegistry
from opulse.definition import ast
from opulse.definition.parser import DefinitionParser
from opulse.generation.pipeline import OperatorFactory, build_layers


def _grow(config, counts, seed=19, initial=INITIAL_OPERATORS):
    settings = Settings.from_dict(config)
    registry = OperatorRegistry.from_jsonl(initial)
    build_layers(OperatorFactory(settings, registry, random.Random(seed)), counts)
    return [(op, DefinitionParser(settings.symbols, registry).parse(op.definition))
            for op in registry if op.definition is not None]


def _call_depth(node):
    if isinstance(node, ast.Apply):
        return 1 + max((_call_depth(arg) for arg in node.args), default=0)
    return 0


def _comparisons(node):
    if isinstance(node, ast.Compare):
        return 1
    if isinstance(node, (ast.And, ast.Or)):
        return _comparisons(node.left) + _comparisons(node.right)
    if isinstance(node, ast.Not):
        return _comparisons(node.operand)
    return 0


def test_default_fixed_seed_definitions_are_unchanged():
    # Legacy names reproduce the output from before the switches existed.
    definitions = [op.definition for op, _ in _grow({"operators": {"naming": "legacy"}}, [8, 4], seed=11)]
    digest = hashlib.sha256("\n".join(definitions).encode()).hexdigest()
    assert digest == "3e2d60622db04a172e4d3fe90d7f502a5391e4d1dda294a526f52ebcf2e27ac6"


def test_branch_condition_arity_and_recursion_limits_on_every_definition():
    generated = _grow({"operators": {"allow_simple": False, "max_arity": 1,
                                     "max_if_branches": 3, "max_substitution_depth": 2,
                                     "max_condition_comparisons": 1, "condition_atoms": ["reverse"]},
                       "recursion": {"style": "direct", "direct_bound": 2,
                                     "max_recursive_calls": 1}}, [24, 12])
    assert len(generated) == 36
    assert {op.definition_type for op, _ in generated} == {"branch_definition", "recursive_definition"}
    for op, definition in generated:
        assert op.n_ary == 1
        if op.definition_type == "branch_definition":
            assert 2 <= len(definition.branches) <= 3
            for branch in definition.branches:
                assert _call_depth(branch.expr) <= 2
                if branch.condition is not None:
                    assert _comparisons(branch.condition) <= 1
                    assert {call.symbol for call in ast.iter_applications(branch.condition)} == {"@"}
        else:
            assert len(definition.branches) == 3
            for branch in definition.branches[1:]:
                calls = [call for call in ast.iter_applications(branch.expr) if call.symbol == op.symbol]
                assert len(calls) == 1
            assert "<= 2" in op.definition and ">= - 2" in op.definition


def test_simple_depth_and_branch_disable_are_independent():
    generated = _grow({"operators": {"allow_branches": False, "max_substitution_depth": 1},
                       "expressions": {"max_depth": 5}}, [25])
    assert len(generated) == 25
    assert all(op.definition_type == "simple_definition" for op, _ in generated)
    assert all(_call_depth(definition.branches[0].expr) <= 1 for _, definition in generated)


def test_recursion_can_be_disabled_without_disabling_branches():
    generated = _grow({"recursion": {"enabled": False}}, [30])
    assert len(generated) == 30
    assert {op.definition_type for op, _ in generated} == {"simple_definition", "branch_definition"}
    with pytest.raises(ValueError, match="higher layers require recursion.enabled"):
        _grow({"recursion": {"enabled": False}}, [5, 5])


@pytest.mark.parametrize("style,marker", [("bounded_mod", "%"), ("direct", "<= 2"),
                                          ("peano", "⁻")])
def test_recursion_style_and_bound_on_every_recursive_definition(style, marker):
    initial = (INITIAL_OPERATORS.parent / "atomic_operators.jsonl"
               if style == "peano" else INITIAL_OPERATORS)
    generated = _grow({"recursion": {"styles": [style], "modulus_min": 3, "modulus_max": 3,
                                     "direct_bound": 2, "max_recursive_calls": 1}}, [8, 12], initial=initial)
    recursive = [op for op, _ in generated if op.definition_type == "recursive_definition"]
    assert recursive
    assert all(marker in op.definition for op in recursive)
    if style == "bounded_mod":
        assert all("% 3" in op.definition for op in recursive)
    else:
        assert all("<= 2" in op.definition and ">= - 2" in op.definition for op in recursive)


def test_cli_switches_apply_to_generated_operators(tmp_path):
    from opulse.cli.main import main

    output = tmp_path / "operators.jsonl"
    assert main(["operators", "--out", str(output), "--layers", "12", "--seed", "4",
                 "--no-recursion", "--no-branches", "--max-arity", "1",
                 "--max-substitution-depth", "1"]) == 0
    operators = [op for op in OperatorRegistry.from_jsonl(output) if op.definition is not None]
    assert len(operators) == 12
    assert all(op.definition_type == "simple_definition" and op.n_ary == 1 for op in operators)


def test_max_arity_caps_arity_weights():
    weights = {"arity_weights": {1: 1, 2: 1, 3: 2}}
    grown = _grow({"operators": {**weights, "max_arity": 2}}, [6, 3], seed=4)
    assert grown and max(op.n_ary for op, _ in grown) <= 2
    assert any(op.n_ary == 3 for op, _ in _grow({"operators": weights}, [6, 3], seed=4))
    with pytest.raises(ValueError, match="max_arity"):
        _grow({"operators": {"arity_weights": {3: 1}, "max_arity": 2}}, [2])


def test_recursion_styles_may_include_primitive():
    grown = _grow({"recursion": {"styles": ["primitive", "direct"]}}, [6, 4], seed=3)
    recursive = [op for op, _ in grown if op.definition_type == "recursive_definition"]
    assert recursive
