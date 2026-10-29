import pytest

from opulse.core import (
    BINARY,
    PREFIX,
    RECURSIVE,
    SIMPLE,
    UNARY,
    Operator,
    OperatorRegistry,
)


def test_operator_round_trips_through_json():
    op = Operator(func_id="abc", symbol="⊕", n_ary=BINARY, definition="a ⊕ b = { a }",
                  definition_type=SIMPLE, dependencies=["x"])
    assert Operator.from_json(op.to_json()) == op


def test_unary_operator_requires_position():
    with pytest.raises(ValueError):
        Operator(func_id="abc", symbol="⊕", n_ary=UNARY)


def test_unknown_json_fields_are_ignored():
    op = Operator.from_dict({"func_id": "f", "symbol": "+", "n_ary": 2, "legacy_field": 1})
    assert op.symbol == "+"


def test_registry_loads_initial_operators(registry):
    assert len(registry) == 25
    assert registry.find("-", BINARY).func_id != registry.find("-", UNARY, PREFIX).func_id
    assert len(registry.binary()) == 5
    assert registry.base_marker(16) is not None
    # base markers are excluded from ordinary selection
    assert all(op.is_base is None for op in registry.prefix())


def test_registry_rejects_duplicates(registry):
    plus = registry.find("+", BINARY)
    with pytest.raises(ValueError):
        registry.add(plus)


def test_dependencies_and_recursive_layer(registry):
    plus = registry.find("+", BINARY)
    source = f"def op_new(a, b):\n    return op_{plus.func_id}(a, op_new(a, b))\n"
    deps = registry.dependencies_of(source, own_func_id="new")
    assert deps == [plus.func_id]
    simple = Operator(func_id="s1", symbol="⊕", n_ary=BINARY, definition_type=SIMPLE,
                      dependencies=deps)
    recursive = Operator(func_id="r1", symbol="⊗", n_ary=BINARY, definition_type=RECURSIVE,
                         dependencies=deps)
    assert registry.recursive_layer_of(simple) == 0
    assert registry.recursive_layer_of(recursive) == 1


def test_topological_order_puts_dependencies_first(registry, tmp_path):
    plus = registry.find("+", BINARY)
    registry.add(Operator(func_id="s1", symbol="⊕", n_ary=BINARY, definition="x", op_compute_func="c", op_count_func="n",
                          dependencies=[plus.func_id], recursive_layer=0))
    order = [op.func_id for op in registry.topological_order()]
    assert order.index(plus.func_id) < order.index("s1")
    path = tmp_path / "ops.jsonl"
    registry.to_jsonl(path)
    assert len(OperatorRegistry.from_jsonl(path)) == len(registry)
