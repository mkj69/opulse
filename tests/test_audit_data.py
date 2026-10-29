"""Dataset audit statistics and release gates."""

import json

import pytest

from opulse.cli.main import main


def _record(index, answer=None, *, undefined=False, config="config"):
    tree = {"type": "binary", "operator": "+",
            "left_expr": {"type": "numeric_atoms", "value": index, "base": 10},
            "right_expr": {"type": "numeric_atoms", "value": 1, "base": 10}}
    return {"id": index, "expression": f"{index} + 1", "tree": tree,
            "result": answer, "undefined": undefined, "expansion": index + 1,
            "operation_count": 1, "steps": [{"text": "step"}], "cot": "abc" if index == 0 else None,
            "provenance": {"operator_set": "ops", "config": config}}


def _write(path, records):
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records), encoding="utf-8")
    return path


def _run(paths, output, *options):
    status = main(["audit-data", *(str(path) for path in paths), "--out", str(output), *options])
    return status, json.loads(output.read_text(encoding="utf-8"))


@pytest.fixture
def sample(tmp_path):
    records = [_record(i, i) for i in range(6)] + [_record(6, undefined=True)]
    records[5]["result"] = 9
    return _write(tmp_path / "expressions.jsonl", records), records


def test_hand_calculated_statistics_and_default_pass(sample, tmp_path, capsys):
    path, _ = sample
    status, report = _run([path], tmp_path / "audit.json")
    assert status == 0
    assert report["counts"] == {"total": 7, "by_kind": {"expression": 7}}
    assert report["answers"]["undefined_share"] == pytest.approx(1 / 7)
    assert report["answers"]["distinct"] == 6
    assert report["answers"]["top_10"][0] == {"answer": 0, "count": 1}
    assert report["answers"]["most_common_share"] == pytest.approx(1 / 6)
    assert report["answers"]["zero_share"] == pytest.approx(1 / 6)
    assert report["answers"]["equals_expression_number_share"] == pytest.approx(5 / 6)
    assert report["axes"]["expression_depth"]["median"] == 2
    assert report["axes"]["expansion"]["p90"] == pytest.approx(6.4)
    assert report["axes"]["steps"]["histogram"] == {"1": 7}
    assert report["axes"]["cot_length"]["count"] == 1
    assert report["files"][0]["duplicates"]["trees"]["count"] == 0
    assert report["provenance"]["uniform"]
    assert "Quality gates: PASS" in capsys.readouterr().out


@pytest.mark.parametrize(("mutate", "failure"), [
    (lambda rows: rows.append(dict(rows[0])), "duplicate share"),
    (lambda rows: rows[1].update(result=0), "most-common-answer share"),
    (lambda rows: rows[1]["provenance"].update(config="other"), "provenance mixture"),
])
def test_each_single_file_gate_fails_and_can_be_relaxed(sample, tmp_path, mutate, failure):
    _, source = sample
    records = json.loads(json.dumps(source))
    mutate(records)
    path = _write(tmp_path / "changed.jsonl", records)
    status, report = _run([path], tmp_path / "report.json")
    assert status == 1 and failure in report["gates"]["failures"]
    status, report = _run([path], tmp_path / "relaxed.json", "--max-duplicate-share", "1",
                          "--max-most-common-answer-share", "1", "--no-require-uniform-provenance")
    assert status == 0 and report["gates"]["passed"]


def test_cross_file_tree_and_prompt_overlap(sample, tmp_path):
    first, rows = sample
    second = _write(tmp_path / "test.jsonl", [dict(rows[0]), _record(9, 9)])
    status, report = _run([first, second], tmp_path / "report.json")
    assert status == 1 and "cross-file overlap" in report["gates"]["failures"]
    pair = report["overlap"]["pairs"][0]
    assert pair["trees"]["count"] == pair["prompts"]["count"] == 1
    assert pair["trees"]["share"] == 0.5
    assert pair["trees"]["examples"]
    status, _ = _run([first, second], tmp_path / "relaxed.json", "--max-cross-file-overlap", "0.5",
                     "--max-most-common-answer-share", "0.25")
    assert status == 0


def test_benchmark_prompts_and_axes(tmp_path):
    rows = [{"id": f"compute-{i}", "prompt": f"What is {i} + 1?", "expression": f"{i} + 1",
             "answer": i, "axes": {"expression_depth": 2, "definitions_needed": i,
                                      "answer_is_nan": False},
             "provenance": {"operator_set": "ops", "config": "cfg"}} for i in range(6)]
    path = _write(tmp_path / "tasks.jsonl", rows)
    status, report = _run([path], tmp_path / "report.json")
    assert status == 0 and report["counts"]["by_kind"] == {"benchmark": 6}
    assert report["axes"]["definitions_needed"]["median"] == 2.5
    assert "answer_is_nan" not in report["axes"]
    rows[1]["prompt"] = rows[0]["prompt"]
    _write(path, rows)
    status, report = _run([path], tmp_path / "duplicate.json")
    assert status == 1 and report["files"][0]["duplicates"]["prompts"]["count"] == 1


def test_generated_expression_and_benchmark_datasets(tmp_path):
    operators = tmp_path / "ops.jsonl"
    expressions = tmp_path / "expressions.jsonl"
    tasks = tmp_path / "tasks.jsonl"
    aliases = tmp_path / "aliases.jsonl"
    assert main(["operators", "--out", str(operators), "--layers", "6", "3", "--seed", "4"]) == 0
    assert main(["expressions", "--operators", str(operators), "--out", str(expressions),
                 "--count", "6", "--seed", "7"]) == 0
    assert main(["bench", "build", "--operators", str(operators), "--out", str(tasks),
                 "--count", "6", "--seed", "7"]) == 0
    assert main(["bench", "build", "--operators", str(operators), "--out", str(aliases),
                 "--count", "2", "--seed", "7", "--naming", "pseudo"]) == 0
    for path in (expressions, tasks, aliases):
        status, report = _run([path], tmp_path / f"{path.stem}.json", "--operators", str(operators),
                              "--max-duplicate-share", "1", "--max-most-common-answer-share", "1")
        assert status == 0 and report["counts"]["total"] == (2 if path == aliases else 6)
        assert report["operator_coverage"]["defined_total"] == 9
        assert report["operator_coverage"]["used_count"] > 0
        assert report["operator_coverage"]["unparsed_records"] == 0
