"""Operator names and plain sentences of the world showcases are faithful to the definitions."""

import itertools
import re

import pytest

from opulse.core.semantics import NAN, base_operation_name
from opulse.definition import ast
from opulse.definition.parser import DefinitionParser
from opulse.verify import Oracle
from opulse.worlds.action import _condition
from opulse.worlds.grid import _grid_text
from opulse.worlds.pitch import _pitch_text
from opulse.worlds.present import Describer, alias, operator_names
from opulse.worlds.showcase import world_spec

WORLDS = ("successor", "integer", "clock", "bits", "strings", "lists", "logic", "perm", "rel", "grid", "pitch")


def test_literal_text_uses_the_requested_language():
    grid = ((0, 0), (0, 0))
    melody = ((60, 1), (64, 2))
    for value, kind, callback, english, chinese in (
        (grid, "grid", _grid_text, "the 2×2 grid 00/00", "2×2 网格 00/00"),
        (melody, "melody", _pitch_text, "[C4:1 E4:2]", "旋律 [C4:1 E4:2]"),
        ((), "melody", _pitch_text, "the empty melody", "空旋律"),
        (60, "note", _pitch_text, "C4", "C4"),
    ):
        phrase = Describer(None, {}, None, callback).noun(ast.Literal(value), set(), kind)
        assert (phrase.en, phrase.zh) == (english, chinese)
    plain = Describer(None, {}, None, lambda value, kind: "same text")
    phrase = plain.noun(ast.Literal(grid), set(), "grid")
    assert (phrase.en, phrase.zh) == ("same text", "same text")


def test_generated_operator_steps_name_inputs():
    class EmptyRegistry:
        def find(self, *args):
            return None

    describer = Describer(EmptyRegistry(), {}, None)
    unary = ast.Apply("◇", (ast.Var("a"),), ast.PREFIX)
    nested = ast.Apply("♧", (ast.Var("b"),), ast.PREFIX)
    chain = ast.Apply("□", (unary, nested))
    assert describer.clause(chain, set())[0] == (
        "apply ◇ to a, then apply □ to the result and (♧ b)")
    direct = ast.Apply("□", (ast.Var("a"), ast.Num(0)))
    assert describer.clause(direct, set())[0] == "compute a □ 0"


def _atom(registry, name, *args):
    op = next(op for op in registry if op.definition is None
              and base_operation_name(op.symbol, op.n_ary, op.unary_position) == name)
    return ast.Apply(op.symbol, args, op.unary_position)


def test_chains_name_the_computed_result(grown):
    spec, _settings, registry, generated, names, parser, _oracle = grown
    describer = Describer(registry, names, parser, spec.value_text)
    if spec.world == "integer":
        digits = _atom(registry, "digitsum", ast.Var("a"))
        expr = _atom(registry, "add", digits, digits)
        definition = ast.Definition(ast.Apply("X", (ast.Var("a"),), ast.PREFIX), (ast.Branch(expr),))
        assert describer._cases(definition, set()) == (
            "Sum the digits of a, then add the result to itself.",
            "先求 a 的各位数字之和，再把结果与自身相加。")
        level_readings = [reading for op in generated
                          if (reading := describer.describe(op)).en.startswith("Recurse on ")]
        assert any(", counting with " in reading.en and "计数" in reading.zh
                   for reading in level_readings)
    elif spec.world == "rel":
        parent = _atom(registry, "rel_parent", ast.Var("a"))
        expr = _atom(registry, "rel_equal", parent, ast.Literal("Kira"))
        definition = ast.Definition(ast.Apply("X", (ast.Var("a"),), ast.PREFIX), (ast.Branch(expr),))
        assert describer._cases(definition, set()) == (
            'Look up the parent of a, then test whether the result equals "Kira".',
            '先查 a 的父母，再判断结果是否等于 "Kira"。')
    elif spec.world == "grid":
        crop = _atom(registry, "grid_crop", ast.Var("a"))
        definition = ast.Definition(ast.Apply("X", (ast.Var("a"),), ast.PREFIX), (ast.Branch(crop),))
        assert describer._cases(definition, set()) == (
            "Crop a to the smallest rectangle that holds all its nonzero cells.",
            "把 a 裁成包含所有非零格的最小矩形。")
        assert describer.noun(crop, set()).en == (
            "a cropped to the smallest rectangle that holds all its nonzero cells")


def test_front_wall_guard_includes_outside_the_map():
    assert _condition("front_wall", True) == (
        "the cell ahead is a wall or outside the map", "正前方是墙或在地图外")
    assert _condition("front_wall", False) == ("the cell ahead is open", "正前方可以走")


def _nodes(definition):
    found = set()

    def expr(node):
        if isinstance(node, ast.Var):
            found.add(("var", node.name))
        elif isinstance(node, (ast.Num, ast.Literal)):
            found.add(("const", repr(node.value)))
        elif isinstance(node, ast.Apply):
            if node.symbol == "-" and node.n_ary == 1 and isinstance(node.args[0], ast.Num):
                found.add(("const", repr(-node.args[0].value)))
                return
            found.add(("op", node.symbol))
            for arg in node.args:
                expr(arg)

    for branch in definition.branches:
        expr(branch.expr)
    return found


@pytest.fixture(scope="module", params=WORLDS)
def grown(request):
    spec = world_spec(request.param)
    settings, registry, generated = spec.build()
    names = operator_names(generated, settings, [op.symbol for op in registry if op.definition is None], 1)
    parser = DefinitionParser(settings.symbols, registry)
    oracle = Oracle(registry, settings.symbols, settings.semantics.build())
    return spec, settings, registry, generated, names, parser, oracle


def test_names_keep_generated_shapes_with_local_indices(grown):
    _spec, _settings, registry, generated, names, _parser, _oracle = grown
    shown = [names[op.symbol] for op in generated]
    digits = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
    for index, (op, name) in enumerate(zip(generated, shown), 1):
        old_shape = re.sub(r"[₀-₉]+$", "", op.symbol)
        match = re.fullmatch(r"(.+?)([₀-₉]+)", name)
        assert match and match.group(1) == old_shape
        assert int(match.group(2).translate(digits)) == index
    assert len(set(shown)) == len(shown)
    atoms = {op.symbol for op in registry if op.definition is None}
    assert not {name[0] for name in shown} & atoms


def test_alias_replaces_only_whole_operator_symbols():
    assert alias("◇₃ ◇₃₁ ◇₃₁₀", {"◇₃": "◇₁", "◇₃₁": "◇₂"}) == "◇₁ ◇₂ ◇₃₁₀"


def test_every_sentence_names_what_its_definition_uses(grown):
    spec, _settings, registry, generated, names, parser, _oracle = grown
    describer = Describer(registry, names, parser, spec.value_text)
    readings = set()
    for op in generated:
        description = describer.describe(op)
        readings.add(description.reading)
        assert description.en.endswith(".") and description.zh.endswith("。"), op.definition
        assert "\0" not in description.en + description.zh
        assert not re.search("[–—]", description.en + description.zh)
        assert "notes of it" not in description.en
        used = _nodes(parser.parse(op.definition))
        if description.reading == "summary":
            used = {item for item in used if item[0] == "op"}
        if description.reading == "repetition":
            used.discard(("const", "1"))  # the step of the counter is said as "times"
            used.discard(("const", "0"))
        missing = used - description.mentions - {("op", op.symbol)}
        assert not missing, (op.definition, description.en, missing)
        for kind, symbol in description.mentions:
            if kind == "op" and symbol in names and symbol != op.symbol:
                assert names[symbol] in description.en and names[symbol] in description.zh, (symbol, description.en)
    assert "direct" in readings


def _count(repetition, args):
    loop_value = args[repetition["position"]]
    if repetition["halving"]:
        bound = repetition["bound"]
        if loop_value < 0 or (bound is not None and loop_value > bound):
            return None
        return loop_value.bit_length()
    if repetition["modulus"] is not None:
        m = repetition["modulus"]
        r = abs(loop_value) % m
        return r
    bound = repetition["bound"]
    if repetition["two_sided"]:
        return abs(loop_value) if bound is None or abs(loop_value) <= bound else None
    return loop_value if 0 <= loop_value and (bound is None or loop_value <= bound) else None


def test_repetition_sentences_agree_with_evaluation(grown):
    """'Start from x and do y n times' is replayed by evaluation and compared with the operator."""
    spec, _settings, registry, generated, names, parser, oracle = grown
    describer = Describer(registry, names, parser, spec.value_text)
    checked = 0
    for op in generated:
        description = describer.describe(op)
        if description.reading != "repetition":
            continue
        repetition = description.repetition
        params = parser.parse(op.definition).parameters
        pools = [list(spec.values(kind))[:7] for kind in op.parameter_types]
        for args in itertools.islice(itertools.product(*pools), 40):
            expected = oracle.evaluate(op, args).value
            n = _count(repetition, args)
            env = dict(zip(params, args))
            if n is None:
                assert expected is NAN, (op.definition, args)
                continue
            value = oracle.evaluate_expr(repetition["base"], env).value
            for _ in range(n):
                if value is NAN:
                    break
                value = oracle.evaluate_expr(repetition["step"], {**env, repetition["hole"]: value}).value
            assert value == expected or (value is NAN and expected is NAN), (op.definition, args, value, expected)
            checked += 1
    assert checked > 0
