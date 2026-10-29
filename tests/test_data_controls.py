"""Generation controls change measured records, including in typed worlds."""

import json
from collections import Counter

import pytest
import yaml

from opulse.cli.main import main
from opulse.core.registry import OperatorRegistry
from opulse.expression.generator import OperatorPool

WORLDS = ("integer", "clock", "successor", "bits", "strings", "lists")


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


@pytest.fixture(scope="module", params=WORLDS)
def world(request, tmp_path_factory):
    name = request.param
    directory = tmp_path_factory.mktemp("controls_" + name)
    ops = directory / "ops.jsonl"
    assert main(["operators", "--preset", name, "--out", str(ops), "--layers", "8",
                 "--seed", "4", "--no-branches", "--no-recursion"]) == 0
    config = directory / "config.yaml"
    config.write_text(yaml.safe_dump({"preset": name}), encoding="utf-8")
    return name, ops, config, directory


def expressions(world, label, *options, count=120, config=None):
    _, ops, default_config, directory = world
    output = directory / f"{label}.jsonl"
    assert main(["expressions", "--operators", str(ops), "--config", str(config or default_config),
                 "--out", str(output), "--count", str(count), "--seed", "3", *options]) == 0
    return rows(output)


def test_operator_frequency_changes_every_world_and_concentrates_top_rank(world):
    name, ops, _, _ = world
    pool = OperatorPool.from_registry(OperatorRegistry.from_jsonl(ops))
    groups = pool.frequency_ranking(seed=0)
    kind = max(groups, key=lambda key: len(groups[key]))
    assert len(groups[kind]) >= 2, name
    top = groups[kind][0]
    members = set(groups[kind])
    uniform = expressions(world, "uniform", "--operator-frequency", "uniform", count=240)
    zipf = expressions(world, "zipf", "--operator-frequency", "zipf:2", count=240)
    assert [r["tree"] for r in uniform] != [r["tree"] for r in zipf]
    assert {r["provenance"]["operator_frequency"] for r in zipf} == {"zipf:2"}

    def share(samples):
        uses = Counter(fid for row in samples for fid in row["defined_operators"] if fid in members)
        return uses[top] / sum(uses.values())

    assert share(zipf) > share(uniform) + 0.08


def test_frequency_seed_changes_which_operator_is_common(world):
    _, ops, _, _ = world
    pool = OperatorPool.from_registry(OperatorRegistry.from_jsonl(ops))
    groups = pool.frequency_ranking(seed=0)
    kind = max(groups, key=lambda key: len(groups[key]))
    first = groups[kind][0]
    other_seed = next(seed for seed in range(1, 30)
                      if pool.frequency_ranking(seed)[kind][0] != first)
    second = pool.frequency_ranking(other_seed)[kind][0]
    first_rows = expressions(world, "rank_first", "--operator-frequency", "zipf:3",
                             "--frequency-seed", "0", count=180)
    second_rows = expressions(world, "rank_second", "--operator-frequency", "zipf:3",
                              "--frequency-seed", str(other_seed), count=180)
    first_counts = Counter(fid for row in first_rows for fid in row["defined_operators"])
    second_counts = Counter(fid for row in second_rows for fid in row["defined_operators"])
    assert first_counts[first] > first_counts[second]
    assert second_counts[second] > second_counts[first]


def test_expression_depth_control_changes_every_world(world):
    name, _, _, directory = world
    depths = []
    for limit in (1, 4):
        config = directory / f"depth_{limit}.yaml"
        config.write_text(yaml.safe_dump({"preset": name, "expressions": {"max_depth": limit}}),
                          encoding="utf-8")
        samples = expressions(world, f"depth_{limit}", config=config, count=100)
        depths.append([row["tree"] for row in samples])
    from opulse.cli.data_summary import _depth

    assert depths[0] != depths[1]
    assert sum(map(_depth, depths[1])) / 100 > sum(map(_depth, depths[0])) / 100


def test_type_weights_change_application_mix_in_every_world(world):
    name, _, _, directory = world
    config = directory / "postfix_weight.yaml"
    config.write_text(yaml.safe_dump({"preset": name, "expressions": {"type_weights":
                             {"binary": 0.01, "unary_prefix": 0.01,
                              "unary_postfix": 5.0, "atom": 0.1}}}), encoding="utf-8")
    baseline = expressions(world, "type_baseline", count=100)
    weighted = expressions(world, "type_postfix", config=config, count=100)

    def postfix_calls(node):
        count = node.get("type") == "unary" and node.get("position") == "postfix"
        return int(count) + sum(postfix_calls(node[key]) for key in
                                ("left_expr", "right_expr", "unary_expr") if key in node) + sum(
                                    postfix_calls(child) for child in node.get("args", ()))

    assert [r["tree"] for r in baseline] != [r["tree"] for r in weighted]
    assert sum(postfix_calls(r["tree"]) for r in weighted) > sum(
        postfix_calls(r["tree"]) for r in baseline)


def test_numeric_sampling_range_changes_literals(world):
    name = world[0]
    if name in ("strings", "lists"):
        pytest.skip("typed atoms have their own value samplers")
    _, _, _, directory = world

    def values(node):
        found = [node["value"]] if node.get("type") == "numeric_atoms" else []
        for key in ("left_expr", "right_expr", "unary_expr"):
            if key in node:
                found.extend(values(node[key]))
        for child in node.get("args", ()):
            found.extend(values(child))
        return found

    samples = []
    for low, high in ((0, 3), (40, 43)):
        config = directory / f"range_{low}.yaml"
        config.write_text(yaml.safe_dump({"preset": name, "expressions":
                                         {"value_min": low, "value_max": high}}), encoding="utf-8")
        samples.append(expressions(world, f"range_{low}", config=config, count=50))
    first = [v for row in samples[0] for v in values(row["tree"]) if isinstance(v, int)]
    second = [v for row in samples[1] for v in values(row["tree"]) if isinstance(v, int)]
    assert first and second and max(first) < min(second)


def test_answer_share_control_and_summary(world, capsys):
    if world[0] != "integer":
        pytest.skip("integer answer distribution")
    base = expressions(world, "answers_base", count=80)
    limited = expressions(world, "answers_limited", "--max-answer-share", "0.1", count=80)
    assert [r["tree"] for r in base] != [r["tree"] for r in limited]
    counts = Counter(json.dumps(r["result"]) for r in limited)
    assert max(counts.values()) <= 8
    output = capsys.readouterr().out
    assert "top answers" in output and "NaN" in output and "Depth histogram" in output


def test_frequency_rejects_a_world_without_competing_defined_operators(tmp_path):
    ops = tmp_path / "ops.jsonl"
    assert main(["operators", "--out", str(ops), "--layers", "0", "--seed", "1"]) == 0
    with pytest.raises(ValueError, match="needs at least two defined operators"):
        main(["expressions", "--operators", str(ops), "--out", str(tmp_path / "x.jsonl"),
              "--count", "1", "--operator-frequency", "zipf:1"])


def test_benchmark_depth_and_frequency_controls(world, capsys):
    _, ops, config, directory = world

    def build(label, *options):
        path = directory / f"bench_{label}.jsonl"
        assert main(["bench", "build", "--operators", str(ops), "--config", str(config),
                     "--out", str(path), "--count", "12", "--seed", "3",
                     "--max-answer-share", "1", *options]) == 0
        return rows(path)

    shallow = build("shallow", "--max-depth", "1")
    deep = build("deep", "--max-depth", "4")
    assert sum(row["axes"]["expression_depth"] for row in deep) > sum(
        row["axes"]["expression_depth"] for row in shallow)
    uniform = build("uniform", "--operator-frequency", "uniform")
    zipf = build("zipf", "--operator-frequency", "zipf:2")
    assert [r["expression"] for r in uniform] != [r["expression"] for r in zipf]
    assert "Data summary" in capsys.readouterr().out


def test_nan_filter_changes_nan_share_in_integer_world(world):
    if world[0] != "integer":
        pytest.skip("integer NaN source")
    filtered = expressions(world, "nan_filtered", count=100)
    kept = expressions(world, "nan_kept", "--keep-undefined", count=100)
    assert not any(row["undefined"] for row in filtered)
    assert sum(row["undefined"] for row in kept) > 0
    assert [row["tree"] for row in filtered] != [row["tree"] for row in kept]


def test_benchmark_notation_changes_prompts_but_preserves_answers(world):
    _, ops, config, directory = world
    output = []
    for naming in ("symbols", "pseudo"):
        path = directory / f"naming_{naming}.jsonl"
        assert main(["bench", "build", "--operators", str(ops), "--config", str(config),
                     "--out", str(path), "--count", "8", "--seed", "4",
                     "--max-answer-share", "1", "--naming", naming]) == 0
        output.append(rows(path))
    assert [row["prompt"] for row in output[0]] != [row["prompt"] for row in output[1]]
    assert [row["answer"] for row in output[0]] == [row["answer"] for row in output[1]]


def test_corpus_expressions_per_document_changes_line_count(world):
    _, ops, config, directory = world
    lengths = []
    for count in (2, 4):
        path = directory / f"corpus_{count}"
        assert main(["corpus", "--operators", str(ops), "--config", str(config),
                     "--out", str(path), "--documents", "3", "--seed", "2", "--no-dedup",
                     "--mix", "definitions=0,values=1,derivations=0,descriptions=0",
                     "--expressions-per-document", str(count)]) == 0
        records = [row for shard in (path / "train").glob("*.jsonl") for row in rows(shard)]
        lengths.append([len(row["text"].splitlines()) for row in records])
    assert lengths == [[2] * 3, [4] * 3]


def test_typed_world_rejects_inapplicable_atom_weights(world):
    if world[0] not in ("strings", "lists"):
        pytest.skip("numeric trees use atom weights")
    name, _, _, directory = world
    config = directory / "inapplicable.yaml"
    config.write_text(yaml.safe_dump({"preset": name, "expressions":
                                     {"atom_weights": {"variable": 0.1, "number": 0.9}}}),
                      encoding="utf-8")
    with pytest.raises(ValueError, match="cannot change this world"):
        expressions(world, "inapplicable", config=config, count=1)


def test_cli_rejects_controls_without_their_target_data(world):
    if world[0] != "integer":
        pytest.skip("CLI validation is independent of world")
    _, ops, config, directory = world
    with pytest.raises(SystemExit, match="require --cot"):
        main(["expressions", "--operators", str(ops), "--config", str(config),
              "--out", str(directory / "no_cot.jsonl"), "--count", "1", "--cot-depth", "1"])
    with pytest.raises(SystemExit, match="requires --context full"):
        main(["bench", "build", "--operators", str(ops), "--config", str(config),
              "--out", str(directory / "no_context.jsonl"), "--count", "1",
              "--context", "none", "--distractors", "1"])
    with pytest.raises(SystemExit, match="needs values"):
        main(["corpus", "--operators", str(ops), "--config", str(config),
              "--out", str(directory / "no_values"), "--documents", "1",
              "--mix", "definitions=1,values=0,derivations=0,descriptions=0",
              "--expressions-per-document", "2"])


def test_curriculum_target_band_changes_selected_difficulty(tmp_path):
    selected = []
    for label, low, high in (("hard", "0.2", "0.4"), ("easy", "0.7", "0.9")):
        log = tmp_path / f"{label}.jsonl"
        assert main(["env", "curriculum", "--simulate", "--episodes", "60", "--seed", "1",
                     "--low", low, "--high", high, "--log", str(log)]) == 0
        selected.append([row["cell"] for row in rows(log)])
    assert selected[0] != selected[1]
    difficulty = lambda cells: sum(cell["definitions_needed"] + cell["operator_layer"] +
                                   cell["expression_depth"] + cell["branches"] +
                                   cell["recursion_bound"] for cell in cells) / len(cells)
    assert difficulty(selected[0]) > difficulty(selected[1])
