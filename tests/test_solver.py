"""z3 encoding, dead branches, algebraic properties and fill-in-the-blank problems.

Every solver answer is compared with the reference oracle: the encoding must
agree with it value by value, counterexamples must be real, and every
solution of a blank must evaluate to the target.
"""

import itertools

import pytest
import z3

from opulse.config import Symbols
from opulse.core import (
    BINARY,
    BRANCH,
    NAN,
    POSTFIX,
    PREFIX,
    RECURSIVE,
    SIMPLE,
    UNARY,
    Operator,
    Semantics,
)
from opulse.expression.nodes import Call, Number, Variable
from opulse.solver.holes import HoleSolver, hole_paths
from opulse.solver.properties import PropertyChecker
from opulse.solver.static import dead_branch_reason, reachable_branches
from opulse.solver.z3_encode import Z3Encoder, ZVal, evaluate_concrete
from opulse.verify import Oracle

B = 2**31 - 1
EDGES = [0, 1, -1, 2, -2, 7, -7, 8, -8, 9, -9, 100, -100, 12345, -12345, B, -B, B - 1, -(B - 1)]


def define(registry, oracle, text, symbol, n_ary, position=None, kind=SIMPLE):
    operator = Operator(func_id=f"t{len(registry)}", symbol=symbol, n_ary=n_ary, unary_position=position,
                        definition=text, definition_type=kind)
    operator.id = len(registry) + 1
    registry.add(operator)
    oracle.refresh()
    oracle.include(operator)  # resolvable without compiled code
    return operator


@pytest.fixture
def setup(registry):
    oracle = Oracle(registry, Symbols())
    return registry, oracle, Z3Encoder(oracle)


def _inputs(operator):
    return itertools.product([*EDGES, NAN], repeat=operator.n_ary)


@pytest.mark.parametrize("text,symbol,n_ary,position,kind", [
    ("a ⊕ b = { (a + 3) * b }", "⊕", BINARY, None, SIMPLE),
    ("a ⊕ b = { a / b, if a > 0; a % b, if (a / b) < 0 }", "⊕", BINARY, None, BRANCH),
    ("a ⊕ b = { (a @) - (# b), if a >= b; & (a * b), else }", "⊕", BINARY, None, BRANCH),
    ("⋮ a = { a $ }", "⋮", UNARY, PREFIX, SIMPLE),
    ("⋮ a = { a, if a % 7 == 0; (⋮ ((a % 7) - 1)) + 3, if a % 7 > 0; (⋮ ((a % 7) + 1)) * 2, if a % 7 < 0 }",
     "⋮", UNARY, PREFIX, RECURSIVE),
    ("a ⋮ = { 1, if a == 0; ((a - 1) ⋮) + a, if a > 0 and a <= 8; ((a + 1) ⋮) - a, if a < 0 and a >= -8 }",
     "⋮", UNARY, POSTFIX, RECURSIVE),
])
def test_encoding_agrees_with_oracle(setup, text, symbol, n_ary, position, kind):
    registry, oracle, encoder = setup
    operator = define(registry, oracle, text, symbol, n_ary, position, kind)
    for args in _inputs(operator):
        expected = oracle.evaluate(operator, args).value
        got = evaluate_concrete(encoder, operator, args)
        assert got is expected if expected is NAN else got == expected, (args, got, expected)


@pytest.mark.parametrize("text,position", [
    ("⋮ a = { a, if a % 7 == 0; (⋮ ((a % 7) - 1)) + 3, if a % 7 > 0; (⋮ ((a % 7) + 1)) * 2, if a % 7 < 0 }", PREFIX),
    ("⋮ a = { 1, if a == 0; (⋮ (a - 1)) + a, if a > 0 and a <= 8; (⋮ (a + 1)) - a, if a < 0 and a >= -8 }", PREFIX),
])
def test_recursion_on_undefined_argument_is_undefined(setup, text, position):
    """A NaN loop argument makes the first comparison abort, so the call is NaN."""
    registry, oracle, encoder = setup
    operator = define(registry, oracle, text, "⋮", UNARY, position, RECURSIVE)
    assert oracle.evaluate(operator, (NAN,)).value is NAN
    encoder.reset()
    defined = z3.Bool("d")
    result = encoder._apply(operator, [ZVal(defined, z3.Int("y"))], 0)
    solver = z3.Solver()
    solver.add(z3.Not(defined), result.defined)
    assert solver.check() == z3.unsat
    # The same through a fill-in-the-blank problem: 5 / x is NaN at x = 0.
    div = registry.find("/", BINARY)
    tree = Call(operator, (Call(div, (Number(5), Variable("x"))),))
    target = oracle.evaluate(operator, (5,)).value
    found = HoleSolver(encoder, oracle).solve(tree, target)
    assert 0 not in found.values and 1 in found.values


def test_truncating_division_and_zero_divisor(setup):
    registry, _oracle, encoder = setup
    div = registry.find("/", BINARY)
    mod = registry.find("%", BINARY)
    assert evaluate_concrete(encoder, div, (-7, 2)) == -3   # truncation, not floor (-4)
    assert evaluate_concrete(encoder, mod, (-7, 2)) == -1   # sign of the dividend, not +1
    assert evaluate_concrete(encoder, mod, (7, -2)) == 1
    assert evaluate_concrete(encoder, div, (5, 0)) is NAN
    assert evaluate_concrete(encoder, mod, (5, 0)) is NAN


def test_dead_branch_is_found(setup):
    registry, oracle, encoder = setup
    op = define(registry, oracle, "a ⊕ b = { a, if a > 5; b, if a > 10; a + b, else }", "⊕", BINARY, kind=BRANCH)
    assert reachable_branches(op, encoder) == ["reachable", "dead"]
    assert dead_branch_reason(op, encoder) == "dead branch 2"


def test_always_undefined_branch_is_found(setup):
    registry, oracle, encoder = setup
    op = define(registry, oracle, "a ⊕ b = { (b / (a - a)) * b, if a > 5; a + b, else }", "⊕", BINARY,
                kind=BRANCH)
    assert reachable_branches(op, encoder) == ["undefined"]
    assert dead_branch_reason(op, encoder) == "undefined branch 1"


def test_negative_remainder_branch_is_reachable(setup):
    """With truncating %, ``v % m < 0`` is reachable exactly for v < 0."""
    registry, oracle, encoder = setup
    op = define(registry, oracle,
                "⋮ a = { a, if a % 7 == 0; ⋮ ((a % 7) - 1), if a % 7 > 0; ⋮ ((a % 7) + 1), if a % 7 < 0 }",
                "⋮", UNARY, PREFIX, RECURSIVE)
    assert reachable_branches(op, encoder) == ["reachable"] * 3
    # A square is never negative: it is either >= 0 or overflows to NaN (which aborts).
    dead = define(registry, oracle, "⋯ a = { a, if (a * a) < 0; a + 1, else }", "⋯", UNARY, PREFIX, BRANCH)
    assert reachable_branches(dead, encoder) == ["dead"]


def test_properties_of_base_operations(setup):
    registry, oracle, encoder = setup
    checker = PropertyChecker(encoder)
    plus, minus, times = (registry.find(s, BINARY) for s in "+-*")
    assert checker.check(plus, "commutative").status == "proved"
    refuted = checker.check(minus, "commutative")
    assert refuted.status == "refuted"
    a, b = refuted.counterexample
    assert oracle.evaluate(minus, (a, b)).value != oracle.evaluate(minus, (b, a)).value
    identity = checker.check(times, "right_identity")
    assert (identity.status, identity.witness) == ("proved", 1)
    # Under the bound, overflow to NaN breaks associativity; the counterexample is real.
    assoc = checker.check(plus, "associative")
    assert assoc.status == "refuted"
    x, y, z = assoc.counterexample
    left = oracle.evaluate(plus, (oracle.evaluate(plus, (x, y)).value, z)).value
    right = oracle.evaluate(plus, (x, oracle.evaluate(plus, (y, z)).value)).value
    assert not (left is right or left == right)


def test_unique_blank_and_reverse_steps(setup):
    registry, oracle, encoder = setup
    plus, times = registry.find("+", BINARY), registry.find("*", BINARY)
    tree = Call(times, (Call(plus, (Number(2), Number(3))), Number(4)))  # (2 + 3) * 4 = 20
    solver = HoleSolver(encoder, oracle)
    problem = solver.problem(tree, (0, 0))
    assert problem.target == 20 and problem.answer == 2
    assert problem.solutions.unique and problem.solutions.values == [2]
    assert [step.candidates for step in problem.reverse] == [[5], [2]]
    assert all(step.complete for step in problem.reverse)


def test_blank_solutions_are_all_correct(setup):
    registry, oracle, encoder = setup
    mod = registry.find("%", BINARY)
    tree = Call(mod, (Number(10), Number(4)))  # 10 % 4 = 2; x % 4 = 2 has many solutions
    solver = HoleSolver(encoder, oracle)
    for path in hole_paths(tree):
        problem = solver.problem(tree, path)
        assert not problem.solutions.unique
        for value in problem.solutions.values:
            assert solver.value(problem.expression, value) == problem.target


def test_smt_export_round_trip_and_solving(setup):
    """The z3 field: exported text re-evaluates to the oracle and lets z3 solve for an input."""
    from opulse.solver.smt import SmtEvaluator, export, module, prelude, smt_name

    registry, oracle, encoder = setup
    branch = define(registry, oracle, "a ⊕ b = { (a @) - (# b), if a >= b; & (a * b), else }", "⊕", BINARY,
                    kind=BRANCH)
    rec = define(registry, oracle,
                 "⋮ a = { a, if a % 7 == 0; (⋮ ((a % 7) - 1)) ⊕ a, if a % 7 > 0; (⋮ ((a % 7) + 1)) ⊕ a, if a % 7 < 0 }",
                 "⋮", UNARY, PREFIX, RECURSIVE)
    base = prelude(encoder)
    for operator in (branch, rec):
        assert export(operator, encoder, base)  # raises if any boundary/NaN point disagrees
    text = module(rec, encoder, base)
    target = oracle.evaluate(rec, (20,)).value
    ctx = z3.Context()
    solver = z3.Solver(ctx=ctx)
    name = smt_name(rec)
    solver.add(z3.parse_smt2_string(
        text + f"(declare-const x Int)(assert (<= 0 x 50))(assert (distinct x 20))"
               f"(assert ({name}_d true x))(assert (= ({name}_v true x) {target}))", ctx=ctx))
    assert solver.check() == z3.sat  # z3 finds another input with the same value
    x = solver.model().eval(z3.Int("x", ctx), model_completion=True).as_long()
    assert x != 20 and oracle.evaluate(rec, (x,)).value == target
    # Euclidean SMT-LIB division in the independent evaluator.
    evaluator = SmtEvaluator("")
    assert evaluator.evaluate("(div (- 7) 2)") == -4 and evaluator.evaluate("(mod (- 7) 2)") == 1
    assert evaluator.evaluate("(div 7 (- 2))") == -3 and evaluator.evaluate("(mod 7 (- 2))") == 1


def test_property_must_match_arity(setup):
    registry, _, encoder = setup
    neg = registry.find("-", UNARY, PREFIX)
    with pytest.raises(ValueError, match="not a property of 1-ary"):
        PropertyChecker(encoder).check(neg, "commutative")


def _small_bound_setup(registry, bound):
    oracle = Oracle(registry, Symbols(), Semantics("exact", bound))
    return oracle, Z3Encoder(oracle)


def test_digit_operations_on_literals_above_the_bound(registry):
    """Review findings: with B = 100, ``1000 @`` is 1 (the literal may exceed B); z3 used a width of 3 digits."""
    oracle, encoder = _small_bound_setup(registry, 100)
    reverse = registry.find("@", UNARY, POSTFIX)
    assert evaluate_concrete(encoder, reverse, (1000,)) == 1 == oracle.evaluate(reverse, (1000,)).value
    op = define(registry, oracle, "a ⊕ b = { 1000 @, if a == 37; 0, else }", "⊕", BINARY, kind=BRANCH)
    encoder = Z3Encoder(oracle)
    from opulse.solver.equivalence import EquivalenceChecker

    verdict = EquivalenceChecker(encoder).check(Call(op, (Variable("a"), Variable("b"))), Number(0))
    assert verdict.status == "refuted" and verdict.counterexample["a"] == 37
    times = registry.find("*", BINARY)
    hole = Call(times, (Variable("x"), Call(reverse, (Number(100),))))  # x * (100 @) = 1  ->  x = 1
    found = HoleSolver(encoder, oracle).solve(hole, 1)
    assert found.complete and found.values == [1]


def test_searches_stay_inside_the_value_domain(registry):
    """Review findings: counterexamples and branch witnesses must lie in [-B, B]."""
    oracle, _ = _small_bound_setup(registry, 3)
    op = define(registry, oracle, "a ⊕ b = { a, if a <= 3; 0, else }", "⊕", BINARY, kind=BRANCH)
    from opulse.solver.equivalence import EquivalenceChecker

    checker = EquivalenceChecker(Z3Encoder(oracle))
    assert checker.check(Call(op, (Variable("a"), Variable("b"))), Variable("a")).status == "proved"
    dead = define(registry, oracle, "a ⊗ b = { a, if a == 100; b, else }", "⊗", BINARY, kind=BRANCH)
    assert reachable_branches(dead, Z3Encoder(oracle)) == ["dead"]


def test_identity_not_found_is_not_a_refutation(registry):
    oracle, _ = _small_bound_setup(registry, 200)
    op = define(registry, oracle, "a ⊕ b = { b, if a == 101; 0, else }", "⊕", BINARY, kind=BRANCH)
    verdict = PropertyChecker(Z3Encoder(oracle)).check(op, "left_identity")
    assert verdict.status != "refuted"


def test_smt_export_without_a_bound(registry):
    from opulse.solver.smt import export, prelude

    oracle, encoder = _small_bound_setup(registry, None)
    assert "base_reverse" not in prelude(encoder)  # digit operations need a bound
    op = define(registry, oracle, "a ⊕ b = { (a + b) * 2 }", "⊕", BINARY)
    assert export(op, Z3Encoder(oracle))
    digits = define(registry, oracle, "a ⊗ b = { (a + b) @ }", "⊗", BINARY)
    assert export(digits, Z3Encoder(oracle)) is None


def test_reverse_derivation_through_an_undefined_argument(setup):
    """Benchmark finding: x sits under a NaN sub-expression that the outer definition ignores."""
    registry, oracle, encoder = setup
    op = define(registry, oracle, "a ⊕ b = { b, if b > 0; a + b, else }", "⊕", BINARY, kind=BRANCH)
    div = registry.find("/", BINARY)
    tree = Call(op, (Call(div, (Number(7), Number(0))), Number(5)))  # (7 / 0) ⊕ 5 = 5
    problem = HoleSolver(encoder, oracle).problem(tree, (0, 0))   # blank the 7
    assert problem.target == 5
    assert problem.reverse[0].complete is False and problem.reverse[0].candidates == []
    for value in problem.solutions.values:
        assert HoleSolver(encoder, oracle).value(problem.expression, value) == 5
