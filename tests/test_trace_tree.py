import itertools
import json
import random

import pytest

from opulse.config import Settings
from opulse.core.semantics import NAN
from opulse.definition.parser import DefinitionParser
from opulse.expression.generator import ExpressionGenerator, OperatorPool
from opulse.expression.nodes import Call, Number, literal_form, to_ast
from opulse.expression.render import ExpressionRenderer
from opulse.generation.pipeline import OperatorFactory, build_layers
from opulse.trace import Reducer
from opulse.trace.explain import Explainer, render_explanation, simplify
from opulse.trace.tree import (
    TreeBuilder,
    align,
    build_tree,
    cut,
    flatten,
    flatten_view,
    from_json,
    render_text,
    to_json,
    verify_tree,
)
from opulse.verify import Oracle


@pytest.fixture(scope="module")
def world():
    from conftest import INITIAL_OPERATORS

    from opulse.core import OperatorRegistry

    settings = Settings()
    registry = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
    factory = OperatorFactory(settings, registry, random.Random(22))
    build_layers(factory, [12, 8, 5])
    parser = DefinitionParser(settings.symbols, registry)
    oracle = Oracle(registry, settings.symbols, settings.semantics.build())
    return registry, factory.runtime, parser, oracle, ExpressionRenderer(settings.symbols)


@pytest.fixture(scope="module")
def expressions(world):
    registry = world[0]
    generator = ExpressionGenerator(Settings().expressions, random.Random(5))
    pool = OperatorPool.from_registry(registry)
    found = []
    while len(found) < 25:
        tree = generator.tree(pool)
        if isinstance(tree, Call):
            found.append(literal_form(tree, registry))
    return found


def _max_layer(registry) -> int:
    return max((op.recursive_layer or 0) for op in registry if op.definition)


def test_flatten_equals_the_reducer_at_every_cut(world, expressions):
    registry, runtime, parser, _oracle, _ = world
    top = _max_layer(registry)
    middle = sorted(op.symbol for op in registry if op.definition and op.recursive_layer == 1)[:3]
    cuts = [(cut(known_layers=layers), None) for layers in range(top + 2)]
    cuts += [(cut(known=middle), None), (None, 0), (None, 1), (None, 2), (cut(known_layers=1), 2)]
    for tree in expressions:
        root = build_tree(tree, registry, runtime, parser)
        for expand, depth in cuts:
            want = Reducer(registry, runtime, parser, expand=expand, max_depth=depth).reduce(tree)
            got = flatten(root, expand, depth, max_steps=2000)
            assert got.steps == want.steps
            assert got.truncated == want.truncated


def test_every_node_verifies(world, expressions):
    registry, runtime, parser, oracle, _ = world
    total = 0
    for tree in expressions:
        root = build_tree(tree, registry, runtime, parser)
        total += verify_tree(root, oracle)
        for node in root.nodes():
            for item in node.steps:
                opened = item.step.kind == "eval" and item.step.operator.definition is not None
                assert (item.child is not None) == opened
    assert total > len(expressions)


def test_finest_cut_reaches_only_atoms(world, expressions):
    registry, runtime, parser, *_ = world
    for tree in expressions:
        view = flatten_view(build_tree(tree, registry, runtime, parser))
        for v in view:
            assert v.child is None
            assert (v.step.kind == "eval") == (v.step.operator.definition is None)


def test_coarsest_cut_is_one_eval_per_application(world, expressions):
    registry, runtime, parser, *_ = world
    from opulse.expression.nodes import iter_calls

    for tree in expressions:
        root = build_tree(tree, registry, runtime, parser)
        trace = flatten(root, cut(known_layers=_max_layer(registry) + 1))
        assert [s.kind for s in trace.steps] == ["eval"] * len(list(iter_calls(tree)))
        assert [s.operator for s in trace.steps] == [c.operator for c in iter_calls(tree)]
        assert [s.step for s in root.steps] == trace.steps


def test_json_round_trip(world, expressions):
    registry, runtime, parser, oracle, renderer = world
    for tree in expressions[:10]:
        root = build_tree(tree, registry, runtime, parser)
        data = json.loads(json.dumps(to_json(root, renderer), ensure_ascii=False))
        assert data["schema"] == "opulse.derivation/1"
        back = from_json(data, registry)
        assert to_json(back, renderer) == data
        verify_tree(back, oracle)
        for layers in range(_max_layer(registry) + 2):
            assert flatten(back, cut(known_layers=layers)).steps == flatten(root, cut(known_layers=layers)).steps


def test_nan_and_undefined_steps_survive(world):
    registry, runtime, parser, oracle, renderer = world
    divide = registry.find("/", 2)
    defined = next(op for op in registry if op.definition and op.n_ary == 1)
    tree = Call(defined, (Call(divide, (Number(1), Number(0))),))  # a defined operator applied to NaN
    root = build_tree(tree, registry, runtime, parser)
    verify_tree(root, oracle)
    assert root.value is NAN or root.value == runtime.compute(defined)(NAN)
    assert flatten(root).steps == Reducer(registry, runtime, parser).reduce(tree).steps
    assert from_json(json.loads(json.dumps(to_json(root, renderer))), registry).value is root.value


def test_text_rendering_opens_sub_derivations(world, expressions):
    registry, runtime, parser, _, renderer = world
    tree = next(t for t in expressions if any(c.operator.definition for c in [t] if isinstance(t, Call)))
    root = build_tree(tree, registry, runtime, parser)
    coarse = render_text(root, renderer, cut(known_layers=99))
    opened = render_text(root, renderer, cut(known_layers=99), open_levels=1)
    assert coarse.splitlines()[0] == renderer.minimal(tree)
    assert len(opened.splitlines()) > len(coarse.splitlines())
    assert "[expand" in opened and "[expand" not in coarse


def test_shared_nodes_are_built_once(world):
    registry, runtime, parser, *_ = world
    op = next(o for o in registry if o.definition and o.n_ary == 2)
    builder = TreeBuilder(registry, runtime, parser)
    first = builder.application(op, (3, 4))
    assert builder.application(op, (3, 4)) is first


# ------------------------------------------------------------------ explanation
@pytest.fixture(scope="module")
def explainer(world):
    registry, runtime, _parser, oracle, renderer = world
    return Explainer(registry, oracle, runtime, renderer, timeout_ms=2000)


def test_explanation_formula_equals_interpreter(world, explainer):
    registry, _runtime, _parser, oracle, _renderer = world
    rng = random.Random(0)
    checked = 0
    for op in [o for o in registry if o.definition][:20]:
        definition = oracle._definition_of(op)
        names = definition.parameters
        for index, branch in enumerate(definition.branches):
            from opulse.expression.nodes import from_ast

            body = from_ast(branch.expr, registry)
            inlined = explainer.inline(body)
            proposal = simplify(explainer.fold(inlined), registry)
            for _ in range(15):
                env = {name: rng.randint(-60, 60) for name in names}
                want = oracle.evaluate_expr(branch.expr, env).value
                got = oracle.evaluate_expr(to_ast(inlined), env).value
                assert got is want or got == want
                if proposal is not None and _small(env):
                    # SymPy's form uses exact integer algebra; it agrees wherever nothing overflows.
                    value = oracle.evaluate_expr(to_ast(proposal), env).value
                    if want is not NAN and value is not NAN:
                        assert value == want
                checked += 1
    assert checked > 100


def _small(env) -> bool:
    return all(abs(v) <= 60 for v in env.values())


def test_explanation_reports_checks_and_table(world, explainer):
    registry, _runtime, _parser, oracle, _ = world
    from opulse.expression.nodes import from_ast

    def body(o):
        return from_ast(oracle._definition_of(o).branches[0].expr, registry)

    simple = next(o for o in registry if o.definition_type == "simple_definition"
                  and not explainer._recursive(o) and explainer.inline(body(o)) != body(o))
    data = explainer.explain(simple)
    row = data["formula"]["branches"][0]
    assert row["inlined"] is not None
    assert row["inlined_check"]["status"] == "proved"
    assert row["simplified_check"] is None or row["simplified_check"]["status"] in ("proved", "refuted", "bounded")
    recursive = next(o for o in registry if o.definition_type == "recursive_definition" and o.n_ary == 1)
    data = explainer.explain(recursive, (-9, 9))
    rows = data["table"]["rows"]
    assert rows[0]["from"] == -9 and rows[-1]["to"] == 9
    assert all(a["to"] + 1 == b["from"] for a, b in itertools.pairwise(rows))
    assert all(a["path"] != b["path"] for a, b in itertools.pairwise(rows))
    for row in rows:
        for x, value in zip(range(row["from"], row["to"] + 1), row["values"]):
            want = oracle.evaluate(recursive, (x,)).value
            assert (value is None and want is NAN) or value == want
    assert data["formula"]["recursive"] and data["outline"]["self"]
    text = render_explanation(data)
    assert recursive.symbol in text and "branch" in text


def test_binary_table_blocks_cover_the_grid(world, explainer):
    registry = world[0]
    op = next(o for o in registry if o.definition_type == "branch_definition" and o.n_ary == 2)
    table = explainer.table(op, (0, 20), (0, 20))
    blocks = table["blocks"]
    assert blocks[0]["from"] == 0 and blocks[-1]["to"] == 20
    for block in blocks:
        runs = block["runs"]
        assert runs[0]["from"] == 0 and runs[-1]["to"] == 20
        assert all(a["to"] + 1 == b["from"] for a, b in itertools.pairwise(runs))


def test_cli_trace_and_explain(tmp_path, capsys):
    from opulse.cli.main import main

    ops = tmp_path / "ops.jsonl"
    assert main(["operators", "--out", str(ops), "--layers", "6", "4", "--seed", "3"]) == 0
    rows = [json.loads(line) for line in ops.read_text().splitlines()]
    deep = next(r for r in rows if r["definition"] and r["recursive_layer"] == 1 and r["n_ary"] == 2)
    expression = f"3 {deep['symbol']} 4"
    out = tmp_path / "tree.json"
    assert main(["trace", "--operators", str(ops), "--expression", expression, "--format", "json",
                 "--out", str(out)]) == 0
    data = json.loads(out.read_text())
    from opulse.canary import CANARY

    assert data["meta"]["canary"] == CANARY
    assert data["schema"] == "opulse.derivation/1" and data["root"] == "n0"
    capsys.readouterr()
    assert main(["trace", "--operators", str(ops), "--expression", expression, "--known-layers", "1",
                 "--open", "1"]) == 0
    text = capsys.readouterr().out
    assert text.splitlines()[0] == expression and "[expand" in text
    assert main(["explain", "--operators", str(ops), "--operator", deep["func_id"], "--range", "0", "5",
                 "--range-b", "0", "3"]) == 0
    assert "uses" in capsys.readouterr().out


def test_docs_shape_names_parse_and_preserve_values(world):
    from tools.docs_granularity import named_operators

    registry, _runtime, _parser, oracle, _renderer = world
    renamed = named_operators(registry, Settings())
    parser = DefinitionParser(Settings().symbols, renamed)
    renamed_oracle = Oracle(renamed, Settings().symbols, Settings().semantics.build())
    for op in renamed:
        if op.definition is None:
            continue
        assert op.symbol[0] in "■□▲△▼▽◆◇●○★☆"
        assert op.symbol[1:].startswith("₁") or op.symbol[1:].startswith("₂") or op.symbol[1:].startswith("₃")
        assert parser.parse(op.definition).lhs.symbol == op.symbol
        inputs = (3,) * op.n_ary
        before = oracle.evaluate(registry.get(op.func_id), inputs).value
        after = renamed_oracle.evaluate(op, inputs).value
        assert before is after or before == after


@pytest.fixture(scope="module")
def search_nary_world():
    from conftest import INITIAL_OPERATORS

    from opulse.core import OperatorRegistry

    settings = Settings.from_dict({"operators": {"arity_weights": {1: 0.3, 2: 0.3, 3: 0.4}},
                                   "recursion": {"search_enabled": True, "search_bound": 4}})
    registry = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
    factory = OperatorFactory(settings, registry, random.Random(3))
    build_layers(factory, [8, 6, 5])
    parser = DefinitionParser(settings.symbols, registry)
    oracle = Oracle(registry, settings.symbols, settings.semantics.build())
    renderer = ExpressionRenderer(settings.symbols)
    search = next(op for op in registry if op.definition and "search(" in op.definition)
    ternary = next(op for op in registry if op.definition and op.n_ary == 3)
    return settings, registry, factory.runtime, parser, oracle, renderer, search, ternary


def _generated_cli_files(tmp_path, search_nary_world):
    _settings, registry, *_ = search_nary_world
    config = tmp_path / "config.yaml"
    config.write_text("operators: {arity_weights: {1: 0.3, 2: 0.3, 3: 0.4}}\n"
                      "recursion: {search_enabled: true, search_bound: 4}\n")
    operators = tmp_path / "operators.jsonl"
    registry.to_jsonl(operators)
    return config, operators


def test_trace_open_search_is_a_leaf(tmp_path, capsys, search_nary_world):
    from opulse.cli.main import main

    settings, registry, runtime, parser, oracle, renderer, search, _ = search_nary_world
    args = tuple(range(1, search.n_ary + 1))
    expression = search.apply_str(*(str(value) for value in args), symbols=settings.symbols)
    root = build_tree(Call(search, tuple(Number(value) for value in args)), registry, runtime, parser)
    assert verify_tree(root, oracle) == 2
    assert len(root.steps) == 1
    search_node = root.steps[0].child
    assert search_node is not None
    step = search_node.steps[0].step
    assert step.kind == "eval" and step.branch_index == 0 and step.condition
    assert search_node.steps[0].child is None
    assert flatten(root).steps == Reducer(registry, runtime, parser).reduce(root.source).steps
    assert "[search " in render_text(root, renderer, open_levels=2)
    data = json.loads(json.dumps(to_json(root, renderer)))
    assert data["nodes"]["n0"]["steps"][0]["child"] == "n1"
    assert data["nodes"]["n1"]["steps"][0]["child"] is None
    assert data["nodes"]["n1"]["steps"][0]["condition"] == step.condition
    assert to_json(from_json(data, registry), renderer) == data

    config, operators = _generated_cli_files(tmp_path, search_nary_world)
    command = ["trace", "--config", str(config), "--operators", str(operators),
               "--expression", expression, "--open", "1"]
    assert main(command) == 0
    assert "[search " in capsys.readouterr().out
    assert main(command + ["--known", search.symbol]) == 0
    opened = capsys.readouterr().out
    assert "[eval " in opened and "[search " in opened
    assert main(command[:-2] + ["--format", "json"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["nodes"]["n1"]["steps"][0]["child"] is None


def test_trace_ternary_call(tmp_path, capsys, search_nary_world):
    from opulse.cli.main import main

    settings, registry, runtime, parser, oracle, renderer, _, ternary = search_nary_world
    expression = ternary.apply_str("1", "2", "3", symbols=settings.symbols)
    source = Call(ternary, (Number(1), Number(2), Number(3)))
    root = build_tree(source, registry, runtime, parser)
    verify_tree(root, oracle)
    assert flatten(root).steps == Reducer(registry, runtime, parser).reduce(source).steps
    assert to_json(root, renderer)["expression"] == expression
    config, operators = _generated_cli_files(tmp_path, search_nary_world)
    assert main(["trace", "--config", str(config), "--operators", str(operators),
                 "--expression", expression, "--known", ternary.symbol, "--open", "1"]) == 0
    output = capsys.readouterr().out
    assert output.splitlines()[0] == expression and "[expand " in output


def test_explain_ternary_call(tmp_path, capsys, search_nary_world):
    from opulse.cli.main import main

    settings, registry, runtime, _, oracle, renderer, _, ternary = search_nary_world
    data = Explainer(registry, oracle, runtime, renderer).explain(ternary, (0, 1))
    assert data["table"]["n_ary"] == 3
    assert data["table"]["note"] == "table covers arity 1 and 2 only"
    assert data["outline"]["form"] == ternary.apply_str("a", "b", "c", symbols=settings.symbols)
    assert ternary.symbol + "(" in render_explanation(data)
    config, operators = _generated_cli_files(tmp_path, search_nary_world)
    assert main(["explain", "--config", str(config), "--operators", str(operators),
                 "--operator", ternary.func_id, "--range", "0", "1"]) == 0
    assert "table covers arity 1 and 2 only" in capsys.readouterr().out


def test_explain_search_body(tmp_path, capsys, search_nary_world):
    from opulse.cli.main import main
    from opulse.definition import ast

    _settings, registry, runtime, _, oracle, renderer, search, _ = search_nary_world
    data = Explainer(registry, oracle, runtime, renderer).explain(search, (0, 1), (0, 1))
    row = data["formula"]["branches"][0]
    body = oracle._definition_of(search).branches[0].expr
    assert row["body"] == ast.render_expr(body, oracle.parser.symbols)
    assert "search(" in row["body"]
    assert row["inlined"] is row["simplified"] is None
    assert row["inlined_check"] is row["simplified_check"] is None
    assert "search" in row["skip_reason"]
    assert data["table"]["rows" if search.n_ary == 1 else "blocks"]
    config, operators = _generated_cli_files(tmp_path, search_nary_world)
    assert main(["explain", "--config", str(config), "--operators", str(operators),
                 "--operator", search.func_id, "--range", "0", "1", "--range-b", "0", "1"]) == 0
    output = capsys.readouterr().out
    assert row["body"] in output and row["skip_reason"] in output


def test_align_lines_up_coarse_and_fine_steps(world, expressions):
    registry, runtime, parser, *_ = world
    top = _max_layer(registry)
    cuts = [cut(known_layers=top + 1), cut(known_layers=1), cut(known_layers=0)]
    for tree in expressions:
        root = build_tree(tree, registry, runtime, parser)
        views, owners = align(root, cuts)
        for expand, view in zip(cuts, views):
            assert [v.step for v in view] == flatten(root, expand).steps
        assert [owner[-1] for owner in owners] == list(range(len(views[-1])))
        for level, view in enumerate(views):
            column = [owner[level] for owner in owners]
            # one coarse step stands for a contiguous, non-empty block of finer steps
            assert column == sorted(column) and set(column) == set(range(len(view)))
            for index, step in enumerate(view):
                block = [j for j, owner in enumerate(owners) if owner[level] == index]
                last = views[-1][block[-1]].step
                # after its block the finer derivation is at the same expression as the coarse one
                assert last.expression_after == step.step.expression_after
                if step.step.kind != "eval" or step.step.operator.definition is None:
                    assert len(block) == 1 and views[-1][block[0]].step.kind == step.step.kind
        # medium blocks nest inside coarse blocks
        assert all(a[0] <= b[0] and (a[1] < b[1] or a[0] == b[0]) for a, b in itertools.pairwise(owners))


def test_align_rejects_cuts_out_of_order(world, expressions):
    registry, runtime, parser, *_ = world
    root = build_tree(expressions[0], registry, runtime, parser)
    with pytest.raises(ValueError):
        align(root, [cut(known_layers=0), cut(known_layers=_max_layer(registry) + 1)])


def test_granularity_animation_data_is_the_interpreter_trace(tmp_path):
    """docs/assets/data/granularity_anim.json is what tools/docs_granularity.py builds, and every
    level of it is the reducer's trace at its cut (checked inside ``animation``)."""
    from pathlib import Path

    from opulse.cli.operators import DEFAULT_CONFIG
    from tools.docs_granularity import ANIM_OUT, animation

    data = animation(Settings.load(DEFAULT_CONFIG), workdir=tmp_path)
    committed = json.loads(Path(ANIM_OUT).read_text(encoding="utf-8"))
    assert data == committed, "run python tools/docs_granularity.py --anim"
    coarse, fine, cuts = data["coarse"], data["fine"], data["cuts"]
    assert len(coarse) < len(fine)
    assert {s["cls"] for s in fine} >= {"expand", "branch", "recursion", "atom"}
    assert all(s["cls"] in ("expand", "branch", "recursion", "atom") for s in fine)
    strip = lambda steps: [{k: v for k, v in s.items() if k != "owner"} for s in steps]  # noqa: E731
    assert strip(cuts[0]["steps"]) == strip(fine) and strip(cuts[-1]["steps"]) == strip(coarse)
    for index, step in enumerate(coarse):
        assert step["owner"] == [index]
    for item in cuts:
        steps = item["steps"]
        assert item["count"] == len(steps) and steps[-1]["text"] == str(data["value"])
        assert len(coarse) <= len(steps) <= len(fine)
        # every step of the cut stands for a contiguous block of fine steps inside one coarse step
        assert item["fine"] == sorted(item["fine"]) and set(item["fine"]) == set(range(len(steps)))
        for index, step in enumerate(steps):
            assert step["owner"][1] == index
            block = [j for j, owner in enumerate(item["fine"]) if owner == index]
            assert {fine[j]["owner"][0] for j in block} == {step["owner"][0]}
            assert fine[block[-1]]["text"] == step["text"]
            if step["hit"] is not None:
                start, end = step["hit"]
                assert 0 <= start < end <= len(step["text"])


def test_granularity_animation_has_every_cut_of_the_reducer(tmp_path):
    """The animation holds one derivation for every subset of its defined operators made known,
    and each one is the reducer's trace with that known set, checked by the reference interpreter."""
    from pathlib import Path

    from opulse.cli.operators import DEFAULT_CONFIG
    from opulse.runtime import PythonRuntime
    from opulse.verify.records import verify_trace
    from tools.docs_granularity import ANIM_EXPRESSION, ANIM_OUT, animation_registry, expression_from_spec

    data = json.loads(Path(ANIM_OUT).read_text(encoding="utf-8"))
    settings = Settings.load(DEFAULT_CONFIG)
    registry = animation_registry(settings, tmp_path)
    runtime = PythonRuntime(registry, settings.semantics.build())
    parser = DefinitionParser(settings.symbols, registry)
    oracle = Oracle(registry, settings.symbols, settings.semantics.build())
    renderer = ExpressionRenderer(settings.symbols)
    expression = expression_from_spec(ANIM_EXPRESSION, registry)
    chips = data["chips"]
    defined = {s.operator.symbol for s in Reducer(registry, runtime, parser).reduce(expression).steps
               if s.kind == "expand"}
    assert set(chips) == defined and 1 <= len(chips) <= 5
    assert len(data["cuts"]) == 2 ** len(chips)
    seen = set()
    for mask, item in enumerate(data["cuts"]):
        known = [symbol for i, symbol in enumerate(chips) if mask >> i & 1]
        assert item["known"] == known
        trace = Reducer(registry, runtime, parser, expand=cut(known=known)).reduce(expression)
        verify_trace(trace, oracle)
        assert not trace.truncated
        assert [(s["kind"], s["op"], s["text"]) for s in item["steps"]] == \
            [(s.kind, s.operator.symbol, renderer.minimal(s.expression_after)) for s in trace.steps]
        seen.add(tuple(known))
    assert len(seen) == 2 ** len(chips)
    assert data["presets"]["all"] == 2 ** len(chips) - 1 and data["presets"]["none"] == 0
