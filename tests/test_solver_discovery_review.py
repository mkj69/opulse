"""Regressions for the solver and discovery review findings."""

import pytest

from opulse.bench.check import base_registry
from opulse.cli.main import main
from opulse.config import Settings, Symbols
from opulse.core.operator import Operator
from opulse.core.presets import PRESETS, register_preset
from opulse.core.primitives import (
    atom_records,
    register_primitive,
    unregister_primitive,
)
from opulse.core.registry import OperatorRegistry
from opulse.core.semantics import Semantics
from opulse.discovery.loop import _evaluate
from opulse.expression.nodes import Call, Variable
from opulse.solver.equivalence import EquivalenceChecker, equivalent_operators
from opulse.solver.properties import PropertyChecker
from opulse.solver.smt import check_module, export, module
from opulse.solver.z3_encode import NotExpressible, Z3Encoder
from opulse.verify import Oracle


def _defined(registry, symbol, definition, arity, *, position=None):
    operator = Operator(f"review_{len(registry)}", symbol, arity, position, definition=definition)
    registry.add(operator)
    return operator


def test_smt_check_samples_nary_bound(registry):
    op = _defined(registry, "◇", "◇(a, b, c) = { a }", 3)
    encoder = Z3Encoder(Oracle(registry, Symbols(), Semantics("exact", 4)))
    text = module(op, encoder)
    changed = text.replace("  (a_d\n   a))", "  (a_d\n   (ite (= a 4) 0 a)))")
    assert changed != text
    with pytest.raises(AssertionError, match="SMT export"):
        check_module(changed, op, encoder)


@pytest.mark.parametrize("property_name", ["left_identity", "left_absorbing"])
def test_property_element_stays_in_domain(registry, property_name):
    definition = ("a ⊕ b = { b, if a == 10; 0, else }" if property_name == "left_identity"
                  else "a ⊕ b = { 10, if a == 10; b, else }")
    op = _defined(registry, "⊕", definition, 2)
    checker = PropertyChecker(Z3Encoder(Oracle(registry, Symbols(), Semantics("exact", 3))))
    verdict = checker.check(op, property_name)
    assert not (verdict.status == "proved" and verdict.witness == 10)
    assert verdict.status == "not_found"


def test_equivalence_rejects_typed_direct_call():
    register_preset("strings")
    registry = OperatorRegistry(Operator.from_dict(row) for row in atom_records(PRESETS["strings"]))
    checker = EquivalenceChecker(Z3Encoder(Oracle(registry)))
    assert isinstance(equivalent_operators(registry, checker), list)
    with pytest.raises(NotExpressible, match="integer"):
        equivalent_operators(registry, checker, [registry.find("⊕", 2)])
    typed = registry.find("⊕", 2)
    tree = Call(typed, (Variable("a"), Variable("b")))
    with pytest.raises(NotExpressible, match="integer"):
        checker.check(tree, tree)


def test_equivalences_cli_uses_integer_pool(tmp_path):
    register_preset("strings")
    registry = OperatorRegistry(Operator.from_dict(row) for row in atom_records(PRESETS["strings"]))
    operators = tmp_path / "strings.jsonl"
    output = tmp_path / "equivalences.jsonl"
    registry.to_jsonl(operators)
    assert main(["equivalences", "--operators", str(operators), "--out", str(output),
                 "--count", "3", "--max-depth", "2"]) == 0


def test_smt_export_rejects_boolean_condition(registry):
    register_primitive("review_bool_condition", "⚑", lambda a: a > 0,
                       rule="a ⚑ is true when a is positive.", result_type="bool",
                       z3=lambda a: a > 0)
    try:
        registry.add(Operator("review_bool_atom", "⚑", 1, "postfix", result_type="bool"))
        op = _defined(registry, "☆", "a ☆ = { 1, if a ⚑; 0, else }", 1, position="postfix")
        encoder = Z3Encoder(Oracle(registry))
        assert [encoder.oracle.evaluate(op, (a,)).value for a in (-1, 0, 1)] == [0, 0, 1]
        with pytest.raises(NotExpressible, match="integer"):
            export(op, encoder)
    finally:
        unregister_primitive("review_bool_condition")


def test_discovery_shadow_avoids_base_atom(registry):
    settings = Settings()
    base = base_registry(registry)
    register_primitive("review_shadow", "§", lambda a: a,
                       rule="a § returns a.")
    try:
        base.add(Operator("review_shadow_atom", "§", 1, "postfix"))
        original = "a ☆ = { (a + 0) + 0 }"
        state = {"base": base, "symbols": settings.symbols,
                 "semantics": settings.semantics.build(), "library": [original],
                 "problems": ["(5 + 0) + 0"], "metric": "size", "target": "☆",
                 "inputs": [], "checked_range": (-8, 8), "round": 1}
        row = _evaluate(state, {"definition": "a ☆ = { a + 0 }", "replaces": "☆"})
        assert row["accepted"], row.get("reason")
        assert row["verdict"]["status"] == "proved"
    finally:
        unregister_primitive("review_shadow")
