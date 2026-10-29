"""CLI task files keep grading semantics through each evaluation export."""

import importlib.util
import json

import pytest

from opulse.bench.families import common
from opulse.bench.reward import compute_score
from opulse.bench.score import score_response
from opulse.cli.main import main
from opulse.config import Symbols
from opulse.integrations.common import grading_record, read_tasks


FAMILIES = ("compute", "hole", "contrast", "equivalence", "simplify", "law", "edit",
            "invent", "handbook", "faster", "refactor", "induce")
ADAPTERS = ("verl_jsonl", "verl_parquet", "media_jsonl", "trl", "lm_eval", "inspect")


@pytest.fixture(scope="module")
def operators(tmp_path_factory):
    path = tmp_path_factory.mktemp("workflow_ops") / "operators.jsonl"
    assert main(["operators", "--out", str(path), "--layers", "10", "6", "3", "--seed", "4"]) == 0
    return path


@pytest.fixture(scope="module", params=FAMILIES)
def task_file(request, operators, tmp_path_factory):
    family = request.param
    path = tmp_path_factory.mktemp(f"workflow_{family}") / "tasks.jsonl"
    options = ["--handbook-size", "4", "--handbook-needed", "2"] if family == "handbook" else []
    assert main(["bench", "build", "--operators", str(operators), "--out", str(path),
                 "--family", family, "--count", "1", "--seed", "4", "--max-depth", "2", *options]) == 0
    records = read_tasks(path)
    assert records and all(record["family"] == family for record in records)
    return path, records[0]


def unchanged_definition(task):
    """Put the displayed definition under the requested name without changing its body."""
    if task["family"] == "refactor":
        base, semantics = common.base_from_prompt(task["prompt"])
        ops = common.text_registry(task["definitions"], base, Symbols(), semantics)
        names = set(task["axes"]["original_symbols"])
        return "Answer: " + " || ".join(text for text in task["definitions"]
                                         if ops.parser.parse(text).lhs.symbol in names)
    base, semantics = common.base_from_prompt(task["prompt"])
    ops = common.text_registry(task["definitions"] + [task["answer_text"]], base, Symbols(), semantics)
    original = ops.parser.parse(task["definitions"][-1])
    wanted = ops.parser.parse(task["answer_text"]).lhs.symbol
    return "Answer: " + common.render(common.rename(original, wanted), Symbols())


def answers(task):
    replies = {"reference": f"Answer: {task['answer_text']}", "wrong": "Answer: definitely invalid"}
    if task["family"] in ("simplify", "faster", "refactor"):
        replies["unchanged"] = unchanged_definition(task)
    else:
        replies["unchanged"] = "Answer: still invalid"
    return replies


def test_compact_inspect_record_matches_direct_grader(task_file):
    _, task = task_file
    exported = grading_record(task)
    for response in answers(task).values():
        assert score_response(exported, response) == score_response(task, response)


@pytest.mark.parametrize("adapter", ADAPTERS)
def test_cli_build_reload_export_and_grade(task_file, operators, tmp_path, adapter):
    path, task = task_file
    family = task["family"]
    replies = answers(task)
    direct = {name: score_response(task, response) for name, response in replies.items()}
    assert direct["reference"]["correct"], direct["reference"]
    assert not direct["wrong"]["correct"], direct["wrong"]
    assert not direct["unchanged"]["correct"], direct["unchanged"]

    if adapter in ("verl_jsonl", "verl_parquet"):
        if adapter == "verl_parquet":
            pytest.importorskip("pyarrow", reason="Parquet export requires pyarrow")
        out = tmp_path / ("rl.parquet" if adapter == "verl_parquet" else "rl.jsonl")
        assert main(["bench", "export", "--tasks", str(path), "--out", str(out)]) == 0
        if adapter == "verl_parquet":
            import pandas as pd
            row = pd.read_parquet(out).to_dict("records")[0]
        else:
            row = json.loads(out.read_text(encoding="utf-8").splitlines()[0])
        assert row["prompt"][0]["content"] == task["prompt"]
        truth = row["reward_model"]["ground_truth"]
        reward = lambda response: compute_score(row["data_source"], response, truth, row["extra_info"])
    elif adapter == "media_jsonl":
        out = tmp_path / "media.jsonl"
        assert main(["bench", "export", "--tasks", str(path), "--out", str(out), "--media"]) == 0
        row = json.loads(out.read_text(encoding="utf-8").splitlines()[0])
        assert row["messages"][0]["role"] == "user"
        reward = lambda response: float(score_response(row, response)["correct"])
    elif adapter == "trl":
        from examples.trl.bridge import outcome_reward, rows_from_tasks

        row = rows_from_tasks(read_tasks(path))[0]
        reward = lambda response: outcome_reward([row["prompt"]], [response],
                                                  ground_truth=[row["ground_truth"]],
                                                  operators=[row["operators"]], config=[row["config"]])[0]
    elif adapter == "lm_eval":
        out = tmp_path / "lm_eval"
        assert main(["integrations", "lm-eval", "--tasks", str(path), "--out", str(out)]) == 0
        exported = read_tasks(out / "tasks.jsonl")
        assert exported[0]["id"] == task["id"]
        spec = importlib.util.spec_from_file_location(f"workflow_lm_{family}", out / "utils.py")
        hooks = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hooks)
        reward = lambda response: hooks.process_results({"id": task["id"]}, [response])["accuracy"]
    else:
        pytest.importorskip("inspect_ai", reason="Inspect adapter requires inspect_ai")
        from inspect_ai import eval as inspect_eval
        from inspect_ai.model import ModelOutput, get_model
        from opulse.integrations.inspect_eval import bench

        benchmark = bench(tasks=str(path))

        def reward(response):
            model = get_model("mockllm/model", custom_outputs=lambda *args: ModelOutput.from_content(
                model="mockllm", content=response))
            log = inspect_eval(benchmark, model=model, display="none", log_dir=str(tmp_path))[0]
            return float(log.results.scores[0].metrics["accuracy"].value)

    for name, response in replies.items():
        value = reward(response)
        expected = (min(1.0, direct[name].get("score", 1.0)) if direct[name]["correct"] else 0.0)
        if adapter in ("lm_eval", "inspect"):
            expected = float(direct[name]["correct"])
        assert value == pytest.approx(expected), (family, adapter, name, direct[name])
        assert value == (1.0 if name == "reference" else 0.0), (family, adapter, name)


def test_step_export_rewards_match_direct_verdict(operators, tmp_path):
    path = tmp_path / "steps.jsonl"
    assert main(["bench", "build", "--operators", str(operators), "--out", str(path),
                 "--family", "compute", "--format", "steps", "--count", "1", "--seed", "4"]) == 0
    task = read_tasks(path)[0]
    out = tmp_path / "steps_rl.jsonl"
    assert main(["bench", "export", "--tasks", str(path), "--out", str(out),
                 "--operators", str(operators)]) == 0
    row = json.loads(out.read_text(encoding="utf-8").splitlines()[0])
    for response in (f"Answer: {task['answer_text']}", "Answer: definitely invalid"):
        verdict = score_response(task, response)["correct"]
        assert compute_score("opulse", response, row["reward_model"]["ground_truth"],
                             {**row["extra_info"], "reward_mode": "outcome"}) == float(verdict)


def test_induce_example_memorizer_is_refuted(operators, tmp_path):
    path = tmp_path / "induce.jsonl"
    assert main(["bench", "build", "--operators", str(operators), "--out", str(path),
                 "--family", "induce", "--count", "1", "--seed", "1"]) == 0
    task = read_tasks(path)[0]
    assert task["parameter_types"] == ["int", "int"] and task["result_type"] == "int"
    lhs = task["reference_definition"].split(" = ", 1)[0]

    def number(value):
        return "NaN" if value is None else str(value) if value >= 0 else f"- {abs(value)}"

    branches = [f"{number(row['output'])}, if a == {number(row['inputs'][0])} "
                f"and b == {number(row['inputs'][1])}" for row in task["examples"]]
    definition = f"{lhs} = {{ " + "; ".join(branches) + "; 12345, else }"
    predictions = task["answer_text"].splitlines()[:len(task["queries"])]
    verdict = score_response(task, "Answer: " + "\n".join([*predictions, definition]))
    assert verdict["queries_correct"] == len(task["queries"])
    assert verdict["definition_parses"] and verdict["definition_matches_examples"]
    assert verdict["definition_equivalent"] == "refuted with a counterexample"
    assert not verdict["correct"]
