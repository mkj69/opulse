"""The legacy audit distinguishes stored code from written definitions."""

from opulse.cli.main import main
from opulse.core import Operator, OperatorRegistry


def test_legacy_audit_reports_agreement_and_a_local_mismatch(tmp_path, capsys):
    path = tmp_path / "operators.jsonl"
    operators = [
        Operator(func_id="add", symbol="+", n_ary=2),
        Operator(func_id="good", symbol="⊕", n_ary=2,
                 definition="a ⊕ b = { a + b }", definition_type="simple_definition",
                 op_compute_func="def op_good(a, b):\n    return a + b\n",
                 op_count_func="def op_count_good(a, b):\n    return 1\n"),
        Operator(func_id="bad", symbol="⊗", n_ary=2,
                 definition="a ⊗ b = { a + b }", definition_type="simple_definition",
                 op_compute_func="def op_bad(a, b):\n    return a - b\n",
                 op_count_func="def op_count_bad(a, b):\n    return 1\n"),
    ]
    OperatorRegistry(operators).to_jsonl(path)

    assert main(["audit", "--operators", str(path), "--samples", "12", "--seed", "4"]) == 1
    output = capsys.readouterr().out
    assert "'local agree': 1" in output
    assert "'local mismatch': 1" in output
    assert "a ⊗ b = { a + b }" in output


def test_legacy_audit_accepts_matching_stored_code(tmp_path, capsys):
    path = tmp_path / "operators.jsonl"
    OperatorRegistry([
        Operator(func_id="add", symbol="+", n_ary=2),
        Operator(func_id="good", symbol="⊕", n_ary=2,
                 definition="a ⊕ b = { a + b }", definition_type="simple_definition",
                 op_compute_func="def op_good(a, b):\n    return a + b\n",
                 op_count_func="def op_count_good(a, b):\n    return 1\n"),
    ]).to_jsonl(path)
    assert main(["audit", "--operators", str(path), "--samples", "4", "--seed", "0"]) == 0
    assert "'global agree': 1" in capsys.readouterr().out
