"""Operator frequency: uniform sampling stays as it was; zipf:ALPHA gives a long tail of concepts."""

import json
import random
from collections import Counter

import pytest

from opulse.bench.tasks import BenchBuilder
from opulse.cli.main import main
from opulse.config import Settings
from opulse.core import OperatorRegistry
from opulse.expression.dataset import ExpressionDataset
from opulse.expression.generator import ExpressionGenerator, OperatorPool
from opulse.expression.nodes import Call, defined_operators, from_dict, iter_calls
from opulse.runtime import PythonRuntime


@pytest.fixture(scope="module")
def ops(tmp_path_factory):
    path = tmp_path_factory.mktemp("frequency") / "ops.jsonl"
    assert main(["operators", "--out", str(path), "--layers", "10", "6", "3", "--seed", "4"]) == 0
    return path


def test_uniform_spec_changes_nothing(ops):
    registry = OperatorRegistry.from_jsonl(ops)
    settings = Settings()
    plain = OperatorPool.from_registry(registry)
    uniform = plain.with_frequency("uniform", seed=7)
    assert uniform.weights is None
    first = ExpressionGenerator(settings.expressions, random.Random(5))
    second = ExpressionGenerator(settings.expressions, random.Random(5))
    assert [first.tree(plain, max_depth=4) for _ in range(50)] == [second.tree(uniform, max_depth=4)
                                                                     for _ in range(50)]

    default = [t.to_dict() for t in BenchBuilder(settings, registry, random.Random(3)).tasks("compute", 10)]
    explicit = [t.to_dict() for t in BenchBuilder(settings, registry, random.Random(3), operator_frequency="uniform",
                                                  frequency_seed=11).tasks("compute", 10)]
    assert default == explicit


def test_zipf_weights_cover_the_pool_and_keep_the_defined_mass(ops):
    pool = OperatorPool.from_registry(OperatorRegistry.from_jsonl(ops))
    weighted = pool.with_frequency("zipf:1.5", seed=2)
    assert set(weighted.weights) == {op.func_id for op in pool.all()}
    for ops_of_kind in (pool.binary, pool.prefix, pool.postfix):
        defined = [op for op in ops_of_kind if op.definition is not None]
        assert sum(weighted.weights[op.func_id] for op in defined) == pytest.approx(len(defined))
        assert all(weighted.weights[op.func_id] == 1.0 for op in ops_of_kind if op.definition is None)
    assert pool.with_frequency("zipf:1.5", seed=2).weights == weighted.weights          # seeded
    assert pool.with_frequency("zipf:1.5", seed=3).weights != weighted.weights
    assert all(w == pytest.approx(1.0) for w in pool.with_frequency("zipf:0").weights.values())


def test_zipf_makes_the_top_operator_frequent(ops):
    registry = OperatorRegistry.from_jsonl(ops)
    pool = OperatorPool.from_registry(registry)
    ranking = pool.frequency_ranking(seed=1)["binary"]
    generator = ExpressionGenerator(Settings().expressions, random.Random(0))
    counts = {spec: Counter() for spec in ("uniform", "zipf:1.5")}
    for spec, counter in counts.items():
        weighted = pool.with_frequency(spec, seed=1)
        for _ in range(400):
            counter.update(defined_operators(generator.tree(weighted, max_depth=4)))
    top, median = ranking[0], ranking[len(ranking) // 2]
    zipf = counts["zipf:1.5"]
    assert zipf[top] > 3 * max(zipf[median], 1)
    assert counts["uniform"][top] < 2 * counts["uniform"][median]
    # the number of defined operators per expression stays about the same
    assert abs(sum(zipf.values()) - sum(counts["uniform"].values())) < 0.15 * sum(counts["uniform"].values())


@pytest.mark.parametrize("spec", ["zipf", "zipf:", "zipf:-1", "zipf:abc", "zipf:nan", "zipf:inf", "pareto:2",
                                  "Uniform"])
def test_invalid_specs_raise(ops, spec):
    registry = OperatorRegistry.from_jsonl(ops)
    with pytest.raises(ValueError):
        OperatorPool.from_registry(registry).with_frequency(spec)
    with pytest.raises(ValueError):
        BenchBuilder(Settings(), registry, random.Random(0), operator_frequency=spec)
    with pytest.raises(ValueError):
        ExpressionDataset(Settings(), registry, PythonRuntime(registry), operator_frequency=spec)


def test_bench_tasks_record_the_defined_operators(ops):
    registry = OperatorRegistry.from_jsonl(ops)
    builder = BenchBuilder(Settings(), registry, random.Random(4), operator_frequency="zipf:1.5")
    for task in builder.tasks("compute", 5):
        assert task.axes["defined_operators"]
        assert all(registry.get(fid).definition for fid in task.axes["defined_operators"])


def test_cli_round_trip(ops, tmp_path):
    tasks = tmp_path / "t.jsonl"
    assert main(["bench", "build", "--operators", str(ops), "--out", str(tasks), "--count", "8",
                 "--operator-frequency", "zipf:1.5", "--frequency-seed", "3"]) == 0
    rows = [json.loads(line) for line in tasks.read_text().splitlines()]
    assert all(r["provenance"]["operator_frequency"] == "zipf:1.5" and r["provenance"]["frequency_seed"] == 3
               for r in rows)
    assert all(r["axes"]["defined_operators"] for r in rows)
    responses = tmp_path / "r.jsonl"
    assert main(["bench", "run", "--tasks", str(tasks), "--out", str(responses), "--reference"]) == 0
    summary = tmp_path / "s.json"
    assert main(["bench", "score", "--tasks", str(tasks), "--responses", str(responses), "--out", str(summary)]) == 0
    assert json.loads(summary.read_text())["accuracy"] == 1.0

    expr = tmp_path / "e.jsonl"
    assert main(["expressions", "--operators", str(ops), "--out", str(expr), "--count", "10",
                 "--operator-frequency", "zipf:2", "--frequency-seed", "5"]) == 0
    records = [json.loads(line) for line in expr.read_text().splitlines()]
    assert len(records) == 10
    assert all(r["provenance"]["operator_frequency"] == "zipf:2" and r["provenance"]["frequency_seed"] == 5
               for r in records)
    registry = OperatorRegistry.from_jsonl(ops)
    for record in records:
        tree = from_dict(record["tree"], registry)
        assert isinstance(tree, Call)
        assert record["defined_operators"] == sorted(c.operator.func_id for c in iter_calls(tree)
                                                     if c.operator.definition is not None)
    assert main(["verify", "--operators", str(ops), "--expressions", str(expr)]) == 0
    with pytest.raises(ValueError):
        main(["expressions", "--operators", str(ops), "--out", str(expr), "--count", "1",
              "--operator-frequency", "zipf:x"])
