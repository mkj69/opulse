import random
from collections import Counter

import pytest
from conftest import INITIAL_OPERATORS

from opulse.config import OperatorSettings, Settings
from opulse.core import BINARY, RECURSIVE
from opulse.definition.parser import DefinitionParser
from opulse.generation.pipeline import OperatorFactory, build_layers, layer_plan
from opulse.generation.priority import assign_priorities
from opulse.generation.symbols import SymbolFactory, build_alphabet


def test_alphabet_excludes_ascii_and_lookalikes():
    alphabet = set(SymbolFactory(OperatorSettings()).alphabet)
    assert not alphabet & set("+-*/%=<>|")
    assert not alphabet & set("−∕∗∖≤≥≠≡∣")  # U+2212, U+2215, U+2217, ...
    assert "⊕" in alphabet
    legacy = build_alphabet(("2200-22FF",), "+-*/%", False)
    assert "−" in legacy and "+" in legacy


def test_named_symbol_sets():
    from opulse.generation.symbols import NAMED_SETS, alphabet_for

    assert set(alphabet_for(OperatorSettings(symbol_sets=("suits",)))) == set(NAMED_SETS["suits"])
    for name, chars in NAMED_SETS.items():  # every listed character survives the look-alike filter
        assert set(alphabet_for(OperatorSettings(symbol_sets=(name,)))) == set(chars), name
    assert not set(NAMED_SETS["greek"]) & set("ΑΒΕΖΗΙΚΜΝΟΡΤΥΧ")  # Greek capitals that look Latin
    extra = alphabet_for(OperatorSettings(symbol_sets=(), symbol_chars="♪♫"))
    assert extra == ("♪", "♫")
    with pytest.raises(ValueError, match="unknown operators.symbol_sets"):
        alphabet_for(OperatorSettings(symbol_sets=("emoji",)))
    with pytest.raises(ValueError, match="non-ASCII"):
        alphabet_for(OperatorSettings(symbol_chars="ab"))


def test_layer_plan_puts_recursive_first_and_respects_totals():
    plan = layer_plan(10, 2, (0.4, 0.4, 0.2), random.Random(0))
    assert len(plan) == 10 and plan[:2] == [RECURSIVE, RECURSIVE]
    assert RECURSIVE not in layer_plan(10, 0, (0.4, 0.4, 0.2), random.Random(0))
    assert layer_plan(5, 1, (0.5, 0.5, 0.0), random.Random(0))[0] == RECURSIVE  # a recursive seed is forced


@pytest.fixture(scope="module")
def grown():
    from conftest import INITIAL_OPERATORS

    from opulse.core import OperatorRegistry

    registry = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
    factory = OperatorFactory(Settings(), registry, random.Random(7))
    build_layers(factory, [30, 20, 15, 10])
    return factory


def test_layers_and_kinds(grown):
    generated = [op for op in grown.registry if op.definition is not None]
    assert len(generated) == 75
    layers = Counter(op.recursive_layer for op in generated)
    assert layers == {0: 30, 1: 20, 2: 15, 3: 10}
    assert all(op.recursive_layer >= 1 for op in generated if op.definition_type == RECURSIVE)


def test_generated_definitions_parse_back(grown):
    parser = DefinitionParser(Settings().symbols)
    for op in grown.registry:
        if op.definition is not None:
            parser.parse(op.definition)


def test_compiled_code_agrees_with_definition(grown):
    """The property the legacy recursive generator violated, now with both counts."""
    from opulse.verify import Oracle, check_operator

    oracle = Oracle(grown.registry)
    for op in grown.registry:
        if op.definition is None:
            continue
        assert not check_operator(op, grown.runtime.evaluate(op), oracle, random.Random(0), 100)


def test_symbols_are_unique_and_ids_sequential(grown):
    ops = list(grown.registry)
    assert len({(op.symbol, op.n_ary, op.unary_position) for op in ops}) == len(ops)
    generated_ids = [op.id for op in ops if op.definition is not None]
    assert generated_ids == list(range(26, 26 + len(generated_ids)))


def test_priorities_keep_initial_and_are_consistent(grown):
    plus = grown.registry.find("+", BINARY)
    before = plus.priority
    assign_priorities(grown.registry, random.Random(0), max_levels=12)
    assert plus.priority == before
    assoc_of_level = {}
    for op in grown.registry:
        if op.is_base is not None:
            continue
        assert op.priority is not None
        assert assoc_of_level.setdefault(op.priority, op.associativity_direction) == op.associativity_direction
        if op.unary_position == "prefix":
            assert op.associativity_direction == "right"
        if op.unary_position == "postfix":
            assert op.associativity_direction == "left"
    assert len(assoc_of_level) <= 12


def test_generation_is_deterministic_for_a_seed():
    from conftest import INITIAL_OPERATORS

    from opulse.core import OperatorRegistry

    def run():
        registry = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
        build_layers(OperatorFactory(Settings(), registry, random.Random(11)), [8, 4])
        return [op.definition for op in registry]

    assert run() == run()


def test_degenerate_probe_stops_after_distinct_values(monkeypatch):
    from types import SimpleNamespace

    from opulse.definition import ast
    from opulse.generation import checks

    node = ast.Apply("+", (ast.Var("a"), ast.Num(1)))
    monkeypatch.setattr(checks, "_subexpressions", lambda definition: [node])
    calls = []

    class ProbeOracle:
        def evaluate_expr(self, expression, env):
            calls.append(env["a"])
            return SimpleNamespace(value=env["a"])

    draft = SimpleNamespace(definition=SimpleNamespace(parameters=("a",)))
    assert checks.degenerate_subexpression(draft, object(), ProbeOracle(), object(), 200) is None
    assert calls == [0, 1]


def test_generation_from_atoms():
    """Start from neg/succ/pred/double/half/parity only; recursion steps use ⁻ / ⁺."""
    import random
    from pathlib import Path

    from opulse.config import Settings
    from opulse.core import OperatorRegistry
    from opulse.generation.pipeline import OperatorFactory, build_layers
    from opulse.solver.smt import export, prelude
    from opulse.solver.z3_encode import Z3Encoder, evaluate_concrete
    from opulse.verify import Oracle, check_operator

    root = Path(__file__).resolve().parents[1]
    registry = OperatorRegistry.from_jsonl(INITIAL_OPERATORS.parent / "atomic_operators.jsonl")
    settings = Settings.load(root / "configs" / "atomic.yaml")
    factory = OperatorFactory(settings, registry, random.Random(1))
    build_layers(factory, [6, 4])
    defined = [op for op in registry if op.definition]
    recursive = [op for op in defined if op.definition_type == "recursive_definition"]
    assert recursive and all("⁻" in op.definition and " - 1" not in op.definition for op in recursive)
    used = {symbol for op in defined for symbol in ("+", "*", "/", "%") if f" {symbol} " in op.definition}
    assert not used  # nothing outside the atomic domain
    oracle = Oracle(registry, settings.symbols, settings.semantics.build())
    encoder = Z3Encoder(oracle)
    base = prelude(encoder)
    rng = random.Random(0)
    for op in defined:
        assert not check_operator(op, factory.runtime.evaluate(op), oracle, rng)
        for args in [(0,) * op.n_ary, (5,) * op.n_ary, (-3,) * op.n_ary]:
            expected = oracle.evaluate(op, args).value
            got = evaluate_concrete(encoder, op, args)
            assert got is expected or got == expected
        assert export(op, encoder, base)


def test_recursion_style_needs_its_operations():

    import pytest

    from opulse.config import Settings
    from opulse.core import OperatorRegistry
    from opulse.generation.pipeline import OperatorFactory

    atoms = OperatorRegistry.from_jsonl(INITIAL_OPERATORS.parent / "atomic_operators.jsonl")
    with pytest.raises(ValueError, match="needs base operations"):
        OperatorFactory(Settings(), atoms)


def test_symbol_index_scales_and_stays_prefix_free():
    import time

    from opulse.generation.symbols import SymbolFactory, uniquely_decodable

    factory = SymbolFactory(OperatorSettings(), random.Random(0))
    assert factory.capacity() == len(factory.alphabet) ** 3 > 100_000
    start = time.perf_counter()
    made = []
    for _ in range(100_000):
        symbol = factory.new_symbol()
        factory.reserve(symbol)
        made.append(symbol)
    assert time.perf_counter() - start < 60
    assert len(set(made)) == 100_000
    assert not any(made[i][:k] in factory._index.symbols for i in range(0, 100_000, 997)
                   for k in range(1, len(made[i])))
    assert uniquely_decodable(set(made[:300]))


def test_too_many_operators_for_the_alphabet_fail_early():
    from conftest import INITIAL_OPERATORS

    from opulse.core import OperatorRegistry
    from opulse.generation.pipeline import OperatorFactory, build_layers

    settings = Settings.from_dict({"operators": {"naming": "legacy", "symbol_sets": ["suits"],
                                                  "symbol_max_len": 1}})
    factory = OperatorFactory(settings, OperatorRegistry.from_jsonl(INITIAL_OPERATORS), random.Random(0))
    with pytest.raises(ValueError, match="at most 8"):
        build_layers(factory, [9])


def test_recursion_size_must_fit_the_bound():
    """Review finding: with B = 3 and T = 8 the threshold ``- 8`` is NaN, so ``v < 0`` never recurses."""
    from conftest import INITIAL_OPERATORS

    from opulse.core import OperatorRegistry
    from opulse.generation.pipeline import OperatorFactory

    settings = Settings.from_dict({"semantics": {"bound": 3}, "recursion": {"style": "direct", "direct_bound": 8}})
    with pytest.raises(ValueError, match="exceeds semantics.bound"):
        OperatorFactory(settings, OperatorRegistry.from_jsonl(INITIAL_OPERATORS), random.Random(0))


def _candidate(registry, text, symbol="⊕", n_ary=2, kind="simple_definition"):
    from opulse.config import Symbols
    from opulse.core import Operator
    from opulse.definition.codegen import compile_definition, registry_resolver
    from opulse.definition.parser import DefinitionParser
    from opulse.generation.drafts import Draft

    definition = DefinitionParser(Symbols(), registry).parse(text)
    op = Operator(func_id="cand", symbol=symbol, n_ary=n_ary, unary_position=None if n_ary == 2 else "prefix",
                  definition=text, definition_type=kind)
    code = compile_definition(definition, op.func_id, registry_resolver(registry, op))
    op.op_compute_func, op.op_count_func = code.compute, code.count
    return Draft(symbol, n_ary, op.unary_position, definition, kind), op


def test_degenerate_subexpressions_are_proved_and_rejected():
    from conftest import INITIAL_OPERATORS

    from opulse.core import OperatorRegistry
    from opulse.generation import checks
    from opulse.solver.z3_encode import Z3Encoder
    from opulse.verify import Oracle

    registry = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
    oracle = Oracle(registry)
    encoder = Z3Encoder(oracle)
    for text in ("a ⊕ b = { b / (a - a) }", "a ⊕ b = { (b * 2) + (a % a) }", "a ⊕ b = { b / ((a $) - (a $)) }"):
        draft, op = _candidate(registry, text)
        oracle.include(op)
        assert checks.degenerate_subexpression(draft, op, oracle, encoder, 200) == "degenerate subexpression", text
    for text in ("a ⊕ b = { b / (a - 3) }", "a ⊕ b = { (a * b) - (b % 7) }"):
        draft, op = _candidate(registry, text)
        oracle.include(op)
        assert checks.degenerate_subexpression(draft, op, oracle, encoder, 200) is None, text


def test_defined_share_and_its_exemptions():
    from conftest import INITIAL_OPERATORS

    from opulse.core import OperatorRegistry
    from opulse.generation import checks
    from opulse.runtime import PythonRuntime

    registry = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
    runtime = PythonRuntime(registry)
    mostly_nan, op = _candidate(registry, "a ⊕ b = { b / (a % 2) }")  # NaN for every even a
    runtime.load(op)
    assert checks.defined_share(op, runtime, random.Random(0), 0.95, (0, 100)) == "defined on too few inputs"
    _fine, op2 = _candidate(registry, "a ⊗ b = { b / (a - 3) }", symbol="⊗")  # NaN only at a = 3
    runtime.load(op2)
    assert checks.defined_share(op2, runtime, random.Random(0), 0.9, (0, 100)) is None
    partial, _ = _candidate(registry, "a ⊖ b = { a + b, if a > 50 }", symbol="⊖", kind="branch_definition")
    assert checks.intentionally_partial(partial, "bounded_mod")
    assert not checks.intentionally_partial(mostly_nan, "bounded_mod")


def test_generation_does_not_depend_on_earlier_runs_in_the_process(tmp_path):
    """z3 answers under rlimit must not depend on queries an earlier run sent (isolated worker)."""
    import io
    from contextlib import redirect_stdout

    from opulse.cli.main import main

    outputs = []
    for name in ("first", "second"):
        out = tmp_path / f"{name}.jsonl"
        with redirect_stdout(io.StringIO()):
            assert main(["operators", "--out", str(out), "--layers", "20", "10", "6", "--seed", "3"]) == 0
        outputs.append(out.read_bytes())
    assert outputs[0] == outputs[1]
