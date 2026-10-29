"""``opulse equivalences``: equivalence data with checked labels.

Three kinds of records, each labelled by :mod:`opulse.solver.equivalence`
(``equivalent`` is true only when proved, false only with a counterexample
re-checked by the reference oracle, null when undecided):

* ``operators``      - pairs of operators with different definitions and the same values;
* ``simplification`` - an arithmetic expression over variables and SymPy's expanded form,
                       which may or may not survive the bound (overflow gives NaN);
* ``commuted``       - an expression and the same expression with the operands of one
                       binary application swapped.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from opulse.canary import marked
from opulse.cli.operators import DEFAULT_CONFIG
from opulse.config import Settings
from opulse.core.registry import OperatorRegistry
from opulse.core.semantics import base_operation_name
from opulse.expression.generator import ExpressionGenerator, OperatorPool
from opulse.expression.nodes import Call, Node, Variable, to_dict
from opulse.expression.render import ExpressionRenderer
from opulse.solver.equivalence import (
    ARITHMETIC,
    EquivalenceChecker,
    equivalent_operators,
    sympy_candidate,
)
from opulse.solver.fallback import checked_label, resolve_range
from opulse.solver.z3_encode import NotExpressible, Z3Encoder
from opulse.verify import Oracle


def register(commands) -> None:
    cmd = commands.add_parser("equivalences", help="equivalent operators and expression pairs with checked labels")
    cmd.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    cmd.add_argument("--operators", type=Path, required=True)
    cmd.add_argument("--out", type=Path, required=True)
    cmd.add_argument("--count", type=int, default=100, help="expression pairs of each kind")
    cmd.add_argument("--max-depth", type=int, default=3)
    cmd.add_argument("--seed", type=int, default=0)
    cmd.add_argument("--timeout-ms", type=int, default=30_000, help="z3 safety timeout per check")
    cmd.add_argument("--rlimit", type=int, default=None, help="z3 resource limit per check")
    cmd.add_argument("--keep-undecided", action="store_true", help="also write pairs z3 could not decide")
    cmd.add_argument("--fallback-range", type=int, nargs=2, metavar=("LO", "HI"),
                     help="reference check range when z3 encoding is unavailable")
    cmd.set_defaults(run=run)


def run(args) -> int:
    settings = Settings.load(args.config)
    registry = OperatorRegistry.from_jsonl(args.operators)
    oracle = Oracle(registry, settings.symbols, settings.semantics.build())
    try:
        encoder = Z3Encoder(oracle)
    except NotExpressible as exc:
        raise SystemExit(f"equivalences needs exact semantics: {exc}") from exc
    try:
        fallback_range = resolve_range(settings.solver.fallback_range, args.fallback_range, encoder.bound)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    checker = EquivalenceChecker(encoder, timeout_ms=args.timeout_ms, fallback_range=fallback_range,
                                 rlimit=settings.solver.rlimit if args.rlimit is None else args.rlimit,
                                 max_nodes=settings.solver.max_nodes)
    rng = random.Random(args.seed)
    renderer = ExpressionRenderer(settings.symbols)
    generator = ExpressionGenerator(settings.expressions, rng)
    variables = settings.symbols.operands(2)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        fallback_written = 0
        proved_written = 0
        def write(kind: str, left: Node, right: Node, verdict) -> None:
            nonlocal fallback_written, proved_written
            if verdict.equivalent is None and verdict.status != "checked" and not args.keep_undecided:
                return
            record = {"kind": kind, "left": renderer.minimal(left), "right": renderer.minimal(right),
                      **verdict.to_dict(), "left_tree": to_dict(left), "right_tree": to_dict(right)}
            handle.write(json.dumps(marked(record), ensure_ascii=False) + "\n")
            fallback_written += verdict.strength is not None
            proved_written += verdict.status == "proved"

        for f, g, verdict in equivalent_operators(registry, checker):
            names = variables[: f.n_ary] if f.n_ary <= 2 else settings.symbols.operands(f.n_ary)
            write("operators", Call(f, tuple(map(Variable, names))), Call(g, tuple(map(Variable, names))), verdict)

        arithmetic = OperatorPool.from_registry(_arithmetic_registry(registry))
        for _ in range(args.count):
            tree = generator.tree(arithmetic, max_depth=args.max_depth, atoms="mixed", variables=variables)
            candidate = sympy_candidate(tree, registry) if isinstance(tree, Call) else None
            if candidate is not None and candidate != tree:
                write("simplification", tree, candidate, checker.check(tree, candidate))

        integer_registry = OperatorRegistry(op for op in registry
                                            if op.result_type == "int" and
                                            all(kind == "int" for kind in op.parameter_types))
        pool = OperatorPool.from_registry(integer_registry)
        for _ in range(args.count):
            tree = generator.tree(pool, max_depth=args.max_depth, atoms="mixed", variables=variables)
            swapped = _swap_one(tree, rng)
            if swapped is not None:
                write("commuted", tree, swapped, checker.check(tree, swapped))
    if fallback_range is not None:
        print(f"equivalences: {proved_written} proved; {fallback_written} "
              f"{checked_label(fallback_range)} (reference interpreter)")
    return 0


def _arithmetic_registry(registry: OperatorRegistry) -> OperatorRegistry:
    subset = OperatorRegistry()
    for op in registry:
        if op.definition is None and base_operation_name(op.symbol, op.n_ary, op.unary_position) in ARITHMETIC:
            subset.add(op)
    return subset


def _swap_one(tree: Node, rng: random.Random) -> Node | None:
    """``tree`` with the operands of one binary application swapped (None if there is none)."""
    paths = []

    def walk(node, path):
        if isinstance(node, Call):
            if node.operator.n_ary == 2 and node.args[0] != node.args[1]:
                paths.append(path)
            for i, arg in enumerate(node.args):
                walk(arg, path + (i,))

    walk(tree, ())
    if not paths:
        return None
    target = rng.choice(paths)

    def rebuild(node, path):
        if path == target:
            return Call(node.operator, (node.args[1], node.args[0]))
        if isinstance(node, Call):
            return Call(node.operator, tuple(rebuild(arg, path + (i,)) for i, arg in enumerate(node.args)))
        return node

    return rebuild(tree, ())
