"""Regressions for trace verification, record audits, and step grading."""

from dataclasses import replace

import pytest

from opulse.config import Settings
from opulse.core import BINARY, SIMPLE, Operator
from opulse.core.semantics import NAN
from opulse.definition.parser import DefinitionParser
from opulse.expression.dataset import ExpressionDataset
from opulse.expression.nodes import Call, Number
from opulse.runtime import PythonRuntime
from opulse.trace import Reducer
from opulse.verify import Oracle, VerificationError, verify_trace
from opulse.verify.records import audit_record
from opulse.verify.steps import check_steps, step_lines


def _trace(registry, source):
    parser = DefinitionParser(Settings().symbols, registry)
    trace = Reducer(registry, PythonRuntime(registry), parser).reduce(source)
    oracle = Oracle(registry)
    verify_trace(trace, oracle)
    return trace, oracle, parser


def test_bounded_negation_is_not_a_literal_step(registry):
    parser = DefinitionParser(Settings().symbols, registry)
    oracle = Oracle(registry)
    source = Call(registry.find("+", 2),
                  (Call(registry.find("-", 1, "prefix"), (Number(2147483648),)), Number(1)))
    report = check_steps(source, ["NaN"], parser, registry, oracle, NAN)
    assert report.single_steps == 0
    assert report.credit == 0


def test_verify_trace_rejects_unknown_kind(registry):
    source = Call(registry.find("+", 2), (Number(1), Number(2)))
    trace, oracle, _ = _trace(registry, source)
    trace.steps[0] = replace(trace.steps[0], kind="fabricated")
    with pytest.raises(VerificationError, match="kind"):
        verify_trace(trace, oracle)


def test_verify_trace_rejects_indirect_undefined_rewrite(registry):
    source = Call(registry.find("/", 2), (Number(1), Number(0)))
    trace, oracle, _ = _trace(registry, source)
    replacement = Call(registry.find("%", 2), (Number(2), Number(0)))
    trace.steps[0] = replace(trace.steps[0], kind="undefined", after=replacement,
                             expression_after=replacement)
    next_step, _, _ = _trace(registry, replacement)
    trace.steps.append(replace(next_step.steps[0], index=1))
    with pytest.raises(VerificationError, match="undefined"):
        verify_trace(trace, oracle)


def test_verify_trace_rejects_false_condition_text(registry):
    op = Operator("review_cond", "⊕", BINARY,
                  definition="a ⊕ b = { a + b, if a > b; a - b, else }",
                  definition_type=SIMPLE)
    op.op_compute_func = "def op_review_cond(a, b):\n    return a + b if a > b else a - b\n"
    op.op_count_func = "def op_count_review_cond(a, b):\n    return 1\n"
    registry.add(op)
    trace, oracle, _ = _trace(registry, Call(op, (Number(3), Number(2))))
    assert trace.steps[0].condition == "3 > 2"
    trace.steps[0] = replace(trace.steps[0], condition="3 < 2")
    with pytest.raises(VerificationError, match="condition"):
        verify_trace(trace, oracle)


def test_audit_record_rejects_missing_derivation(registry):
    settings = Settings()
    runtime = PythonRuntime(registry)
    source = Call(registry.find("+", 2), (Number(1), Number(2)))
    row = ExpressionDataset(settings, registry, runtime).record(0, source)
    oracle = Oracle(registry)
    assert audit_record(row, registry, oracle, settings) == []
    row["steps"] = []
    assert any("steps" in problem for problem in audit_record(row, registry, oracle, settings))


def test_unchecked_derivation_line_prevents_complete_credit(registry):
    source = Call(registry.find("+", 2), (Number(1), Number(2)))
    parser = DefinitionParser(Settings().symbols, registry)
    lines = step_lines("= 3\n3 = 99\nAnswer: 3")
    report = check_steps(source, lines, parser, registry, Oracle(registry), 3)
    assert report.first_error is not None
    assert report.credit < 1


def test_prose_without_equals_is_not_a_step():
    from opulse.verify.steps import step_lines

    reply = "Let me work it out.\n= 28 + 3\n31 = 99\n= 31\nAnswer: 31"
    assert step_lines(reply) == ["28 + 3", "31 = 99", "31"]
