"""Behavioural deduplication and interestingness scores (opulse.generation.interest)."""

import json
from dataclasses import replace

import pytest
import yaml
from conftest import INITIAL_OPERATORS

from opulse.cli.main import main
from opulse.config import InterestSettings, Settings, Symbols, stable_dict
from opulse.core import BRANCH, SIMPLE, Operator, OperatorRegistry
from opulse.definition.codegen import compile_definition, registry_resolver
from opulse.definition.parser import DefinitionParser
from opulse.generation import interest
from opulse.generation.interest import (
    IDENTITY,
    NEGATION,
    SWAP,
    Scorer,
    detect_regularities,
    duplicate_rate,
    featured_operators,
    score_registry,
)
from opulse.runtime import PythonRuntime


def define(registry, text, symbol, n_ary, position=None, kind=SIMPLE):
    operator = Operator(func_id=f"h{len(registry)}", symbol=symbol, n_ary=n_ary, unary_position=position,
                        definition=text, definition_type=kind)
    parser = DefinitionParser(Symbols(), registry)
    code = compile_definition(parser.parse(text), operator.func_id, registry_resolver(registry, operator))
    operator.op_compute_func, operator.op_count_func = code.compute, code.count
    operator.dependencies = list(code.dependencies)
    operator.recursive_layer = registry.recursive_layer_of(operator)
    operator.id = len(registry) + 1
    registry.add(operator)
    return operator


@pytest.fixture
def world():
    registry = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
    runtime = PythonRuntime(registry, Settings().semantics.build())

    def add(text, symbol, n_ary, position=None, kind=SIMPLE):
        op = define(registry, text, symbol, n_ary, position, kind)
        runtime.load(op)
        return op

    return registry, runtime, add


def regularities(op, runtime, settings=None):
    settings = settings or InterestSettings()
    scorer = Scorer(settings, runtime.compute)
    found = detect_regularities(op, runtime.compute(op), scorer.fp, settings)
    found.pop("_applicable")
    return found


# ------------------------------------------------------------------ deduplication
def test_dedup_catches_duplicates_swaps_and_negations(world):
    registry, runtime, add = world
    base = add("a ⊕ b = { (a * 2) - b }", "⊕", 2)
    same = add("a ⊗ b = { (a + a) - b }", "⊗", 2)
    swapped = add("a ⊘ b = { (b * 2) - a }", "⊘", 2)
    negated = add("a ⊖ b = { b - (a * 2) }", "⊖", 2)
    other = add("a ⊙ b = { (a * 3) - b }", "⊙", 2)
    scorer = Scorer(InterestSettings(), runtime.compute)
    for op in registry:
        if op.definition is None:
            scorer.add(op)
    assert scorer.duplicate(base) is None
    scorer.add(base)
    assert scorer.duplicate(same) == (IDENTITY, "⊕")
    assert scorer.duplicate(swapped) == (SWAP, "⊕")
    assert scorer.duplicate(negated) == (NEGATION, "⊕")
    assert scorer.duplicate(other) is None
    assert scorer.novelty(same)[0] == 0.0 and scorer.novelty(other)[0] > 0


def test_dedup_catches_an_atom_rewritten(world):
    registry, runtime, add = world
    plus = add("a ⊛ b = { (b + a) * 1 }", "⊛", 2)
    scorer = Scorer(InterestSettings(), runtime.compute)
    for op in registry:
        if op.definition is None:
            scorer.add(op)
    assert scorer.duplicate(plus) == (IDENTITY, "+")


def test_duplicate_rate_counts_later_copies(world):
    registry, _, add = world
    add("a ⊕ b = { (a * 2) - b }", "⊕", 2)
    add("a ⊘ b = { (b * 2) - a }", "⊘", 2)
    add("a ⊙ b = { (a * 3) - b }", "⊙", 2)
    assert duplicate_rate(registry, Settings()) == (1, 3)


def test_probe_grid_is_closed_under_negation_and_capped():
    fp = interest.Fingerprinter(InterestSettings())
    for arity in (1, 2, 3, 4, 5):
        columns, points = fp.grid(("int",) * arity)
        assert len(points) <= InterestSettings().max_probe_points
        for column in columns:
            assert set(column) == {-v for v in column} and 0 in column
            assert len(column) < 5 or max(column) == 100  # spread over the whole range
    columns, _ = fp.grid(("str", "int"))
    assert set(("", "a", "b", "ab", "ba", "aab", "Ana", "Bo")) <= set(columns[0])


def test_high_arity_grid_varies_every_integer_argument_without_false_duplicate():
    settings = InterestSettings()
    fp = interest.Fingerprinter(settings)
    types = ("int",) * 7
    _, points = fp.grid(types)
    assert len(points) <= settings.max_probe_points
    assert all(any(point[i] > 0 for point in points) and
               any(point[i] < 0 for point in points) for i in range(7))
    for _, _, index, _, _ in fp.transforms(types):
        assert len(index) == len(points)
    first = Operator("first", "⊕", 7, definition="first", op_compute_func="stub", op_count_func="stub")
    second = Operator("second", "⊗", 7, definition="second", op_compute_func="stub", op_count_func="stub")
    scorer = Scorer(settings, lambda op: (lambda *args: sum(args) + (args[0] if op is second else 0)))
    scorer.add(first)
    assert scorer.duplicate(second) is None


def test_high_arity_probe_cap_rejected_before_scoring():
    settings = InterestSettings(probe_ints=(-2, -1, 1, 2), max_probe_points=8)
    operator = Operator("demo", "⊕", 8, definition="demo", op_compute_func="stub", op_count_func="stub")
    with pytest.raises(ValueError, match="max_probe_points"):
        Scorer(settings, lambda _: lambda *args: sum(args)).score(operator)


# ------------------------------------------------------------------ components
def test_symmetry_monotonicity_and_sign(world):
    _, runtime, add = world
    sym = add("a ⊛ b = { (a * b) + (a + b) }", "⊛", 2)
    assert set(regularities(sym, runtime)) >= {"symmetric"}
    triple = add("⊞ a = { a * 3 }", "⊞", 1, "prefix")
    found = regularities(triple, runtime)
    assert found["odd"]["status"] == "table" and "even" not in found
    assert found["monotone"]["positions"] == [[0, "increasing"]]
    assert found["fixed_points"]["values"] == [0]
    square = add("⊟ a = { a * a }", "⊟", 1, "prefix")
    found = regularities(square, runtime)
    assert "even" in found and "odd" not in found and "monotone" not in found


def test_periodicity(world):
    _, runtime, add = world
    op = add("⊠ a = { (a * a) % 3 }", "⊠", 1, "prefix")
    found = regularities(op, runtime)
    assert found["periodic"]["positions"] == [[0, 3]]
    assert "monotone" not in found


def test_fixed_points_idempotence_and_involution(world):
    _, runtime, add = world
    op = add("⊡ a = { (a * a) - (a * 2) }", "⊡", 1, "prefix")
    assert regularities(op, runtime)["fixed_points"]["values"] == [0, 3]
    absolute = add("⊚ a = { a, if a >= 0; - a, else }", "⊚", 1, "prefix", BRANCH)
    found = regularities(absolute, runtime)
    assert "idempotent" in found and "even" in found and "involution" not in found
    mirror = add("⊜ a = { 7 - a }", "⊜", 1, "prefix")
    found = regularities(mirror, runtime)
    assert "involution" in found and "idempotent" not in found
    assert found["monotone"]["positions"] == [[0, "decreasing"]]


def test_solver_proves_and_refutes_table_regularities(world):
    registry, _, add = world
    add("a ⊛ b = { (a * b) + (a + b) }", "⊛", 2)
    add("⊞ a = { a * 3 }", "⊞", 1, "prefix")
    add("⊜ a = { 7 - a }", "⊜", 1, "prefix")
    records = score_registry(registry, Settings.from_dict({"interest": {"solver_timeout_ms": 5000}}), solver=True)
    by_symbol = {registry.get(fid).symbol: r for fid, r in records.items()}
    assert by_symbol["⊛"]["regularities"]["symmetric"]["status"] == "proved"
    assert by_symbol["⊞"]["regularities"]["monotone"]["status"] == "proved"
    # 7 - a leaves the value domain for a near -B, so f(f(a)) is NaN there: not an involution.
    assert by_symbol["⊜"]["regularities"]["involution"]["status"] == "refuted"
    plain = score_registry(registry, Settings())
    held = lambda r: sum(i["status"] != "refuted" for i in r["regularities"].values())
    assert held(by_symbol["⊜"]) == held(plain["h" + str(len(registry) - 1)]) - 1


def test_novelty_is_the_distance_to_the_nearest_operator(world):
    _, runtime, add = world
    triple = add("⊞ a = { a * 3 }", "⊞", 1, "prefix")
    partly = add("⊠ a = { a * 3, if a >= 50; a, else }", "⊠", 1, "prefix", BRANCH)
    scorer = Scorer(InterestSettings(), runtime.compute)
    scorer.add(triple)
    # 25 probes; the two agree at 0 and at the four probes >= 50.
    distance, nearest, _ = scorer.novelty(partly)
    assert distance == pytest.approx(20 / 25) and nearest == "⊞"
    lonely = Scorer(InterestSettings(), runtime.compute)
    assert lonely.novelty(partly) == (1.0, None, None)


def test_non_degeneracy_and_compression(world):
    _, runtime, add = world
    constant = add("⊝ a = { (a - a) + 5 }", "⊝", 1, "prefix")
    triple = add("⊞ a = { a * 3 }", "⊞", 1, "prefix")
    partial = add("⊗ a = { 100 / a }", "⊗", 1, "prefix")
    scorer = Scorer(InterestSettings(), runtime.compute)
    flat, varied, holes = (scorer.score(op) for op in (constant, triple, partial))
    assert flat["defined_share"] == 1.0 and flat["entropy_bits"] == 0.0 and flat["non_degeneracy"] == 0.0
    assert varied["non_degeneracy"] == 1.0  # 25 distinct defined values
    assert holes["defined_share"] == pytest.approx(24 / 25)
    assert flat["compression"] < varied["compression"]
    assert flat["table_bytes"] < varied["table_bytes"]


def test_reuse_counts_later_callers(world):
    registry, _, add = world
    add("⊞ a = { a * 3 }", "⊞", 1, "prefix")
    add("a ⊕ b = { (⊞ a) - (⊞ b) }", "⊕", 2)
    add("⊟ a = { (⊞ a) + 1 }", "⊟", 1, "prefix")
    records = score_registry(registry, Settings())
    by_symbol = {registry.get(fid).symbol: r for fid, r in records.items()}
    assert by_symbol["⊞"]["callers"] == 2 and by_symbol["⊞"]["reuse"] == pytest.approx(2 / 3)
    assert by_symbol["⊟"]["callers"] == 0 and by_symbol["⊟"]["reuse"] == 0.0


def test_total_is_the_weighted_mean(world):
    registry, _, add = world
    add("⊞ a = { a * 3 }", "⊞", 1, "prefix")
    weights = {"novelty": 2.0, "regularity": 0.0, "reuse": 1.0, "non_degeneracy": 1.0, "compression": 0.0}
    settings = replace(Settings(), interest=InterestSettings(weights=weights))
    (record,) = score_registry(registry, settings).values()
    expected = (2 * record["novelty"] + record["reuse"] + record["non_degeneracy"]) / 4
    assert record["score"] == pytest.approx(expected, abs=1e-6)


# ------------------------------------------------------------------ settings and runs
def test_settings_are_opt_in_and_validated():
    assert not Settings().interest.enabled
    assert "interest" not in stable_dict(Settings())
    loaded = Settings.from_dict({"interest": {"dedup": True, "weights": {"reuse": 0}, "probe_ints": [1, 0, -1]}})
    assert loaded.interest.enabled and loaded.interest.weights["reuse"] == 0.0
    assert loaded.interest.weights["novelty"] == 1.0 and loaded.interest.probe_ints == (1, 0, -1)
    assert "interest" in stable_dict(loaded)
    for bad in ({"selection": "top"}, {"pool": 0}, {"weights": {"beauty": 1}}, {"probe_ints": [1, 2, 3]},
                {"weights": dict.fromkeys(("novelty", "regularity", "reuse", "non_degeneracy", "compression"), 0)}):
        with pytest.raises(ValueError):
            Settings.from_dict({"interest": bad})


def _run(tmp_path, name, interest_settings, seed=5):
    config = tmp_path / f"{name}.yaml"
    config.write_text(yaml.safe_dump({"interest": interest_settings}))
    out = tmp_path / f"{name}.jsonl"
    assert main(["operators", "--config", str(config), "--out", str(out), "--layers", "6", "4", "2",
                 "--seed", str(seed)]) == 0
    return out


def test_selection_runs_are_deterministic_and_duplicate_free(tmp_path, capsys):
    first = _run(tmp_path, "a", {"dedup": True, "selection": "sample", "pool": 3})
    second = _run(tmp_path, "b", {"dedup": True, "selection": "sample", "pool": 3})
    assert first.read_bytes() == second.read_bytes()
    summary = json.loads(capsys.readouterr().out.split("\n}\n")[0] + "\n}")
    assert summary["rejected"]["not selected by interest"] == 2 * 12
    registry = OperatorRegistry.from_jsonl(first)
    assert duplicate_rate(registry, Settings())[0] == 0
    rows = [json.loads(line) for line in first.read_text().splitlines()]
    scored = [row for row in rows if row.get("definition")]
    assert len(scored) == 12 and all(row["interest"]["probes"] for row in scored)
    assert all("interest" not in row for row in rows if not row.get("definition"))


def test_scores_are_deterministic(operators):
    registry = OperatorRegistry.from_jsonl(operators)
    assert score_registry(registry, Settings()) == score_registry(OperatorRegistry.from_jsonl(operators), Settings())


def test_featured_operators(operators):
    registry = OperatorRegistry.from_jsonl(operators)
    records = score_registry(registry, Settings())
    chosen = featured_operators(registry, Settings(), k=5, per_layer=2, records=records)
    assert len(chosen) == 5
    scores = [record["score"] for _, record in chosen]
    assert scores == sorted(scores, reverse=True)
    layers = [op.recursive_layer for op, _ in chosen]
    assert all(layers.count(layer) <= 2 for layer in layers)
    best = max(records.values(), key=lambda r: r["score"])
    assert featured_operators(registry, Settings(), k=1, records=records)[0][1] is best


def test_interest_command(operators, tmp_path, capsys):
    out = tmp_path / "scored.jsonl"
    assert main(["interest", "--operators", str(operators), "--out", str(out), "--top", "3", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["summary"]["operators"] == 36 and len(report["top"]) == 3
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert sum("interest" in row for row in rows) == 36
    assert main(["interest", "--operators", str(operators), "--top", "2"]) == 0
    assert "behavioural duplicates" in capsys.readouterr().out
