"""Checked measurements, new families, and discovery record replay."""

import json
import random

import pytest
from conftest import INITIAL_OPERATORS

from opulse.bench.check import base_registry, check_tasks
from opulse.bench.families import common, invent
from opulse.bench.families.faster import grade_faster
from opulse.bench.families.refactor import grade_refactor
from opulse.bench.reward import compute_score, rl_record
from opulse.bench.score import score_response
from opulse.bench.tasks import BenchBuilder
from opulse.config import Settings
from opulse.core.registry import OperatorRegistry
from opulse.discovery import metrics
from opulse.discovery.loop import replay, run


@pytest.fixture
def setup():
    settings = Settings()
    base = base_registry(OperatorRegistry.from_jsonl(INITIAL_OPERATORS))
    return settings, base


def test_exact_metrics_and_verdict(setup, monkeypatch):
    settings, base = setup
    ops = common.text_registry(["a ☆ = { (a + 0) + 0 }", "a ★ = { a + 0 }"],
                               base, settings.symbols, settings.semantics.build())
    first, second = [ops.parser.parse(text) for text in ("a ☆ = { (a + 0) + 0 }", "a ★ = { a + 0 }")]
    assert metrics.size(first) == 2
    assert metrics.library_size([first, second]) == 3
    assert metrics.cost(ops, "a ☆", [(-2,), (0,), (2,)]) == 6
    assert metrics.cost(ops, "a ★", [(-2,), (0,), (2,)]) == 3
    branched = common.text_registry(["a ♠ = { a + 1, if a + 1 > 0; a + 2, else }"],
                                    base, settings.symbols, settings.semantics.build())
    assert metrics.cost(branched, "a ♠", [(-2,), (2,)]) == 4
    problems = [ops.parser.parse_expr("(5 + 0) + 0", expression_mode=True)]
    assert metrics.usefulness(problems, [first]) == 2
    assert metrics.equivalence(ops, "a ☆", "a ★")["status"] == "proved"
    monkeypatch.setattr(common, "decide", lambda *args, **kwargs: common.Verdict("undecided", "none"))
    bounded = metrics.equivalence(ops, "a ☆", "a ★", (-2, 2))
    assert bounded["status"] == "checked"
    assert bounded["strength"] == "checked on range [-2, 2]"


def test_simplify_beats_redundant_reference(setup):
    settings, _base = setup
    from opulse.bench.families.equivalence import score_simplify, simplify_question

    given = "a ♠ = { (a + 0) + 0 }"
    reference = "a ☆ = { a + 0 }"
    question = simplify_question("♠", "☆", 1, "postfix", 1,
                                 settings.semantics.build(), settings.symbols.nan, settings.symbols)
    prompt = common.assemble([given], question, ["add"], settings.semantics.build(), "NaN")
    task = {"prompt": prompt, "answer_text": reference}
    graded = score_simplify(task, "Answer: a ☆ = { a }")
    assert graded["correct"] and graded["score"] > 1
    assert graded["beats_reference"] and graded["margin"] == 1


def test_faster_and_refactor_families(setup):
    settings, base = setup
    ops = common.text_registry(["a ☆ = { ((a + 1) + 2) + 3 }"],
                               base, settings.symbols, settings.semantics.build())
    builder = BenchBuilder(settings, ops.registry, random.Random(1))
    faster = next(builder.tasks("faster", 1)).to_dict()
    assert check_tasks([faster], base, settings.symbols, settings.semantics.build()) == []
    assert score_response(faster, "Answer: " + faster["answer_text"])["correct"]
    assert compute_score("opulse", "Answer: " + faster["answer_text"],
                         rl_record(faster)["reward_model"]["ground_truth"]) == 1.0
    wanted = faster["answer_text"].split(" = ")[0]
    candidate = wanted + " = { ((a + 1) + 2) + 3 }"
    assert grade_faster(faster, candidate)["correct"]
    assert not grade_faster(faster, wanted + " = { a + 9 }")["correct"]
    refactor = next(BenchBuilder(settings, ops.registry, random.Random(1)).tasks("refactor", 1)).to_dict()
    assert check_tasks([refactor], base, settings.symbols, settings.semantics.build()) == []
    graded = grade_refactor(refactor, refactor["answer_text"])
    assert graded["correct"] and len(graded["verdicts"]) == 2
    assert all(v["status"] in ("proved", "checked") for v in graded["verdicts"])
    wrong = list(refactor["answer"])
    wrong[-1] = wrong[-1].split(" = ", 1)[0] + " = { a + 1 }"
    assert not grade_refactor(refactor, " || ".join(wrong))["correct"]
    assert compute_score("opulse", "Answer: " + refactor["answer_text"],
                         rl_record(refactor)["reward_model"]["ground_truth"]) == 1.0


def test_invent_reports_better_than_reference(setup):
    settings, base = setup
    hidden = "a ♧ = { ((a + 0) + 1) + 2 }"
    shorter_equal = "a ☆ = { (a + 1) + 2 }"
    problems = ["((5 + 0) + 1) + 2", "(7 + 1) + 2", "(8 + 1) + 2", "(9 + 1) + 2"]
    question = ("Problems:\n" + "\n".join(f"{i}. {p}" for i, p in enumerate(problems, 1)) +
                "\n\nPropose up to 1 new postfix unary definitions with fresh operator symbols. ")
    prompt = common.assemble([], question, ["add"], settings.semantics.build(), "NaN")
    ops = common.text_registry([hidden], base, settings.symbols, settings.semantics.build())
    trees = [ops.parser.parse_expr(p, expression_mode=True) for p in problems]
    baseline = invent.reduction(trees, [ops.parser.parse(hidden)])
    task = {"prompt": prompt, "answer": [hidden], "expression": "; ".join(problems),
            "axes": {"problems": 4, "invent_k": 1}}
    graded = invent.grade_invent(task, shorter_equal, base,
                                 settings.symbols, settings.semantics.build())
    assert baseline > 0 and graded["score"] > 1
    assert graded["beats_reference"] and graded["margin"] > 0
    assert graded["proposals"][0]["equivalent"] is True


def test_loop_accepts_improvement_rejects_duplicates_and_replay_detects_tampering(setup, tmp_path):
    from opulse.canary import CANARY
    settings, base = setup
    proposals = [{"definition": "a ☆ = { a + 1 }"},
                 {"definition": "a ★ = { a + 1 }"},
                 {"definition": "a ♠ = { a ❓ 1 }"}]
    record = tmp_path / "discovery.jsonl"
    report = run(base, settings.symbols, settings.semantics.build(), ["5 + 1", "7 + 1"], [],
                 lambda index, library, problems: proposals[index - 1], 3, record)
    assert report["accepted"] == 1 and (report["initial_value"], report["final_value"]) == (6, 4)
    assert replay(record, base, settings.symbols, settings.semantics.build())["accepted"] == 1
    with pytest.raises(ValueError, match="initial definitions"):
        replay(record, base, settings.symbols, settings.semantics.build(), ["a ☆ = { a }"])
    rows = [json.loads(line) for line in record.read_text().splitlines()]
    assert all(row["meta"]["canary"] == CANARY for row in rows)
    from opulse.discovery.loop import _digest

    assert all(row["hash"] == _digest({key: value for key, value in row.items()
                                       if key not in ("hash", "meta")}) for row in rows)
    record.write_text("\n".join(json.dumps({key: value for key, value in row.items() if key != "meta"})
                                for row in rows) + "\n")
    assert replay(record, base, settings.symbols, settings.semantics.build())["accepted"] == 1
    assert rows[1]["shorter_problems"] == [1, 2]
    assert rows[2]["reason"] == "no improvement"
    assert not rows[3]["accepted"]
    assert "no operator" in rows[3]["reason"]
    record.write_text("\n".join(json.dumps(row) for row in rows[:-1]) + "\n")
    with pytest.raises(ValueError, match="missing or extra rounds"):
        replay(record, base, settings.symbols, settings.semantics.build())
    rows[1]["after"] = 0
    record.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    with pytest.raises(ValueError, match="round 1"):
        replay(record, base, settings.symbols, settings.semantics.build())


def test_loop_replacement_needs_equivalence_before_size_or_cost(setup, tmp_path):
    settings, base = setup
    original = ["a ☆ = { (a + 0) + 0 }"]
    proposals = [{"definition": "a ☆ = { a + 0 }", "replaces": "☆"},
                 {"definition": "a ☆ = { a + 1 }", "replaces": "☆"}]
    for metric in ("size", "cost"):
        record = tmp_path / f"{metric}.jsonl"
        report = run(base, settings.symbols, settings.semantics.build(), ["5 + 0"], original,
                     lambda index, library, problems: proposals[index - 1], 2, record,
                     metric=metric, target="☆", inputs=[(-2,), (0,), (2,)])
        assert report["accepted"] == 1
        rows = [json.loads(line) for line in record.read_text().splitlines()]
        assert rows[1]["verdict"]["status"] == "proved"
        assert rows[1]["shorter_problems"] == [1]
        assert rows[2]["verdict"]["status"] == "refuted"
        assert not rows[2]["accepted"]
        assert replay(record, base, settings.symbols, settings.semantics.build())["accepted"] == 1


def test_loop_records_proposer_errors(setup, tmp_path):
    settings, base = setup
    record = tmp_path / "error.jsonl"
    report = run(base, settings.symbols, settings.semantics.build(), ["5 + 1"], [],
                 lambda index, library, problems: {"definition": "", "proposer": "endpoint",
                                                   "error": "HTTP 503"}, 1, record)
    assert report["accepted"] == 0
    row = json.loads(record.read_text().splitlines()[1])
    assert row["proposer_error"] == "HTTP 503"
    assert replay(record, base, settings.symbols, settings.semantics.build())["accepted"] == 0
