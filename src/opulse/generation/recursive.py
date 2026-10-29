"""Recursive operators built from one callee of the layer below.

Two templates (docs/reference/semantics.md section 4.1). ``v`` is the loop
variable, ``g`` the callee, ``f`` the new operator.

Template A, ``bounded_mod`` (``m`` the modulus)::

    f(..v..) = { base,                         if v % m == 0
                 g(args with R = f(..(v % m) - 1..)), if v % m > 0
                 g(args with R = f(..(v % m) + 1..)), if v % m < 0 }

``%`` keeps the dividend's sign, so the recursion walks ``v % m`` toward 0
from either side and unfolds at most ``m - 1`` times.

Template B, ``direct`` (``T`` the bound)::

    f(..v..) = { base,                          if v == 0
                 g(args with R = f(..v - 1..)),  if v > 0 and v <= T
                 g(args with R = f(..v + 1..)),  if v < 0 and v >= - T }

The direction follows the sign of ``v`` itself; beyond ``|v| > T`` no branch
matches and the result is undefined. It unfolds at most ``T`` times.
Style ``peano`` is template B written with the atoms ``v ⁻`` / ``v ⁺``
instead of ``v - 1`` / ``v + 1`` (same values), for operator sets that start
from the atomic domain. ``R`` marks the
recursive result inside the callee's arguments; the other argument slots hold
the operator's own parameters (taken from the *current* frame, exactly as the
definition reads).

Template D, ``primitive`` (the primitive-recursion schema, ``n`` the last
parameter, ``x`` the others, ``T`` the bound)::

    h(x, n) = { base(x),                         if n == 0
                g(x, n - 1, h(x, n - 1)),        if n > 0 and n <= T
                g(x, n + 1, h(x, n + 1)),        if n < 0 and n >= - T }

The branch shape and bound are those of template B, so termination, the NaN
beyond ``|n| > T`` and the z3 case split are the same. What changes is the
body: ``base`` is an expression over the other parameters built from lower
layers, and the step ``g(...)`` is an expression of lower-layer operators that
reads the stepped counter *and* the previous result (and possibly parameters).
With only the atoms ``⁻ ⁺`` available (no binary ``- +``) the counter steps
with them, as in template C.

The compute/count functions are produced by the ordinary code generator from
this definition, so they agree with it by construction. (The legacy generator
wrote a separate loop that disagreed with the definition for 54 of 127
parseable recursive operators in ``operator_1k.jsonl``.)
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from opulse.config import RecursionSettings, Symbols
from opulse.core.operator import BINARY, POSTFIX, RECURSIVE, Operator
from opulse.core.semantics import base_operation_name
from opulse.definition import ast
from opulse.generation.drafts import Draft, lhs

REC = "#R"  # placeholder (not a valid parameter name) for the recursive result in an argument template


@dataclass(frozen=True)
class RecursiveSpec:
    symbol: str
    n_ary: int
    unary_position: str | None
    callee: Operator
    loop_variable: str
    modulus: int
    arguments: tuple[str, ...]  # one entry per callee slot: REC or a parameter name
    base: ast.Expr
    style: str = "bounded_mod"  # or "direct"/"peano"; ``modulus`` holds T for those
    step_down: str = "⁻"
    step_up: str = "⁺"
    nonnegative: bool = False

    @property
    def recursive_slots(self) -> int:
        return self.arguments.count(REC)

    def complexity(self) -> tuple[int, int]:
        """Worst case: ``m-1`` (or ``T``) unfoldings; two recursive slots double the calls per level."""
        unfold = self.modulus - 1 if self.style == "bounded_mod" else self.modulus
        calls = 2**unfold - 1 if self.recursive_slots == 2 else unfold
        return unfold * self.callee.max_path_depth, calls * self.callee.max_edge_count


def random_spec(symbol: str, n_ary: int, unary_position: str | None, callee: Operator,
                settings: RecursionSettings, symbols: Symbols, rng: random.Random,
                style: str | None = None) -> RecursiveSpec:
    params = symbols.operands(n_ary)
    loop_variable = rng.choice(params)
    others = [p for p in params if p != loop_variable]

    if callee.n_ary == BINARY:
        templates = ([(REC, REC)] if settings.max_recursive_calls == 2 else []) + \
            [(REC, p) for p in params] + [(p, REC) for p in params]
        arguments = rng.choice(templates)
    elif callee.n_ary > BINARY:  # one recursive slot (more would multiply the calls per level)
        slot = rng.randrange(callee.n_ary)
        arguments = tuple(REC if i == slot else rng.choice(params) for i in range(callee.n_ary))
    else:
        arguments = (REC,)

    constant = ast.negate(rng.randint(settings.constant_min, settings.constant_max))
    base_choices = [ast.Var(p) for p in others] or [ast.Var(loop_variable)]
    base = rng.choice(base_choices + [constant])
    style = settings.style if style is None else style
    if style in ("direct", "peano", "bits"):
        size = settings.direct_bound
    elif style == "bounded_mod":
        size = rng.randint(settings.modulus_min, settings.modulus_max)
    else:
        raise ValueError(f"recursion style must be bounded_mod, direct, peano, bits or primitive, got {style!r}")
    return RecursiveSpec(symbol, n_ary, unary_position, callee, loop_variable, size, arguments, base,
                         style, settings.step_down, settings.step_up, settings.nonnegative)


def recursive_draft(spec: RecursiveSpec, symbols: Symbols) -> Draft:
    head = lhs(spec.symbol, spec.n_ary, spec.unary_position, symbols)
    v = ast.Var(spec.loop_variable)
    # Template A walks ``v % m``; template B walks ``v`` itself.
    control = ast.Apply("%", (v, ast.Num(spec.modulus))) if spec.style == "bounded_mod" else v

    def step_body(step_symbol: str) -> ast.Expr:
        if spec.style == "bits":
            stepped = ast.Apply("⇒", (control, ast.Num(1)))
        elif spec.style == "peano":
            stepped = ast.Apply(spec.step_down if step_symbol == "-" else spec.step_up, (control,), POSTFIX)
        else:
            stepped = ast.Apply(step_symbol, (control, ast.Num(1)))
        frame = tuple(stepped if arg.name == spec.loop_variable else arg for arg in head.args)
        recursive_call = ast.Apply(spec.symbol, frame, spec.unary_position)
        callee_args = tuple(recursive_call if slot == REC else ast.Var(slot) for slot in spec.arguments)
        return ast.Apply(spec.callee.symbol, callee_args, spec.callee.unary_position)

    if spec.style == "bounded_mod":
        down = ast.Compare(control, ">", ast.Num(0))
        up = ast.Compare(control, "<", ast.Num(0))
    else:
        bound = spec.modulus
        down = ast.And(ast.Compare(v, ">", ast.Num(0)), ast.Compare(v, "<=", ast.Num(bound)))
        up = ast.And(ast.Compare(v, "<", ast.Num(0)), ast.Compare(v, ">=", ast.negate(-bound)))
    branches = [ast.Branch(spec.base, ast.Compare(control, "==", ast.Num(0))),
                ast.Branch(step_body("-"), down)]
    if not spec.nonnegative:
        branches.append(ast.Branch(step_body("+"), up))
    return Draft(spec.symbol, spec.n_ary, spec.unary_position, ast.Definition(head, tuple(branches)),
                 RECURSIVE, complexity=spec.complexity(), recursion_style=spec.style)


# ------------------------------------------------------------- template D: primitive recursion


def counter_steps(registry) -> tuple[str, str]:
    """How template D writes ``n - 1`` / ``n + 1``: "arith" (binary ``-``, ``+``) or "peano"
    (postfix ``⁻``, ``⁺``), whichever the starting set has (arith preferred)."""
    have = {base_operation_name(op.symbol, op.n_ary, op.unary_position)
            for op in registry if op.definition is None}
    if {"sub", "add"} <= have:
        return "arith"
    if {"pred", "succ"} <= have:
        return "peano"
    raise ValueError("recursion.style 'primitive' needs the base operations sub and add (or pred and succ)")


def _stepped(counter: ast.Var, down: bool, steps: str) -> ast.Expr:
    if steps == "peano":
        return ast.Apply("⁻" if down else "⁺", (counter,), POSTFIX)
    return ast.Apply("-" if down else "+", (counter, ast.Num(1)))


@dataclass(frozen=True)
class PrimitiveSpec:
    """``h(x, n) = { base, if n == 0; step[C = n - 1], ...; step[C = n + 1], ... }``.

    ``step`` is an expression in which ``Var(COUNTER)`` stands for the stepped counter and
    ``Var(REC)`` for the previous result ``h(x, C)``; the other variables are parameters.
    """

    symbol: str
    n_ary: int
    unary_position: str | None
    base: ast.Expr
    step: ast.Expr
    bound: int
    steps: str = "arith"  # or "peano"


COUNTER = "#C"  # placeholder (not a valid parameter name) for the stepped counter inside ``PrimitiveSpec.step``


def random_primitive_spec(symbol: str, n_ary: int, unary_position: str | None, callee: Operator,
                          registry, layer: int, settings: RecursionSettings, symbols: Symbols,
                          expressions, rng: random.Random) -> PrimitiveSpec:
    """A template-D operator whose step calls ``callee`` (layer ``layer - 1``).

    The step reads the counter and the previous result: ``callee`` gets both in two of its
    argument slots (the other slots get parameters or the counter); a unary callee gets them
    combined by a binary operator of a lower layer, ``g(R ⊙ C)`` or ``g(C ⊙ R)``. ``base`` is a
    random expression over the other parameters built from operators below ``layer``, or a
    parameter, or a constant.
    """
    from opulse.expression.generator import NoCandidateError, OperatorPool
    from opulse.expression.nodes import to_ast

    params = symbols.operands(n_ary)
    others = params[:-1]
    rec, counter = ast.Var(REC), ast.Var(COUNTER)
    if callee.n_ary == 1:
        binary = registry.binary(max_layer=layer - 1)
        if not binary:
            raise NoCandidateError("a unary step needs a binary operator below the layer to read the counter")
        combine = rng.choice(binary)
        pair = (rec, counter) if rng.random() < 0.5 else (counter, rec)
        step = ast.Apply(callee.symbol, (ast.Apply(combine.symbol, pair),), callee.unary_position)
    else:
        slots = rng.sample(range(callee.n_ary), 2)
        unused = [ast.Var(p) for p in others]
        rng.shuffle(unused)
        args = []
        for i in range(callee.n_ary):
            if i in slots:
                args.append(rec if i == slots[0] else counter)
            else:  # free slots: parameters not placed yet first, then any parameter or the counter
                args.append(unused.pop() if unused else rng.choice([ast.Var(p) for p in others] + [counter]))
        step = ast.Apply(callee.symbol, tuple(args), callee.unary_position)

    constant = ast.negate(rng.randint(settings.constant_min, settings.constant_max))
    choice = rng.random()
    if others and choice < 0.5:
        pool = OperatorPool.from_registry(registry, max_layer=layer - 1)
        tree = expressions.tree(pool, max_depth=rng.randint(1, max(1, expressions.settings.max_depth - 1)),
                                atoms="mixed", variables=others)
        base = to_ast(tree)
    elif others and choice < 0.8:
        base = ast.Var(rng.choice(others))
    else:
        base = constant
    # Every other parameter must matter outside the recursive frame (which only passes it on).
    if set(others) - _names(base) - _names(step):
        raise NoCandidateError("a parameter is only passed along the recursion")
    return PrimitiveSpec(symbol, n_ary, unary_position, base, step, settings.direct_bound,
                         counter_steps(registry))


def _names(node: ast.Expr) -> set[str]:
    if isinstance(node, ast.Var):
        return {node.name}
    if isinstance(node, ast.Apply):
        return set().union(*(_names(arg) for arg in node.args))
    return set()


def _substitute(node: ast.Expr, mapping: dict[str, ast.Expr]) -> ast.Expr:
    if isinstance(node, ast.Var) and node.name in mapping:
        return mapping[node.name]
    if isinstance(node, ast.Apply):
        return ast.Apply(node.symbol, tuple(_substitute(arg, mapping) for arg in node.args), node.unary_position)
    return node


def primitive_draft(spec: PrimitiveSpec, symbols: Symbols, resolve=None) -> Draft:
    """The template-D definition; ``resolve`` (an application -> operator lookup for everything
    but the new operator) gives the structural metrics, else they are derived later."""
    head = lhs(spec.symbol, spec.n_ary, spec.unary_position, symbols)
    n = head.args[-1]
    bound = spec.bound

    def step_body(down: bool) -> ast.Expr:
        stepped = _stepped(n, down, spec.steps)
        frame = tuple(stepped if arg == n else arg for arg in head.args)
        recursive_call = ast.Apply(spec.symbol, frame, spec.unary_position)
        return _substitute(spec.step, {REC: recursive_call, COUNTER: stepped})

    down = ast.And(ast.Compare(n, ">", ast.Num(0)), ast.Compare(n, "<=", ast.Num(bound)))
    up = ast.And(ast.Compare(n, "<", ast.Num(0)), ast.Compare(n, ">=", ast.negate(-bound)))
    branches = (
        ast.Branch(spec.base, ast.Compare(n, "==", ast.Num(0))),
        ast.Branch(step_body(True), down),
        ast.Branch(step_body(False), up),
    )
    complexity = None
    if resolve is not None:
        from opulse.definition.complexity import expr_complexity

        stepped = _stepped(n, True, spec.steps)
        one_step = _substitute(spec.step, {REC: ast.Num(0), COUNTER: stepped})
        step_cost = expr_complexity(one_step, resolve)
        base_cost = expr_complexity(spec.base, resolve)
        complexity = (bound * step_cost.max_path_depth + base_cost.max_path_depth,
                      bound * step_cost.max_edge_count + base_cost.max_edge_count)
    return Draft(spec.symbol, spec.n_ary, spec.unary_position, ast.Definition(head, branches),
                 RECURSIVE, complexity=complexity, recursion_style="primitive")
