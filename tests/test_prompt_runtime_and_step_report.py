"""Regressions for prompt code generation and the two final-step verdicts."""

import json

from conftest import INITIAL_OPERATORS

from opulse.bench.check import base_registry, prompt_definitions, prompt_registry
from opulse.cli.main import main
from opulse.config import Symbols
from opulse.core.operator import SIMPLE, Operator
from opulse.core.registry import OperatorRegistry
from opulse.definition.parser import DefinitionParser
from opulse.expression.evaluator import Evaluator
from opulse.expression.nodes import from_ast
from opulse.runtime import PythonRuntime
from opulse.verify import Oracle
from opulse.verify.steps import check_steps

INITIAL = INITIAL_OPERATORS


def test_built_prompt_registry_runs_in_python_runtime(tmp_path):
    preset = tmp_path / "operators.jsonl"
    assert main(["operators", "--preset", "integer", "--out", str(preset), "--seed", "17"]) == 0
    tasks = tmp_path / "tasks.jsonl"
    assert main(["bench", "build", "--operators", str(preset), "--out", str(tasks),
                 "--count", "1", "--max-definitions", "3", "--seed", "3"]) == 0
    task = json.loads(tasks.read_text(encoding="utf-8").splitlines()[0])
    full = OperatorRegistry.from_jsonl(preset)
    shown = prompt_registry(prompt_definitions(task["prompt"]), base_registry(full))

    prompt_tree = from_ast(shown.parser.parse_expr(task["expression"], expression_mode=True), shown.registry)
    full_parser = DefinitionParser(Symbols(), full)
    full_tree = from_ast(full_parser.parse_expr(task["expression"], expression_mode=True), full)
    prompt_value = Evaluator(PythonRuntime(shown.registry)).evaluate(prompt_tree).value
    full_value = Evaluator(PythonRuntime(full)).evaluate(full_tree).value

    assert task["definitions"] and task["answer"] != 0
    assert prompt_value == full_value == task["answer"]


def test_last_value_is_independent_of_derivation_validity():
    registry = OperatorRegistry.from_jsonl(INITIAL)
    parser = DefinitionParser(Symbols(), registry)
    oracle = Oracle(registry)
    start = from_ast(parser.parse_expr("0 * (1 + 2)", expression_mode=True), registry)

    slipped = check_steps(start, ["0 * (1 + 3)", "0"], parser, registry, oracle, 0)
    assert slipped.first_error == 0
    assert slipped.final_value_correct is True
    assert slipped.derivation_correct is False
    assert slipped.final_correct is False  # legacy meaning in saved records
    assert slipped.to_dict()["final_value_correct"] is True
    assert slipped.to_dict()["final_correct"] is False

    valid = check_steps(start, ["0"], parser, registry, oracle, 0)
    assert valid.final_value_correct and valid.derivation_correct and valid.final_correct


def test_equivalent_expression_is_not_a_valid_direct_expansion():
    registry = OperatorRegistry.from_jsonl(INITIAL)
    op = Operator("demo", "◇", 2, definition="a ◇ b = { a + b }", definition_type=SIMPLE)
    op.op_compute_func = "def op_demo(a, b):\n    return a + b\n"
    op.op_count_func = "def op_count_demo(a, b):\n    return 1\n"
    registry.add(op)
    parser = DefinitionParser(Symbols(), registry)
    oracle = Oracle(registry)
    start = from_ast(parser.parse_expr("1 ◇ 2", expression_mode=True), registry)

    expanded = check_steps(start, ["1 + 2", "3"], parser, registry, oracle, 3)
    assert expanded.single_steps == 2 and expanded.derivation_correct

    shortcut = check_steps(start, ["1 + (1 + 1)", "3"], parser, registry, oracle, 3)
    assert shortcut.first_error == 0
    assert "not the body" in shortcut.errors[0]
    assert shortcut.final_value_correct and not shortcut.derivation_correct
