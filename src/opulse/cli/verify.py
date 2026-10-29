"""``opulse verify``: check an operator file (and optionally an expression file) against the spec.

Every operator's compiled code is compared with the reference interpreter on
boundary and random inputs (value, base operations, calls). Every field of
each expression record is re-derived (opulse.verify.records.audit_record). Exit status 1 on any mismatch.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from opulse.cli.operators import DEFAULT_CONFIG
from opulse.config import Settings
from opulse.core.registry import OperatorRegistry
from opulse.runtime import PythonRuntime
from opulse.verify import Oracle, check_operator
from opulse.verify.records import audit_record


def register(commands) -> None:
    cmd = commands.add_parser("verify", help="check operators/expressions against the reference semantics")
    cmd.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    cmd.add_argument("--operators", type=Path, required=True)
    cmd.add_argument("--expressions", type=Path, default=None)
    cmd.add_argument("--samples", type=int, default=200, help="random inputs per operator")
    cmd.add_argument("--seed", type=int, default=0)
    cmd.add_argument("--cython-build-dir", type=Path, default=None)
    cmd.set_defaults(run=run)


def run(args) -> int:
    settings = Settings.load(args.config)
    semantics = settings.semantics.build()
    registry = OperatorRegistry.from_jsonl(args.operators)
    if args.cython_build_dir:
        from opulse.runtime.cython_backend import CythonRuntime
        runtime = CythonRuntime(registry, args.cython_build_dir, semantics)
    else:
        runtime = PythonRuntime(registry, semantics)
    oracle = Oracle(registry, settings.symbols, semantics)
    failures = 0
    checked = 0
    for operator in registry:
        if operator.definition is None:
            continue
        checked += 1
        mismatches = check_operator(operator, runtime.evaluate(operator), oracle,
                                    random.Random(args.seed), args.samples)
        if mismatches:
            failures += 1
            print(f"MISMATCH {operator.func_id} {operator.definition}\n    {mismatches[0]}")
    print(f"operators: {checked} checked, {failures} with mismatches")
    if args.expressions:
        bad = 0
        trace_cache = {}
        rows = [json.loads(line) for line in open(args.expressions, encoding="utf-8") if line.strip()]
        for row in rows:
            problems = audit_record(row, registry, oracle, settings, runtime, trace_cache)
            if problems:
                bad += 1
                print(f"MISMATCH expression {row['id']}: " + "; ".join(problems))
        print(f"expressions: {len(rows)} checked, {bad} mismatches")
        failures += bad
    return 1 if failures else 0
