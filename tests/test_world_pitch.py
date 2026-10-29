"""Pitch atoms, typed generation, traces, benchmark checks and showcase."""

import random

from world_contract import check_showcase

from opulse.bench.check import (
    base_registry,
    check_tasks,
    prompt_registry,
    prompt_signatures,
)
from opulse.bench.tasks import BenchBuilder
from opulse.config import Settings, Symbols
from opulse.core.operator import Operator
from opulse.core.presets import PRESETS, register_preset
from opulse.core.primitives import atom_records
from opulse.core.registry import OperatorRegistry
from opulse.core.semantics import NAN, Semantics
from opulse.core.types import matches
from opulse.definition.parser import DefinitionParser
from opulse.expression.nodes import Call, Number, from_ast
from opulse.expression.render import ExpressionRenderer
from opulse.generation.pipeline import OperatorFactory
from opulse.runtime import PythonRuntime
from opulse.solver.z3_encode import Z3Encoder, evaluate_concrete
from opulse.trace import Reducer
from opulse.verify import Oracle
from opulse.verify.records import verify_trace
from opulse.verify.steps import check_steps
from opulse.worlds.pitch import (
    export_world_showcase,
    melody_text,
    note_name,
    register_pitch,
)


def _set():
    register_preset("pitch")
    settings = Settings.from_dict({"recursion": {"style": "direct", "direct_bound": 4},
                                   "operators": {"reject_dead_branches": False}})
    registry = OperatorRegistry(Operator.from_dict(row) for row in atom_records(PRESETS["pitch"], 35))
    factory = OperatorFactory(settings, registry, random.Random(35))
    generated = []
    for kind, layer in (("simple_definition", 0), ("branch_definition", 0),
                        ("recursive_definition", 1)):
        op = factory.generate(kind, layer)
        factory.add(op)
        generated.append(op)
    return settings, registry, generated


def test_pitch_atoms_and_names():
    register_pitch()
    operations = Semantics().operations()
    melody = ((60, 1), (64, 2), (67, 1))
    assert operations["pitch_transpose"](60, 4) == 64
    assert operations["pitch_transpose"](127, 1) is NAN
    assert operations["pitch_octave_up"](60) == 72
    assert operations["pitch_octave_down"](60) == 48
    assert operations["pitch_interval"](60, 67) == 7
    assert operations["pitch_invert"](melody, 60) == ((60, 1), (56, 2), (53, 1))
    assert operations["pitch_retrograde"](melody) == tuple(reversed(melody))
    assert operations["pitch_scale_step"](60) == 62
    assert operations["pitch_major_triad"](60) == ((60, 1), (64, 1), (67, 1))
    assert operations["pitch_minor_triad"](60) == ((60, 1), (63, 1), (67, 1))
    assert operations["pitch_repeat"](melody, 2) == melody * 2
    assert operations["pitch_concat"](melody, melody) == melody * 2
    assert matches(melody, "melody") and not matches(((60, 0),), "melody")
    assert note_name(60) == "C4"
    assert melody_text(melody) == "C4:1 E4:2 G4:1"
    register_pitch("D", "minor")
    assert Semantics().operations()["pitch_scale_step"](62) == 64
    register_pitch()


def test_pitch_generated_pipeline_and_prompt_steps(tmp_path):
    settings, registry, generated = _set()
    assert {op.definition_type for op in generated} == {
        "simple_definition", "branch_definition", "recursive_definition"}
    saved = tmp_path / "operators.jsonl"
    registry.to_jsonl(saved)
    loaded = OperatorRegistry.from_jsonl(saved)
    op = loaded.find(generated[0].symbol, generated[0].n_ary, generated[0].unary_position)
    samples = {"melody": ((60, 1), (64, 1), (67, 2)), "note": 60, "int": 2}
    args = tuple(samples[kind] for kind in op.parameter_types)
    oracle = Oracle(loaded)
    runtime = PythonRuntime(loaded)
    expected = oracle.evaluate(op, args)
    assert runtime.evaluate(op)(*args) == (expected.value, expected.base_ops, expected.calls)
    tree = Call(op, tuple(Number(v) for v in args))
    parser = DefinitionParser(Symbols(), loaded)
    trace = Reducer(loaded, runtime, parser).reduce(tree)
    verify_trace(trace, oracle)
    assert trace.value == expected.value
    text = ExpressionRenderer(Symbols())
    lines = [text.full(step.expression_after) for step in trace.steps]
    report = check_steps(tree, lines, parser, loaded, oracle, expected.value)
    assert report.final_correct and report.first_error is None
    # A one step reduction at another granularity still has the same value.
    compact = Reducer(loaded, runtime, parser, max_depth=0).reduce(tree)
    verify_trace(compact, oracle)
    assert compact.value == expected.value

    tasks = [task.to_dict() for task in BenchBuilder(
        settings, loaded, random.Random(35), max_depth=2, answer_format="steps"
    ).tasks("compute", 2)]
    assert not check_tasks(tasks, base_registry(loaded))
    assert "Note names:" in tasks[0]["prompt"]
    first = tasks[0]
    prompt = prompt_registry(first["definitions"], base_registry(loaded),
                             signatures=prompt_signatures(first["prompt"]))
    parsed = prompt.parser.parse_expr(first["expression"], expression_mode=True)
    prompt_tree = from_ast(parsed, prompt.registry)
    prompt_trace = Reducer(prompt.registry, PythonRuntime(prompt.registry), prompt.parser).reduce(prompt_tree)
    answer = prompt.oracle.evaluate_expr(parsed, {}).value
    assert check_steps(prompt_tree, [text.full(s.expression_after) for s in prompt_trace.steps],
                       prompt.parser, prompt.registry, prompt.oracle, answer).final_correct


def test_pitch_z3_and_showcase(tmp_path):
    _, registry, _ = _set()
    oracle = Oracle(registry)
    encoder = Z3Encoder(oracle)
    interval = registry.find("⟷", 2)
    assert encoder.expressible(interval)
    assert evaluate_concrete(encoder, interval, (60, 67)) == 7
    assert evaluate_concrete(encoder, interval, (128, 67)) is NAN
    assert evaluate_concrete(encoder, registry.find("♯", 2), (60, 4)) == 64
    assert evaluate_concrete(encoder, registry.find("♯", 2), (127, 1)) is NAN
    assert evaluate_concrete(encoder, registry.find("⇈", 1, "postfix"), (120,)) is NAN
    assert evaluate_concrete(encoder, registry.find("♬", 1, "postfix"), (60,)) == 62
    variables, _ = encoder.variables(interval)
    assert len(variables) == 2
    assert encoder.expressible(registry.find("≐", 2))
    assert not encoder.expressible(registry.find("⇅", 2))
    data = export_world_showcase("pitch", tmp_path / "pitch.json")
    check_showcase(data, tmp_path)
    assert data["dimension"] == "sound"
    values = [example["output"]["t"] for op in data["operators"] for example in op["examples"]]
    assert {"note", "melody", "nan"} <= set(values)
