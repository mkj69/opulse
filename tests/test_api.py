"""The high level API (opulse.api): grow, evaluate, trace, save/load, tasks, views."""

from __future__ import annotations

import json
import random
from html.parser import HTMLParser

import pytest

import opulse
from opulse.api import World, make_settings
from opulse.cli.main import main
from opulse.core.semantics import NAN
from opulse.verify import Oracle


@pytest.fixture(scope="module")
def world() -> World:
    return World.grow(layers=[12, 6, 3], seed=1)


def test_lazy_exports():
    assert opulse.World is World
    assert "World" in dir(opulse)


def test_grow_is_deterministic_and_matches_the_cli(world, tmp_path):
    again = World.grow(layers=[12, 6, 3], seed=1)
    assert [op.definition for op in again.operators] == [op.definition for op in world.operators]
    out = tmp_path / "ops.jsonl"
    assert main(["operators", "--out", str(out), "--layers", "12", "6", "3", "--seed", "1"]) == 0
    cli = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert [row["definition"] for row in cli] == [op.definition for op in world.registry]
    assert [row["priority"] for row in cli] == [op.priority for op in world.registry]


def test_summary_counts_layers(world):
    summary = world.summary()
    assert summary["operators"] == len(world) == 21
    assert {layer: sum(c.values()) for layer, c in summary["layers"].items()} == {0: 12, 1: 6, 2: 3}
    assert all(op.kind in ("simple", "branch", "recursive") for op in world.operators)
    assert all(op.kind == "atom" for op in world.atoms)


def test_evaluate_equals_the_oracle(world):
    oracle = Oracle(world.registry, world.settings.symbols, world.settings.semantics.build())
    rng = random.Random(0)
    for op in world.operators:
        for _ in range(10):
            args = tuple(rng.randint(-30, 120) for _ in range(op.arity))
            expected = oracle.evaluate(op.record, args).value
            assert op.evaluate(*args) == (None if expected is NAN else expected)
            assert op(*args) == op.evaluate(*args)


def test_evaluation_rejects_non_integer_inputs(world):
    assert world["+"].evaluate(2, None) is None
    with pytest.raises(TypeError, match="integer"):
        world["+"].evaluate(2.9, 1)
    with pytest.raises(TypeError, match="integer"):
        world.expression("a + 1").evaluate(a=2.9)


def test_lookup_by_symbol_and_role(world):
    op = world.operators[3]
    assert world[op.symbol] is op
    assert world.operator(op.func_id) is op
    assert world["-", "prefix"].evaluate(5) == -5
    assert world["-", "binary"].evaluate(5, 2) == 3
    with pytest.raises(KeyError, match="several roles"):
        world["-"]
    with pytest.raises(KeyError):
        world["no such symbol"]


def test_traces_end_at_the_oracle_value(world):
    rng = random.Random(1)
    for op in world.operators:
        args = tuple(rng.randint(0, 40) for _ in range(op.arity))
        trace = op.trace(*args)
        assert not trace.truncated
        assert trace.value == op.evaluate(*args)
        lines = trace.lines()
        assert len(lines) == len(trace) + 1
        assert lines[-1] == ("NaN" if trace.value is None else str(trace.value))


def test_expressions_parse_with_priorities(world):
    expr = world.expression("3 + 4 * 2")
    assert expr.value == 11
    assert world.expression("(3 + 4) * 2").value == 14
    op = next(o for o in world.operators if o.arity == 2)
    expr = world.expression(f"7 {op.symbol} 2")
    assert expr.value == op.evaluate(7, 2)
    assert expr.trace().value == expr.value
    free = world.expression(f"a {op.symbol} b")
    assert free.variables == ("a", "b")
    assert free.evaluate(a=7, b=2) == op.evaluate(7, 2)


def test_sampled_expressions_carry_dataset_records(world):
    first = world.sample_expressions(5, depth=2, frequency="zipf:1.5", seed=3)
    second = world.sample_expressions(5, depth=2, frequency="zipf:1.5", seed=3)
    assert [e.text for e in first] == [e.text for e in second]
    for expr in first:
        assert expr.record["result"] == expr.value
        assert expr.record["expression_plain"] == expr.text


def test_save_load_round_trip(world, tmp_path):
    from opulse.canary import CANARY

    path = world.save(tmp_path / "w")
    assert json.loads((path / "world.json").read_text())["meta"]["canary"] == CANARY
    assert (path / "config.yaml").read_text().startswith(f"# {CANARY}\n")
    loaded = World.load(path)
    assert [op.to_dict() for op in loaded.registry] == [op.to_dict() for op in world.registry]
    assert loaded.settings == world.settings
    assert loaded.seed == 1 and loaded.layers_requested == [12, 6, 3]
    assert loaded.fingerprint == world.fingerprint
    plain = World.load(path / "operators.jsonl")
    assert plain.fingerprint == world.fingerprint


def test_tasks_pass_bench_check(world, tmp_path):
    tasks = world.tasks("compute", n=8, seed=2)
    assert len(tasks) == 8 and tasks.check() == []
    out = tasks.to_jsonl(tmp_path / "tasks.jsonl")
    world.save(tmp_path / "w")
    assert main(["bench", "check", "--tasks", str(out), "--operators", str(tmp_path / "w" / "operators.jsonl"),
                 "--config", str(tmp_path / "w" / "config.yaml")]) == 0
    contrast = world.tasks("contrast", n=4, seed=2)
    assert contrast.check() == []


def test_holes_and_equivalences(world):
    holes = world.holes(2, depth=2, unique_only=True, seed=1, timeout_ms=500, domain=50)
    for hole in holes:
        assert hole.unique and hole.solutions == [hole.answer]
    verdict = world.equivalent("a + b", "b + a")
    assert verdict.status == "proved"
    assert world.equivalent("a - b", "b - a").status == "refuted"
    assert isinstance(world.equivalences(), list)


def test_dependencies_and_graph(world):
    top = world.layer(2)[0]
    deps = world.dependencies(top, transitive=True)
    assert set(top.callees) <= set(deps)
    assert all(top in dep.callers for dep in top.callees)
    graph = world.graph(focus=top)
    assert set(graph.ops) == {top, *deps}
    svg = graph.svg()
    assert svg.startswith("<svg") and svg.endswith("</svg>")
    assert world.graph().data()["nodes"]
    with pytest.raises(ValueError, match="different world"):
        world.dependencies(World.grow(layers=[1], seed=3).operators[0])


def test_settings_overrides():
    settings = make_settings(None, recursion={"style": "direct"}, semantics__bound=None)
    assert settings.recursion.style == "direct" and settings.semantics.bound is None
    with pytest.raises(ValueError):
        make_settings(None, nonsense=1)


def test_grow_from_atom_names():
    world = World.grow(layers=[4], seed=0, atoms=["add", "sub", "mul", "mod", "neg", "succ", "pred"])
    assert len(world.atoms) == 7 and len(world) == 4


class _Checker(HTMLParser):
    """Fails on unbalanced tags; collects the text."""

    VOID = frozenset(("br", "img", "hr", "meta", "input", "path", "rect"))

    def __init__(self) -> None:
        super().__init__()
        self.stack: list[str] = []
        self.text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        pass

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        assert self.stack and self.stack[-1] == tag, f"unbalanced </{tag}>, open {self.stack[-3:]}"
        self.stack.pop()

    def handle_data(self, data):
        self.text.append(data)


def _text(html: str) -> str:
    checker = _Checker()
    checker.feed(html)
    checker.close()
    assert checker.stack == [], f"unclosed tags {checker.stack}"
    return "".join(checker.text)


def test_html_views_are_valid_and_show_definitions(world):
    text = _text(world._repr_html_())
    for op in world.operators:
        assert op.definition in text
    for op in world.operators[:6] + world.atoms[:2]:
        shown = _text(op._repr_html_())
        assert (op.definition or op.signature) in shown
        assert op.kind in shown
    rec = next(op for op in world.operators if op.is_recursive)
    trace = rec.trace(*([5] * rec.arity))
    html = trace._repr_html_()
    assert 'background:color-mix(in srgb,' in html
    shown = _text(html)
    assert "unfold" in shown and str(trace.value if trace.value is not None else "NaN") in shown
    tasks = world.tasks("compute", n=3, seed=5)
    shown = _text(tasks[0]._repr_html_())
    assert all(d in shown for d in tasks[0].definitions)
    _text(tasks._repr_html_())
    _text(world.expression("3 + 4")._repr_html_())
    _text(world.graph()._repr_html_())
    for obj in (world, world.operators[0], trace, tasks[0], tasks):
        assert obj._repr_markdown_()
