"""Branch selection respects short circuits and undefined comparisons."""

from opulse.analysis.coverage import branch_witnesses, selected_branch
from opulse.core import BRANCH, Operator
from opulse.solver.z3_encode import Z3Encoder
from opulse.verify import Oracle


def test_or_short_circuit_keeps_zero_defined_and_other_inputs_undefined(registry):
    operator = Operator(func_id="shortcircuit", symbol="⊕", n_ary=1, unary_position="prefix",
                        definition="⊕ a = { 1, if a == 0 or a / 0 > 0; 2, else }",
                        definition_type=BRANCH)
    registry.add(operator)
    oracle = Oracle(registry)

    assert selected_branch(operator, (0,), oracle) == 0
    assert selected_branch(operator, (1,), oracle) is None
    assert selected_branch(operator, (-1,), oracle) is None
    assert branch_witnesses(operator, Z3Encoder(oracle)) == [(0,), None]


def test_not_condition_selects_both_branches(registry):
    operator = Operator(func_id="negatedcondition", symbol="⊗", n_ary=1, unary_position="prefix",
                        definition="⊗ a = { 1, if not (a == 0); 2, else }",
                        definition_type=BRANCH)
    registry.add(operator)
    oracle = Oracle(registry)

    assert selected_branch(operator, (0,), oracle) == 1
    assert selected_branch(operator, (2,), oracle) == 0
    witnesses = branch_witnesses(operator, Z3Encoder(oracle))
    assert [selected_branch(operator, point, oracle) for point in witnesses] == [0, 1]
