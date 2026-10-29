"""Undefined operands retain their expected sort in typed Z3 expressions."""

import json
from pathlib import Path

import pytest
import z3

from opulse.config import Settings
from opulse.core.operator import Operator
from opulse.core.presets import register_preset
from opulse.core.registry import OperatorRegistry
from opulse.core.semantics import NAN
from opulse.expression.nodes import Number, from_dict
from opulse.solver.z3_encode import UNDEF, Z3Encoder, const, evaluate_concrete
from opulse.verify import Oracle

RECORDS = [
    json.loads(line)
    for line in (Path(__file__).parent / "fixtures" / "z3_typed_undefined.jsonl").read_text().splitlines()
]


def _oracle_tree(node, oracle):
    if isinstance(node, Number):
        return node.value
    return oracle.evaluate(node.operator, tuple(_oracle_tree(arg, oracle) for arg in node.args)).value


def _z3_tree(node, encoder):
    if isinstance(node, Number):
        return UNDEF if node.value is NAN else const(node.value)
    return encoder.apply(node.operator, [_z3_tree(arg, encoder) for arg in node.args])


@pytest.mark.parametrize("record", RECORDS, ids=lambda row: f"{row['world']}-{row['seed']}-{row['index']}")
def test_recorded_undefined_operand(record):
    register_preset(record["world"])
    settings = Settings.from_dict(record["settings"])
    registry = OperatorRegistry(Operator.from_dict(row) for row in record["operators"])
    oracle = Oracle(registry, settings.symbols, settings.semantics.build())
    tree = from_dict(record["tree"], registry)
    assert record["reference"] == {"undefined": True}
    assert _oracle_tree(tree, oracle) is NAN
    encoded = _z3_tree(tree, Z3Encoder(oracle, max_nodes=settings.solver.max_nodes))
    assert z3.is_false(z3.simplify(encoded.defined))
    assert encoded.value.sort() == {"lists": z3.SeqSort(z3.IntSort()),
                                    "strings": z3.BoolSort()}[record["world"]]


@pytest.mark.parametrize(
    "world,symbol,position,args,result_sort",
    [
        ("strings", "ℓ", "postfix", (NAN,), z3.IntSort()),
        ("strings", "⊕", None, ("a", NAN), z3.StringSort()),
        ("strings", "≡", None, (NAN, "a"), z3.BoolSort()),
        ("lists", "ℒ", "postfix", (NAN,), z3.IntSort()),
        ("lists", "⊞", None, ((1,), NAN), z3.SeqSort(z3.IntSort())),
        ("lists", "≍", None, (NAN, (1,)), z3.BoolSort()),
    ],
)
def test_undefined_typed_atom(world, symbol, position, args, result_sort):
    from opulse.core.presets import PRESETS
    from opulse.core.primitives import atom_records

    register_preset(world)
    registry = OperatorRegistry(Operator.from_dict(row) for row in atom_records(PRESETS[world]))
    operator = registry.find(symbol, len(args), position)
    oracle = Oracle(registry)
    assert oracle.evaluate(operator, args).value is NAN
    assert evaluate_concrete(Z3Encoder(oracle), operator, args) is NAN
    encoded = Z3Encoder(oracle).apply(operator, [UNDEF if arg is NAN else const(arg) for arg in args])
    assert encoded.value.sort() == result_sort


@pytest.mark.parametrize(
    "kind,literal,value,other,result_sort",
    [
        ("int", "1", 1, 2, z3.IntSort()),
        ("bool", "true", True, False, z3.BoolSort()),
        ("str", '"x"', "x", "y", z3.StringSort()),
        ("list[int]", "[1]", (1,), (2,), z3.SeqSort(z3.IntSort())),
    ],
)
def test_typed_branch_undefined_result(kind, literal, value, other, result_sort):
    registry = OperatorRegistry()
    oracle = Oracle(registry)
    for branch, argument in ((f"NaN, if a == {literal}; a, else", value),
                             (f"a, if a == {literal}", other)):
        operator = Operator(
            func_id="branch", symbol="◇", n_ary=1, unary_position="postfix",
            parameter_types=(kind,), result_type=kind,
            definition=f"a ◇ = {{ {branch} }}", definition_type="branch_definition",
        )
        oracle.include(operator)
        assert oracle.evaluate(operator, (argument,)).value is NAN
        encoder = Z3Encoder(oracle)
        encoded = encoder.apply(operator, [UNDEF if argument is NAN else const(argument)])
        assert z3.is_false(z3.simplify(encoded.defined))
        assert encoded.value.sort() == result_sort
