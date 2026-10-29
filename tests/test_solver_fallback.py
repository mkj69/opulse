"""Reference range checks for atoms without a z3 encoding."""

import json

import pytest

from opulse.cli.main import main
from opulse.config import Settings
from opulse.core import OperatorRegistry, Semantics
from opulse.core.primitives import (
    atom_records,
    register_primitive,
    unregister_primitive,
)
from opulse.expression.nodes import Call, Variable
from opulse.solver.equivalence import EquivalenceChecker
from opulse.solver.holes import HoleSolver
from opulse.solver.properties import PropertyChecker, same
from opulse.solver.z3_encode import Z3Encoder
from opulse.verify import Oracle


@pytest.fixture
def atoms(tmp_path):
    register_primitive("range_square", "⊛", lambda a: a * a, rule="a ⊛ is a times a.")
    register_primitive("range_square_copy", "⊜", lambda a: a * a, rule="a ⊜ is a times a.")
    register_primitive("range_double", "⊡", lambda a: 2 * a, rule="a ⊡ is twice a.",
                       z3=lambda a: 2 * a)
    path = tmp_path / "atoms.jsonl"
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in
                            atom_records(["range_square", "range_square_copy", "range_double"])))
    registry = OperatorRegistry.from_jsonl(path)
    try:
        by_symbol = {operator.symbol: operator for operator in registry}
        yield path, registry, by_symbol["⊛"], by_symbol["⊡"]
    finally:
        unregister_primitive("range_square")
        unregister_primitive("range_square_copy")
        unregister_primitive("range_double")


def test_reference_fallback_matches_brute_force(atoms):
    _, registry, square, double = atoms
    oracle = Oracle(registry, semantics=Semantics("exact", 20))
    encoder = Z3Encoder(oracle)
    domain = (-3, 3)
    x = Variable("x")
    expression = Call(square, (x,))
    holes = HoleSolver(encoder, oracle, not_expressible_domain=domain)
    solutions = holes.solve(expression, 4)
    assert solutions.values == [v for v in range(-3, 4) if oracle.evaluate(square, (v,)).value == 4]
    assert solutions.method == "fallback" and solutions.strength == "checked on range [-3, 3]"
    assert solutions.complete and solutions.domain == domain

    equivalence = EquivalenceChecker(encoder, fallback_range=domain)
    same_expression = Call(square, (x,))
    verdict = equivalence.check(expression, same_expression)
    assert verdict.status == "checked" and verdict.equivalent is None
    assert verdict.to_dict()["strength"] == "checked on range [-3, 3]"
    different = equivalence.check(expression, Call(double, (x,)))
    assert different.status == "refuted" and different.strength == "checked on range [-3, 3]"
    assert -3 <= different.counterexample["x"] <= 3

    properties = PropertyChecker(encoder, fallback_range=domain)
    even = properties.check(square, "even")
    expected = all(same(oracle.evaluate(square, (-v,)).value, oracle.evaluate(square, (v,)).value)
                   for v in range(-3, 4))
    assert expected and even.status == "checked" and even.strength == "checked on range [-3, 3]"
    assert properties.check(square, "involution").status == "refuted"

    encoded = PropertyChecker(encoder, fallback_range=domain).check(double, "odd")
    assert encoded.status == "proved" and encoded.strength is None
    assert HoleSolver(encoder, oracle, not_expressible_domain=domain).solve(Call(double, (x,)), 4).method == "z3"


def test_config_and_cli_analyze_report_missing_smt(atoms, tmp_path, capsys):
    path, _, _, _ = atoms
    config = tmp_path / "settings.yaml"
    config.write_text("solver:\n  fallback_range: [-2, 2]\n")
    assert Settings.load(config).solver.fallback_range == (-2, 2)
    out = tmp_path / "analyzed.jsonl"
    assert main(["analyze", "--config", str(config), "--operators", str(path), "--out", str(out),
                 "--fallback-range", "-3", "3"]) == 0
    rows = {row["symbol"]: row for row in map(json.loads, out.read_text().splitlines())}
    square = rows["⊛"]
    assert square["z3"] is None and square["z3_status"] == "unavailable: no z3 encoding"
    assert square["properties"]["even"]["status"] == "checked"
    assert square["properties"]["even"]["strength"] == "checked on range [-3, 3]"
    assert "checked on range [-3, 3]" in capsys.readouterr().out
    equivalences = tmp_path / "equivalences.jsonl"
    assert main(["equivalences", "--config", str(config), "--operators", str(path),
                 "--out", str(equivalences), "--count", "0", "--fallback-range", "-3", "3"]) == 0
    records = list(map(json.loads, equivalences.read_text().splitlines()))
    assert any(row["status"] == "checked" and row["equivalent"] is None and
               row["strength"] == "checked on range [-3, 3]" for row in records)
    assert "checked on range [-3, 3]" in capsys.readouterr().out

    square_only = tmp_path / "square.jsonl"
    square_rows = [next(row for row in map(json.loads, path.read_text().splitlines())
                        if row["symbol"] == "⊛"), *atom_records(["neg"], seed=2)]
    square_only.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in square_rows))
    holes = tmp_path / "holes.jsonl"
    for seed in range(10):
        assert main(["holes", "--config", str(config), "--operators", str(square_only), "--out", str(holes),
                     "--count", "1", "--max-depth", "1", "--seed", str(seed),
                     "--fallback-range", "-100", "100"]) == 0
        hole = json.loads(holes.read_text().splitlines()[0])
        if hole["method"] == "fallback":
            break
    assert hole["method"] == "fallback" and hole["strength"] == "checked on range [-100, 100]"
    assert "checked on range [-100, 100]" in capsys.readouterr().out
