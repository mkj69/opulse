"""Equivalence verdicts are proofs or oracle-checked counterexamples."""

import json

from opulse.cli.main import main
from opulse.config import Symbols
from opulse.core import BINARY, NAN, SIMPLE, Operator, OperatorRegistry, Semantics
from opulse.expression.nodes import Call, Variable
from opulse.solver.equivalence import (
    EquivalenceChecker,
    equivalent_operators,
    sympy_candidate,
)
from opulse.solver.z3_encode import Z3Encoder
from opulse.verify import Oracle

A, B = Variable("a"), Variable("b")


def _checker(registry, bound=2**31 - 1):
    oracle = Oracle(registry, Symbols(), Semantics("exact", bound))
    return EquivalenceChecker(Z3Encoder(oracle)), oracle


def test_cancellation_fails_at_the_bound_and_holds_without_it(registry):
    plus, minus = registry.find("+", BINARY), registry.find("-", BINARY)
    left = Call(minus, (Call(plus, (A, B)), B))
    checker, _ = _checker(registry)
    verdict = checker.check(left, A)
    assert verdict.status == "refuted" and verdict.equivalent is False
    env = verdict.counterexample
    assert checker.value(left, env) is NAN and checker.value(A, env) == env["a"]  # a + b overflowed
    unbounded, _ = _checker(registry, bound=None)
    assert unbounded.check(left, A).status == "proved"


def test_sympy_proposal_is_checked(registry):
    plus, times = registry.find("+", BINARY), registry.find("*", BINARY)
    square = Call(times, (Call(plus, (A, B)), Call(plus, (A, B))))
    expanded = sympy_candidate(square, registry)
    assert expanded is not None and expanded != square
    unbounded, _ = _checker(registry, bound=None)
    assert unbounded.check(square, expanded).status == "proved"
    bounded, _ = _checker(registry)
    verdict = bounded.check(square, expanded)
    assert verdict.status == "refuted"  # e.g. a = B, b = -B: the square is 0, a * a overflows
    left, right = verdict.left_value, verdict.right_value
    assert (left is NAN) != (right is NAN) or left != right


def test_equivalent_operators_are_found(registry):
    def define(func_id, symbol, text):
        op = Operator(func_id=func_id, symbol=symbol, n_ary=BINARY, definition=text, definition_type=SIMPLE)
        op.op_compute_func = f"def op_{func_id}(a, b):\n    return 0\n"  # resolvable; values come from the oracle
        op.op_count_func = f"def op_count_{func_id}(a, b):\n    return 0\n"
        registry.add(op)
        return op

    f = define("eqf", "⊕", "a ⊕ b = { a + b }")
    g = define("eqg", "⊗", "a ⊗ b = { (b + a), if a > 3; b + a, else }")
    h = define("eqh", "⊖", "a ⊖ b = { a - b }")
    checker, _ = _checker(registry)
    pairs = {(x.symbol, y.symbol): v.status for x, y, v in equivalent_operators(registry, checker, [f, g, h])}
    assert pairs == {("⊕", "⊗"): "proved"}


def test_equivalences_cli(tmp_path):
    ops = tmp_path / "ops.jsonl"
    assert main(["operators", "--out", str(ops), "--layers", "6", "3", "--seed", "5"]) == 0
    out = tmp_path / "eq.jsonl"
    assert main(["equivalences", "--operators", str(ops), "--out", str(out), "--count", "6",
                 "--max-depth", "2"]) == 0
    registry = OperatorRegistry.from_jsonl(ops)
    oracle = Oracle(registry)
    from opulse.expression.nodes import from_dict, to_ast

    for line in out.read_text().splitlines():
        record = json.loads(line)
        assert record["equivalent"] in (True, False)
        if record["equivalent"] is False:
            env = record["counterexample"]
            left = oracle.evaluate_expr(to_ast(from_dict(record["left_tree"], registry)), env).value
            right = oracle.evaluate_expr(to_ast(from_dict(record["right_tree"], registry)), env).value
            assert (None if left is NAN else left) == record["left_value"]
            assert (None if right is NAN else right) == record["right_value"]
            assert record["left_value"] != record["right_value"]
