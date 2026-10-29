"""The relation world through generation, evaluation, traces, prompts, and edits."""

import random

import yaml
from world_contract import check_showcase

from opulse.bench.check import base_registry, check_tasks
from opulse.bench.tasks import BenchBuilder
from opulse.config import Settings, Symbols
from opulse.core.operator import Operator
from opulse.core.presets import PRESETS, register_preset
from opulse.core.primitives import atom_records
from opulse.core.registry import OperatorRegistry
from opulse.core.semantics import NAN
from opulse.definition.codegen import compile_definition, registry_resolver
from opulse.definition.parser import DefinitionParser
from opulse.expression.nodes import Call, Number
from opulse.generation.pipeline import OperatorFactory, build_layers
from opulse.runtime import PythonRuntime
from opulse.solver.z3_encode import Z3Encoder
from opulse.trace import Reducer
from opulse.verify import Oracle
from opulse.verify.records import verify_trace
from opulse.verify.steps import check_steps
from opulse.worlds.rel import DEFAULT_CONFIG, export_world_showcase, load_table


def registry():
    register_preset("rel")
    return OperatorRegistry(Operator.from_dict(row) for row in atom_records(PRESETS["rel"], 33))


def test_relation_generation_and_edit(monkeypatch, tmp_path):
    table = load_table()
    assert len(table["entities"]) == 12
    current = tmp_path / "rel.yaml"
    current.write_text(DEFAULT_CONFIG.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setenv("OPULSE_REL_CONFIG", str(current))
    operators = registry()
    factory = OperatorFactory(Settings(), operators, random.Random(33))
    build_layers(factory, [5, 3])
    generated = [op for op in operators if op.definition]
    assert {op.definition_type for op in generated} == {
        "simple_definition", "branch_definition", "recursive_definition"
    }
    # The generated sample depends on the active naming and shape settings;
    # define the relation composition this edit check is about explicitly.
    composed = Operator("relcomposed", "◇₉₉", 1, unary_position="postfix",
                        definition="a ◇₉₉ = { (a ↝) ↟ }",
                        definition_type="simple_definition",
                        parameter_types=("str",), result_type="str")
    definition = DefinitionParser(Symbols(), operators).parse(composed.definition)
    code = compile_definition(definition, composed.func_id,
                              registry_resolver(operators, composed),
                              composed.parameter_types, composed.result_type)
    composed.op_compute_func, composed.op_count_func = code.compute, code.count
    composed.dependencies = list(code.dependencies)
    operators.add(composed)
    oracle = Oracle(operators)
    runtime = PythonRuntime(operators)
    assert oracle.evaluate(composed, ("Bo",)).value == "Kira"
    assert runtime.evaluate(composed)("Bo")[0] == "Kira"
    assert oracle.evaluate(composed, ("unknown",)).value is NAN
    assert not Z3Encoder(oracle).expressible(composed)

    tree = Call(composed, (Number("Bo"),))
    trace = Reducer(operators, runtime, DefinitionParser(Symbols(), operators)).reduce(tree)
    assert trace.value == "Kira" and not trace.truncated
    verify_trace(trace, oracle)
    from opulse.expression.render import ExpressionRenderer

    lines = [ExpressionRenderer(Symbols()).full(step.expression_after) for step in trace.steps]
    result = check_steps(tree, lines, DefinitionParser(Symbols(), operators),
                         operators, oracle, "Kira")
    assert result.final_correct and result.first_error is None

    table["relations"]["colleague"]["Bo"] = "Cora"
    current.write_text(yaml.safe_dump(table, allow_unicode=True), encoding="utf-8")
    assert oracle.evaluate(composed, ("Bo",)).value == "Hana"
    assert runtime.evaluate(composed)("Bo")[0] == "Hana"


def test_relation_bench_and_showcase(tmp_path):
    operators = registry()
    build_layers(OperatorFactory(Settings(), operators, random.Random(33)), [5, 3])
    builder = BenchBuilder(Settings(), operators, random.Random(23), max_depth=2,
                           answer_format="steps")
    tasks = [task.to_dict() for task in builder.tasks("compute", 3)]
    assert not check_tasks(tasks, base_registry(operators))
    assert all("Relation table (JSON): " in task["prompt"] for task in tasks)
    changed = dict(tasks[0], prompt=tasks[0]["prompt"].replace("Relation table (JSON): ",
                                                              "Facts: "))
    assert check_tasks([changed], base_registry(operators))
    result = export_world_showcase("rel", tmp_path / "rel.json")
    check_showcase(result, tmp_path)
    assert result["edit"]["changes"] and result["context"]["entities"]
