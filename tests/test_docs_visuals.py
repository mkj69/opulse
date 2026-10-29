"""The published visual tour values follow the reference interpreter."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import INITIAL_OPERATORS, requires_zh_site

from opulse.bench.check import answer_from_prompt, base_registry, prompt_registry
from opulse.cli.operators import DEFAULT_CONFIG
from opulse.config import Settings
from opulse.core import BRANCH, RECURSIVE, Operator, OperatorRegistry
from opulse.core.semantics import NAN
from opulse.definition.parser import DefinitionParser
from opulse.expression.nodes import from_ast
from opulse.solver.equivalence import EquivalenceChecker
from opulse.solver.z3_encode import Z3Encoder
from opulse.verify import Oracle
from opulse.verify.steps import check_steps

ROOT = Path(__file__).resolve().parents[1]
NAMES = ("growth", "unfold", "contrast", "steps", "equivalence", "ripple", "frequency")
SOLVE_DATA = ROOT / "docs" / "assets" / "data" / "scales_solve"


def examples(name):
    text = (ROOT / "docs" / "snippets" / f"vis_{name}.html").read_text(encoding="utf-8")
    start = text.index('<script type="application/json">') + len('<script type="application/json">')
    payload = json.loads(text[start:text.index("</script>", start)].replace("<\\/", "</"))
    result = payload["examples"]
    for entry in result:
        if "url" in entry:
            entry["data"] = json.loads((ROOT / "docs" / "assets" / entry["url"]).read_text(encoding="utf-8"))
    return result


def value(oracle, parser, expression, env=None):
    result = oracle.evaluate_expr(parser.parse_expr(expression, expression_mode=True), env or {}).value
    return None if result is NAN else result


def depth(node):
    return 1 + max((depth(arg) for arg in getattr(node, "args", ())), default=0)


@pytest.fixture(scope="module")
def worlds():
    settings = Settings.load(DEFAULT_CONFIG)
    base = base_registry(OperatorRegistry.from_jsonl(INITIAL_OPERATORS))
    result = []
    for entry in examples("growth"):
        definitions = [node["definition"] for node in entry["data"]["nodes"] if node["definition"]]
        ops = prompt_registry(definitions, base, settings.symbols, settings.semantics.build(),
                              variables=("x", "a", "b"))
        result.append((entry["data"], ops))
    return base, settings, result


@pytest.mark.parametrize("name", NAMES)
def test_tour_examples_match_interpreter(name, worlds):
    base, settings, grown = worlds
    entries = examples(name)
    assert len(entries) == (1 if name == "equivalence" else 4)
    for index, entry in enumerate(entries):
        data = entry["data"]
        growth, ops = grown[index]
        assert entry["operators"] > 0 and entry["steps"] > 0
        parser, oracle = ops.parser, ops.oracle
        if name == "growth":
            assert data == growth
            for node in data["nodes"]:
                for sample in node["samples"][:2]:
                    assert value(oracle, parser, sample["call"]) == sample["value"]
        elif name == "unfold":
            assert len(data["frames"]) == entry["steps"]
            for frame in data["frames"][::max(1, len(data["frames"]) // 8)]:
                assert value(oracle, parser, frame["text"]) == data["value"]
        elif name == "contrast":
            for variant in data["variants"]:
                task = {"family": "contrast", "prompt": variant["prompt"],
                        "definitions": variant["definitions"], "expression": data["expression"]}
                result = answer_from_prompt(task, base, settings.symbols, settings.semantics.build())
                assert ("NaN" if result is NAN else str(result)) == variant["rederived"]
                assert variant["answer"] == variant["rederived"]
        elif name == "steps":
            question = from_ast(parser.parse_expr(data["question"], expression_mode=True), ops.registry)
            for run in data["runs"]:
                lines = [row["line"] for row in run["rows"]]
                report = check_steps(question, lines, parser, ops.registry, oracle,
                                     NAN if data["answer"] is None else data["answer"])
                assert report.first_error == run["report"]["first_error"]
                assert report.derivation_correct == run["report"]["derivation_correct"]
        elif name == "equivalence":
            registry = OperatorRegistry(list(ops.registry))
            for index_extra, definition in enumerate(data["definitions"]):
                symbol, arity, position, kind = (
                    ("⊕", 2, None, BRANCH), ("⊗", 2, None, BRANCH),
                    ("◈", 1, "prefix", RECURSIVE), ("⊛", 2, None, BRANCH)
                )[index_extra]
                func_id = f"tourtest{index_extra}"
                args = "a" if arity == 1 else "a, b"
                registry.add(Operator(func_id, symbol, arity, position, definition=definition,
                                      definition_type=kind,
                                      op_compute_func=f"def op_{func_id}({args}):\n    return 0\n",
                                      op_count_func=f"def op_count_{func_id}({args}):\n    return 0\n"))
            parser = DefinitionParser(settings.symbols, registry, variables=("a", "b"))
            oracle = Oracle(registry, settings.symbols, settings.semantics.build())
            checker = EquivalenceChecker(Z3Encoder(oracle), timeout_ms=10_000)
            assert [pair["kind"] for pair in data["pairs"]] == [
                "Inlining", "Constant folding", "Disjoint branches", "Bounded recursion",
                "Rare interior input", "Value bound"]
            for pair in data["pairs"]:
                assert len(pair["grid"]) == 81
                for a, b, left, right in pair["grid"]:
                    assert value(oracle, parser, pair["left"], {"a": a, "b": b}) == left
                    assert value(oracle, parser, pair["right"], {"a": a, "b": b}) == right
                if pair["status"] == "checked":
                    assert pair["range"] == [0, 8] and pair["method"] == "exhaustive"
                    for a in range(9):
                        assert value(oracle, parser, pair["left"], {"a": a}) == value(
                            oracle, parser, pair["right"], {"a": a})
                else:
                    left = from_ast(parser.parse_expr(pair["left"], expression_mode=True), registry)
                    right = from_ast(parser.parse_expr(pair["right"], expression_mode=True), registry)
                    assert checker.check(left, right).status == pair["status"]
                if pair["status"] == "refuted":
                    assert value(oracle, parser, pair["left"], pair["counterexample"]) == pair["left_value"]
                    assert value(oracle, parser, pair["right"], pair["counterexample"]) == pair["right_value"]
                    assert pair["left_value"] != pair["right_value"]
        elif name == "ripple":
            definitions = [node["definition"] for node in growth["nodes"] if node["definition"]]
            changed = [data["after"] if definition == data["before"] else definition for definition in definitions]
            edited = prompt_registry(changed, base, settings.symbols, settings.semantics.build())
            for node in data["nodes"][::max(1, len(data["nodes"]) // 8)]:
                assert value(oracle, parser, node["call"]) == node["old"]
                assert value(edited.oracle, edited.parser, node["call"]) == node["new"]
        else:
            for series in data["series"]:
                for sample in series["sample"]:
                    assert value(oracle, parser, sample["expression"]) == sample["value"]
                assert len(series["snapshots"][-1]) == len(data["operators"])


def test_hard_examples_have_declared_complexity(worlds):
    _, _, grown = worlds
    for index in (2, 3):
        growth, ops = grown[index]
        for name, expression in (("unfold", examples("unfold")[index]["data"]["frames"][0]["text"]),
                                 ("contrast", examples("contrast")[index]["data"]["expression"]),
                                 ("steps", examples("steps")[index]["data"]["question"])):
            entry = examples(name)[index]
            tree = from_ast(ops.parser.parse_expr(expression, expression_mode=True), ops.registry)
            assert 5 <= entry["operators"] <= 10
            assert depth(tree) >= 4
            assert all(any(node["kind"] == kind and node["symbol"] in expression
                           for node in growth["nodes"]) for kind in ("branch", "recursive"))
        assert len(examples("unfold")[index]["data"]["frames"]) >= 30
        assert len(examples("steps")[index]["data"]["runs"][0]["rows"]) >= 30
        assert max(node["distance"] for node in examples("ripple")[index]["data"]["nodes"]) >= 3
    pairs = examples("equivalence")[0]["data"]["pairs"]
    assert pairs[4]["counterexample"] == {"a": 2, "b": -3}
    assert sum(row[2] != row[3] for row in pairs[4]["grid"]) == 1
    assert max(abs(v) for v in pairs[5]["counterexample"].values()) > 1000
    assert any(node["definition"] and node["symbol"] in pairs[0]["left"]
               for node in grown[0][0]["nodes"])


def test_scale_solve_snippet_and_published_values():
    script = (ROOT / "docs" / "assets" / "js" / "scales-solve.js").read_text(encoding="utf-8")
    assert 'fetch(base + keys[index] + ".json")' in script
    assert 'operatorText(data.expression, data.target_operator)' in script
    assert '<code><span class="op-sym">' in script
    _check_solve_snippet("docs", "en")
    files = sorted(SOLVE_DATA.glob("s*.json"))
    assert {"s10.json", "s100.json", "s1000.json"} <= {path.name for path in files}
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["schema"] == "opulse.scales-solve/1"
        assert data["scale"] == path.stem
        assert data["target_operator"] in data["expression"]
        assert data["target_layer"] >= 2 and data["closure_size"] >= 2
        assert data["unique"] and data["complete"]
        assert data["solutions"] == data["hits"] == [data["answer"]]
        assert [row["x"] for row in data["scan"]] == list(range(data["domain"][0], data["domain"][1] + 1))
        assert [row["x"] for row in data["scan"] if row["value"] == data["target"]] == [data["answer"]]
        assert data["check_value"] == data["target"]
        assert data["scan"][data["answer"] - data["domain"][0]]["steps"] == data["check_steps"]
        assert data["check_steps"] > 1


def _check_solve_snippet(site, lang):
    snippet = (ROOT / site / "snippets" / "vis_solve.html").read_text(encoding="utf-8")
    assert f'data-lang="{lang}"' in snippet
    assert 'data-base="' in snippet and 'assets/data/scales_solve/' in snippet
    assert 'scales-solve.js' in snippet


@requires_zh_site
def test_chinese_scale_solve_snippet_and_mirror():
    script = (ROOT / "docs/assets/js/scales-solve.js").read_text(encoding="utf-8")
    mirror = ROOT / "docs_zh/snippets/localized_assets/js/scales-solve.js"
    assert mirror.read_text(encoding="utf-8") == script
    _check_solve_snippet("docs_zh", "zh")


def test_scale_widgets_are_scoped_to_their_pages():
    home = (ROOT / "docs" / "assets" / "js" / "home-scales.js").read_text(encoding="utf-8")
    tour = (ROOT / "docs" / "assets" / "js" / "scales-tour.js").read_text(encoding="utf-8")
    assert '.op-home-scales:not([data-ready])' in home
    assert 'root.dataset.scalesTourReady' in tour
    assert 'renderStepList(stepBox, example, cut' in tour
    assert 'renderTree(treeBox, example, cut)' in tour
    _check_widget_scope("docs", "home_examples_en.html")


@requires_zh_site
def test_chinese_scale_widgets_are_scoped_to_their_pages():
    _check_widget_scope("docs_zh", "home_examples_zh.html")


def _check_widget_scope(base, home_snippet):
    tour_snippet = "granularity_scales.html"
    assert home_snippet in (ROOT / base / "index.md").read_text(encoding="utf-8")
    assert tour_snippet in (ROOT / base / "guide" / "visual-tour.md").read_text(encoding="utf-8")
    snippet = (ROOT / base / "snippets" / tour_snippet).read_text(encoding="utf-8")
    assert 'data-mode="granularity"' in snippet
    assert 'scales-tour.js' in snippet
