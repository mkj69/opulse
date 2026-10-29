"""Regression tests for generation review findings."""

import json
import random

import pytest
from conftest import INITIAL_OPERATORS

from opulse.config import ExpressionSettings, OperatorSettings, Settings, Symbols
from opulse.core import OperatorRegistry
from opulse.core.operator import BRANCH, RECURSIVE, SIMPLE, Operator
from opulse.definition import ast
from opulse.expression.generator import ExpressionGenerator, OperatorPool
from opulse.expression.nodes import Number
from opulse.generation.drafts import Draft, branch_draft
from opulse.generation.pipeline import OperatorFactory, layer_plan


def test_degenerate_rejection_survives_disabled_dead_branch_check():
    registry = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
    settings = Settings.from_dict({"operators": {"reject_dead_branches": False,
                                                   "reject_degenerate": True}})
    factory = OperatorFactory(settings, registry, random.Random(0))
    definition = ast.Definition(
        ast.Apply("◇", (ast.Var("a"),), "prefix"),
        (ast.Branch(ast.Apply("-", (ast.Var("a"), ast.Var("a")))),),
    )
    draft = Draft("◇", 1, "prefix", definition, "simple_definition")
    operator = factory._compile(draft)
    assert factory._reject_reason(draft, operator, 0) == "degenerate subexpression"


def test_degenerate_solver_timeout_rejects_candidate_and_generation_continues(monkeypatch):
    from opulse.solver import isolated

    registry = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
    factory = OperatorFactory(Settings(), registry, random.Random(0), max_attempts=2)
    lhs = ast.Apply("◇", (ast.Var("a"),), "prefix")
    timed_out = Draft("◇", 1, "prefix", ast.Definition(lhs, (
        ast.Branch(ast.Apply("-", (ast.Var("a"), ast.Var("a")))),
    )), SIMPLE)
    accepted = Draft("◇", 1, "prefix", ast.Definition(lhs, (
        ast.Branch(ast.Apply("+", (ast.Var("a"), ast.Num(1)))),
    )), SIMPLE)
    drafts = iter((timed_out, accepted))
    monkeypatch.setattr(factory, "_draft", lambda kind, layer: next(drafts))
    calls = []

    def timeout(*args, **kwargs):
        calls.append((args, kwargs))
        raise TimeoutError("z3 safety timeout")

    monkeypatch.setattr(isolated, "check", timeout)
    rejected = []
    factory.on_reject = lambda operator, reason, kind, layer: rejected.append((operator, reason, kind, layer))

    result = factory.generate(SIMPLE, 0)

    reason = "solver safety timeout in degenerate check"
    assert len(calls) == 1
    assert result.definition == "◇ a = { a + 1 }"
    assert factory.stats.accepted[SIMPLE] == 1
    assert factory.stats.rejected[reason] == 1
    assert factory.stats.summary()["rejected"] == {reason: 1}
    assert len(rejected) == 1
    assert rejected[0][0] is not None
    assert rejected[0][1:] == (reason, SIMPLE, 0)


def test_dead_branch_solver_timeout_rejects_candidate(monkeypatch):
    from opulse.solver import static

    registry = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
    settings = Settings.from_dict({"operators": {"reject_degenerate": False}})
    factory = OperatorFactory(settings, registry, random.Random(0), max_attempts=1)
    lhs = ast.Apply("◇", (ast.Var("a"),), "prefix")
    draft = Draft("◇", 1, "prefix", ast.Definition(lhs, (
        ast.Branch(ast.Apply("+", (ast.Var("a"), ast.Num(1))),
                   ast.Compare(ast.Var("a"), "<", ast.Num(0))),
        ast.Branch(ast.Apply("+", (ast.Var("a"), ast.Num(2)))),
    )), BRANCH)
    monkeypatch.setattr(factory, "_draft", lambda kind, layer: draft)

    def timeout(*args, **kwargs):
        raise TimeoutError("z3 safety timeout")

    monkeypatch.setattr(static, "dead_branch_reason", timeout)
    rejected = []
    factory.on_reject = lambda operator, reason, kind, layer: rejected.append(reason)

    with pytest.raises(RuntimeError, match="no acceptable branch_definition"):
        factory.generate(BRANCH, 0)

    reason = "solver safety timeout in dead branch check"
    assert factory.stats.rejected[reason] == 1
    assert rejected == [reason]


def test_typed_generation_rejects_operator_undefined_on_all_samples():
    from opulse.core.operator import SIMPLE
    from opulse.core.primitives import (
        atom_records,
        register_primitive,
        unregister_primitive,
    )
    from opulse.core.semantics import NAN

    names = ("review_nan_one", "review_nan_two")
    try:
        for name, symbol in zip(names, ("⊛", "⊙")):
            register_primitive(name, symbol, lambda value: NAN, rule="Always undefined.",
                               parameter_types=("str",), result_type="str")
        registry = OperatorRegistry(Operator.from_dict(row) for row in
                                    atom_records(("add", "sub", "mod", *names)))
        factory = OperatorFactory(Settings(), registry, random.Random(18), max_attempts=10)
        with pytest.raises(RuntimeError, match="no acceptable simple_definition"):
            factory.generate(SIMPLE, 0)
        assert factory.stats.rejected["undefined on all samples"] > 0
    finally:
        for name in names:
            unregister_primitive(name)


@pytest.mark.parametrize("count,proportions", [
    (1, (0, 1, 0)),
    (2, (0, 1, 0)),
    (3, (1 / 3, 2 / 3, 0)),
])
def test_layer_plan_forced_seed_respects_count(count, proportions):
    plan = layer_plan(count, 1, proportions, random.Random(0))
    assert len(plan) == count
    assert plan[0] == RECURSIVE
    if proportions[0] == 0:
        assert plan.count(BRANCH) == count - 1


@pytest.mark.parametrize("body_count", [2, 3, 4])
def test_narrow_threshold_range_rejects_partial_unary_draft(body_count):
    settings = OperatorSettings(condition_min=0, condition_max=0, partial_probability=1)
    with pytest.raises(ValueError, match="threshold range is too small"):
        branch_draft("◇", 1, "prefix", [Number(i) for i in range(body_count)],
                     settings, Symbols(), random.Random(0))


def test_random_numeral_base_uses_configured_maximum():
    settings = Settings.from_dict({"numerals": {"max_base": 20},
                                   "expressions": {"random_numeral_base": True}})
    generator = ExpressionGenerator(settings.expressions, random.Random(0), max_base=settings.numerals.max_base)
    bases = {generator.number().base for _ in range(200)}
    assert max(bases) == 20
    assert min(bases) >= 2


def test_expression_cli_uses_configured_numeral_maximum(tmp_path):
    from opulse.cli.main import main

    config = tmp_path / "config.yaml"
    config.write_text("numerals:\n  max_base: 20\nexpressions:\n  random_numeral_base: true\n")
    output = tmp_path / "expressions.jsonl"
    assert main(["expressions", "--operators", str(INITIAL_OPERATORS), "--config", str(config),
                 "--out", str(output), "--count", "50", "--seed", "0"]) == 0
    rows = [json.loads(line) for line in output.read_text().splitlines()]

    def bases(tree):
        if tree["type"] == "numeric_atoms":
            yield tree["base"]
        for child in ("left_expr", "right_expr", "unary_expr"):
            if child in tree:
                yield from bases(tree[child])
        for child in tree.get("args", ()):
            yield from bases(child)

    assert max(base for row in rows for base in bases(row["tree"])) > 16


def test_zero_weight_available_kinds_fall_back_to_atom():
    settings = ExpressionSettings(max_depth=2, type_weights={
        "binary": 1, "unary_prefix": 0, "unary_postfix": 0, "atom": 0,
    })
    generator = ExpressionGenerator(settings, random.Random(0))
    pool = OperatorPool.from_registry(OperatorRegistry.from_jsonl(INITIAL_OPERATORS))
    tree = generator.tree(pool, leaf_budget=2)
    assert tree is not None


def test_zipf_rejects_underflowed_rank_weights():
    pool = OperatorPool(binary=[
        Operator(func_id=str(i), symbol=f"◇{i}", n_ary=2, definition="defined")
        for i in range(3)
    ])
    with pytest.raises(ValueError, match="Zipf.*underflow"):
        pool.with_frequency("zipf:1100", seed=0)
