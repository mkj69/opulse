"""The browser playground's packaged code, examples, and public results."""

import ast
import importlib.util
import json
import os
import random
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from opulse.config import Symbols
from opulse.core.operator import BINARY, PREFIX
from opulse.core.semantics import NAN
from opulse.expression.evaluator import Evaluator
from opulse.expression.nodes import Call
from opulse.expression.render import ExpressionRenderer
from opulse.playground import (
    Workspace,
    _render_marked,
    _to_ast,
    atom_table,
    atoms,
    available_worlds,
    check_equivalent,
    check_equivalent_json,
    challenge_steps,
    challenge_steps_json,


    check_playground_guess_json,
    export,
    grow,
    run,
    run_json,
    size,
    symbol_problem,
    table_json,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _restore_atoms():
    """Each test leaves the shared atom tables (renamed symbols, custom atoms) as it found them."""
    yield
    from opulse.playground import _restore

    _restore()


@pytest.fixture(scope="module")
def builder():
    spec = importlib.util.spec_from_file_location("build_playground", ROOT / "tools" / "build_playground.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def examples(builder):
    return builder.read_examples()


def _example(examples, name):
    return next(example for example in examples if example["id"] == name)


def _value(value):
    return "NaN" if value is NAN else str(value)


def _subtree_text(tree, path, renderer):
    parent = None
    for index in path:
        parent, tree = tree.operator, tree.args[index]
    return renderer._render(tree, parent, None, minimal=False)


def test_bundle_matches_import_closure(builder):
    bundled = builder.read_bundle()
    assert bundled == builder.expected_files(), "run python tools/build_playground.py"
    assert "opulse/playground.py" in bundled
    assert "opulse/generation/pipeline.py" in bundled  # the Grow button
    assert not any(path.startswith(("opulse/solver/", "opulse/cli/")) for path in bundled)


def test_challenge_equivalence_exhausts_integer_domain_and_reports_errors():
    rules = "a ◇ b = { (a + b) * 2 }\na ◆ = { a ◇ 1 }"
    equal = check_equivalent(rules, "◇", "a ◇ b = { (a + b) + (a + b) }", [-2, 2])
    assert equal == {"equivalent": True, "proof": "range", "counterexample": None, "parse_error": None}
    assert json.loads(check_equivalent_json(rules, "◇", "a ◇ b = { a + b }", "[-2,2]")) == (
        check_equivalent(rules, "◇", "a ◇ b = { a + b }", [-2, 2]))
    different = check_equivalent(rules, "◇", "a ◇ b = { a + b }", [-2, 2])
    assert different["counterexample"] == {"inputs": [-2, -2], "expected": -8, "got": -4}
    assert check_equivalent(rules, "◇", "a ◇ = { a + 1 }", [0, 2])["parse_error"]
    assert check_equivalent(rules, "◇", "a ◇ b = { a + }", [0, 2])["parse_error"]
    assert check_equivalent(rules, "◇", "a ◇ b = { a }", [2, 0])["parse_error"]


def test_hidden_definition_check_uses_world_semantics_and_typed_inputs():
    def check(definitions, symbol, candidate, domain, world=""):
        return json.loads(check_playground_guess_json(
            definitions, symbol, candidate, json.dumps(domain), world))

    rules = "a ♧ b = { a + b }\na ★ b = { (a ♧ b) * 2 }"
    assert check(rules, "★", "a ★ b = { (a + b) + (a + b) }", [-3, 3])["equivalent"]
    wrong = check(rules, "★", "a ★ b = { a + b }", [-3, 3])
    assert wrong["counterexample"] == {"inputs": [-3, -3], "expected": -12, "got": -6}
    assert check("a ◇ b = { a + b }", "◇", "a ◇ b = { (a + b) + 12 }", [0, 11], "clock")["equivalent"]
    strings = check("a ◇ b = { a ⊕ b }", "◇", "a ◇ b = { b ⊕ a }",
                    {"values": [["a", "b"], ["x", "y"]]}, "strings")
    assert strings["counterexample"] == {"inputs": ["a", "x"], "expected": "ax", "got": "xa"}
    permutation = check("a ◇ = { a }", "◇", "a ◇ = { a }",
                        {"literals": [["P[0, 1, 2, 3, 4]", "P[1, 0, 2, 3, 4]"]]}, "perm")
    assert permutation["equivalent"] and permutation["proof"] == "values"
    assert check(rules, "★", "a ★ = { a }", [-3, 3])["parse_error"]


def test_challenge_size_matches_simplify_count():
    from opulse.bench.families.common import count_operations

    definitions = [
        "a ◇ b = { (a + b) * 2 }",
        "a ◇ = { - 1, if a < - 2; a + 1, else }",
    ]
    for definition in definitions:
        assert size(definition) == count_operations(Workspace(definition).parser.parse(definition))


def test_challenge_steps_match_reference_interpreter_cost():
    from opulse.bench.families import common
    from opulse.discovery import metrics
    from tools.challenge_shorten import BASE, SEMANTICS, SYMBOLS

    rules = "a ◇ b = { a, if b <= 0; (a ◇ (b - 1)) + 2, else }"
    answer = "a ◇ b = { a + (b * 2) }"
    inputs = [[1, 0], [1, 2], [3, 4]]
    result = challenge_steps(rules, answer, inputs)
    ops = common.text_registry([answer], BASE, SYMBOLS, SEMANTICS)
    assert result["total"] == metrics.cost(ops, "a ◇ b", [tuple(row) for row in inputs])
    assert [row["steps"] for row in result["per_input"]] == [2, 2, 2]
    assert json.loads(challenge_steps_json(rules, answer, json.dumps(inputs))) == result
    assert challenge_steps(rules, "a ◇ b = { a + }", inputs)["parse_error"]


def test_challenge_checker_is_registered_only_on_challenge_pages():
    script = '<script src="../assets/js/challenge-check.js" defer></script>'
    pages = ["docs/challenge.md"]
    if (ROOT / "docs_zh").is_dir():
        pages.append("docs_zh/challenge.md")
    for page in pages:
        assert script in (ROOT / page).read_text(encoding="utf-8")
    assert "challenge-check.js" not in (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    assert (ROOT / "docs/assets/js/opulse-runtime.js").is_file()


def test_selector_worlds_run_from_bundle(builder):
    """Mirror the browser's bare Pyodide path with no editable install or PyYAML."""
    script = (ROOT / "docs" / "assets" / "js" / "playground.js").read_text(encoding="utf-8")
    defaults = {
        name: (ast.literal_eval(definition), ast.literal_eval(expression))
        for name, definition, expression in re.findall(
            r'^\s*(\w+): \{ definitions: (.+?), expression: (.+?), note:', script, re.M)
    }
    selectors = re.findall(r'state\.worlds = \[\.\.\.new Set\(\[(.*?)\]', script)
    assert selectors
    names = {name for selector in selectors for name in re.findall(r'"([a-z]+)"', selector)}
    index = json.loads((ROOT / "docs" / "assets" / "data" / "worlds" / "index.json").read_text())
    names.update(entry if isinstance(entry, str) else entry.get("id", entry.get("world", entry.get("name")))
                 for entry in index)
    assert names
    with tempfile.TemporaryDirectory() as temp:
        bundle = Path(temp)
        for path, content in builder.read_bundle().items():
            target = bundle / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        # -I -S leaves only stdlib paths. The page has no loadPackage/micropip call.
        probe = """
import importlib, json, pkgutil, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import opulse.worlds
from opulse.playground import available_worlds, run
names = set(json.loads(sys.argv[2]))
defaults = json.loads(sys.argv[3])
assert names <= set(available_worlds()), names - set(available_worlds())
for module in pkgutil.walk_packages(opulse.worlds.__path__, opulse.worlds.__name__ + "."):
    importlib.import_module(module.name)
for name in sorted(names):
    definition, expression = defaults.get(name, ("a ◇ = { a }", "3 ◇"))
    result = run(definition, expression, world=name)
    assert result["ok"], (name, result.get("error"))
assert "yaml" not in sys.modules and "z3" not in sys.modules
"""
        result = subprocess.run([sys.executable, "-I", "-S", "-c", probe, str(bundle),
                                 json.dumps(sorted(names)), json.dumps(defaults)],
                                capture_output=True, text=True)
        assert result.returncode == 0, result.stderr


def test_import_does_not_load_optional_dependencies():
    probe = "import opulse.playground, sys; assert 'z3' not in sys.modules; assert 'yaml' not in sys.modules"
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    subprocess.run([sys.executable, "-c", probe], env=env, check=True, capture_output=True, text=True)


def test_example_values_and_unique_ids(examples):
    ids = [example["id"] for example in examples]
    assert len(ids) == len(set(ids))
    for example in examples:
        result = run(example["definitions"], example["expression"])
        assert result["ok"], (example["id"], result.get("error"))
        assert result["value"] == example["value"], example["id"]


@pytest.fixture(scope="module")
def handwritten_workspace(examples):
    definitions = []
    seen = set()
    for example in examples:
        if example["group"] != "Written by hand" or not example["definitions"]:
            continue
        candidate = Workspace(example["definitions"])
        shapes = {(op.symbol, op.n_ary, op.unary_position) for op in candidate.defined}
        if seen & shapes:
            continue
        seen.update(shapes)
        definitions.append(example["definitions"])
    source = "\n".join(definitions)
    return source, Workspace(source)


def _random_expressions(workspace, seed, count):
    rng = random.Random(seed)
    atom_shapes = {(row["symbol"], row["shape"]) for row in atoms()}
    operators = [op for op in workspace.registry
                 if (op.symbol, "binary" if op.n_ary == BINARY else op.unary_position) in atom_shapes]
    operators += workspace.defined

    def make(depth, root=True):
        if depth == 0 or (not root and rng.random() < 0.42):
            return str(rng.randrange(31))
        op = rng.choice(operators)
        left = make(depth - 1, False)
        if op.n_ary == BINARY:
            text = f"{left} {op.symbol} {make(depth - 1, False)}"
        elif op.unary_position == PREFIX:
            text = f"{op.symbol} {left}"
        else:
            text = f"{left} {op.symbol}"
        return text if root else f"({text})"

    for _ in range(count):
        yield make(rng.choices((0, 1, 2, 3, 4), weights=(5, 55, 32, 7, 1))[0])


def test_random_expressions_agree_with_reference_and_compiled_runtime(handwritten_workspace):
    definitions, workspace = handwritten_workspace
    checked = 0
    for expression in _random_expressions(workspace, seed=2026, count=2200):
        result = run(definitions, expression)
        if not result["ok"] and "nested more than" in result["error"]["message"]:
            continue
        assert result["ok"], (expression, result.get("error"))
        tree = workspace.parse(expression)
        assert result["value"] == _value(workspace.oracle.evaluate_expr(_to_ast(tree), {}).value), expression
        assert result["value"] == _value(Evaluator(workspace.runtime).evaluate(tree).value), expression
        if not result["truncated"]:
            assert result["agrees"] is True, expression
            final = result["steps"][-1]["after"] if result["steps"] else result["expression"]
            assert final == result["value"], expression
        checked += 1
    assert checked >= 1900


def test_step_spans_chain_and_renderer(examples, handwritten_workspace):
    for name in ("composition", "branching", "factorial", "nan"):
        example = _example(examples, name)
        workspace = Workspace(example["definitions"])
        trace = workspace.reducer.reduce(workspace.parse(example["expression"]))
        renderer = workspace.renderer
        steps = run(example["definitions"], example["expression"])["steps"]
        assert steps, name
        assert len(steps) == len(trace.steps)
        for index, (step, raw_step) in enumerate(zip(steps, trace.steps)):
            before = step["before"]
            after = step["after"]
            focus = before[slice(*step["focus"])]
            replacement = after[slice(*step["new"])]
            assert focus == _subtree_text(raw_step.expression_before, raw_step.path, renderer)
            assert replacement == _subtree_text(raw_step.expression_after, raw_step.path, renderer)
            assert replacement in (step["replacement"], f"({step['replacement']})")
            if step["focus"] == [0, len(before)]:
                assert focus == before
            if index + 1 < len(steps):
                assert after == steps[index + 1]["before"]

    root_step = run("", "3 + 4")["steps"][0]
    assert root_step["focus"] == [0, len(root_step["before"])]
    assert root_step["before"][slice(*root_step["focus"])] == root_step["before"]

    _, workspace = handwritten_workspace
    renderer = ExpressionRenderer(Symbols())
    for expression in _random_expressions(workspace, seed=17, count=80):
        tree = workspace.parse(expression)
        paths = [()]
        for path in paths:
            node = tree
            for index in path:
                node = node.args[index]
            if isinstance(node, Call):
                paths.extend(path + (index,) for index in range(len(node.args)))
            text, span = _render_marked(tree, path, Symbols())
            assert text == renderer.full(tree)
            assert text[slice(*span)] == _subtree_text(tree, path, renderer)


def test_nan_causes_and_factorial_branches(examples):
    nan_example = _example(examples, "nan")
    steps = run(nan_example["definitions"], nan_example["expression"])["steps"]
    assert [step["nan_cause"] for step in steps if step["nan_cause"]] == [
        "division_by_zero", "nan_condition", "no_branch", "nan_input"]

    factorial = _example(examples, "factorial")
    expansions = [step for step in run(factorial["definitions"], factorial["expression"])["steps"]
                  if step["kind"] == "expand"]
    assert expansions
    for step in expansions:
        assert step["branch_index"] is not None
        assert step["branches"][-1]["index"] == step["branch_index"]
        assert step["branches"][-1]["truth"] is True
        assert all(branch["truth"] is False for branch in step["branches"][:-1])


def test_errors_include_positions_and_recursion_is_bounded():
    error = run("a ⊕ b = { a + }", "1")["error"]
    assert (error["where"], error["line"], error["column"]) == ("definitions", 1, 14)

    error = run("", "3 ⊙ 4")["error"]
    assert (error["where"], error["column"]) == ("expression", 2)

    error = run("a ⊕ b = { a ⊗ b }\na ⊗ b = { a ⊕ b }", "1")["error"]
    assert "cycle" in error["message"].lower()

    error = run("a ⁺ = { a }", "1")["error"]
    assert error["where"] == "definitions"

    error = run("a ⊕ b = { a +\n (b * ) }", "1")["error"]
    assert (error["where"], error["line"]) == ("definitions", 2)

    error = run("", "a + 1")["error"]
    assert error["where"] == "expression"

    result = run("a ↯ = { (a + 1) ↯ }", "1 ↯")
    assert result["ok"] is False
    assert "nested more than" in result["error"]["message"]


def test_composition_graph(examples):
    example = _example(examples, "composition")
    graph = run(example["definitions"], example["expression"])["graph"]
    nodes = {node["id"]: node for node in graph["nodes"]}
    by_symbol = {node["symbol"]: node for node in graph["nodes"]}
    assert by_symbol["⊕"]["kind"] == by_symbol["⊗"]["kind"] == "simple"
    assert {"source": by_symbol["⊗"]["id"], "target": by_symbol["⊕"]["id"]} in graph["edges"]
    assert all(nodes[edge["target"]]["column"] < nodes[edge["source"]]["column"]
               for edge in graph["edges"])
    assert by_symbol["⊕"]["used"] is True
    assert by_symbol["⊗"]["used"] is True
    assert by_symbol["+"]["used"] is True


def test_custom_atoms_are_registered_scoped_and_report_errors():
    cube = {"name": "cube", "symbol": "⊛", "arity": 1, "position": "postfix",
            "rule": "a ⊛ is a cubed.", "code": "def cube(a):\n    return a ** 3"}
    result = run("a ◇ = { a ⊛ }", "3 ◇", [cube])
    assert result["ok"] and result["value"] == "27" and result["agrees"]
    assert result["steps"][-1]["atom"] == "cube"
    assert any(node["rule"] == cube["rule"] for node in result["graph"]["nodes"])
    assert run("", "3 ⊛")["ok"] is False
    assert run("", "2 ⊛", [cube])["value"] == "8"
    assert any(row["name"] == "cube" for row in atoms(custom_atoms=[cube]))
    assert run("", "2 ⊛", [dict(cube, code="def cube(a):\n return a / 2")])["error"]["where"] == "atoms"
    for bad in (dict(cube, code="def cube(a):\n return ("),
                dict(cube, code="def wrong(a):\n return a"),
                dict(cube, arity=2), dict(cube, symbol="⁺")):
        error = run("", "2 ⊛", [bad])["error"]
        assert error["where"] == "atoms" and error["line"] == 1
    assert '"value": "27"' in run_json("", "3 ⊛", json.dumps([cube]))

    blend = {"name": "blend", "symbol": "⋄", "arity": 2, "position": "postfix",
             "rule": "a ⋄ b is twice a plus b.", "code": "def blend(a, b):\n    return 2 * a + b"}
    binary = run("a ◇ b = { a ⋄ b }", "3 ◇ 4", [blend])
    assert binary["ok"] and binary["value"] == "10" and binary["agrees"]


def test_world_examples_and_atom_isolation():
    examples = {
        "successor": ("a ◇ = { a ↑ }", "3 ◇", "4", "↑"),
        "integer": ("a ◇ = { # (a + 2) }", "3 ◇", "15", "#"),
        "bits": ("a ◇ b = { a ⊻ b }", "5 ◇ 3", "6", "⊻"),
        "strings": ("a ◇ b = { a ⊕ b }", '"ab" ◇ "cd"', '"abcd"', "⊕"),
        "lists": ("a ◇ b = { a ⊞ b }", "[1, 2] ◇ [3]", "[1, 2, 3]", "⊞"),
    }
    assert set(examples) <= set(available_worlds())
    for world, (definition, expression, value, symbol) in examples.items():
        result = run(definition, expression, world=world)
        assert result["ok"] and result["value"] == value and result["agrees"], world
        assert any(row["symbol"] == symbol for row in atoms(world)), world
    assert not any(row["symbol"] == "⊞" for row in atoms("successor"))
    assert run("", "1", world="missing")["error"]["where"] == "atoms"


# ------------------------------------------------------------------ atoms and settings panel

CUBE = {"name": "cube", "symbol": "⊛", "arity": 1, "position": "postfix", "rule": "a ⊛ is a cubed.",
        "code": "def cube(a):\n    return a ** 3"}


def _row(rows, name):
    return next(row for row in rows if row["name"] == name)


def test_atom_table_switches_renames_and_restores():
    rows = atom_table()
    assert [row["name"] for row in rows][:3] == ["add", "sub", "mul"]
    assert all(row["error"] is None and row["on"] for row in rows)
    add = _row(rows, "add")
    assert (add["symbol"], add["n_ary"], add["shape"], add["types"]) == ("+", 2, "binary", "int, int → int")

    config = {"off": ["mul"], "symbols": {"add": "⊞"}, "rules": {"add": "a ⊞ b adds."}}
    rows = atom_table(config=config)
    assert _row(rows, "mul")["on"] is False
    assert (_row(rows, "add")["symbol"], _row(rows, "add")["rule"]) == ("⊞", "a ⊞ b adds.")
    result = run("a ◇ b = { a ⊞ (b ⊞ 1) }", "2 ◇ 3", config=config)
    assert result["ok"] and result["value"] == "6" and result["agrees"]
    assert result["steps"][-1]["atom"] == "add"
    assert any(node["rule"] == "a ⊞ b adds." for node in result["graph"]["nodes"])
    assert run("", "2 * 3", config=config)["error"]["where"] == "expression"
    assert run("", "1 + 2", config=config)["ok"] is False
    # The next state without the config sees the shipped symbols again.
    assert run("", "1 + 2")["value"] == "3"
    assert _row(atom_table(), "add")["symbol"] == "+"

    world = {"symbols": {"bit_xor": "⊽"}}
    assert run("", "5 ⊽ 3", world="bits", config=world)["value"] == "6"
    assert run("", "5 ⊻ 3", world="bits")["value"] == "6"


@pytest.mark.parametrize(("symbol", "message"), [
    ("", "Write a symbol"), ("a b", "no spaces"), ("x1", "no digits"), ("⊞₁", "no digits"),
    ("³", "no digits"), ("(", "grammar uses"), ("⊞=", "grammar uses"), ("if", "keyword"),
    ("-", "already the symbol of sub"), ("*", "already the symbol of mul"),
])
def test_symbol_clashes_are_reported_per_row(symbol, message):
    row = _row(atom_table(config={"symbols": {"add": symbol}}), "add")
    assert row["error"] and message in row["error"]


def test_symbol_checks_allow_other_roles_and_detect_ambiguity():
    others = [("succ", "⁺", 1, "postfix"), ("sub", "-", 2, None)]
    assert symbol_problem("⁺", 2, None, others) is None  # a binary ⁺ next to the postfix one
    assert "ambiguous" in symbol_problem("--", 2, None, others + [("neg", "-", 1, "prefix")])
    assert "index character" in symbol_problem("◇x", 2, None, [], index_chars="xyz")
    assert symbol_problem("⊞", 2, None, others) is None
    neg = _row(atom_table(config={"symbols": {"neg": "~"}}), "neg")
    assert "cannot change" in neg["error"]
    off = _row(atom_table(config={"off": ["add"], "symbols": {"add": "("}}), "add")
    assert off["error"] is None  # an atom that is off is not checked


def test_custom_atom_rows_types_and_errors():
    repeat = {"name": "rep", "symbol": "⊜", "arity": 2, "types": "str, int -> str",
              "rule": "a ⊜ b repeats a b times.", "code": "def rep(a, b):\n    return a * b"}
    row = _row(atom_table("strings", [repeat]), "rep")
    assert (row["source"], row["custom"], row["types"], row["error"]) == ("custom", 0, "str, int → str", None)
    assert run("", '"ab" ⊜ 3', [repeat], "strings")["value"] == '"ababab"'
    for bad, text in ((dict(repeat, types="str -> str"), "arity"),
                      (dict(repeat, types="str, float -> str"), "unknown type"),
                      (dict(repeat, rule=""), "rule"), (dict(repeat, symbol="⊕"), "already the symbol"),
                      (dict(repeat, name="add", code="def add(a, b):\n    return a"), "already used")):
        rows = atom_table("strings", [bad])
        assert text in next(row for row in rows if row["custom"] == 0)["error"], bad
    assert run("", "1", [dict(repeat, types="str -> str")], "strings")["error"]["where"] == "atoms"


def test_settings_reach_evaluation_and_are_validated():
    bound = {"settings": {"semantics": {"bound": 100}}}
    assert run("", "60 + 50", config=bound)["value"] == "NaN"
    assert run("", "60 + 30", config=bound)["value"] == "90"
    legacy = {"settings": {"semantics": {"bound": 100, "mode": "legacy"}}}
    assert run("", "60 + 50", config=legacy)["value"] == "10"
    for settings, key in (({"semantics": {"bound": 0}}, "semantics.bound"),
                          ({"recursion": {"direct_bound": "x"}}, "recursion.direct_bound"),
                          ({"recursion": {"modulus_min": 9, "modulus_max": 3}}, "recursion.modulus_min"),
                          ({"recursion": {"style": "loop"}}, "recursion.style"),
                          ({"operators": {"index_chars": "1"}}, "operators.index_chars")):
        error = run("", "1", config={"settings": settings})["error"]
        assert error["where"] == "settings" and key in error["message"], settings
    values = json.loads(table_json("successor"))["settings"]
    assert values["recursion"]["style"] == "peano" and values["recursion"]["direct_bound"] == 5


def test_grow_runs_without_z3_and_fills_the_editor():
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    probe = ("import sys, json; from opulse.playground import grow; out = grow('', layers='3 2', seed=4); "
             "assert out['ok'], out; assert 'z3' not in sys.modules and 'yaml' not in sys.modules; "
             "print(json.dumps(out))")
    out = json.loads(subprocess.run([sys.executable, "-c", probe], env=env, check=True, capture_output=True,
                                    text=True).stdout)
    assert out["count"] == 5 and out["definitions"].count("\n") == 4
    result = run(out["definitions"], out["expression"])
    assert result["ok"] and result["value"] != "NaN" and result["agrees"]
    assert grow("", layers="3 2", seed=4)["definitions"] == out["definitions"]  # same seed, same set
    no_mul = grow("", None, {"off": ["mul"]}, "4 2", 4)
    assert no_mul["ok"] and " * " not in no_mul["definitions"]
    for world in ("successor", "atomic", "bits", "strings", "lists"):
        grown = grow(world, layers="3 2", seed=2)
        assert grown["ok"], (world, grown)
        assert run(grown["definitions"], grown["expression"], world=world)["ok"], world
    assert grow("", layers="50", seed=1)["error"]["where"] == "grow"
    assert grow("", None, {"off": ["mod"]}, "2 2", 1)["error"]["where"] == "grow"


def test_export_round_trip_through_yaml_and_the_cli(tmp_path):
    yaml = pytest.importorskip("yaml")
    from opulse.config import Settings

    config = {"off": ["popcount"], "symbols": {"reverse": "↩"}, "rules": {"add": "a + b adds."},
              "settings": {"semantics": {"bound": 100000}, "recursion": {"modulus_max": 6}}}
    out = export("", [CUBE], config, "3 2", 5)
    assert out["ok"]
    raw = yaml.safe_load(out["yaml"])
    assert raw == out["json"]
    settings = Settings.from_dict(raw)
    assert settings.semantics.bound == 100000 and settings.recursion.modulus_max == 6
    assert settings.operators.reject_dead_branches is False and settings.operators.reject_degenerate is False
    assert "--layers 3 2" in out["commands"] and "--seed 5" in out["commands"]

    (tmp_path / "world.yaml").write_text(out["yaml"], encoding="utf-8")
    (tmp_path / "world_atoms.py").write_text(out["plugin"], encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    subprocess.run([sys.executable, "world_atoms.py", "initial.jsonl"], cwd=tmp_path, env=env, check=True)
    symbols = [json.loads(line)["symbol"] for line in (tmp_path / "initial.jsonl").read_text().splitlines()]
    assert "↩" in symbols and "⊛" in symbols and "$" not in symbols
    command = " ".join(line.rstrip("\\ ") for line in out["commands"].splitlines()[1:]).split()
    assert command[0] == "opulse"
    subprocess.run([sys.executable, "-m", "opulse.cli.main", *command[1:]], cwd=tmp_path, env=env, check=True,
                   capture_output=True)
    rows = [json.loads(line) for line in (tmp_path / "operators.jsonl").read_text().splitlines()]
    cli = [row["definition"] for row in rows if row["definition"]]
    grown = grow("", [CUBE], config, "3 2", 5)
    assert sorted(cli) == sorted(grown["definitions"].split("\n"))
    assert run("", "21 ↩ ⊛", [CUBE], config=config)["value"] == "1728"
