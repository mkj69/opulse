"""Cross-check generated worlds against independent execution paths.

Run with ``python tools/crosscheck.py --quick`` or set ``--count`` for a longer run.
The count is per world, divided deterministically among the requested seeds.
Failures are JSONL records containing the settings, operators, and expression tree.
"""

from __future__ import annotations

import argparse
import importlib
import json
import multiprocessing as mp
import random
import sys
import tempfile
import time
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def worlds() -> list[str]:
    """Read the registries at run time so newly installed worlds join the run."""
    from opulse.core.presets import PRESETS as typed
    from opulse.presets import PRESETS as numeric

    names = {"default", "action", *numeric, *typed}
    try:
        module = importlib.import_module("opulse.worlds")
    except ModuleNotFoundError as exc:
        if exc.name != "opulse.worlds":
            raise
    else:
        for attribute in ("WORLDS", "PRESETS", "REGISTRY"):
            registered = getattr(module, attribute, None)
            if registered is not None:
                names.update(registered)
        for attribute in ("list_worlds", "available_worlds"):
            listing = getattr(module, attribute, None)
            if callable(listing):
                names.update(listing())
    return sorted(names)


def _setup(world: str, seed: int, layers: tuple[int, ...]):
    from opulse.config import Settings
    from opulse.core.operator import Operator
    from opulse.core.presets import PRESETS as typed
    from opulse.core.presets import register_preset as register_typed
    from opulse.core.primitives import atom_records
    from opulse.core.registry import OperatorRegistry
    from opulse.core.starting_sets import starting_registry
    from opulse.generation.pipeline import OperatorFactory, build_layers
    from opulse.presets import PRESETS as numeric

    if world == "default":
        settings = Settings()
        registry = starting_registry()
        proportions = (0.4, 0.4, 0.2)
    elif world in numeric:
        settings = Settings.from_dict({"preset": world})
        registry = OperatorRegistry(Operator.from_dict(row) for row in atom_records(numeric[world]["atoms"], seed))
        proportions = numeric[world]["proportions"]
    elif world in typed:
        register_typed(world)
        settings = Settings.from_dict({"preset": world,
                                       "recursion": {"style": "bounded_mod" if "mod" in typed[world]
                                                     else "direct"}})
        registry = OperatorRegistry(Operator.from_dict(row) for row in atom_records(typed[world], seed))
        proportions = (0.4, 0.4, 0.2)
    else:
        module = importlib.import_module("opulse.worlds")
        builder = getattr(module, "crosscheck_world", None)
        if builder is not None:
            settings, registry, proportions = builder(world, seed)
        else:
            specs = next((getattr(module, name) for name in ("WORLDS", "PRESETS", "REGISTRY")
                          if world in getattr(module, name, {})), None)
            spec = specs[world] if specs is not None else None
            if callable(spec):
                settings, registry, proportions = spec(seed)
            else:
                raise ValueError(f"registered world {world!r} needs a callable world factory or "
                                 "opulse.worlds.crosscheck_world(name, seed)")
    factory = OperatorFactory(settings, registry, random.Random(seed + len(registry)))
    build_layers(factory, list(layers), proportions)
    return settings, registry, factory.runtime


def _json_value(value):
    from opulse.core.semantics import NAN

    if value is NAN:
        return {"undefined": True}
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    return value


def _oracle_tree(node, oracle):
    from opulse.expression.nodes import Number

    if isinstance(node, Number):
        return node.value
    args = tuple(_oracle_tree(arg, oracle) for arg in node.args)
    return oracle.evaluate(node.operator, args).value


def _runtime_tree(node, runtime):
    from opulse.expression.nodes import Number

    if isinstance(node, Number):
        return node.value
    args = tuple(_runtime_tree(arg, runtime) for arg in node.args)
    return runtime.compute(node.operator)(*args)


def _z3_tree(node, encoder):
    from opulse.core.semantics import NAN
    from opulse.expression.nodes import Number
    from opulse.solver.z3_encode import UNDEF, const

    if isinstance(node, Number):
        return UNDEF if node.value is NAN else const(node.value)
    return encoder.apply(node.operator, [_z3_tree(arg, encoder) for arg in node.args])


def _z3_value(node, encoder):
    import z3

    from opulse.core.semantics import NAN
    from opulse.solver.z3_encode import NotExpressible, _sequence_value

    result = _z3_tree(node, encoder)
    defined = z3.simplify(result.defined)
    if z3.is_false(defined):
        return NAN
    if not z3.is_true(defined):
        raise AssertionError(f"z3 definedness did not simplify: {defined}")
    value = z3.simplify(result.value)
    if z3.is_int_value(value):
        return value.as_long()
    if z3.is_true(value) or z3.is_false(value):
        return z3.is_true(value)
    if z3.is_string_value(value):
        return value.as_string()
    if value.sort().kind() == z3.Z3_SEQ_SORT:
        return _sequence_value(value)
    raise NotExpressible(f"z3 value did not simplify: {value}")


def _check_network(registry, oracle, seed: int):
    """Exercise one generated integer operator and a two part stitch when possible."""
    from opulse.compile import OOV, CompileError, Compiler, Vocab
    from opulse.compile.network import build_network, stitch
    from opulse.core.types import same_value

    candidates = [op for op in registry if op.definition and op.n_ary == 1
                  and op.parameter_types == ("int",) and op.result_type == "int"]
    if not candidates:
        return {"checked": 0, "reason": "no unary integer definition"}
    vocab = Vocab(-2, 4)
    compiler = Compiler(oracle, vocab, input_values=range(3), max_blocks=200)
    networks = []
    for op in candidates:
        try:
            networks.append((op, build_network(compiler.compile(op))))
        except CompileError:
            continue
        if len(networks) == 2:
            break
    if not networks:
        return {"checked": 0, "reason": "no definition fits the small compiler domain"}
    rng = random.Random(seed)
    rows = [(rng.randrange(3),) for _ in range(4)]
    checked = 0
    for op, network in networks:
        for row, got in zip(rows, network.run(rows)):
            expected = oracle.evaluate(op, row).value
            if got is OOV:
                continue
            if not same_value(got, expected):
                raise AssertionError(f"network {op.symbol}{row}: {got!r} != {expected!r}")
            checked += 1
    stitched = 0
    if len(networks) == 2:
        first, second = networks
        joined = stitch([("first", first[1]), ("second", second[1])],
                        {f"second.{second[1].inputs[0]}": f"first.{first[1].output}"},
                        f"second.{second[1].output}")
        for row, got in zip(rows, joined.run(rows)):
            inner = oracle.evaluate(first[0], row).value
            expected = oracle.evaluate(second[0], (inner,)).value
            if got is OOV or first[1].run([row])[0] is OOV:
                continue
            if not same_value(got, expected):
                raise AssertionError(f"stitched {row}: {got!r} != {expected!r}")
            stitched += 1
    return {"checked": checked, "stitched": stitched}


def _action_worker(seed: int, count: int) -> dict:
    """Check action skill traces against a separate evaluator of skill records."""
    from opulse.core.semantics import NAN
    from opulse.core.types import same_value
    from opulse.worlds.action import (
        _examples_states,
        apply_atom,
        encode,
        generate_skills,
        run_skill,
    )

    skills = generate_skills(seed=seed, count=100)
    library = {skill.name: skill for skill in skills}
    states = _examples_states()
    rng = random.Random(seed ^ 0xC05C)

    def evaluate(ref, state):
        if state is NAN:
            return NAN
        skill = library.get(ref)
        if skill is None:
            return apply_atom(ref, state)
        if skill.kind == "composition":
            return evaluate(skill.second, evaluate(skill.first, state))
        if skill.kind == "branch":
            observed = apply_atom(skill.guard, state)
            return NAN if observed is NAN else evaluate(
                skill.first if observed == skill.expected else skill.second, state)
        result = state
        for _ in range(skill.bound):
            observed = apply_atom(skill.guard, result)
            if observed is NAN:
                return NAN
            if observed == skill.expected:
                break
            result = evaluate(skill.first, result)
            if result is NAN:
                break
        return result

    problems = []
    for index in range(count):
        skill = rng.choice(skills)
        state = rng.choice(states)
        expected = evaluate(skill.name, state)
        actual, trace = run_skill(skill, state, library)
        if not same_value(actual, expected) or not trace or trace[-1]["value"] != encode(actual):
            problems.append({"world": "action", "seed": seed, "index": index,
                             "skill": skill.record(), "state": encode(state),
                             "expected": encode(expected), "actual": encode(actual)})
    return {"world": "action", "seed": seed, "count": count,
            "sampled": {"z3": 0, "z3 not applicable": 0, "bench": 0, "network": 0, "stitch": 0},
            "checked": {"action": count, "interpreter": 0, "compiled_python": 0,
                        "reductions": 0, "verify_trace": 0, "cython": 0},
            "problems": problems, "cython": False}


def _worker(job):
    world, seed, count, rates, layers, cython, network = job
    if world == "action":
        return _action_worker(seed, count)
    from opulse.bench.check import answer_from_prompt, base_registry
    from opulse.bench.tasks import BenchBuilder
    from opulse.core.types import same_value
    from opulse.expression.generator import ExpressionGenerator, OperatorPool
    from opulse.expression.nodes import Call, Number, iter_calls, to_dict
    from opulse.solver.z3_encode import NotExpressible, Z3Encoder
    from opulse.trace import Reducer
    from opulse.verify import Oracle, verify_trace

    settings, registry, python = _setup(world, seed, layers)
    oracle = Oracle(registry, settings.symbols, settings.semantics.build())
    typed = world in ("strings", "lists") or any(
        op.result_type != "int" or op.parameter_types != ("int",) * op.n_ary for op in registry)
    generator = ExpressionGenerator(settings.expressions, random.Random(seed ^ 0xC05C))
    pool = OperatorPool.from_registry(registry)
    reducers = {
        "finest": Reducer(registry, python, oracle.parser, max_steps=10000),
        "coarsest": Reducer(registry, python, oracle.parser, expand=lambda op: False),
    }
    try:
        encoder = Z3Encoder(oracle)
    except Exception:  # noqa: BLE001 - an unavailable optional path must not abort a world
        encoder = None
    cython_runtime = None
    if cython:
        try:
            import Cython  # noqa: F401
        except ImportError:
            pass
        else:
            from opulse.runtime.cython_backend import CythonRuntime

            with tempfile.TemporaryDirectory(prefix=".opulse-crosscheck-", dir=ROOT) as directory:
                # The extension must remain loaded after the build directory is removed.
                cython_runtime = CythonRuntime(registry, directory, settings.semantics.build(), jobs=1)
    problems = []
    sampled = {"z3": 0, "z3 not applicable": 0, "bench": 0, "network": 0, "stitch": 0}
    checked = {"action": 0, "interpreter": 0, "compiled_python": 0,
               "reductions": 0, "verify_trace": 0, "cython": 0}
    base = base_registry(registry)
    for index in range(count):
        tree = generator.typed_tree(pool, max_depth=2) if typed else generator.tree(pool, max_depth=2)
        expected = None
        task = None
        if isinstance(tree, Number):
            # Retain an operator application on every trial.
            roots = [op for op in pool.all() if op.definition]
            if roots:
                op = roots[index % len(roots)]
                if typed:
                    from opulse.generation.typed import sample_value

                    tree = Call(op, tuple(Number(sample_value(t, generator.rng)) for t in op.parameter_types))
                else:
                    tree = Call(op, tuple(generator.number() for _ in range(op.n_ary)))
        try:
            expected = _oracle_tree(tree, oracle)
            checked["interpreter"] += 1
            for label, runtime in (("python", python), ("cython", cython_runtime)):
                if runtime is not None:
                    actual = _runtime_tree(tree, runtime)
                    checked["compiled_python" if label == "python" else "cython"] += 1
                    if not same_value(actual, expected):
                        raise AssertionError(f"{label}: {_json_value(actual)} != {_json_value(expected)}")
            for label, reducer in reducers.items():
                trace = reducer.reduce(tree)
                checked["reductions"] += 1
                if trace.truncated:
                    raise AssertionError(f"{label} trace truncated")
                verify_trace(trace, oracle)
                checked["verify_trace"] += 1
                if not same_value(trace.value, expected):
                    raise AssertionError(f"{label} trace: {_json_value(trace.value)} != {_json_value(expected)}")
            if random.Random((seed << 32) + index).random() < rates[0]:
                try:
                    if encoder is None or not all(encoder.expressible(call.operator) for call in iter_calls(tree)):
                        raise NotExpressible("z3 cannot encode this expression")
                    actual = _z3_value(tree, encoder)
                except Exception:  # noqa: BLE001 - an unavailable optional path is not a disagreement
                    sampled["z3 not applicable"] += 1
                else:
                    sampled["z3"] += 1
                    if not same_value(actual, expected):
                        raise AssertionError(f"z3: {_json_value(actual)} != {_json_value(expected)}")
            if random.Random((seed << 32) + index + 17).random() < rates[1]:
                builder = BenchBuilder(settings, registry, random.Random(seed * 1000003 + index),
                                       max_depth=2, allow_nan=True, max_answer_share=1.0)
                built = builder._compute(tree, index)  # the sampled expression is the question when eligible
                task = (built or next(builder.tasks("compute", 1))).to_dict()
                actual = answer_from_prompt(task, base, settings.symbols, settings.semantics.build())
                answer = task["answer"]
                if isinstance(answer, list):
                    answer = tuple(answer)
                if answer is None:
                    from opulse.core.semantics import NAN

                    answer = NAN
                sampled["bench"] += 1
                if not same_value(actual, answer):
                    raise AssertionError(f"bench prompt: {_json_value(actual)} != {_json_value(answer)}")
                if built is not None and not same_value(actual, expected):
                    raise AssertionError(f"bench expression: {_json_value(actual)} != {_json_value(expected)}")
        except Exception as exc:  # noqa: BLE001 - every disagreement needs a reproduction
            import traceback

            problems.append({"world": world, "seed": seed, "index": index, "count": count,
                             "settings": asdict(settings), "operators": [op.to_dict() for op in registry],
                             "tree": to_dict(tree), "task": task, "reference": _json_value(expected),
                             "error": f"{type(exc).__name__}: {exc}",
                             "traceback": traceback.format_exc(limit=6)})
    if network and not typed:
        try:
            import torch  # noqa: F401
        except ImportError:
            pass
        else:
            try:
                result = _check_network(registry, oracle, seed)
                sampled["network"] = result["checked"]
                sampled["stitch"] = result.get("stitched", 0)
            except Exception as exc:  # noqa: BLE001
                problems.append({"world": world, "seed": seed, "index": None,
                                 "settings": asdict(settings), "operators": [op.to_dict() for op in registry],
                                 "error": f"network: {type(exc).__name__}: {exc}"})
    return {"world": world, "seed": seed, "count": count, "sampled": sampled, "checked": checked,
            "problems": problems,
            "cython": cython_runtime is not None}


def run(*, selected: list[str], count: int, seeds: list[int], z3_rate: float,
        bench_rate: float, processes: int, output: Path, layers: tuple[int, ...] = (4, 3),
        cython: bool = True, network: bool = True) -> dict:
    if count < 1 or not seeds or len(seeds) != len(set(seeds)):
        raise ValueError("count must be positive and seeds must be distinct")
    if not 0 <= z3_rate <= 1 or not 0 <= bench_rate <= 1:
        raise ValueError("sample rates must be between 0 and 1")
    available = worlds()
    if set(selected) - set(available):
        raise ValueError(f"unknown worlds: {sorted(set(selected) - set(available))}")
    jobs = [(world, seed, count // len(seeds) + (i < count % len(seeds)),
             (z3_rate, bench_rate), layers, cython, network)
            for world in selected for i, seed in enumerate(seeds)]
    jobs = [job for job in jobs if job[2]]
    results = []
    workers = min(32, max(1, processes), len(jobs))
    if workers == 1:
        results = [_worker(job) for job in jobs]
    else:
        with mp.get_context("spawn").Pool(workers) as pool:
            results = pool.map(_worker, jobs)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for result in results:
            for problem in result["problems"]:
                handle.write(json.dumps(problem, ensure_ascii=False, default=str) + "\n")
    summary = {"worlds": selected, "expressions": sum(r["count"] for r in results),
               "expressions_per_world": {
                   world: sum(r["count"] for r in results if r["world"] == world)
                   for world in selected},
               "checked": {key: sum(r["checked"][key] for r in results)
                           for key in ("action", "interpreter", "compiled_python", "reductions",
                                       "verify_trace", "cython")},
               "z3": sum(r["sampled"]["z3"] for r in results),
               "z3 not applicable": sum(r["sampled"]["z3 not applicable"] for r in results),
               "bench": sum(r["sampled"]["bench"] for r in results),
               "network": sum(r["sampled"]["network"] for r in results),
               "stitch": sum(r["sampled"]["stitch"] for r in results),
               "cython_world_seeds": sum(r["cython"] for r in results),
               "disagreements": sum(len(r["problems"]) for r in results), "output": str(output)}
    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quick", action="store_true", help="check 2000 expressions per world")
    parser.add_argument("--count", type=int, default=None, help="expressions per world, default 100000")
    parser.add_argument("--worlds", nargs="*", default=None, help="selected world names")
    parser.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    parser.add_argument("--z3-rate", type=float, default=0.01)
    parser.add_argument("--bench-rate", type=float, default=0.001)
    parser.add_argument("--processes", type=int, default=4)
    parser.add_argument("--out", type=Path, default=Path("crosscheck_disagreements.jsonl"))
    parser.add_argument("--no-cython", action="store_true")
    parser.add_argument("--no-network", action="store_true")
    args = parser.parse_args(argv)
    start = time.perf_counter()
    summary = run(selected=args.worlds if args.worlds else worlds(),
                  count=args.count if args.count is not None else (2000 if args.quick else 100000),
                  seeds=args.seeds, z3_rate=args.z3_rate, bench_rate=args.bench_rate,
                  processes=args.processes, output=args.out,
                  cython=not args.no_cython, network=not args.no_network)
    summary["runtime_seconds"] = round(time.perf_counter() - start, 2)
    print(json.dumps(summary, ensure_ascii=False))
    return int(summary["disagreements"] > 0)


if __name__ == "__main__":
    raise SystemExit(main())
