"""Regressions for typed definitions, value limits, and preset atom identity."""

import json

import pytest

from opulse.config import Symbols
from opulse.core.operator import Operator
from opulse.core.presets import register_preset
from opulse.core.primitives import CUSTOM, atom_records, register_primitive
from opulse.core.registry import OperatorRegistry
from opulse.core.semantics import BASE_OPERATIONS, NAN, Semantics
from opulse.definition.codegen import compile_definition, registry_resolver
from opulse.definition.parser import DefinitionParser
from opulse.runtime import PythonRuntime
from opulse.solver.z3_encode import Z3Encoder, evaluate_concrete
from opulse.verify import Oracle


def _compiled_constant(kind, argument):
    operator = Operator(func_id="typed_constant", symbol="◇", n_ary=1,
                        unary_position="prefix", parameter_types=(kind,), result_type="str",
                        definition='◇ a = { "ok" }')
    registry = OperatorRegistry([operator])
    definition = DefinitionParser(Symbols(), registry).parse(operator.definition)
    code = compile_definition(definition, operator.func_id,
                              registry_resolver(registry, operator), operator.parameter_types,
                              operator.result_type)
    operator.op_compute_func, operator.op_count_func = code.compute, code.count
    oracle = Oracle(registry)
    return (oracle.evaluate(operator, (argument,)).value,
            PythonRuntime(registry).evaluate(operator)(argument)[0],
            evaluate_concrete(Z3Encoder(oracle), operator, (argument,)))


def test_typed_definition_can_ignore_undefined_argument():
    assert _compiled_constant("str", NAN) == ("ok", "ok", "ok")


def test_typed_result_checks_integer_parameter():
    assert _compiled_constant("int", "wrong") == (NAN, NAN, NAN)


def test_compiler_infers_typed_result_for_existing_callers():
    operator = Operator(func_id="inferred", symbol="◇", n_ary=1,
                        unary_position="prefix", parameter_types=("int",), result_type="str",
                        definition='◇ a = { "ok" }')
    registry = OperatorRegistry([operator])
    definition = DefinitionParser(Symbols(), registry).parse(operator.definition)
    code = compile_definition(definition, operator.func_id,
                              registry_resolver(registry, operator), operator.parameter_types)
    operator.op_compute_func, operator.op_count_func = code.compute, code.count
    assert PythonRuntime(registry).evaluate(operator)("wrong")[0] is NAN


def test_fractional_numeric_bound_already_rejected():
    with pytest.raises(ValueError, match="bound"):
        Semantics(mode="legacy", bound=2.5)


@pytest.mark.parametrize("field", ["max_string_length", "max_list_length"])
@pytest.mark.parametrize("value", [2.5, True])
def test_value_length_limit_requires_nonnegative_integer(field, value):
    with pytest.raises(ValueError, match=field):
        Semantics(**{field: value})


def test_unsupported_list_type_rejected_at_registration():
    with pytest.raises(ValueError, match=r"list\[str\]"):
        Operator(func_id="bad_list", symbol="◇", n_ary=1, unary_position="prefix",
                 parameter_types=("list[str]",), result_type="list[str]")


def test_preset_rejects_custom_atom_with_same_name():
    custom_before = CUSTOM.copy()
    operations_before = BASE_OPERATIONS.copy()
    try:
        register_primitive("str_concat", "◇", lambda a, b: a + b,
                           n_ary=2, position=None, rule="a ◇ b adds numbers.")
        with pytest.raises(ValueError, match="str_concat"):
            register_preset("strings")
    finally:
        CUSTOM.clear()
        CUSTOM.update(custom_before)
        BASE_OPERATIONS.clear()
        BASE_OPERATIONS.update(operations_before)


def test_preset_record_carries_and_checks_primitive_identity(tmp_path):
    register_preset("strings")
    row = atom_records(["str_concat"])[0]
    assert row["primitive_name"] == "str_concat"
    path = tmp_path / "atom.jsonl"
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    assert OperatorRegistry.from_jsonl(path).find("⊕", 2).primitive_name == "str_concat"
    row["symbol"] = "◇"
    path = tmp_path / "wrong_atom.jsonl"
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="str_concat"):
        OperatorRegistry.from_jsonl(path)
