"""Empirical fits must reflect measured costs and reach every definition branch."""

import json

import pytest

from opulse.analysis.complexity import analyze_operator, measurement_grid
from opulse.analysis.coverage import branch_witnesses, selected_branch
from opulse.cli.main import main
from opulse.config import Symbols
from opulse.core import PREFIX, RECURSIVE, SIMPLE, UNARY, Operator, OperatorRegistry
from opulse.definition.codegen import compile_definition, registry_resolver
from opulse.definition.parser import DefinitionParser
from opulse.runtime import PythonRuntime
from opulse.solver.z3_encode import Z3Encoder
from opulse.verify import Oracle


def _operator(registry, text, func_id, symbol, definition_type):
    parser = DefinitionParser(Symbols(), registry)
    operator = Operator(func_id=func_id, symbol=symbol, n_ary=UNARY,
                        unary_position=PREFIX, definition=text,
                        definition_type=definition_type)
    code = compile_definition(parser.parse(text), func_id, registry_resolver(registry, operator))
    operator.op_compute_func, operator.op_count_func = code.compute, code.count
    operator.dependencies = list(code.dependencies)
    registry.add(operator)
    return operator


def test_constant_cost(registry):
    operator = _operator(registry, "⊕ a = { a + 1 }", "constcost", "⊕", SIMPLE)
    runtime = PythonRuntime(registry)
    oracle = Oracle(registry)
    result = analyze_operator(operator, runtime, oracle, Z3Encoder(oracle))
    assert result["model"] == "constant"
    assert result["coefficients"] == [1.0]
    assert result["r2"] == 1.0
    assert result["max_abs_residual"] == 0
    assert result["branch_coverage"] == 1.0


def test_undefined_points_are_excluded_from_fit(registry):
    operator = _operator(registry, "⊕ a = { a / 0, if a == 0; a + 1, else }",
                         "partialcost", "⊕", SIMPLE)
    runtime = PythonRuntime(registry)
    oracle = Oracle(registry)
    result = analyze_operator(operator, runtime, oracle, Z3Encoder(oracle))
    assert result["model"] == "constant"
    assert result["coefficients"] == [1.0]
    # z3 may pick different branch witnesses on each call, so bound the count by the grid
    # plus one witness per branch, minus the excluded NaN point a = 0 (which is in the grid).
    grid = set(measurement_grid(operator))
    assert (0,) in grid
    assert result["n_points"] <= len(grid) + 2 - 1
    without_witnesses = analyze_operator(operator, runtime, oracle, None)
    assert without_witnesses["n_points"] == len(grid) - 1  # exactly the NaN point a = 0 is left out
    assert result["branch_coverage"] == 1.0


def test_bounded_mod_recursion_does_not_look_linear_in_input(registry):
    text = ("⊕ a = { 0, if a % 7 == 0; "
            "1 + (⊕ ((a % 7) - 1)), if a % 7 > 0; "
            "1 + (⊕ ((a % 7) + 1)), if a % 7 < 0 }")
    operator = _operator(registry, text, "boundedcost", "⊕", RECURSIVE)
    runtime = PythonRuntime(registry)
    oracle = Oracle(registry)
    result = analyze_operator(operator, runtime, oracle, Z3Encoder(oracle))
    assert result["model"] == "bounded_mod"
    assert result["branch_coverage"] == 1.0
    assert result["n_points"] > 50


@pytest.fixture(scope="module")
def generated_operators(tmp_path_factory):
    path = tmp_path_factory.mktemp("complexity") / "operators.jsonl"
    assert main(["operators", "--out", str(path), "--layers", "3",
                 "--proportions", "0", "1", "0", "--seed", "3"]) == 0
    return path


def test_witnesses_cover_generated_branch_operators(generated_operators):
    registry = OperatorRegistry.from_jsonl(generated_operators)
    oracle = Oracle(registry)
    encoder = Z3Encoder(oracle)
    runtime = PythonRuntime(registry)
    generated = [op for op in registry if op.definition is not None]
    assert generated
    for operator in generated:
        witnesses = branch_witnesses(operator, encoder)
        assert len(witnesses) == len(oracle._definition_of(operator).branches)
        assert all(point is not None for point in witnesses)
        assert [selected_branch(operator, point, oracle) for point in witnesses] == list(range(len(witnesses)))
        assert analyze_operator(operator, runtime, oracle, encoder)["branch_coverage"] == 1.0


def test_cli_end_to_end(generated_operators, tmp_path):
    output = tmp_path / "complexity.jsonl"
    assert main(["complexity", "--operators", str(generated_operators), "--out", str(output)]) == 0
    rows = [json.loads(line) for line in output.read_text().splitlines()]
    assert len(rows) == 3
    assert all(row["branch_coverage"] == 1.0 for row in rows)
    assert all(row["n_points"] > 0 and row["model"] for row in rows)
    assert all(isinstance(row["coefficients"], list) for row in rows)
