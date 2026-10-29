"""Released expression records are checked against the reference interpreter."""

from copy import deepcopy

import pytest

from opulse.config import Settings
from opulse.expression.dataset import operator_set_hash
from opulse.expression.nodes import Call, Number, to_dict
from opulse.verify import Oracle
from opulse.verify.records import VerificationError, audit_record, verify_evaluation


def _record(registry):
    add = registry.find("+", 2)
    tree = Call(add, (Number(1), Number(2)))
    return tree, {
        "tree": to_dict(tree), "result": 3, "undefined": False, "expansion": 1,
        "expression": "1 + 2", "expression_plain": "1 + 2",
        "expression_full_brackets": "(1 + 2)", "result_text": "3", "result_base": 10,
        "text": "1 + 2 = 3", "steps": [{"func_id": add.func_id, "symbol": "+", "inputs": [1, 2],
                                             "output": 3, "base_ops": 1, "depth": 0}],
        "provenance": {"operator_set": operator_set_hash(registry)},
    }


def test_verify_evaluation_rejects_wrong_value_and_expansion(registry):
    tree, _ = _record(registry)
    oracle = Oracle(registry)
    verify_evaluation(tree, 3, 1, oracle)
    with pytest.raises(VerificationError, match="value 4"):
        verify_evaluation(tree, 4, 1, oracle)
    with pytest.raises(VerificationError, match="expansion 0"):
        verify_evaluation(tree, 3, 0, oracle)


@pytest.mark.parametrize(("field", "bad", "finding"), [
    ("result", 4, "value:"),
    ("expansion", 0, "value:"),
    ("expression", "(", "expression does not parse:"),
    ("result_text", "3G", "result_text does not decode:"),
    ("text", "wrong", "text is not"),
])
def test_audit_record_finds_independent_corruptions(registry, field, bad, finding):
    _, row = _record(registry)
    oracle = Oracle(registry)
    settings = Settings()
    assert audit_record(row, registry, oracle, settings) == []

    changed = deepcopy(row)
    changed[field] = bad
    assert any(problem.startswith(finding) for problem in audit_record(changed, registry, oracle, settings))


def test_audit_record_rejects_wrong_operator_set_provenance(registry):
    _, row = _record(registry)
    row["provenance"]["operator_set"] = "other set"
    findings = audit_record(row, registry, Oracle(registry), Settings())
    assert "provenance: the record was made from a different operator set" in findings


def test_audit_record_rejects_missing_steps_without_operation_count(registry):
    _, row = _record(registry)
    row["steps"] = []
    findings = audit_record(row, registry, Oracle(registry), Settings())
    assert any(problem.startswith("steps:") for problem in findings)
