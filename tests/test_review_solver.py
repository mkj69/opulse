"""Regressions for solver findings from the fifth review."""

import pytest
import z3

from opulse.analysis.coverage import branch_witnesses, selected_branch
from opulse.config import Symbols
from opulse.core import BRANCH, NAN, RECURSIVE, SIMPLE, Operator, Semantics
from opulse.expression.nodes import Call, Variable
from opulse.solver.equivalence import (
    EquivalenceChecker,
    encode_node,
    equivalent_operators,
)
from opulse.solver.smt import export, module, prelude
from opulse.solver.z3_encode import Z3Encoder, ZVal
from opulse.verify import Oracle


def _define(registry, func_id, symbol, definition, kind, arity=1):
    operator = Operator(func_id=func_id, symbol=symbol, n_ary=arity,
                        unary_position="prefix" if arity == 1 else None,
                        definition=definition, definition_type=kind)
    parameters = ", ".join(("a", "b")[:arity])
    operator.op_compute_func = f"def op_{func_id}({parameters}):\n    return 0\n"
    operator.op_count_func = f"def op_count_{func_id}({parameters}):\n    return 0\n"
    registry.add(operator)
    return operator


def test_recursive_split_preserves_undefined_remainder(registry):
    g = _define(registry, "review_g", "◇", "◇ a = { 5, if a == 3; 0, else }", BRANCH)
    f = _define(registry, "review_f", "⋮",
                "⋮ a = { 0, if a % 6 == 0; ⋮ ((a % 6) - 1), if a % 6 > 0; "
                "⋮ ((a % 6) + 1), if a % 6 < 0 }", RECURSIVE)
    h = _define(registry, "review_h", "◆",
                "◆ a = { 1, if ⋮ (◇ a) == 0; 0, else }", BRANCH)
    oracle = Oracle(registry, Symbols(), Semantics("exact", 4))
    encoder = Z3Encoder(oracle)
    expression = Call(f, (Call(g, (Variable("a"),)),))
    assert oracle.evaluate_expr(oracle._definition_of(h).branches[0].condition.left,
                                {"a": 3}).value is NAN
    a = z3.Int("a")
    encoded = encode_node(encoder, expression, {"a": ZVal(z3.BoolVal(True), a)})
    solver = z3.Solver()
    solver.add(a == 3, encoded.defined)
    assert solver.check() == z3.unsat
    for index, witness in enumerate(branch_witnesses(h, encoder)):
        if witness is not None:
            assert selected_branch(h, witness, oracle) == index


def test_smt_export_rejects_stale_digit_prelude(registry):
    oracle = Oracle(registry, Symbols(), Semantics("exact", 100))
    encoder = Z3Encoder(oracle)
    old_base = prelude(encoder)
    op = _define(registry, "review_digit", "⊕",
                 "a ⊕ b = { 1000 @, if a == 37; 0, else }", BRANCH, 2)
    oracle.refresh()
    oracle.include(op)
    fresh = prelude(encoder)
    assert fresh != old_base
    assert oracle.evaluate(op, (37, 0)).value == 1
    with pytest.raises(ValueError, match="stale prelude"):
        module(op, encoder, old_base)
    with pytest.raises(ValueError, match="stale prelude"):
        export(op, encoder, old_base)


def test_equivalent_operator_fingerprint_stays_in_bound(registry):
    f = _define(registry, "review_identity", "◇", "◇ a = { a }", SIMPLE)
    g = _define(registry, "review_clamped", "◆",
                "◆ a = { a, if a <= 3; 0, else }", BRANCH)
    oracle = Oracle(registry, Symbols(), Semantics("exact", 3))
    checker = EquivalenceChecker(Z3Encoder(oracle))
    assert checker.check(Call(f, (Variable("a"),)), Call(g, (Variable("a"),))).status == "proved"
    pairs = equivalent_operators(registry, checker, [f, g])
    assert len(pairs) == 1 and pairs[0][2].status == "proved"
