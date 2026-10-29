"""Finite correspondence evidence, probes, world allocation, and skill adapters."""

import json
import random
from collections import Counter

import pytest
from conftest import INITIAL_OPERATORS
from test_skeleton import _defined

from opulse.cli.main import main
from opulse.config import Settings
from opulse.core.operator import Operator
from opulse.core.presets import PRESETS, register_preset
from opulse.core.primitives import atom_records, register_primitive
from opulse.core.registry import OperatorRegistry
from opulse.definition import ast
from opulse.matched import correspondence_grade
from opulse.skeleton import SkeletonSet, extract
from opulse.skeleton_adapter import SkillRun, instantiate_skills
from opulse.world_mix import parse_world_mix, world_schedule


def _mod_atom(name, symbol, fn):
    register_primitive(name, symbol, fn, rule="Computes a value in the set from zero to two.",
                       n_ary=2)
    return Operator.from_dict(atom_records((name,))[0])


def test_grades_on_finite_modular_atoms():
    add = _mod_atom("w43add", "⧺", lambda a, b: (a + b) % 3)
    rotated = _mod_atom("w43rotadd", "⨁", lambda a, b: (a + b + 1) % 3)
    multiply = _mod_atom("w43mul", "⨂", lambda a, b: (a * b) % 3)
    subtract = _mod_atom("w43sub", "⩩", lambda a, b: (a - b) % 3)
    # The second operation is a renamed group operation under x -> x + 1 modulo 3.
    source = OperatorRegistry((add,))
    target = OperatorRegistry((rotated,))
    domain = {"int": [0, 1, 2]}
    equations = [{"atom": add.func_id, "law": "associativity"},
                 {"atom": add.func_id, "law": "commutativity"}]
    g3 = correspondence_grade(source, target, {add.func_id: rotated.func_id},
                              source_domains=domain, target_domains=domain, equations=equations)
    assert g3["grade"] == "G3"
    assert g3["isomorphism"] == "established"
    g2 = correspondence_grade(source, OperatorRegistry((multiply,)), {add.func_id: multiply.func_id},
                              source_domains=domain, target_domains=domain, equations=equations)
    assert g2["grade"] == "G2"
    g1 = correspondence_grade(source, OperatorRegistry((subtract,)), {add.func_id: subtract.func_id},
                              source_domains=domain, target_domains=domain, equations=equations)
    assert g1["grade"] == "G1"
    assert g1["equations"][1]["target"] is False


def test_strings_lists_have_bounded_partial_isomorphism():
    register_preset("strings")
    register_preset("lists")
    strings = OperatorRegistry(Operator.from_dict(row) for row in atom_records(PRESETS["strings"]))
    lists = OperatorRegistry(Operator.from_dict(row) for row in atom_records(PRESETS["lists"]))
    mapping = {strings.find(a, arity, position).func_id: lists.find(b, arity, position).func_id
               for a, b, arity, position in (("⊕", "⊞", 2, None), ("ℓ", "ℒ", 1, "postfix"),
                                              ("⇥", "⌄", 1, "postfix"), ("≡", "≍", 2, None))}
    report = correspondence_grade(strings, lists, mapping, type_map={"str": "list[int]"},
                                  source_domains={"str": ["", "a"], "int": [0, 1],
                                                  "bool": [False, True]},
                                  target_domains={"list[int]": [[], [1]], "int": [0, 1],
                                                  "bool": [False, True]}, partial=True)
    assert report["grade"] == "G3"
    assert report["method"] == "bounded exhaustive partial isomorphism"
    assert correspondence_grade(strings, lists, mapping, type_map={"str": "list[int]"},
                                source_domains={"str": ["", "a"], "int": [0, 1], "bool": [False, True]},
                                target_domains={"list[int]": [[], [1]], "int": [0, 1],
                                                "bool": [False, True]})["grade"] != "G3"


def test_all_listed_equation_forms_are_checked():
    _mod_atom("w43max", "⩘", max)
    for name, symbol, fn in (("w43inc", "⤴", lambda a: (a + 1) % 3),
                             ("w43dec", "⤵", lambda a: (a - 1) % 3),
                             ("w43neg", "⤶", lambda a: (-a) % 3)):
        register_primitive(name, symbol, fn, rule="Maps the input into the set from zero to two.")
    registry = OperatorRegistry(Operator.from_dict(row)
                                for row in atom_records(("w43max", "w43inc", "w43dec", "w43neg")))
    maximum = registry.find("⩘", 2)
    names = {op.symbol: op.func_id for op in registry}
    equations = [{"atom": maximum.func_id, "law": "identity",
                  "source_element": 0, "target_element": 0},
                 {"atom": maximum.func_id, "law": "absorbing",
                  "source_element": 2, "target_element": 2},
                 {"atom": maximum.func_id, "law": "idempotence"},
                 {"atom": names["⤶"], "law": "involution"},
                 {"atom": names["⤴"], "law": "inverse_pair", "other": names["⤵"]}]
    report = correspondence_grade(registry, registry, {op.func_id: op.func_id for op in registry},
                                  source_domains={"int": [0, 1, 2]}, target_domains={"int": [0, 1, 2]},
                                  equations=equations)
    assert report["grade"] == "G3"
    assert all(item["source"] and item["target"] for item in report["equations"])


def test_isomorphism_keeps_paired_undefined_results():
    initial = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
    divide = initial.find("/", 2)
    report = correspondence_grade(initial, initial, {divide.func_id: divide.func_id},
                                  source_domains={"int": [-1, 0, 1]},
                                  target_domains={"int": [-1, 0, 1]})
    assert report["grade"] == "G3"


def test_unary_idempotence_is_distinct_from_involution():
    register_primitive("w43zero", "⤳", lambda a: 0,
                       rule="Returns zero for every input.")
    atom = Operator.from_dict(atom_records(("w43zero",))[0])
    registry = OperatorRegistry((atom,))
    domain = {"int": [0, 1, 2]}
    idem = correspondence_grade(registry, registry, {atom.func_id: atom.func_id},
                                source_domains=domain, target_domains=domain,
                                equations=[{"atom": atom.func_id, "law": "idempotence"}])
    assert idem["equations"][0]["source"] is True
    involution = correspondence_grade(registry, registry, {atom.func_id: atom.func_id},
                                      source_domains=domain, target_domains=domain,
                                      equations=[{"atom": atom.func_id, "law": "involution"}])
    assert involution["equations"][0]["source"] is False


def test_world_schedule_is_seeded_and_exact():
    weights = parse_world_mix("strings:0.5,lists:0.3,actions:0.2")
    schedule = world_schedule(101, weights, 7)
    assert Counter(schedule) == {"strings": 51, "lists": 30, "actions": 20}
    assert schedule == world_schedule(101, weights, 7)
    assert schedule != world_schedule(101, weights, 8)
    with pytest.raises(ValueError):
        parse_world_mix("strings:0,lists:0")
    with pytest.raises(ValueError):
        parse_world_mix("../outside:1")


def test_skeleton_weights_reach_bench_and_corpus_generators():
    from opulse.bench.tasks import BenchBuilder
    from opulse.corpus.documents import SplitGenerator
    from opulse.corpus.options import CorpusOptions

    registry = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
    op = _defined(registry, ast.Apply("+", (ast.Var("a"), ast.Num(1))),
                  types=("int",), result="int")
    op.skeleton_id = "s"
    bench = BenchBuilder(Settings(), registry, random.Random(1), skeleton_weights={"s": 0.25})
    assert bench.pool.weights[op.func_id] == 0.25
    options = CorpusOptions(skeleton_weights={"s": 0.25})
    corpus = SplitGenerator("train", Settings(), registry, [op.func_id], options)
    assert corpus.values_dataset.pool.weights[op.func_id] == 0.25


def test_matched_axes_and_world_survive_hidden_definitions():
    from opulse.bench.tasks import BenchBuilder

    registry = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
    op = _defined(registry, ast.Apply("+", (ast.Var("a"), ast.Num(1))),
                  types=("int",), result="int")
    op.skeleton_id = "s"
    op.world = "hidden"
    op.correspondence_grade = "G1"
    builder = BenchBuilder(Settings(), registry, random.Random(4), context="none", max_answer_share=1)
    task = next(builder.tasks("compute", 1)).to_dict()
    assert task["world"] == "hidden" and task["grade"] == "G1"
    assert task["skeleton_id"] == "s"
    assert isinstance(task["axes"]["unfolded_length"], int)


class StubSkillWorld:
    def atoms(self):
        return {"plus": (("int", "int"), "int")}

    def make_skill(self, record, bindings, dependencies):
        return {"record": record, "bindings": bindings, "dependencies": dependencies}

    def run_skill(self, skill, args):
        return SkillRun(args[0] + args[1], False, 2)

    def probe_values(self, kind):
        return [0, 1, 2]


def test_action_adapter_stub_checks_signature_and_probe():
    record = {"id": "s", "holes": [{"id": "h0", "parameter_types": ["bool", "bool"],
                                     "result_type": "bool"}], "dependencies": [],
              "parameter_types": ["bool", "bool"], "result_type": "bool"}
    skills, rows = instantiate_skills(SkeletonSet([record]), StubSkillWorld(), world="action",
                                      type_map={"bool": "int"}, seed=3)
    assert skills["s"]["bindings"] == {"h0": "plus"}
    assert skills["s"]["record"]["parameter_types"] == ["int", "int"]
    assert record["parameter_types"] == ["bool", "bool"]
    assert rows[0]["grade"] == "G1" and rows[0]["unfolded_length"] == 2


def test_bench_world_mixture_records_world_and_unfolded_axis(tmp_path):
    # Use a small existing defined set in both worlds so each build has checked prompts.
    registry = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
    a = ast.Var("a")
    operator = _defined(registry, ast.Apply("+", (a, ast.Num(1))), types=("int",), result="int")
    operator.skeleton_id = "s"
    path = tmp_path / "ops.jsonl"
    registry.to_jsonl(path)
    output = tmp_path / "tasks.jsonl"
    assert main(["bench", "build", "--world", f"one={path}", "--world", f"two={path}",
                 "--world-mix", "one:0.5,two:0.5", "--out", str(output), "--count", "4",
                 "--max-answer-share", "1.0", "--seed", "5"]) == 0
    tasks = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert Counter(task["world"] for task in tasks) == {"one": 2, "two": 2}
    assert len({task["id"] for task in tasks}) == 4
    assert all(isinstance(task["axes"]["unfolded_length"], int) for task in tasks)

    corpus = tmp_path / "corpus"
    assert main(["corpus", "--operators", f"one={path}", "--operators", f"two={path}",
                 "--world-mix", "one:0.5,two:0.5", "--documents", "4", "--out", str(corpus),
                 "--mix", "definitions=0,values=1,derivations=0,descriptions=0",
                 "--no-dedup", "--seed", "5"]) == 0
    documents = [json.loads(line) for line in (corpus / "mixture.jsonl").read_text().splitlines()]
    assert Counter(item["world"] for item in documents) == {"one": 2, "two": 2}
    assert all(item["text"] for item in documents)


def test_unfolded_axis_is_opt_in_for_ordinary_bench(tmp_path):
    registry = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
    operators = tmp_path / "ops.jsonl"
    registry.to_jsonl(operators)
    output = tmp_path / "tasks.jsonl"
    common = ["bench", "build", "--operators", str(operators), "--out", str(output),
              "--count", "1", "--min-definitions", "0", "--max-answer-share", "1"]
    assert main(common) == 0
    ordinary = json.loads(output.read_text().splitlines()[0])
    assert "unfolded_length" not in ordinary["axes"]
    assert main([*common, "--unfolded-length"]) == 0
    measured = json.loads(output.read_text().splitlines()[0])
    assert isinstance(measured["axes"]["unfolded_length"], int)


def test_match_sampler_enforces_probe_tolerance_and_reports_rejects(tmp_path):
    source = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
    _defined(source, ast.Apply("+", (ast.Apply("+", (ast.Var("a"), ast.Var("b"))), ast.Num(1))),
             types=("int", "int"), result="int", arity=2)
    skeletons = extract(source)
    skeleton_file = tmp_path / "skeletons.json"
    skeletons.write(skeleton_file)
    plus = OperatorRegistry((source.find("+", 2),))
    divide = OperatorRegistry((source.find("/", 2),))
    plus_file, divide_file = tmp_path / "plus.jsonl", tmp_path / "divide.jsonl"
    plus.to_jsonl(plus_file)
    divide.to_jsonl(divide_file)
    common = ["skeleton", "match", "--skeletons", str(skeleton_file),
              "--world", f"plus={plus_file}", "--world", f"divide={divide_file}",
              "--out-dir", str(tmp_path / "matched"), "--attempts", "3", "--seed", "11"]
    with pytest.raises(SystemExit, match="undefined rate tolerance.*rejects"):
        main([*common, "--nan-tolerance", "0"])
    assert main([*common, "--nan-tolerance", "1", "--length-tolerance", "0"]) == 0
    report = json.loads((tmp_path / "matched" / "match.json").read_text())
    assert report["comparisons"]["divide"][0]["grade"] == "G1"
    assert report["comparisons"]["divide"][0]["nan_rate_difference"] > 0
    rows = [json.loads(line) for line in (tmp_path / "matched" / "instances.jsonl").read_text().splitlines()]
    assert all("unfolded_length" in row and "grade" in row for row in rows)
    assert rows[0]["probe"]["inputs"] == rows[1]["probe"]["inputs"]
    second = tmp_path / "matched_again"
    replay = [str(second) if value == str(tmp_path / "matched") else value for value in common]
    assert main([*replay, "--nan-tolerance", "1", "--length-tolerance", "0"]) == 0
    assert (second / "match.json").read_bytes() == (tmp_path / "matched" / "match.json").read_bytes()
    assert (second / "instances.jsonl").read_bytes() == (tmp_path / "matched" / "instances.jsonl").read_bytes()
