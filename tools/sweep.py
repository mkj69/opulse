"""Run small operator, expression and benchmark pipelines under many settings.

    python tools/sweep.py [--quick]

Every matrix configuration checks operators and expression records against the reference
interpreter, parses rendered text, verifies traces, re-derives benchmark answers from prompts,
and grades a reference derivation. Bounded exact mode also checks z3 and SMT export. Full mode
adds focused cases for optional pipeline controls. Prints one line per configuration.
"""

from __future__ import annotations

import argparse
import itertools
import json
import random
import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from opulse.config import Settings
from opulse.core import NAN, OperatorRegistry
from opulse.definition.parser import DefinitionParser
from opulse.expression.dataset import ExpressionDataset
from opulse.generation.pipeline import OperatorFactory, build_layers
from opulse.trace import Reducer
from opulse.verify import Oracle, check_operator, verify_trace
from opulse.verify.records import audit_record

SYMBOL_SETS = {
    "default": {},
    "xy-brackets": {"left_operand": "x", "right_operand": "y", "left_paren": "[", "right_paren": "]",
                    "nan": "Undef"},
    "pq-braces-assign": {"left_operand": "p", "right_operand": "q", "left_paren": "⟨", "right_paren": "⟩",
                         "equals": ":=", "nan": "⊥"},
}
OPERATOR_SYMBOLS = {
    "shape-index": {},
    "greek-letters": {"naming": "legacy", "symbol_sets": ("greek",), "symbol_max_len": 2},
    "single-char": {"naming": "legacy", "symbol_min_len": 1, "symbol_max_len": 1, "symbol_sets": (),
                    "symbol_blocks": ("2200-22FF", "2A00-2AFF")},
}
SEMANTICS = {
    "exact": {},
    "exact-small-bound": {"bound": 1000},
    "exact-unbounded": {"bound": None},
    "legacy": {"mode": "legacy"},
}
RECURSION = {"bounded_mod": {"style": "bounded_mod"}, "direct": {"style": "direct", "direct_bound": 5}}
OPERATORS = {"total": {"partial_probability": 0.0}, "partial": {"partial_probability": 0.5}}
EXPRESSIONS = {
    "depth2": {"max_depth": 2},
    "depth4-bases": {"max_depth": 4, "random_numeral_base": True, "random_result_base": True},
}

# These cases run only in the full sweep. The Cartesian product above stays small enough to
# compare notation, arithmetic, recursion, partiality and numeral rendering independently.
EXTRA_CASES = {
    "fixed-bases-cot": {"expressions": {"numeral_base": 16, "result_base": 2, "cot_base": 8},
                        "cot": {"cot": "en", "cot_depth": 1, "cot_known_layers": 1}},
    "known-cot-zipf": {"cot": {"cot": "zh", "cot_known": True,
                              "operator_frequency": "zipf:1.5", "frequency_seed": 7},
                       "bench": {"operator_frequency": "zipf:1.5", "frequency_seed": 7}},
    "hole-free": {"family": "hole", "format": "free"},
    "compute-free": {"format": "free"},
    "contrast-steps": {"family": "contrast", "format": "steps"},
    "no-context": {"ablation": True},
    "pseudo-names": {"bench": {"naming": "pseudo", "distractors": 1, "shuffle": True}},
    "english-names": {"bench": {"naming": "english", "max_layer": 1,
                               "max_definitions": 3, "max_abs_value": 1000000}},
    "peano": {"recursion": {"style": "peano"}, "initial": "atomic"},
}


def settings_for(symbols, op_symbols, semantics, recursion, operators, expressions) -> Settings:
    base = Settings()
    sym = replace(base.symbols, **symbols)
    expr = replace(base.expressions, variables=(sym.left_operand, sym.right_operand), **expressions)
    return replace(base, symbols=sym, semantics=replace(base.semantics, **semantics),
                   operators=replace(base.operators, **op_symbols, **operators),
                   recursion=replace(base.recursion, **recursion), expressions=expr)


def run(name: str, settings: Settings, seed: int, *, initial: str | None = None,
        cot: dict | None = None, family: str = "compute", answer_format: str = "steps",
        bench: dict | None = None, ablation: bool = False) -> str:
    start = time.time()
    from opulse.core.starting_sets import starting_registry

    registry = starting_registry(initial or "integer")
    factory = OperatorFactory(settings, registry, random.Random(seed))
    build_layers(factory, [6, 4])
    semantics = settings.semantics.build()
    oracle = Oracle(registry, settings.symbols, semantics)
    parser = DefinitionParser(settings.symbols, registry)
    rng = random.Random(seed)
    defined = [op for op in registry if op.definition]
    for op in defined:
        mismatches = check_operator(op, factory.runtime.evaluate(op), oracle, rng, random_trials=60)
        if mismatches:
            raise AssertionError(f"{op.definition}: {mismatches[:2]}")
        if parser.parse(op.definition) != oracle._definition_of(op):
            raise AssertionError(f"re-parse differs: {op.definition}")
    cot = dict(cot or {})
    if cot.pop("cot_known", False):
        cot["cot_known"] = (defined[0].symbol,)
    dataset = ExpressionDataset(settings, registry, factory.runtime, random.Random(seed), keep_undefined=True,
                                seed=seed, **cot)
    records = list(dataset.records(12))  # every record is re-computed by the oracle on write
    if "operator_frequency" in cot and not all(
            record["provenance"]["operator_frequency"] == cot["operator_frequency"] for record in records):
        raise AssertionError("expression records lost the requested operator frequency")
    if cot.get("cot", "none") != "none" and not all(
            record.get("cot") and record.get("cot_settings") for record in records):
        raise AssertionError("narrated reductions missing from expression records")
    reducer = Reducer(registry, factory.runtime, parser)
    from opulse.expression.nodes import from_ast, from_dict

    for record in records:
        tree = from_dict(record["tree"], registry)
        problems = audit_record(record, registry, oracle, settings, factory.runtime)
        if problems:
            raise AssertionError(f"verify expression {record['id']}: {problems}")
        # The marked text keeps each literal's numeral base; plain texts are decimal.
        texts = ((record["expression"], tree), (record["expression_plain"], _decimal(tree)),
                 (record["expression_full_brackets"], _decimal(tree)))
        for text, expected in texts:
            if from_ast(parser.parse_expr(text, expression_mode=True), registry) != expected:
                raise AssertionError(f"expression text does not parse back: {text}")
    truncated = 0
    for record in records[:6]:
        trace = reducer.reduce(from_dict(record["tree"], registry))
        if trace.truncated:
            truncated += 1  # longer than the reducer's step limit; not a value check
            continue
        verify_trace(trace, oracle)
    # Bench prompts define exact arithmetic only. For a legacy generation case, also check
    # the same operator definitions as an exact benchmark after the legacy runtime checks.
    bench_settings = settings if semantics.mode == "exact" else replace(
        settings, semantics=replace(settings.semantics, mode="exact"))
    bench_note = _check_benchmark(bench_settings, registry, seed, "compute", "steps", bench or {})
    if semantics.mode != "exact":
        bench_note += " (exact benchmark semantics)"
    if (family, answer_format) != ("compute", "steps"):
        bench_note += "; " + _check_benchmark(bench_settings, registry, seed, family, answer_format, bench or {})
    if ablation:
        _check_no_context(bench_settings, registry, seed)
        bench_note += "; no-context ablation ok"
    solver_note = "z3 n/a"
    if semantics.mode == "exact" and semantics.bound is not None:
        from opulse.solver.smt import export, prelude
        from opulse.solver.z3_encode import Z3Encoder, evaluate_concrete

        encoder = Z3Encoder(oracle)
        base = prelude(encoder)
        for op in defined:
            for args in itertools.product([0, 3, -7, 50], repeat=op.n_ary):
                expected = oracle.evaluate(op, args).value
                got = evaluate_concrete(encoder, op, args)
                if not (got is expected or (got is not NAN and expected is not NAN and got == expected)):
                    raise AssertionError(f"z3 {op.definition} at {args}: {got} vs {expected}")
            export(op, encoder, base)
        solver_note = "z3+smt ok"
    undefined = sum(r["undefined"] for r in records)
    return (f"{name}: {len(defined)} operators, {len(records)} expressions ({undefined} NaN), "
            f"{truncated} traces over the step limit, {bench_note}, {solver_note}, {time.time() - start:.1f}s")


def _check_benchmark(settings: Settings, registry: OperatorRegistry, seed: int, family: str,
                     answer_format: str, options: dict) -> str:
    """Check prompt re-derivation and grade a reference solution through the public step grader."""
    from opulse.bench.check import base_registry, check_tasks, prompt_registry
    from opulse.bench.tasks import BenchBuilder
    from opulse.expression.nodes import from_ast
    from opulse.expression.render import ExpressionRenderer
    from opulse.runtime import PythonRuntime
    from opulse.verify.steps import check_steps

    builder = BenchBuilder(settings, registry, random.Random(seed), max_depth=2, allow_nan=True,
                           answer_format=answer_format, max_answer_share=1.0, **options)
    count = 2 if family == "contrast" else 1
    tasks = [task.to_dict() for task in builder.tasks(family, count)]
    if len(tasks) != count:
        raise AssertionError(f"built {len(tasks)} {family} tasks, expected {count}")
    problems = check_tasks(tasks, base_registry(registry), settings.symbols, settings.semantics.build(),
                           check_holes=True)
    if problems:
        raise AssertionError(f"bench check: {problems}")
    graded = 0
    for task in tasks:
        if task["family"] not in ("compute", "contrast"):
            continue  # hole answers are sets; prompt re-derivation applies to compute and contrast
        shown = prompt_registry(task["definitions"], base_registry(registry), settings.symbols,
                                settings.semantics.build())
        source = from_ast(shown.parser.parse_expr(task["expression"], expression_mode=True), shown.registry)
        trace = Reducer(shown.registry, PythonRuntime(shown.registry, settings.semantics.build()),
                        shown.parser).reduce(source)
        if trace.truncated:
            raise AssertionError("reference benchmark derivation was truncated")
        rendered = ExpressionRenderer(settings.symbols)
        lines = [rendered.full(step.expression_after) for step in trace.steps]
        answer = NAN if task["answer"] is None else task["answer"]
        report = check_steps(source, lines, shown.parser, shown.registry, shown.oracle, answer)
        if not (report.all_valid and report.final_correct and report.credit == 1.0
                and report.single_steps == report.steps):
            raise AssertionError(f"reference derivation did not get full step credit: {report.to_dict()}")
        graded += 1
    return f"bench {family}/{answer_format} {len(tasks)} checked, {graded} full step credit"


def _check_no_context(settings: Settings, registry: OperatorRegistry, seed: int) -> None:
    from opulse.bench.tasks import BenchBuilder

    options = {"max_depth": 2, "allow_nan": True, "max_answer_share": 1.0}
    full = next(BenchBuilder(settings, registry, random.Random(seed), **options).tasks("compute", 1))
    hidden = next(BenchBuilder(settings, registry, random.Random(seed), context="none", **options).tasks("compute", 1))
    if (hidden.expression, hidden.answer) != (full.expression, full.answer) or hidden.definitions:
        raise AssertionError("no-context ablation changed the problem or exposed definitions")


def _decimal(node):
    """The same tree with every literal's display base set to 10."""
    from opulse.expression.nodes import Call, Number

    if isinstance(node, Number):
        return Number(node.value)
    if isinstance(node, Call):
        return Call(node.operator, tuple(_decimal(arg) for arg in node.args))
    return node


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true", help="one value per axis beyond the first")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    axes = [SYMBOL_SETS, OPERATOR_SYMBOLS, SEMANTICS, RECURSION, OPERATORS, EXPRESSIONS]
    if args.quick:  # vary one axis at a time around the defaults
        combos = [tuple(next(iter(axis)) for axis in axes)]
        for i, axis in enumerate(axes):
            for key in list(axis)[1:]:
                combo = [next(iter(a)) for a in axes]
                combo[i] = key
                combos.append(tuple(combo))
    else:
        combos = list(itertools.product(*axes))
    failures = 0
    for combo in combos:
        name = "/".join(combo)
        settings = settings_for(*(axis[key] for axis, key in zip(axes, combo)))
        try:
            print(run(name, settings, args.seed), flush=True)
        except Exception as exc:  # noqa: BLE001 - report every failing configuration
            failures += 1
            print(f"{name}: FAILED {type(exc).__name__}: {exc}", flush=True)
    total = len(combos)
    if not args.quick:
        for name, profile in EXTRA_CASES.items():
            total += 1
            settings = settings_for({}, {}, {}, profile.get("recursion", {}), {},
                                    profile.get("expressions", {"max_depth": 2}))
            try:
                print(run(name, settings, args.seed, initial=profile.get("initial"), cot=profile.get("cot"),
                          family=profile.get("family", "compute"),
                          answer_format=profile.get("format", "steps"),
                          bench=profile.get("bench"), ablation=profile.get("ablation", False)), flush=True)
            except Exception as exc:  # noqa: BLE001 - report every failing configuration
                failures += 1
                print(f"{name}: FAILED {type(exc).__name__}: {exc}", flush=True)
        total += 1
        try:
            print(_plugin_case(args.seed), flush=True)
        except Exception as exc:  # noqa: BLE001 - report every failing configuration
            failures += 1
            print(f"custom-plugin: FAILED {type(exc).__name__}: {exc}", flush=True)
    print(f"{total - failures}/{total} configurations passed")
    return 1 if failures else 0


def _plugin_case(seed: int) -> str:
    """Exercise --plugin through generation, verification, and benchmark prompt checking."""
    from opulse.bench.splits import leakage
    from opulse.cli.main import main as cli_main
    from opulse.core.primitives import load_plugins, write_initial_set

    with tempfile.TemporaryDirectory(prefix="opulse-sweep-") as directory:
        root = Path(directory)
        plugin = root / "atoms.py"
        plugin.write_text(
            'from opulse.core.primitives import register_primitive\n'
            'register_primitive("plus_two", "⊛", lambda a: a + 2, '
            'rule="a ⊛ is a + 2.", z3=lambda a: a + 2)\n', encoding="utf-8")
        load_plugins([str(plugin)])
        initial = write_initial_set(root / "initial.jsonl", ["add", "sub", "mod", "neg", "plus_two"], seed)
        ops, expr, tasks = (root / name for name in ("operators.jsonl", "expressions.jsonl", "tasks.jsonl"))
        commands = [
            ["operators", "--initial", str(initial), "--out", str(ops), "--layers", "6", "4", "--seed", str(seed)],
            ["expressions", "--operators", str(ops), "--out", str(expr), "--count", "6", "--seed", str(seed),
             "--keep-undefined", "--cot", "en", "--operator-frequency", "zipf:1.5"],
            ["verify", "--operators", str(ops), "--expressions", str(expr), "--samples", "20"],
            ["bench", "build", "--operators", str(ops), "--out", str(tasks), "--count", "1",
             "--format", "steps", "--max-answer-share", "1"],
            ["bench", "check", "--tasks", str(tasks), "--operators", str(ops)],
            ["bench", "leakage", "--train-operators", str(ops), "--test-operators", str(ops),
             "--max-shared", "15"],
        ]
        for command in commands:
            if cli_main(["--plugin", str(plugin), *command]) != 0:
                raise AssertionError(f"--plugin command failed: {' '.join(command)}")
        registry = OperatorRegistry.from_jsonl(ops)
        if not any(op.symbol == "⊛" and op.definition is None for op in registry):
            raise AssertionError("custom atom missing from generated operator set")
        if not any(op.definition and "⊛" in op.definition for op in registry):
            raise AssertionError("generated definitions did not use the custom atom")
        report = leakage(registry, registry, semantics=Settings().semantics.build())
        if (report["structural"]["shared"], report["behavioural"]["shared"],
                report["shared_func_ids"]) != (10, 10, 10):
            raise AssertionError(f"self-leakage did not find all generated operators: {report}")
        if not json.loads(tasks.read_text(encoding="utf-8").splitlines()[0])["definitions"]:
            raise AssertionError("plugin benchmark task has no generated definition")
        _check_benchmark(Settings(), registry, seed, "compute", "steps", {})
    return "custom-plugin: CLI generation, expressions, verify, bench check, full step credit ok"


if __name__ == "__main__":
    sys.exit(main())
