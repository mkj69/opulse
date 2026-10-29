"""Skeleton extraction, typed binding, acceptance and held out task groups."""

import json
import random
from argparse import Namespace
from dataclasses import replace

import pytest
from conftest import INITIAL_OPERATORS

from opulse.bench.splits import matched_task_leakage, split_matched_tasks
from opulse.canary import CANARY
from opulse.cli.main import main
from opulse.config import Settings
from opulse.core.operator import BRANCH, RECURSIVE, SIMPLE, Operator
from opulse.core.presets import PRESETS, register_preset
from opulse.core.primitives import atom_records
from opulse.core.registry import OperatorRegistry
from opulse.definition import ast
from opulse.definition.codegen import compile_definition, registry_resolver
from opulse.definition.complexity import definition_complexity
from opulse.generation.pipeline import OperatorFactory
from opulse.skeleton import (
    NoMatchError,
    SkeletonSet,
    extract,
    instantiate,
    verify_match,
)
from opulse.verify import Oracle


def _defined(registry, body, *, types, result, arity=1, symbol="◇", func_id="skeletonsource"):
    names = tuple(ast.Var(name) for name in ("a", "b")[:arity])
    definition = ast.Definition(ast.Apply(symbol, names, "postfix" if arity == 1 else None),
                                (ast.Branch(body),))
    operator = Operator(func_id, symbol, arity, "postfix" if arity == 1 else None,
                        definition=ast.render_definition(definition, Settings().symbols),
                        definition_type=SIMPLE, parameter_types=types, result_type=result)
    resolve = registry_resolver(registry, operator)
    code = compile_definition(definition, operator.func_id, resolve, operator.parameter_types)
    operator.op_compute_func, operator.op_count_func = code.compute, code.count
    operator.dependencies = list(code.dependencies)
    metrics = definition_complexity(definition, resolve)
    operator.max_path_depth = metrics.max_path_depth
    operator.max_edge_count = metrics.max_edge_count
    registry.add(operator)
    return operator


def test_extract_json_and_same_world_round_trip():
    registry = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
    a = ast.Var("a")
    source = _defined(registry, ast.Apply("*", (ast.Apply("+", (a, ast.Num(1))), ast.Num(2))),
                      types=("int",), result="int")
    skeletons = SkeletonSet.from_dict(extract(registry).to_dict())
    record = skeletons.records[0]
    atoms = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
    bindings = {f"{record['id']}:{hole['id']}": record["source_correspondence"][hole["id"]] for hole in record["holes"]}
    instance, rows = instantiate(skeletons, atoms, world="integer", correspondence=bindings, seed=1)
    rebuilt = next(op for op in instance if op.skeleton_id == record["id"])
    assert rebuilt.definition == source.definition
    assert rows[0]["correspondence"] == {hole["id"]: record["source_correspondence"][hole["id"]] for hole in record["holes"]}
    assert extract(instance).records[0]["id"] == record["id"]
    assert verify_match(registry, instance, record["id"])["composition_depth_equal"]
    original_oracle, rebuilt_oracle = Oracle(registry), Oracle(instance)
    for value in (-3, 0, 4):
        assert original_oracle.evaluate(source, (value,)).value == rebuilt_oracle.evaluate(rebuilt, (value,)).value


def test_typed_cross_world_preserves_structure_and_changes_values():
    register_preset("strings")
    register_preset("lists")
    strings = OperatorRegistry(Operator.from_dict(row) for row in atom_records(PRESETS["strings"]))
    lists = OperatorRegistry(Operator.from_dict(row) for row in atom_records(PRESETS["lists"]))
    a, b = ast.Var("a"), ast.Var("b")
    _defined(strings, ast.Apply("↶", (ast.Apply("⊕", (a, b)),), "postfix"),
             types=("str", "str"), result="str", arity=2)
    skeletons = extract(strings)
    record = skeletons.records[0]
    bindings = {f"{record['id']}:h0": lists.find("⊞", 2).func_id,
                f"{record['id']}:h1": lists.find("⌄", 1, "postfix").func_id}
    instance, _ = instantiate(skeletons, lists, world="lists", type_map={"str": "list[int]"},
                              correspondence=bindings, seed=2)
    report = verify_match(strings, instance, record["id"])
    assert report == {"structural_hash_equal": True, "composition_depth_equal": True,
                      "value_tables_differ": True, "grade": "G1"}
    assert next(op for op in instance if op.skeleton_id).parameter_types == ("list[int]", "list[int]")


def test_unmatched_signature_reports_failure():
    registry = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
    a = ast.Var("a")
    _defined(registry, ast.Apply("*", (ast.Apply("+", (a, ast.Num(1))), ast.Num(2))),
             types=("int",), result="int")
    with pytest.raises(NoMatchError, match="no atom matches"):
        instantiate(extract(registry), OperatorRegistry.from_jsonl(INITIAL_OPERATORS),
                    world="missing", type_map={"int": "str"}, attempts=2)


def test_acceptance_rejects_constant_binding():
    registry = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
    a = ast.Var("a")
    _defined(registry, ast.Apply("*", (ast.Apply("+", (a, ast.Num(1))), ast.Num(2))),
             types=("int",), result="int")
    skeletons = extract(registry)
    atom_id = registry.find("%", 2).func_id
    bindings = {f"{skeletons.records[0]['id']}:{hole['id']}": atom_id
                for hole in skeletons.records[0]["holes"]}
    with pytest.raises(NoMatchError, match="no accepted correspondence"):
        instantiate(skeletons, OperatorRegistry.from_jsonl(INITIAL_OPERATORS),
                    world="constant", correspondence=bindings, attempts=2)


def test_instance_needs_only_atoms_used_by_its_skeleton():
    registry = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
    a = ast.Var("a")
    _defined(registry, ast.Apply("*", (ast.Apply("+", (a, ast.Num(1))), ast.Num(2))),
             types=("int",), result="int")
    skeletons = extract(registry)
    atoms = OperatorRegistry((registry.find("+", 2), registry.find("*", 2)))
    record = skeletons.records[0]
    bindings = {f"{record['id']}:{hole['id']}": record["source_correspondence"][hole["id"]] for hole in record["holes"]}
    instance, rows = instantiate(skeletons, atoms, world="small", correspondence=bindings,
                                 sample_values={"int": [0, 1, 2]})
    assert len(rows) == 1
    assert next(op for op in instance if op.skeleton_id).definition == registry.get("skeletonsource").definition


def test_equal_structures_keep_distinct_ids_and_correspondences():
    registry = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
    a = ast.Var("a")
    _defined(registry, ast.Apply("*", (ast.Apply("+", (a, ast.Num(1))), ast.Num(2))),
             types=("int",), result="int")
    _defined(registry, ast.Apply("*", (ast.Apply("-", (a, ast.Num(1))), ast.Num(2))),
             types=("int",), result="int", symbol="♢", func_id="skeletonsecond")
    skeletons = extract(registry)
    assert skeletons.records[0]["structural_hash"] == skeletons.records[1]["structural_hash"]
    assert skeletons.records[0]["id"] != skeletons.records[1]["id"]
    bindings = {f"{record['id']}:{hole['id']}": record["source_correspondence"][hole["id"]]
                for record in skeletons.records for hole in record["holes"]}
    instance, rows = instantiate(skeletons, OperatorRegistry.from_jsonl(INITIAL_OPERATORS),
                                 world="integer", correspondence=bindings, attempts=3)
    assert len(rows) == 2
    assert [record["id"] for record in extract(instance).records] == [record["id"] for record in skeletons.records]


def test_whole_set_preserves_branches_recursion_and_dependencies():
    registry = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
    factory = OperatorFactory(Settings(), registry, random.Random(6), max_attempts=100)
    for kind, layer in ((SIMPLE, 0), (BRANCH, 0), (RECURSIVE, 1)):
        factory.add(factory.generate(kind, layer))
    skeletons = extract(registry)
    assert [record["kind"] for record in skeletons.records] == [SIMPLE, BRANCH, RECURSIVE]
    assert skeletons.records[1]["dependencies"] == [skeletons.records[0]["id"]]
    assert skeletons.records[2]["dependencies"] == [skeletons.records[1]["id"]]
    assert "'kind': 'self'" in str(skeletons.records[2]["branches"])
    bindings = {f"{record['id']}:{hole['id']}": record["source_correspondence"][hole["id"]]
                for record in skeletons.records for hole in record["holes"]}
    instance, rows = instantiate(skeletons, OperatorRegistry.from_jsonl(INITIAL_OPERATORS),
                                 world="integer", correspondence=bindings, seed=6, attempts=5)
    assert len(rows) == 3
    for record in skeletons.records:
        report = verify_match(registry, instance, record["id"])
        assert report["structural_hash_equal"] and report["composition_depth_equal"]


def test_direct_recursion_keeps_its_bound_and_partial_domain():
    settings = Settings()
    settings = replace(settings, recursion=replace(settings.recursion, style="direct"))
    registry = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
    factory = OperatorFactory(settings, registry, random.Random(2), max_attempts=300)
    for kind, layer in ((SIMPLE, 0), (RECURSIVE, 1)):
        factory.add(factory.generate(kind, layer))
    skeletons = extract(registry, settings)
    assert skeletons.records[-1]["recursion_form"] == "direct"
    bindings = {f"{record['id']}:{hole['id']}": record["source_correspondence"][hole["id"]]
                for record in skeletons.records for hole in record["holes"]}
    instance, rows = instantiate(skeletons, OperatorRegistry.from_jsonl(INITIAL_OPERATORS),
                                 world="integer", correspondence=bindings, attempts=5)
    assert len(rows) == 2
    assert verify_match(registry, instance, skeletons.records[-1]["id"])["composition_depth_equal"]


def test_skeleton_and_world_splits_keep_keys_disjoint():
    tasks = [
        {"id": "a", "skeleton_ids": ["s1"], "world": "one"},
        {"id": "b", "skeleton_ids": ["s1", "s2"], "world": "two"},
        {"id": "c", "skeleton_ids": ["s2"], "world": "three"},
        {"id": "d", "skeleton_ids": ["s3"], "world": "one"},
    ]
    for by in ("skeleton", "world"):
        parts = split_matched_tasks(tasks, by=by, ratios={"train": 0.5, "test": 0.5}, seed=5)
        report = matched_task_leakage(parts["train"], parts["test"])
        assert report["shared_skeletons" if by == "skeleton" else "shared_worlds"] == 0
        assert sum(map(len, parts.values())) == len(tasks)
        assert split_matched_tasks(tasks, by=by, ratios={"train": 0.5, "test": 0.5}, seed=5) == parts


def test_cli_instance_tasks_carry_skeleton_id(tmp_path):
    source = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
    a = ast.Var("a")
    _defined(source, ast.Apply("*", (ast.Apply("+", (a, ast.Num(1))), ast.Num(2))),
             types=("int",), result="int")
    source_file = tmp_path / "source.jsonl"
    atoms_file = tmp_path / "atoms.jsonl"
    skeleton_file = tmp_path / "skeletons.json"
    instance_file = tmp_path / "instance.jsonl"
    task_file = tmp_path / "tasks.jsonl"
    source.to_jsonl(source_file)
    OperatorRegistry.from_jsonl(INITIAL_OPERATORS).to_jsonl(atoms_file)
    assert main(["skeleton", "extract", "--operators", str(source_file), "--out", str(skeleton_file)]) == 0
    assert json.loads(skeleton_file.read_text())["meta"]["canary"] == CANARY
    record = SkeletonSet.read(skeleton_file).records[0]
    bindings = {f"{record['id']}:{hole['id']}": record["source_correspondence"][hole["id"]] for hole in record["holes"]}
    binding_file = tmp_path / "bindings.json"
    binding_file.write_text(json.dumps(bindings), encoding="utf-8")
    assert main(["skeleton", "instantiate", "--skeletons", str(skeleton_file), "--atoms", str(atoms_file),
                 "--world", "integer", "--out", str(instance_file), "--correspondence", str(binding_file)]) == 0
    instances = [json.loads(line) for line in instance_file.with_suffix(".instances.jsonl").read_text().splitlines()]
    assert all(row["meta"]["canary"] == CANARY for row in instances)
    assert main(["bench", "build", "--operators", str(instance_file), "--out", str(task_file),
                 "--count", "2", "--max-answer-share", "1.0"]) == 0
    tasks = [json.loads(line) for line in task_file.read_text(encoding="utf-8").splitlines()]
    assert len(tasks) == 2
    assert all(task["skeleton_id"] == record["id"] and task["world"] == "integer" for task in tasks)
    assert all(task["id"].startswith("integer-") for task in tasks)
    split_dir = tmp_path / "splits"
    assert main(["bench", "split", "--tasks", str(task_file), "--out-dir", str(split_dir),
                 "--by", "skeleton"]) == 0
    for split_file in split_dir.glob("*.jsonl"):
        assert all(json.loads(line)["meta"]["canary"] == CANARY for line in split_file.read_text().splitlines())
    assert main(["bench", "leakage", "--train-tasks", str(split_dir / "train.jsonl"),
                 "--test-tasks", str(split_dir / "test.jsonl")]) == 0


def test_match_export_files_carry_canary(tmp_path, monkeypatch):
    from opulse.cli import skeleton as command
    from opulse.core.primitives import write_initial_set

    source = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
    _defined(source, ast.Apply("+", (ast.Var("a"), ast.Num(1))), types=("int",), result="int")
    skeleton_file = tmp_path / "skeletons.json"
    extract(source).write(skeleton_file)
    first = write_initial_set(tmp_path / "one.jsonl", ["add", "succ"], seed=1)
    second = write_initial_set(tmp_path / "two.jsonl", ["add", "succ"], seed=2)

    def bind(_skeletons, atoms, **kwargs):
        return atoms, [{"world": kwargs["world"], "skeleton_id": _skeletons.records[0]["id"],
                        "func_id": next(iter(atoms)).func_id, "correspondence": {},
                        "probe": {"nan_rate": 0.0, "lengths": [1]}, "unfolded_length": 1.0}]

    monkeypatch.setattr("opulse.skeleton.instantiate", bind)
    monkeypatch.setattr("opulse.skeleton.value_table", lambda registry, *_args: [{"value": next(iter(registry)).func_id}])
    monkeypatch.setattr("opulse.skeleton.verify_match", lambda *_args, **_kwargs: {
        "structural_hash_equal": True, "composition_depth_equal": True, "value_tables_differ": True})
    output = tmp_path / "match"
    args = Namespace(skeletons=skeleton_file, world=[f"one={first}", f"two={second}"], out_dir=output,
                     type_maps=None, sample_values=None, grade_domains=None, equations=None,
                     partial_domains=False, nan_tolerance=None, length_tolerance=None,
                     config="configs/default.yaml", seed=0, attempts=1)
    assert command.run_match(args) == 0
    assert json.loads((output / "match.json").read_text())["meta"]["canary"] == CANARY
    assert all(json.loads(line)["meta"]["canary"] == CANARY
               for line in (output / "instances.jsonl").read_text().splitlines())
    for name in ("one", "two"):
        assert all(json.loads(line)["meta"]["canary"] == CANARY
                   for line in (output / f"{name}.jsonl").read_text().splitlines())
