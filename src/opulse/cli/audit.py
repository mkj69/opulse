"""Compare each legacy operator's stored ``op_compute_func`` with its ``definition``.

The definition is evaluated by the reference interpreter in ``legacy`` mode
(docs/reference/semantics.md section 2); the legacy function is executed as stored.
Legacy recursive definitions use ``abs(x)``, which the definition grammar has
no syntax for, so ``abs(x)`` is rewritten to a temporary prefix operator ``∥``
that the interpreter treats as a primitive.

Two checks per operator:

* ``local``  - callees are executed by their stored legacy code, so only the
  operator's own definition is compared with its own stored function;
* ``global`` - callees are interpreted from their definitions too, so a wrong
  callee makes every operator above it disagree.

Usage: opulse audit --operators <operators.jsonl> [--samples N]
"""

from __future__ import annotations

import collections
import json
import random
import re
from typing import Any

from opulse.config import Symbols
from opulse.core import Operator, OperatorRegistry
from opulse.core.semantics import DEFAULT_BOUND, LEGACY, NAN, Semantics
from opulse.definition.codegen import registry_resolver
from opulse.definition.interpreter import ReferenceInterpreter
from opulse.definition.parser import DefinitionParser

ABS_SYMBOL = "∥"
ABS_OPERATOR = Operator(func_id="auditabs", symbol=ABS_SYMBOL, n_ary=1, unary_position="prefix",
                        op_compute_func="def op_auditabs(a):\n    return abs(a)\n",
                        op_count_func="def op_count_auditabs(a):\n    return 1\n")


def rewrite_abs(definition: str) -> str:
    return re.sub(r"abs\((\w)\)", rf"({ABS_SYMBOL} \1)", definition)


class LegacyRuntime:
    """Executes stored legacy code strings unchanged (they read the global ``thres``)."""

    def __init__(self, operators) -> None:
        self.namespace: dict[str, Any] = {"thres": DEFAULT_BOUND}
        for operator in operators:
            if operator.op_compute_func:
                exec(operator.op_compute_func, self.namespace)  # noqa: S102 - auditing stored operator code

    def compute(self, operator: Operator):
        return self.namespace[operator.compute_name]


def register(commands) -> None:
    cmd = commands.add_parser("audit", help="check stored legacy compute functions against definitions")
    cmd.add_argument("--operators", required=True)
    cmd.add_argument("--samples", type=int, default=40)
    cmd.add_argument("--seed", type=int, default=0)
    cmd.set_defaults(run=run)


def run(args) -> int:
    with open(args.operators, encoding="utf-8") as source:
        rows = [json.loads(line) for line in source if line.strip()]
    registry = OperatorRegistry(Operator.from_dict(row) for row in rows)
    registry.add(ABS_OPERATOR)
    legacy = LegacyRuntime(registry)
    parser = DefinitionParser(Symbols())
    rng = random.Random(args.seed)
    parsed: dict[str, Any] = {}

    def definition_of(operator):
        if operator.func_id not in parsed:
            parsed[operator.func_id] = parser.parse(rewrite_abs(operator.definition))
        return parsed[operator.func_id]

    semantics = Semantics(LEGACY, DEFAULT_BOUND)
    resolve = registry_resolver(registry)
    stored = {op.func_id: legacy.compute(op) for op in registry if op.definition is not None}
    global_check = ReferenceInterpreter(resolve, definition_of, semantics, extra_primitives={"auditabs": abs})
    stats: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    examples: dict[str, list] = collections.defaultdict(list)
    for operator in registry:
        if operator.definition is None:
            continue
        kind = operator.definition_type
        try:
            definition_of(operator)
        except ValueError:
            stats[kind]["unparseable"] += 1
            continue
        callees = {fid: fn for fid, fn in stored.items() if fid != operator.func_id}
        local_check = ReferenceInterpreter(resolve, definition_of, semantics,
                                           extra_primitives={"auditabs": abs, **callees})
        for mode, interpreter in (("local", local_check), ("global", global_check)):
            mismatch = None
            for _ in range(args.samples):
                inputs = tuple(rng.randint(-200, 200) for _ in range(operator.n_ary))
                try:
                    expected = interpreter.evaluate(operator, inputs).value
                    actual = legacy.compute(operator)(*inputs)
                except Exception as exc:  # noqa: BLE001 - audit records every failure kind
                    mismatch = (inputs, f"error: {type(exc).__name__}")
                    break
                if expected is NAN or expected != actual:
                    mismatch = (inputs, expected, actual)
                    break
            stats[kind][f"{mode} {'mismatch' if mismatch else 'agree'}"] += 1
            if mode == "local" and mismatch and len(examples[kind]) < 3:
                examples[kind].append((operator.definition, mismatch))

    for kind, counter in sorted(stats.items()):
        print(f"{kind}: {dict(counter)}")
        for definition, mismatch in examples[kind]:
            print(f"    {definition}\n        inputs/expected/actual = {mismatch}")
    return 1 if any(counter["local mismatch"] or counter["unparseable"] for counter in stats.values()) else 0
