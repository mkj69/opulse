"""Regressions for definition parsing and reference evaluation."""

import pytest

from opulse.config import Symbols
from opulse.core import NAN, Operator, OperatorRegistry
from opulse.core.primitives import (
    register_primitive,
    unregister_primitive,
    write_initial_set,
)
from opulse.definition import ast
from opulse.definition.codegen import compile_definition, registry_resolver
from opulse.definition.parser import DefinitionParser, DefinitionSyntaxError
from opulse.runtime import PythonRuntime
from opulse.verify import Oracle


def test_top_level_atom_counts_its_application():
    atom = Operator(func_id="add_review", symbol="+", n_ary=2)
    registry = OperatorRegistry([atom])
    oracle = Oracle(registry)
    runtime = PythonRuntime(registry)
    for args in ((2, 3), (NAN, 3)):
        result = oracle.evaluate(atom, args)
        assert (result.value, result.base_ops, result.calls) == runtime.evaluate(atom)(*args)


def test_top_level_typed_atom_counts_undefined_application(tmp_path):
    register_primitive("length_review", "⟐", len, n_ary=1, parameter_types=("str",),
                       rule="The atom returns the string length.")
    try:
        path = write_initial_set(tmp_path / "atoms.jsonl", ["length_review"])
        registry = OperatorRegistry.from_jsonl(path)
        atom = registry.find("⟐", 1, "postfix")
        result = Oracle(registry).evaluate(atom, (NAN,))
        assert (result.value, result.base_ops, result.calls) == PythonRuntime(registry).evaluate(atom)(NAN)
    finally:
        unregister_primitive("length_review")


def test_binary_definition_rejects_duplicate_parameters():
    with pytest.raises(DefinitionSyntaxError, match="repeat"):
        DefinitionParser(Symbols()).parse("a ⊕ a = { a }")


def test_codegen_rejects_duplicate_parameters_in_direct_ast():
    definition = ast.Definition(
        ast.Apply("⊕", (ast.Var("a"), ast.Var("a"))),
        (ast.Branch(ast.Var("a")),),
    )
    operator = Operator(func_id="dup_review", symbol="⊕", n_ary=2, definition="a ⊕ a = { a }")
    with pytest.raises(ValueError, match="repeat"):
        compile_definition(definition, operator.func_id, registry_resolver(OperatorRegistry(), operator))


@pytest.mark.parametrize("args", [(1,), (1, 2, 3)])
def test_oracle_rejects_wrong_argument_count(args):
    operator = Operator(func_id="arity_review", symbol="◇", n_ary=2,
                        definition="a ◇ b = { a }")
    with pytest.raises(TypeError, match="arguments"):
        Oracle(OperatorRegistry()).evaluate(operator, args)
