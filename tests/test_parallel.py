import json
import random

import pytest

from opulse.cli.main import main
from opulse.cli.operators import DEFAULT_CONFIG
from opulse.config import Settings
from opulse.core.registry import OperatorRegistry
from opulse.core.semantics import NAN
from opulse.expression.dataset import ExpressionDataset
from opulse.expression.nodes import Call, Number, literal_form
from opulse.runtime import PythonRuntime


def _expressions(operators, out, seed=17, workers=None, cot=False):
    args = ["expressions", "--operators", str(operators), "--out", str(out),
            "--count", "40", "--seed", str(seed)]
    if workers is not None:
        args += ["--workers", str(workers), "--block-size", "7"]
    if cot:
        args += ["--cot", "en", "--cot-depth", "1"]
    assert main(args) == 0
    return out.read_bytes()


@pytest.mark.parametrize("cot", [False, True])
def test_worker_count_does_not_change_bytes_or_ids(tmp_path, operators, cot):
    one = _expressions(operators, tmp_path / "one.jsonl", workers=1, cot=cot)
    three = _expressions(operators, tmp_path / "three.jsonl", workers=3, cot=cot)
    assert one == three
    assert [json.loads(line)["id"] for line in one.splitlines()] == list(range(40))


def test_block_seed_reproducibility(tmp_path, operators):
    first = _expressions(operators, tmp_path / "first.jsonl", seed=17, workers=3)
    again = _expressions(operators, tmp_path / "again.jsonl", seed=17, workers=1)
    changed = _expressions(operators, tmp_path / "changed.jsonl", seed=18, workers=1)
    assert first == again
    assert first != changed


def test_no_workers_preserves_legacy_stream(tmp_path, operators):
    seed = 17
    actual = _expressions(operators, tmp_path / "legacy.jsonl", seed=seed)
    settings = Settings.load(DEFAULT_CONFIG)
    registry = OperatorRegistry.from_jsonl(operators)
    dataset = ExpressionDataset(settings, registry, PythonRuntime(registry, settings.semantics.build()),
                                random.Random(seed), seed=seed)
    expected = "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in dataset.records(40))
    assert actual == expected.encode("utf-8")


@pytest.mark.parametrize("depth,known_layers", [(None, 0), (1, 0), (None, 1)])
def test_step_counter_matches_reducer(operators, depth, known_layers):
    settings = Settings.load(DEFAULT_CONFIG)
    registry = OperatorRegistry.from_jsonl(operators)
    dataset = ExpressionDataset(settings, registry, PythonRuntime(registry, settings.semantics.build()),
                                random.Random(11), cot="en", cot_depth=depth,
                                cot_known_layers=known_layers, seed=11)
    dataset.reducer.max_steps = 8
    truncated = complete = 0
    while truncated + complete < 50:
        tree = dataset.generator.tree(dataset.pool, atoms="number")
        if not isinstance(tree, Call):
            continue
        tree = literal_form(tree, registry)
        count = dataset.step_counter.count(tree)
        trace = dataset.reducer.reduce(tree)
        if trace.truncated:
            truncated += 1
            assert count > dataset.reducer.max_steps
            assert len(trace.steps) == dataset.reducer.max_steps
        else:
            complete += 1
            assert count == len(trace.steps)
            assert count <= dataset.reducer.max_steps
    short = Call(registry.find("+", 2), (Number(1), Number(2)))
    short_trace = dataset.reducer.reduce(short)
    assert not short_trace.truncated
    assert dataset.step_counter.count(short) == len(short_trace.steps)
    assert truncated > 0


def test_rejected_records_do_not_build_traces(monkeypatch, operators):
    settings = Settings.load(DEFAULT_CONFIG)
    registry = OperatorRegistry.from_jsonl(operators)
    runtime = PythonRuntime(registry, settings.semantics.build())
    dataset = ExpressionDataset(settings, registry, runtime, random.Random(1), cot="en",
                                max_attempts_per_record=1)

    def unexpected_reduce(_tree):
        raise AssertionError("reducer was called for a rejected record")

    monkeypatch.setattr(dataset.reducer, "reduce", unexpected_reduce)
    undefined = Call(registry.find("/", 2), (Number(1), Number(0)))
    monkeypatch.setattr(dataset.generator, "tree", lambda *_args, **_kwargs: undefined)
    with pytest.raises(RuntimeError, match="undefined"):
        list(dataset.records(1))

    candidates = (Call(op, (Number(1),) * op.n_ary) for op in registry if op.definition)
    over_limit = next(tree for tree in candidates
                      if dataset.evaluator.evaluate(tree).value is not NAN and dataset.step_counter.count(tree) > 3)
    dataset.reducer.max_steps = 3
    monkeypatch.setattr(dataset.generator, "tree", lambda *_args, **_kwargs: over_limit)
    with pytest.raises(RuntimeError, match="solution over the step limit"):
        list(dataset.records(1))
