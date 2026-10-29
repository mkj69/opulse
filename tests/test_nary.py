"""Operators with three or more arguments (call form) through every stage."""

import itertools
import json
import random

import pytest
import z3
from conftest import INITIAL_OPERATORS

from opulse.cli.main import main
from opulse.config import Settings, Symbols
from opulse.core import BINARY, BRANCH, NAN, SIMPLE, Operator, OperatorRegistry
from opulse.core.primitives import (
    CUSTOM,
    register_primitive,
    unregister_primitive,
    write_initial_set,
)
from opulse.core.types import same_value
from opulse.definition import ast
from opulse.definition.codegen import compile_definition, registry_resolver
from opulse.definition.parser import DefinitionParser, DefinitionSyntaxError
from opulse.expression.nodes import Call, Number, Variable, from_ast, from_dict, to_dict
from opulse.expression.render import ExpressionRenderer
from opulse.runtime import PythonRuntime
from opulse.solver.z3_encode import Z3Encoder, evaluate_concrete
from opulse.verify import Oracle, check_operator

B = 2**31 - 1
EDGES = [0, 1, -1, 2, -3, 7, -8, 100, -100, B, -B]


def define(registry, text, symbol, n_ary, position=None, kind=SIMPLE, symbols=None):
    """Register a hand-written definition with compiled code."""
    operator = Operator(func_id=f"h{len(registry)}", symbol=symbol, n_ary=n_ary, unary_position=position,
                        definition=text, definition_type=kind)
    parser = DefinitionParser(symbols or Symbols(), registry)
    code = compile_definition(parser.parse(text), operator.func_id, registry_resolver(registry, operator))
    operator.op_compute_func, operator.op_count_func = code.compute, code.count
    operator.dependencies = list(code.dependencies)
    operator.recursive_layer = registry.recursive_layer_of(operator)
    operator.id = len(registry) + 1
    registry.add(operator)
    return operator


def _recursion_values_match(oracle_value, got):
    return same_value(oracle_value, got)


def test_recursion_comparison_rejects_nan_mismatch():
    assert not _recursion_values_match(123, NAN)


# ------------------------------------------------------------------ notation


def test_symbols_operand_names_and_separator():
    s = Symbols()
    assert s.operands(1) == ("a",) and s.operands(2) == ("a", "b") and s.operands(4) == ("a", "b", "c", "d")
    assert s.call("⊕", ["1", "x", "5"]) == "⊕(1, x, 5)"
    custom = Symbols(operand_names=("x", "y", "z"), left_paren="[", right_paren="]", argument_separator="|")
    assert (custom.left_operand, custom.right_operand) == ("x", "y") and custom.max_arity == 3
    assert custom.call("⊕", ["x", "y", "z"]) == "⊕[x| y| z]"
    with pytest.raises(ValueError, match="names"):
        custom.operands(4)
    assert Symbols(left_operand="p", right_operand="q").operands(3) == ("p", "q", "c")
    with pytest.raises(ValueError, match="differs"):
        Symbols(left_operand="p", operand_names=("x", "y", "z"))
    with pytest.raises(ValueError, match="separator"):
        Symbols(argument_separator=";")
    with pytest.raises(ValueError, match="distinct"):
        Symbols(operand_names=("x", "y", "x"))
    loaded = Settings.from_dict({"symbols": {"operand_names": ["u", "v", "w"]},
                                 "operators": {"arity_weights": {"1": 1, "3": 2}}})
    assert loaded.symbols.operand_names == ("u", "v", "w")
    assert loaded.operators.arity_weights == {1: 1.0, 3: 2.0}


def test_operator_record_and_atoms_accept_three_arguments(tmp_path):
    op = Operator(func_id="x", symbol="⊕", n_ary=3, unary_position="prefix")
    assert op.unary_position is None and op.apply_str("1", "2", "3") == "⊕(1, 2, 3)"
    assert op.apply_str("1", "2", "3", symbols=Symbols(left_paren="[", right_paren="]")) == "⊕[1, 2, 3]"
    with pytest.raises(ValueError):
        Operator(func_id="y", symbol="⊕", n_ary=0)
    register_primitive("mid", "⩙", lambda a, b, c: sorted((a, b, c))[1], n_ary=3,
                       rule="⩙(a, b, c) is the middle value of a, b and c.")
    try:
        path = write_initial_set(tmp_path / "start.jsonl", ["add", "neg", "mid"])
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        mid = rows[-1]
        assert mid["n_ary"] == 3 and mid["unary_position"] is None and mid["priority"] is None
        registry = OperatorRegistry.from_jsonl(path)
        runtime = PythonRuntime(registry)
        op = registry.find("⩙", 3)
        assert runtime.compute(op)(5, -1, 3) == 3 and runtime.compute(op)(NAN, 1, 2) is NAN
    finally:
        unregister_primitive("mid")
    with pytest.raises(ValueError, match="one or more"):
        register_primitive("bad", "⩚", lambda: 0, n_ary=0, rule="x")


@pytest.mark.parametrize("text", [
    "⊕(a, b, c) = { (a + b) * c }",
    "⊕(a, b, c) = { (a + b) * c, if c > 0 and b < 3; ⊕(b, a, c - 1) @, if c < 0; - a, else }",
    "⊕(a, b, c, d) = { ⊕(d, c, b, a) + ⊕(a, a, a, 1), if d == 0; (a * b) - (c % d), else }",
    "a ⊗ b = { ⊛(a, b @, - b) }",
])
def test_definition_round_trip(registry, text):
    parser = DefinitionParser(Symbols(), registry)
    known = DefinitionParser(Symbols(), OperatorRegistry([*registry, Operator("s3", "⊛", 3, definition="x")]))
    use = known if "⊛" in text else parser
    parsed = use.parse(text)
    assert ast.render_definition(parsed, Symbols()) == text
    assert use.parse(ast.render_definition(parsed, Symbols())) == parsed


def test_custom_notation_round_trip(registry):
    symbols = Symbols(operand_names=("x", "y", "z"), left_paren="[", right_paren="]", argument_separator="|")
    text = "⊕[x| y| z] = { [x + y] * z, if z > 0; ⊕[y| x| z - 1], else }"
    parsed = DefinitionParser(symbols, registry).parse(text)
    assert parsed.parameters == ("x", "y", "z")
    assert ast.render_definition(parsed, symbols) == text


def test_call_form_parsing_and_prefix_reading(registry):
    ops = OperatorRegistry([*registry, Operator("p1", "⊕", 1, "prefix", definition="⊕ a = { a }"),
                            Operator("c3", "⊕", 3, definition="⊕(a, b, c) = { a }")])
    parser = DefinitionParser(Symbols(), ops)
    prefix = parser.parse_expr("⊕ (1 + 2)", expression_mode=True)
    assert prefix.n_ary == 1 and prefix.unary_position == "prefix"
    call = parser.parse_expr("- ⊕(1 + 2 * 3, - 4, 5 @) @ + 1", expression_mode=True)
    assert call.symbol == "+" and call.args[0].symbol == "-"
    inner = call.args[0].args[0]
    assert inner.symbol == "@" and inner.args[0].n_ary == 3
    with pytest.raises(DefinitionSyntaxError):
        DefinitionParser(Symbols(), OperatorRegistry([*registry, Operator("c3", "⊕", 3, definition="x")])
                         ).parse_expr("⊕(1, 2)", expression_mode=True)
    with pytest.raises(DefinitionSyntaxError, match="three or more"):
        parser.parse("⊕(a, b) = { a }")
    # strict parsing (step grading) still wants brackets inside the arguments
    parser.parse_expr("⊕((1 + 2) * 3, 4, 5)", expression_mode=True, strict=True)
    with pytest.raises(DefinitionSyntaxError):
        parser.parse_expr("⊕(1 + 2 * 3, 4, 5)", expression_mode=True, strict=True)


def test_expression_rendering_and_tree_json(registry):
    op = Operator("c3", "⊕", 3, definition="⊕(a, b, c) = { a }")
    ops = OperatorRegistry([*registry, op])
    plus = ops.find("+", BINARY)
    tree = Call(plus, (Call(op, (Call(plus, (Number(1), Number(2))), Number(3), Variable("a"))), Number(4)))
    renderer = ExpressionRenderer(Symbols())
    assert renderer.full(tree) == "⊕(1 + 2, 3, a) + 4"
    assert from_dict(to_dict(tree), ops) == tree
    parser = DefinitionParser(Symbols(), ops)
    assert from_ast(parser.parse_expr(renderer.minimal(tree), expression_mode=True), ops) == tree


# ------------------------------------------------- interpreter, code, z3, SMT

TERNARY = [
    ("⊕(a, b, c) = { (a + b) * c }", BRANCH),
    ("⊕(a, b, c) = { (a + b) * c, if c > 0 and b < 3; (a @) - (b % c), if c < 0; # a, else }", BRANCH),
    ("⊕(a, b, c) = { a, if a >= b and a >= c; b, if b >= c; c, else }", BRANCH),
]


@pytest.mark.parametrize("text,kind", TERNARY)
def test_ternary_interpreter_compiled_and_z3_agree(registry, text, kind):
    op = define(registry, text, "⊕", 3, kind=kind)
    oracle = Oracle(registry)
    runtime = PythonRuntime(registry)
    assert not check_operator(op, runtime.evaluate(op), oracle, random.Random(0), random_trials=300)
    encoder = Z3Encoder(oracle)
    for args in itertools.product([0, 1, -1, 7, -8, B, NAN], repeat=3):
        expected = oracle.evaluate(op, args).value
        got = evaluate_concrete(encoder, op, args)
        assert got is expected if expected is NAN else got == expected, (args, got, expected)


def _bound():
    from opulse.config import RecursionSettings

    return RecursionSettings().direct_bound


def primitive_definitions(t: int):
    """Hand-written primitive recursions in ordinary syntax (counter bounded by ``t``)."""
    return {
        # multiplication from addition: h(a, 0) = 0; h(a, n) = h(a, n - 1) + a
        "mul": f"a ⊠ b = {{ 0, if b == 0; (a ⊠ (b - 1)) + a, if b > 0 and b <= {t}; "
               f"(a ⊠ (b + 1)) - a, if b < 0 and b >= - {t} }}",
        # sum 1..n: the step uses the counter: h(n) = h(n - 1) + (n - 1) + 1
        "sum": f"a ∑ = {{ 0, if a == 0; ((a - 1) ∑) + ((a - 1) + 1), if a > 0 and a <= {t}; "
               f"((a + 1) ∑) - (a + 1), if a < 0 and a >= - {t} }}",
        # three parameters, step reads the counter: h(x, y, n) = h(x, y, n - 1) + x * (n - 1) + y
        "lin": f"ρ(a, b, c) = {{ a - b, if c == 0; ρ(a, b, c - 1) + ((a * (c - 1)) + b), if c > 0 and c <= {t}; "
               f"ρ(a, b, c + 1) - b, if c < 0 and c >= - {t} }}",
    }


def test_primitive_recursion_by_hand(registry):
    t = _bound()
    texts = primitive_definitions(t)
    mul = define(registry, texts["mul"], "⊠", 2, kind="recursive_definition")
    total = define(registry, texts["sum"], "∑", 1, "postfix", kind="recursive_definition")
    lin = define(registry, texts["lin"], "ρ", 3, kind="recursive_definition")
    oracle = Oracle(registry)
    runtime = PythonRuntime(registry)
    for a in range(-5, 6):
        for b in range(-t - 2, t + 3):
            want = a * b if abs(b) <= t else NAN
            got = runtime.compute(mul)(a, b)
            assert got is want if want is NAN else got == want
            assert _recursion_values_match(oracle.evaluate(mul, (a, b)).value, got)
    for n in range(t + 3):
        want = n * (n + 1) // 2 if n <= t else NAN
        got = oracle.evaluate(total, (n,)).value
        assert got is want if want is NAN else got == want
    for x, y, n in itertools.product(range(-3, 4), range(-3, 4), range(t + 2)):
        want = x - y + sum(x * k + y for k in range(n)) if n <= t else NAN
        got = runtime.compute(lin)(x, y, n)
        assert got is want if want is NAN else got == want
    encoder = Z3Encoder(oracle)
    for op in (mul, total, lin):
        assert not check_operator(op, runtime.evaluate(op), oracle, random.Random(1), random_trials=100)
        grid = itertools.product([0, 1, -1, 3, t, t + 1, -t, -t - 1, NAN], repeat=op.n_ary)
        for args in itertools.islice(grid, 400):
            expected = oracle.evaluate(op, args).value
            got = evaluate_concrete(encoder, op, args)
            assert got is expected if expected is NAN else got == expected, (op.symbol, args)


def test_addition_from_successor(tmp_path):
    t = _bound()
    registry = OperatorRegistry.from_jsonl(INITIAL_OPERATORS.parent / "atomic_operators.jsonl")
    add = define(registry, f"a ⊞ b = {{ a, if b == 0; (a ⊞ (b ⁻)) ⁺, if b > 0 and b <= {t}; "
                           f"(a ⊞ (b ⁺)) ⁻, if b < 0 and b >= - {t} }}", "⊞", 2, kind="recursive_definition")
    oracle = Oracle(registry)
    for a, b in itertools.product(range(-4, 5), range(-t - 2, t + 3)):
        want = a + b if abs(b) <= t else NAN
        got = oracle.evaluate(add, (a, b)).value
        assert got is want if want is NAN else got == want


def test_smt_export_of_ternary_and_primitive(registry):
    from opulse.solver.smt import export, prelude

    t = _bound()
    tern = define(registry, TERNARY[1][0], "⊕", 3, kind=BRANCH)
    lin = define(registry, primitive_definitions(t)["lin"], "ρ", 3, kind="recursive_definition")
    encoder = Z3Encoder(Oracle(registry))
    base = prelude(encoder)
    for op in (tern, lin):
        assert export(op, encoder, base)  # raises if a checked point disagrees


def test_cython_matches_reference_on_nary(registry, tmp_path):
    pytest.importorskip("Cython")
    from opulse.runtime.cython_backend import CythonRuntime

    tern = define(registry, TERNARY[1][0], "⊕", 3, kind=BRANCH)
    lin = define(registry, primitive_definitions(_bound())["lin"], "ρ", 3, kind="recursive_definition")
    compiled = CythonRuntime(registry, tmp_path / "build", jobs=1)
    oracle = Oracle(registry)
    for op in (tern, lin):
        assert not check_operator(op, compiled.evaluate(op), oracle, random.Random(2), random_trials=100)


def test_properties_for_three_arguments(registry):
    from opulse.solver.properties import PropertyChecker

    op = define(registry, TERNARY[0][0], "⊕", 3, kind=BRANCH)
    checker = PropertyChecker(Z3Encoder(Oracle(registry)))
    properties = checker.check_all(op)
    assert set(properties) == {"symmetric", "idempotent"}
    assert properties["symmetric"]["status"] == "refuted"
    with pytest.raises(ValueError, match="3-ary"):
        checker.check(op, "commutative")


def test_holes_through_a_ternary_operator(registry):
    from opulse.solver.holes import HoleSolver

    op = define(registry, TERNARY[0][0], "⊕", 3, kind=BRANCH)
    oracle = Oracle(registry)
    tree = Call(op, (Number(2), Variable("x"), Number(3)))  # (2 + x) * 3
    found = HoleSolver(Z3Encoder(oracle), oracle).solve(tree, 21)
    assert found.values == [5]


# -------------------------------------------------------------- generation


@pytest.fixture(scope="module")
def ternary_factory():
    from opulse.generation.pipeline import OperatorFactory, build_layers
    from opulse.generation.priority import assign_priorities

    settings = Settings.from_dict({"operators": {"arity_weights": {1: 0.3, 2: 0.4, 3: 0.3}},
                                   "recursion": {"style": "primitive", "direct_bound": 6}})
    registry = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
    factory = OperatorFactory(settings, registry, random.Random(3))
    build_layers(factory, [8, 6, 5])
    assign_priorities(registry, random.Random(0))
    return factory


def _step_reads_counter(op, oracle) -> bool:
    from opulse.language.describe import _step_reads_counter

    return _step_reads_counter(oracle._definition_of(op))


def test_generated_ternary_and_primitive_operators(ternary_factory):
    registry = ternary_factory.registry
    generated = [op for op in registry if op.definition is not None]
    assert any(op.n_ary == 3 for op in generated)
    assert all(op.priority is None for op in generated if op.n_ary == 3)
    recursive = [op for op in generated if op.definition_type == "recursive_definition"]
    assert recursive
    oracle = Oracle(registry, ternary_factory.settings.symbols)
    assert all(_step_reads_counter(op, oracle) for op in recursive)
    parser = DefinitionParser(Symbols(), registry)
    for op in generated:
        definition = parser.parse(op.definition)
        assert ast.render_definition(definition, Symbols()) == op.definition
        params = set(definition.parameters)
        assert params == set(Symbols().operands(op.n_ary))
    runtime = PythonRuntime(registry)
    for op in recursive:  # bounded by recursion.direct_bound: NaN beyond, as in the direct style
        point = tuple([1] * (op.n_ary - 1) + [7])
        assert runtime.compute(op)(*point) is NAN
    for op in generated:
        assert not check_operator(op, runtime.evaluate(op), oracle, random.Random(5), random_trials=50)


def test_default_arity_weights_draw_as_before():
    from opulse.config import OperatorSettings
    from opulse.generation.symbols import SymbolFactory

    old = random.Random(9)
    expected = []
    for _ in range(50):
        expected.append((2, None) if old.random() < 0.5 else (1, old.choice(("prefix", "postfix"))))
    factory = SymbolFactory(OperatorSettings(), random.Random(9))
    assert [factory.new_shape() for _ in range(50)] == expected
    only3 = SymbolFactory(OperatorSettings(arity_weights={3: 1.0}), random.Random(9))
    assert {only3.new_shape() for _ in range(20)} == {(3, None)}


def test_shape_index_names_follow_arity_weights():
    from opulse.config import OperatorSettings
    from opulse.generation.symbols import ShapeIndexFactory, SymbolFactory

    legacy = SymbolFactory(OperatorSettings(), random.Random(9))
    shaped = ShapeIndexFactory(OperatorSettings(), random.Random(9))
    assert [shaped.new_shape() for _ in range(50)] == [legacy.new_shape() for _ in range(50)]
    only3 = ShapeIndexFactory(OperatorSettings(arity_weights={3: 1.0}), random.Random(9))
    assert {only3.new_shape() for _ in range(20)} == {(3, None)}


def test_ternary_generation_uses_shape_index_names(tmp_path):
    config = tmp_path / "c.yaml"
    config.write_text("operators: {arity_weights: {1: 0.3, 2: 0.3, 3: 0.4}}\n")
    out = tmp_path / "ops.jsonl"
    assert main(["operators", "--config", str(config), "--out", str(out), "--layers", "4", "3", "--seed", "1"]) == 0
    ternary = [r for r in map(json.loads, out.read_text().splitlines()) if r["n_ary"] == 3 and r["definition"]]
    assert ternary
    for row in ternary:
        shape, index = row["symbol"][0], row["symbol"][1:]
        assert shape in "■□▲△▼▽◆◇●○★☆♠♣♥♦♤♧♡♢" and index and all(c in "₀₁₂₃₄₅₆₇₈₉" for c in index)
        assert row["definition"].startswith(f"{row['symbol']}(a, b, c) = ")


def test_acceptance_checks_on_ternary_drafts():
    from opulse.generation import checks
    from opulse.generation.drafts import Draft

    def draft(text, kind=SIMPLE):
        definition = DefinitionParser(Symbols(), OperatorRegistry.from_jsonl(INITIAL_OPERATORS)).parse(text)
        return Draft("⊕", 3, None, definition, kind)

    assert checks.uses_all_parameters(draft("⊕(a, b, c) = { a + b }")) == "unused parameter ['c']"
    assert checks.uses_all_parameters(draft("⊕(a, b, c) = { (a + b) * c }")) is None
    with_g = OperatorRegistry([*OperatorRegistry.from_jsonl(INITIAL_OPERATORS),
                               Operator("g3", "⊛", 3, definition="⊛(a, b, c) = { a }")])
    renaming = Draft("⊕", 3, None, DefinitionParser(Symbols(), with_g).parse("⊕(a, b, c) = { ⊛(c, b, a) }"),
                     SIMPLE)
    assert checks.not_a_renaming(renaming) == "single call of the same arity"


def test_custom_notation_generation():
    from opulse.generation.pipeline import OperatorFactory, build_layers

    symbols = {"operand_names": ["x", "y", "z"], "left_paren": "[", "right_paren": "]", "argument_separator": "|"}
    settings = Settings.from_dict({"symbols": symbols, "operators": {"arity_weights": {2: 1, 3: 1}},
                                   "expressions": {"variables": ["x", "y"]}})
    registry = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
    build_layers(OperatorFactory(settings, registry, random.Random(4)), [6, 3])
    ternary = [op for op in registry if op.definition and op.n_ary == 3]
    assert ternary and all(op.definition.split(" = ")[0].endswith("[x| y| z]") for op in ternary)
    oracle = Oracle(registry, settings.symbols)
    runtime = PythonRuntime(registry)
    for op in ternary:
        assert not check_operator(op, runtime.evaluate(op), oracle, random.Random(1), random_trials=30)


def test_too_few_names_for_the_arity():
    from opulse.generation.pipeline import OperatorFactory

    settings = Settings.from_dict({"symbols": {"operand_names": ["x", "y", "z"]},
                                   "operators": {"arity_weights": {4: 1}}})
    with pytest.raises(ValueError, match="names"):
        OperatorFactory(settings, OperatorRegistry.from_jsonl(INITIAL_OPERATORS), random.Random(0))


# ------------------------------------------- pipeline: datasets, bench, aliases


@pytest.fixture
def mid_atom():
    register_primitive("mid", "⩙", lambda a, b, c: sorted((a, b, c))[1], n_ary=3,
                       rule="⩙(a, b, c) is the middle value of a, b and c.",
                       z3=lambda a, b, c: z3.If(z3.Or(z3.And(a <= b, b <= c), z3.And(c <= b, b <= a)), b,
                                                z3.If(z3.Or(z3.And(b <= a, a <= c), z3.And(c <= a, a <= b)), a, c)))
    yield
    for name in list(CUSTOM):
        unregister_primitive(name)


@pytest.fixture
def ternary_set(mid_atom, tmp_path):
    initial = write_initial_set(tmp_path / "start.jsonl",
                                ["add", "sub", "mul", "mod", "neg", "reverse", "succ", "pred", "mid"])
    config = tmp_path / "ternary.yaml"
    config.write_text("operators: {arity_weights: {1: 0.3, 2: 0.4, 3: 0.3}}\n"
                      "recursion: {style: primitive, direct_bound: 6}\n")
    ops = tmp_path / "ops.jsonl"
    assert main(["operators", "--config", str(config), "--initial", str(initial), "--out", str(ops),
                 "--layers", "8", "5", "3", "--seed", "2"]) == 0
    return config, ops


def test_datasets_and_bench_with_ternary_operators(ternary_set, tmp_path):
    config, ops = ternary_set
    registry = OperatorRegistry.from_jsonl(ops)
    assert any(op.n_ary == 3 and op.definition for op in registry)
    assert any(op.definition and "⩙(" in op.definition for op in registry)
    for lang in ("en", "zh"):
        out = tmp_path / f"expr_{lang}.jsonl"
        assert main(["expressions", "--config", str(config), "--operators", str(ops), "--out", str(out),
                     "--count", "25", "--cot", lang, "--seed", "1"]) == 0
        assert main(["verify", "--config", str(config), "--operators", str(ops), "--expressions", str(out)]) == 0
    records = [json.loads(line) for line in (tmp_path / "expr_en.jsonl").read_text().splitlines()]
    parser = DefinitionParser(Symbols(), registry)
    for record in records:
        tree = from_dict(record["tree"], registry)
        assert from_ast(parser.parse_expr(record["expression_plain"], expression_mode=True), registry) == tree
    for naming in ("symbols", "pseudo", "english"):
        tasks = tmp_path / f"tasks_{naming}.jsonl"
        assert main(["bench", "build", "--config", str(config), "--operators", str(ops), "--out", str(tasks),
                     "--count", "12", "--max-depth", "3", "--naming", naming, "--format", "steps",
                     "--seed", "5"]) == 0
        assert main(["bench", "check", "--config", str(config), "--tasks", str(tasks),
                     "--operators", str(ops)]) == 0
        responses = tmp_path / f"ref_{naming}.jsonl"
        assert main(["bench", "run", "--tasks", str(tasks), "--out", str(responses), "--reference"]) == 0
        summary = tmp_path / f"summary_{naming}.json"
        assert main(["bench", "score", "--config", str(config), "--tasks", str(tasks),
                     "--responses", str(responses), "--operators", str(ops), "--out", str(summary)]) == 0
        assert json.loads(summary.read_text())["accuracy"] == 1.0
    prompts = [json.loads(line) for line in (tmp_path / "tasks_symbols.jsonl").read_text().splitlines()]
    called = [t for t in prompts if any(op.n_ary == 3 and op.definition in t["definitions"] for op in registry)]
    assert called and all("call form" in t["prompt"] for t in called)
    assert all("call form" not in t["prompt"] for t in prompts
               if not any("(" in d.split(" = ")[0] for d in t["definitions"]) and "⩙" not in t["prompt"])


def test_step_grading_of_ternary_rewrites(registry):
    from opulse.verify.steps import check_steps, step_lines

    op = define(registry, "⊕(a, b, c) = { (a + b) * c, if c > 0; a - b, else }", "⊕", 3, kind=BRANCH)
    parser = DefinitionParser(Symbols(), registry)
    oracle = Oracle(registry)
    start = from_ast(parser.parse_expr("⊕(1, 2, 1 + 2) + 1", expression_mode=True), registry)
    assert start.args[0].operator is op
    good = check_steps(start, step_lines("= ⊕(1, 2, 3) + 1\n= ((1 + 2) * 3) + 1\n= (3 * 3) + 1\n= 9 + 1\n= 10"),
                       parser, registry, oracle, 10)
    assert good.all_valid and good.final_correct and good.single_steps == 5
    wrong_branch = check_steps(start, step_lines("= ⊕(1, 2, 3) + 1\n= (1 - 2) + 1"), parser, registry, oracle, 10)
    assert wrong_branch.first_error == 1
    jump = check_steps(start, step_lines("= ⊕(1, 2, 3) + 1\n= 9 + 1\n= 10"), parser, registry, oracle, 10)
    assert jump.all_valid and jump.single_steps == 3 - 1


def test_aliases_on_ternary_operators(ternary_factory):
    from opulse.expression.aliases import AliasMap, alias_tree, aliased_registry

    registry = ternary_factory.registry
    oracle = Oracle(registry)
    ternary = [op for op in registry if op.definition and op.n_ary == 3]
    for style in ("pseudo", "english"):
        alias = AliasMap.build(registry, random.Random(1), style)
        renamed = aliased_registry(registry, alias)
        renamed_oracle = Oracle(renamed)
        for op in ternary:
            copy = renamed.get(op.func_id)
            assert copy.definition.startswith(f"{copy.symbol}(a, b, c) = ")
            for args in [(1, 2, 3), (-4, 0, 7), (50, 60, 70)]:
                assert renamed_oracle.evaluate(copy, args).value == oracle.evaluate(op, args).value or \
                    oracle.evaluate(op, args).value is NAN
        tree = Call(ternary[0], (Number(1), Number(2), Number(3)))
        shown = ExpressionRenderer(Symbols()).minimal(alias_tree(tree, renamed))
        assert shown.startswith(alias.symbol_to_word[(ternary[0].symbol, 3, None)] + "(")


def test_leakage_and_describe_on_ternary_operators(ternary_factory):
    from opulse.bench.splits import leakage
    from opulse.language.describe import annotate

    registry = ternary_factory.registry
    report = leakage(registry, registry)
    defined = sum(1 for op in registry if op.definition)
    assert report["structural"]["shared"] == defined
    rows = list(annotate(registry))
    ternary = [r for r in rows if r["n_ary"] == 3 and r["definition"]]
    assert ternary and all("(a, b, c)" in r["nl_description_en"] for r in ternary)
    recursive = [r for r in rows if r["definition_type"] == "recursive_definition"]
    assert all("stepped counter" in r["nl_description_en"] for r in recursive)


def test_equivalences_with_ternary_operators(registry):
    from opulse.solver.equivalence import EquivalenceChecker, equivalent_operators

    first = define(registry, "⊕(a, b, c) = { (a + b) * c }", "⊕", 3, kind=SIMPLE)
    second = define(registry, "⊗(a, b, c) = { c * (b + a) }", "⊗", 3, kind=SIMPLE)
    checker = EquivalenceChecker(Z3Encoder(Oracle(registry)))
    pairs = equivalent_operators(registry, checker, [first, second])
    assert len(pairs) == 1 and pairs[0][2].status == "proved"


def test_analyze_command_on_ternary_operators(ternary_set, tmp_path):
    config, ops = ternary_set
    out = tmp_path / "analyzed.jsonl"
    assert main(["analyze", "--config", str(config), "--operators", str(ops), "--out", str(out)]) == 0
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert any(r["n_ary"] == 3 and r["definition"] and r["z3"] for r in rows)


def test_trace_and_narration_in_call_form(registry):
    from opulse.language.narrate import narrate
    from opulse.trace import Reducer
    from opulse.verify import verify_trace

    t = _bound()
    op = define(registry, TERNARY[1][0], "⊕", 3, kind=BRANCH)
    lin = define(registry, primitive_definitions(t)["lin"], "ρ", 3, kind="recursive_definition")
    parser = DefinitionParser(Symbols(), registry)
    tree = from_ast(parser.parse_expr("⊕(1, 2, 3) + ρ(2, 1, 3)", expression_mode=True), registry)
    trace = Reducer(registry, PythonRuntime(registry), parser).reduce(tree)
    verify_trace(trace, Oracle(registry))
    assert trace.value == (1 + 2) * 3 + (2 - 1 + 1 + 3 + 5)
    renderer = ExpressionRenderer(Symbols())
    english, chinese = narrate(trace, renderer, "en"), narrate(trace, renderer, "zh")
    assert "`⊕(1, 2, 3) + ρ(2, 1, 3)`" in english and "ρ(2, 1, 3 - 1)" in english
    assert "unfold operator `⊕` on inputs `1, 2, 3`" in english and "展开运算符 `ρ`" in chinese
    assert op.n_ary == lin.n_ary == 3


def test_other_commands_on_ternary_operators(ternary_set, tmp_path):
    config, ops = ternary_set
    expr = tmp_path / "expr.jsonl"
    assert main(["expressions", "--config", str(config), "--operators", str(ops), "--out", str(expr),
                 "--count", "30", "--seed", "4"]) == 0
    assert main(["viz", "--operators", str(ops), "--expressions", str(expr), "--out", str(tmp_path / "report")]) == 0
    assert any("call" in p.read_text(errors="ignore") for p in (tmp_path / "report").rglob("*") if p.is_file())
    assert main(["audit-data", str(expr), "--operators", str(ops), "--out", str(tmp_path / "audit.json")]) in (0, 1)
    assert main(["describe", "--operators", str(ops), "--out", str(tmp_path / "described.jsonl")]) == 0
    assert main(["holes", "--config", str(config), "--operators", str(ops), "--out", str(tmp_path / "holes.jsonl"),
                 "--count", "4", "--seed", "1"]) == 0
    assert main(["equivalences", "--config", str(config), "--operators", str(ops),
                 "--out", str(tmp_path / "eq.jsonl"), "--count", "5"]) == 0


def test_primitive_style_on_the_atomic_set():
    from opulse.generation.pipeline import OperatorFactory, build_layers

    settings = Settings.from_dict({"recursion": {"style": "primitive", "direct_bound": 5}})
    registry = OperatorRegistry.from_jsonl(INITIAL_OPERATORS.parent / "atomic_operators.jsonl")
    factory = OperatorFactory(settings, registry, random.Random(6))
    build_layers(factory, [6, 3])
    recursive = [op for op in registry if op.definition_type == "recursive_definition"]
    assert recursive and all("⁻)" in op.definition and "<= 5" in op.definition for op in recursive)
    oracle = Oracle(registry)
    assert all(_step_reads_counter(op, oracle) for op in recursive)
    from opulse.language.describe import Describer

    assert "Each step reads the stepped counter as well as the previous result." in \
        Describer(registry, settings).describe(recursive[0], "en")
    assert "每一步除了上一步的结果，还读取走过一步后的计数器。" in \
        Describer(registry, settings).describe(recursive[0], "zh")
    with pytest.raises(ValueError, match="primitive"):
        OperatorFactory(settings, OperatorRegistry([op for op in registry if op.definition is None
                                                    and op.symbol not in ("⁻", "⁺")]), random.Random(0))


def test_names_and_separator_are_validated():
    from opulse.definition.parser import DefinitionSyntaxError

    with pytest.raises(DefinitionSyntaxError):  # c is a parameter only of operators that declare it
        DefinitionParser(Symbols()).parse("a ⊕ b = { c }")
    for bad in [("a", "b", "if"), ("a", "b", "NaN"), ("a", "b", "x_y")]:
        with pytest.raises(ValueError):
            Symbols(operand_names=bad)
    with pytest.raises(ValueError, match="separator"):
        DefinitionParser(Symbols(argument_separator="+"), OperatorRegistry.from_jsonl(INITIAL_OPERATORS))
