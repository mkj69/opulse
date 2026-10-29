"""Type-directed drafts for worlds that contain typed values."""

from __future__ import annotations

import random

from opulse.config import Symbols
from opulse.core.operator import BRANCH, RECURSIVE, SIMPLE
from opulse.core.semantics import NAN
from opulse.definition import ast
from opulse.expression.nodes import Call, Number, Variable, to_ast
from opulse.generation.drafts import Draft, lhs


def sample_value(kind: str, rng: random.Random, registry=None):
    if kind == "int":
        return rng.randrange(0, 5)
    if kind == "bool":
        return rng.choice((False, True))
    if kind == "str":
        if registry is not None and any(op.symbol == "↟" for op in registry):
            from opulse.worlds.rel import load_table

            return rng.choice(load_table()["entities"])
        return rng.choice(("", "a", "ab", "B"))
    if kind == "list[int]":
        return rng.choice(((), (1,), (1, 2), (2, 3)))
    if kind.startswith("perm["):
        from opulse.core.types import parse_type
        from opulse.worlds.perm import Permutation

        values = list(range(parse_type(kind).size))
        rng.shuffle(values)
        return Permutation(values)
    if kind == "grid":
        return rng.choice((((0, 1), (2, 0)), ((3, 0, 3), (0, 1, 0)), ((0, 0), (0, 0))))
    if kind == "note":
        return rng.choice((48, 60, 62, 64, 67, 72))
    if kind == "melody":
        return rng.choice((((60, 1), (64, 1), (67, 2)),
                           ((62, 1), (65, 2)), ((67, 1),)))
    raise ValueError(f"no sample for {kind}")


def defined_somewhere(operator, runtime, registry=None) -> str | None:
    """Require a defined value on boundary and sampled typed inputs."""
    from opulse.generation.interest import TYPED_PROBES
    from opulse.worlds.metrics import probes as world_probes

    rng = random.Random(0)
    values = {"int": (0, -1, 1, -2, 2), **TYPED_PROBES}
    types = operator.parameter_types
    for kind in types:
        if kind not in values:
            values[kind] = world_probes("typed", kind)
    probes = [tuple(values[kind][0] for kind in types)]
    for i, kind in enumerate(types):
        for value in values[kind][1:]:
            point = list(probes[0])
            point[i] = value
            probes.append(tuple(point))
    probes.extend(tuple(sample_value(kind, rng, registry) for kind in types) for _ in range(60))
    compute = runtime.compute(operator)
    if any(compute(*point) is not NAN for point in probes):
        return None
    return "undefined on all samples"


def draft(
    symbol: str, target, registry, symbols: Symbols, rng: random.Random, kind: str
) -> Draft:
    """Compose a target with a typed wrapper and keep every input well typed."""
    specialize = (target.n_ary == 2 and target.recursive_layer
                  and target.result_type in ("note", "melody") and rng.random() < 0.5)
    names = symbols.operands(1 if specialize else target.n_ary)
    inputs = target.parameter_types[:1] if specialize else target.parameter_types
    inner_args = (Variable(names[0]), Number(sample_value(target.parameter_types[1], rng))) \
        if specialize else tuple(Variable(name) for name in names)
    inner = Call(target, inner_args)
    wrappers = [
        (op, index)
        for op in registry
        for index, value_type in enumerate(op.parameter_types)
        if value_type == target.result_type
        and op.func_id != target.func_id
        and (kind != BRANCH or op.result_type == target.result_type)
        and op.definition_type != "recursive_definition"
    ]
    if not wrappers:
        raise ValueError("no type-compatible wrapper")
    wrapper, slot = rng.choice(wrappers)
    # Boolean worlds wire matching inputs into the wrapper; other typed
    # worlds keep sampled constants so their seeded samples stay fixed.
    wire_inputs = any("bool" in op.parameter_types for op in registry)
    args = [
        Variable(rng.choice([name for name, input_type in zip(names, inputs)
                             if input_type == value_type]))
        if wire_inputs and any(input_type == value_type for input_type in inputs)
        else Number(sample_value(value_type, rng, registry))
        for value_type in wrapper.parameter_types
    ]
    args[slot] = inner
    body = to_ast(Call(wrapper, tuple(args)))
    branches = (ast.Branch(body),)
    if kind == BRANCH:
        guard = _guard(names[0], inputs[0], registry, rng)
        if guard is None:
            raise ValueError("no bool-typed guard")
        # Both branches retain the target call; the other branch uses it directly.
        second = to_ast(inner)
        branches = (ast.Branch(body, guard), ast.Branch(second, is_else=True))
    definition = ast.Definition(
        lhs(symbol, len(inputs), "postfix" if specialize else target.unary_position,
            symbols), branches
    )
    return Draft(
        symbol,
        len(inputs),
        "postfix" if specialize else target.unary_position,
        definition,
        SIMPLE if kind == SIMPLE else BRANCH,
        parameter_types=inputs,
        result_type=wrapper.result_type if kind == SIMPLE else target.result_type,
    )


def _guard(name: str, kind: str, registry, rng: random.Random):
    if kind == "bool":
        return ast.Truth(ast.Var(name))
    equality = next(
        (
            op
            for op in registry
            if op.result_type == "bool" and op.parameter_types == (kind, kind)
        ),
        None,
    )
    if equality is not None:
        return ast.Truth(
            ast.Apply(
                equality.symbol,
                (ast.Var(name), ast.Literal(sample_value(kind, rng, registry))),
                equality.unary_position,
            )
        )
    return None


def recursive_draft(
    symbol: str, registry, symbols: Symbols, rng: random.Random, bound: int,
    layer: int = 1,
) -> Draft:
    """A typed accumulator stepped at most ``bound`` times toward zero."""
    unary = [
        op
        for op in registry
        if op.n_ary == 1
        and op.definition_type != RECURSIVE
        and (op.result_type in ("bool", "str", "list[int]", "grid") or op.result_type.startswith("perm[")
             or (op.result_type in ("note", "melody") and op.recursive_layer == layer - 1))
        and op.parameter_types == (op.result_type,)
    ]
    binary = [
        op for op in registry
        if op.n_ary == 2 and op.definition_type != RECURSIVE
        and op.result_type.startswith("perm[")
        and op.parameter_types == (op.result_type, "int")
    ]
    # Layer one starts with unary moves. Later layers may use a generated
    # binary card move with a fixed integer as the recursive step.
    unary_layer = max((op.recursive_layer for op in unary), default=-1)
    binary_layer = max((op.recursive_layer for op in binary), default=-1)
    candidates = binary if binary_layer > unary_layer else unary
    if layer >= 2:
        # A step from the layer just below puts the new recursion on the requested layer. A
        # binary step of any typed value takes the fixed count 1.
        typed = ("bool", "str", "list[int]", "grid", "note", "melody")
        steps = [op for op in registry
                 if op.definition_type != RECURSIVE and op.recursive_layer == layer - 1
                 and (op.result_type in typed or op.result_type.startswith("perm["))
                 and op.parameter_types in ((op.result_type,), (op.result_type, "int"))]
        candidates = steps or candidates
    if not candidates:
        raise ValueError(
            "typed recursion needs a unary atom that preserves its value type"
        )
    step = rng.choice(candidates)
    a, b = symbols.operands(2)
    variable = ast.Var(b)
    def self_call(change):
        return ast.Apply(symbol, (ast.Var(a), change))
    def step_call(change):
        args = (self_call(change),) if step.n_ary == 1 else (self_call(change), ast.Num(1))
        return ast.Apply(step.symbol, args, step.unary_position)
    positive = ast.Apply("-", (variable, ast.Num(1)))
    negative = ast.Apply("+", (variable, ast.Num(1)))
    branches = (
        ast.Branch(ast.Var(a), ast.Compare(variable, "==", ast.Num(0))),
        ast.Branch(
            step_call(positive),
            ast.And(
                ast.Compare(variable, ">", ast.Num(0)),
                ast.Compare(variable, "<=", ast.Num(bound)),
            ),
        ),
        ast.Branch(
            step_call(negative),
            ast.And(
                ast.Compare(variable, "<", ast.Num(0)),
                ast.Compare(
                    variable, ">=", ast.Apply("-", (ast.Num(bound),), "prefix")
                ),
            ),
        ),
    )
    definition = ast.Definition(lhs(symbol, 2, None, symbols), branches)
    return Draft(
        symbol,
        2,
        None,
        definition,
        RECURSIVE,
        complexity=(3, 3),
        parameter_types=(step.result_type, "int"),
        result_type=step.result_type,
    )
