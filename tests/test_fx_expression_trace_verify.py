"""Regressions for the expression, trace, and record verification review."""

import random
from copy import deepcopy
from dataclasses import replace

import pytest

from opulse.config import ExpressionSettings, Settings
from opulse.core import Operator
from opulse.definition.codegen import compile_definition, registry_resolver
from opulse.definition.parser import DefinitionParser
from opulse.expression.aliases import AliasMap, aliased_registry
from opulse.expression.dataset import ExpressionDataset
from opulse.expression.generator import ExpressionGenerator, OperatorPool
from opulse.expression.nodes import Call, Number, depth
from opulse.expression.numerals import from_base
from opulse.expression.render import ExpressionRenderer
from opulse.language.narrate import narrate
from opulse.runtime import PythonRuntime
from opulse.trace import Reducer
from opulse.trace.count import StepCounter
from opulse.trace.tree import build_tree, from_json, to_json, verify_tree
from opulse.verify import Oracle, VerificationError, verify_trace
from opulse.verify.records import audit_record


def _defined(registry, symbol, body, func_id):
    op = Operator(func_id, symbol, 2, definition=body)
    parser = DefinitionParser(Settings().symbols, registry)
    code = compile_definition(parser.parse(body), func_id, registry_resolver(registry, op))
    op.op_compute_func, op.op_count_func = code.compute, code.count
    op.dependencies = list(code.dependencies)
    registry.add(op)
    return op


def _record(registry, symbol, left, right):
    settings = Settings()
    tree = Call(registry.find(symbol, 2), (Number(left), Number(right)))
    row = ExpressionDataset(settings, registry, PythonRuntime(registry)).record(0, tree)
    return row, settings


def test_fx_audit_structural_fields(registry):
    row, settings = _record(registry, "+", 1, 2)
    assert audit_record(row, registry, Oracle(registry), settings) == []
    for key, value in (("operation_count", 999), ("defined_operators", ["made_up"]),
                       ("used_operators", ["made_up"]), ("max_edge_count", 999),
                       ("max_path_depth", 999)):
        changed = deepcopy(row)
        changed[key] = value
        assert audit_record(changed, registry, Oracle(registry), settings), key


def test_fx_audit_undefined_result_must_be_null(registry):
    row, settings = _record(registry, "/", 1, 0)
    assert row["undefined"] and row["result"] is None
    changed = deepcopy(row)
    changed["result"] = 123
    assert audit_record(changed, registry, Oracle(registry), settings)


def test_fx_typed_tree_respects_depth_and_integer_range(registry):
    op = _defined(registry, "⊕", 'a ⊕ b = { "x" }', "fx_typed")
    op.parameter_types = ("int", "int")
    op.result_type = "str"
    settings = ExpressionSettings(max_depth=1, value_min=100, value_max=100)
    tree = ExpressionGenerator(settings, random.Random(0)).typed_tree(OperatorPool.from_registry(registry))
    assert depth(tree) <= 2
    assert {arg.value for arg in tree.args if isinstance(arg, Number)} == {100}


def test_fx_typed_dataset_uses_configured_sampler(registry):
    op = Operator("fx_typed_dataset", "◇", 2, definition="a ◇ b = { a }",
                  parameter_types=("str", "int"), result_type="str")
    parser = DefinitionParser(Settings().symbols, registry)
    code = compile_definition(parser.parse(op.definition), op.func_id, registry_resolver(registry, op))
    op.op_compute_func, op.op_count_func = code.compute, code.count
    registry.add(op)
    settings = Settings(expressions=ExpressionSettings(max_depth=1, value_min=100, value_max=100))
    row = next(ExpressionDataset(settings, registry, PythonRuntime(registry),
                                 rng=random.Random(1)).records(1))
    assert row["operation_count"] == 1
    assert row["tree"]["right_expr"]["value"] == 100


def test_fx_alias_truth_condition(registry):
    _defined(registry, "◇", "a ◇ b = { a, if true; b, else }", "fx_truth")
    alias = AliasMap.build(registry, random.Random(0))
    renamed = aliased_registry(registry, alias)
    op = renamed.get("fx_truth")
    assert Oracle(renamed).evaluate(op, (3, 4)).value == 3


def test_fx_alias_nested_search(registry):
    _defined(registry, "⊙", "a ⊙ b = { a + b }", "fx_inner")
    _defined(registry, "⊕", "a ⊕ b = { search(i, 2, (i ⊙ a) == b) + 1 }", "fx_outer")
    alias = AliasMap.build(registry, random.Random(0))
    renamed = aliased_registry(registry, alias)
    assert Oracle(renamed).evaluate(renamed.get("fx_outer"), (2, 3)).value == 2


@pytest.mark.parametrize("text", ["", "-", "--1"])
def test_fx_reject_malformed_numeral(text):
    with pytest.raises(ValueError):
        from_base(text, 10, "0123456789ABCDEF")


def test_fx_audit_rejects_empty_result_text(registry):
    row, settings = _record(registry, "+", 0, 0)
    row["result_text"] = ""
    row["text"] = row["expression"] + " = "
    assert audit_record(row, registry, Oracle(registry), settings)


def test_fx_nested_search_trials_visible(registry):
    op = _defined(registry, "⊕", "a ⊕ b = { search(i, 2, (i + a) == b) + 1 }", "fx_search")
    tree = Call(op, (Number(2), Number(3)))
    parser = DefinitionParser(Settings().symbols, registry)
    runtime = PythonRuntime(registry)
    reducer = Reducer(registry, runtime, parser)
    trace = reducer.reduce(tree)
    verify_trace(trace, Oracle(registry))
    assert trace.value == 2
    assert any(step.search_attempts and "i=0: False" in step.search_attempts
               and "i=1: True" in step.search_attempts
               for step in trace.steps)
    assert StepCounter(reducer).count(tree) == len(trace.steps)
    assert "i=1: True" in narrate(trace, ExpressionRenderer(Settings().symbols), "en")
    changed = deepcopy(trace)
    changed.steps[0] = replace(changed.steps[0], search_attempts="i=0: True")
    with pytest.raises(VerificationError, match="search trials"):
        verify_trace(changed, Oracle(registry))
    derivation = build_tree(tree, registry, runtime, parser)
    assert verify_tree(from_json(to_json(derivation), registry), Oracle(registry)) >= 1


def test_fx_trace_rejects_bad_index_and_reason(registry):
    tree = Call(registry.find("+", 2), (Number(1), Number(2)))
    trace = Reducer(registry, PythonRuntime(registry), DefinitionParser(Settings().symbols, registry)).reduce(tree)
    oracle = Oracle(registry)
    for change in ({"index": 999}, {"reason": "arbitrary"}):
        changed = deepcopy(trace)
        changed.steps[0] = replace(changed.steps[0], **change)
        with pytest.raises(VerificationError):
            verify_trace(changed, oracle)
