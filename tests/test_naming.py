import json
import random

import pytest
from conftest import INITIAL_OPERATORS

from opulse.bench.check import (
    answer_from_prompt,
    base_registry,
    prompt_definitions,
    prompt_registry,
)
from opulse.bench.context import rules_text
from opulse.cli.main import main
from opulse.config import OperatorSettings, Settings, Symbols
from opulse.core import OperatorRegistry, Semantics
from opulse.core.operator import SIMPLE
from opulse.definition.ast import render_definition
from opulse.definition.parser import DefinitionParser, DefinitionSyntaxError
from opulse.expression.aliases import AliasMap, aliased_registry
from opulse.expression.nodes import from_ast
from opulse.generation.pipeline import OperatorFactory
from opulse.generation.symbols import ShapeIndexFactory, SymbolFactory
from opulse.solver.smt import export, prelude
from opulse.solver.z3_encode import Z3Encoder, evaluate_concrete
from opulse.verify.steps import check_steps, step_lines


def test_shape_index_names_and_custom_index_alphabet():
    factory = ShapeIndexFactory(OperatorSettings(shape_sets=(), shape_chars="◆", index_chars="₀₁₂₃₄₅₆₇₈₉"),
                                random.Random(0))
    names = []
    for _ in range(12):
        name = factory.new_symbol()
        factory.reserve(name)
        names.append(name)
    assert names[:2] == ["◆₁", "◆₂"]
    assert names[9:12] == ["◆₁₀", "◆₁₁", "◆₁₂"]
    resumed = ShapeIndexFactory(OperatorSettings(shape_sets=(), shape_chars="◆"), random.Random(1))
    resumed.reserve(names)
    assert resumed.new_symbol() == "◆₁₃"
    assert not set("∑∫√∈∉∀∃¬") & set("".join(ShapeIndexFactory(OperatorSettings()).alphabet))

    letters = ShapeIndexFactory(OperatorSettings(shape_sets=(), shape_chars="▲", index_chars="ab"),
                                random.Random(0))
    assert [letters.new_symbol() for _ in range(4)] == ["▲a", "▲b", "▲aa", "▲ab"]
    subscripts = ShapeIndexFactory(OperatorSettings(shape_sets=(), shape_chars="◆", index_chars="ₐₑ"),
                                   random.Random(0))
    assert [subscripts.new_symbol() for _ in range(3)] == ["◆ₐ", "◆ₑ", "◆ₐₐ"]


def test_shape_index_definitions_parse_with_subscript_and_letter_indices():
    parser = DefinitionParser(Symbols())
    for name in ("◆₁", "◆₁₀", "▲ab", "◆ₐₐ"):
        text = f"a {name} b = {{ a + b, if b > 0; a, else }}"
        tree = parser.parse(text)
        assert tree.lhs.symbol == name
        assert parser.parse(render_definition(tree, Symbols())) == tree
    with pytest.raises(DefinitionSyntaxError):
        parser.parse_expr("₁")


def test_legacy_naming_keeps_seeded_output():
    alphabet = SymbolFactory(OperatorSettings(), random.Random(17))
    assert [alphabet.new_symbol() for _ in range(5)] == ["→↙←", "★∇∄", "∛⇑↩", "▽↓⇔", "☆∨⊂"]
    registry = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
    settings = Settings.from_dict({"operators": {"naming": "legacy"}})
    factory = OperatorFactory(settings, registry, random.Random(17))
    assert factory.generate(SIMPLE, 0).definition == "a ▽↖⊝ b = { (b + a) + (& b) }"


def test_piecewise_prompt_steps_and_z3_with_shape_index():
    compact = "a ◆₁ b = { a + b, if b > 0; a, else }"
    definition = DefinitionParser(Symbols()).parse(compact)
    piecewise = render_definition(definition, Symbols(), layout="piecewise", min_length=1)
    assert piecewise == "a ◆₁ b = {\n  a + b, if b > 0;\n  a, else\n}"
    base = base_registry(OperatorRegistry.from_jsonl(INITIAL_OPERATORS))
    prompt = "Rules:\n" + rules_text(["add"], Semantics()) + "\n\nDefinitions:\n" + piecewise + \
        "\n\nWhat is the value of `2 ◆₁ 3`?"
    task = {"family": "compute", "prompt": prompt, "definitions": [piecewise], "expression": "2 ◆₁ 3"}
    assert prompt_definitions(prompt) == [piecewise]
    assert answer_from_prompt(task, base) == 5
    ops = prompt_registry([piecewise], base)
    tree = from_ast(ops.parser.parse_expr("2 ◆₁ 3"), ops.registry)
    assert check_steps(tree, step_lines("= 5"), ops.parser, ops.registry, ops.oracle, 5).all_valid
    encoder = Z3Encoder(ops.oracle)
    operator = next(op for op in ops.registry if op.symbol == "◆₁")
    assert evaluate_concrete(encoder, operator, (2, 3)) == 5
    assert export(operator, encoder, prelude(encoder))
    alias = AliasMap.build(ops.registry, random.Random(0))
    renamed = aliased_registry(ops.registry, alias)
    assert "\n" in renamed.get(operator.func_id).definition


def test_piecewise_generated_set_verifies_and_builds_step_tasks(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("operators:\n  definition_layout: piecewise\n  piecewise_min_length: 1\n")
    operators = tmp_path / "operators.jsonl"
    tasks = tmp_path / "tasks.jsonl"
    assert main(["operators", "--config", str(config), "--out", str(operators),
                 "--layers", "4", "2", "--seed", "5"]) == 0
    definitions = [json.loads(line)["definition"] for line in operators.read_text().splitlines()]
    assert any("\n" in definition for definition in definitions if definition)
    assert main(["verify", "--operators", str(operators), "--samples", "4"]) == 0
    assert main(["bench", "build", "--operators", str(operators), "--out", str(tasks),
                 "--count", "2", "--format", "steps", "--max-depth", "2"]) == 0
    assert all(json.loads(line)["format"] == "steps" for line in tasks.read_text().splitlines())
