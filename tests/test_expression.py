import random

import pytest

from opulse.config import ExpressionSettings, Symbols
from opulse.core import BINARY, PREFIX, UNARY
from opulse.expression.evaluator import Evaluator, structure_stats
from opulse.expression.generator import ExpressionGenerator, OperatorPool
from opulse.expression.nodes import (
    Call,
    Number,
    Variable,
    depth,
    from_dict,
    to_ast,
    to_dict,
)
from opulse.expression.numerals import NumeralWriter, from_base, to_base
from opulse.expression.render import ExpressionRenderer
from opulse.runtime import PythonRuntime


@pytest.mark.parametrize("value", [0, 1, -1, 255, -4096, 123456])
@pytest.mark.parametrize("base", [2, 7, 10, 16])
def test_base_round_trip(value, base):
    digits = "0123456789ABCDEF"
    assert from_base(to_base(value, base, digits), base, digits) == value


def test_numeral_markers(registry):
    writer = NumeralWriter(registry, "0123456789ABCDEF")
    assert writer.write(255, 16) == registry.base_marker(16).symbol + "FF"
    assert NumeralWriter(registry, "0123456789", use_markers=False).write(5, 10) == "5"


def _ops(registry):
    return registry.find("+", BINARY), registry.find("*", BINARY), registry.find("-", UNARY, PREFIX)


def test_minimal_and_full_rendering(registry):
    plus, _times, neg = _ops(registry)  # priorities: + 1, * 1 (right assoc), - prefix 4
    tree = Call(plus, (Call(neg, (Number(3),)), Call(plus, (Number(1), Number(2)))))
    renderer = ExpressionRenderer(Symbols())
    assert renderer.full(tree) == "(- 3) + (1 + 2)"
    # "+" is right-associative in the initial set, so the right operand needs no brackets.
    assert renderer.minimal(tree) == "(- 3) + 1 + 2"


def test_evaluation_value_count_and_steps(registry):
    plus, times, neg = _ops(registry)
    tree = Call(times, (Call(plus, (Number(2), Number(3))), Call(neg, (Number(4),))))
    result = Evaluator(PythonRuntime(registry)).evaluate(tree)
    assert result.value == -20
    assert result.expansion == 3
    assert [step.render() for step in result.steps] == ["2 + 3 = 5", "- 4 = -4", "5 * -4 = -20"]
    assert (result.max_path_depth, result.max_edge_count) == (2, 5)


def test_variables_need_values(registry):
    plus, _, _ = _ops(registry)
    tree = Call(plus, (Variable("a"), Number(1)))
    with pytest.raises(ValueError):
        Evaluator(PythonRuntime(registry)).evaluate(tree)
    assert Evaluator(PythonRuntime(registry), env={"a": 4}).evaluate(tree).value == 5


def test_generated_trees_respect_depth(registry):
    generator = ExpressionGenerator(ExpressionSettings(max_depth=3), random.Random(1))
    pool = OperatorPool.from_registry(registry)
    for _ in range(200):
        assert depth(generator.tree(pool)) <= 4  # 3 operator levels + atoms


def test_tree_dict_round_trip(registry):
    generator = ExpressionGenerator(ExpressionSettings(), random.Random(2))
    pool = OperatorPool.from_registry(registry)
    for _ in range(50):
        tree = generator.tree(pool)
        assert from_dict(to_dict(tree), registry) == tree


def test_definition_bodies_use_target_layer(registry):
    generator = ExpressionGenerator(ExpressionSettings(), random.Random(3))
    bodies = generator.definition_bodies(registry, layer=0, count=3, variables=("a", "b"))
    assert len(bodies) == 3
    assert all(isinstance(to_ast(body), object) for body in bodies)


def test_structure_stats(registry):
    plus, times, neg = _ops(registry)
    tree = Call(times, (Call(plus, (Number(2), Number(3))), Call(neg, (Number(4),))))
    stats = structure_stats(tree, registry)
    assert stats["operation_count"] == 3
    assert stats["used_operators"] == [plus.func_id, neg.func_id, times.func_id]


def test_negative_numbers_are_written_with_unary_minus(registry):
    """Review finding: a negative literal atom gained a phantom negation in the reference check."""
    import random as _random

    from opulse.config import Settings as _Settings
    from opulse.definition.parser import DefinitionParser
    from opulse.expression.dataset import ExpressionDataset
    from opulse.expression.nodes import Call as _Call
    from opulse.expression.nodes import Number as _Number
    from opulse.expression.nodes import from_ast
    from opulse.runtime import PythonRuntime as _Runtime

    settings = _Settings.from_dict({"expressions": {"value_min": -50, "value_max": 50, "random_numeral_base": True}})
    dataset = ExpressionDataset(settings, registry, _Runtime(registry), _random.Random(3), keep_undefined=True)
    parser = DefinitionParser(settings.symbols, registry)

    def literals(node):
        if isinstance(node, _Number):
            yield node.value
        elif isinstance(node, _Call):
            for arg in node.args:
                yield from literals(arg)

    from opulse.expression.nodes import from_dict

    for record in dataset.records(30):  # verify-on-write raises on any disagreement
        tree = from_dict(record["tree"], registry)
        assert all(v >= 0 for v in literals(tree))
        assert from_ast(parser.parse_expr(record["expression"], expression_mode=True), registry) == tree


def test_negative_marked_numeral_round_trips(registry):
    from opulse.definition.parser import DefinitionParser
    from opulse.expression.numerals import NumeralWriter

    writer = NumeralWriter(registry, "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    text = writer.write(-10, 16)
    parsed = DefinitionParser(Symbols(), registry).parse_expr(text)
    from opulse.verify import Oracle

    assert Oracle(registry).evaluate_expr(parsed, {}).value == -10
