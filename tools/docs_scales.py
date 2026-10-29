"""Export checked, chunked scale examples from cached operator sets.

Run ``python tools/docs_scales.py [--only s10 s100 ...] [--cache DIR]``.
``--generate`` fills missing caches with the recorded CLI commands; the 10000
integer generation takes on the order of an hour. A cache is usable only when
its log ends in ``exit=0 seconds=N``.

Schema ``opulse.scales/1`` (``index.json``): ``scales`` is an ordered array of
``{key,label,range,sets,examples}``. ``sets`` entries contain ``name,world,seed,
config,config_overrides,generation_command,layers,size,number_of_layers,
generation_seconds,funnel``; ``generation_command`` is the recorded CLI command
using the cache path. For int10000b, ``config_overrides`` records a 600000 ms
safety timeout and a degenerate budget of 60. A z3 query in the degenerate
subexpression check ran past a 600 s safety timeout on deep bodies. The smaller
budget skips proof for large subexpressions, which can only accept more
candidates, never wrongly reject one. ``funnel`` has
``accepted`` and ``rejected`` counters from the last completed layer. ``examples``
is an array of ``{id,set,world,kind,target,layer,closure_size,coarse_steps,
middle_steps,full_steps,expression,value}``. ``unfinished`` lists cache names.

Schema ``opulse.scale-example/1`` (``<scale>/<id>.json``): ``header`` contains
``id,scale,set,world,kind,target_kind,target,layer,closure_size,closure_by_layer,expression,
value,sentence,sentence_zh,cut_table,middle_cut,verification``. Each cut table
row is ``{L,label,label_zh,steps}``: operators in layers below L are known. L=0 opens
all definitions and L=top layer+1 keeps all definitions opaque. ``middle_cut``
minimizes log distance to the geometric mean of coarse and full counts; ties
choose the larger L. Verification
contains ``nodes_verified,full_trace_steps,full_trace_verified,verified_with,
per_layer_counts_checked,seconds``. ``operators`` is the closure plus atoms
used by the DAG, in index order: ``{id,symbol,layer,kind,arity,position,
priority,associativity,definition,result_type,parameter_types}``. The main file has no step-text table;
the header contains its own text. ``root`` is the global node index. ``chunks`` is an array of
``{file,layer,start,end,bytes}``; node indices are in [start,end), with the
``root.json`` chunk last. A layer can have several parts named
``layer-<L>-<K>.json``. All paths are relative to the main example file.

Each chunk is ``{strings:[...],nodes:[...]}``. String indices in its nodes and
steps refer only to that chunk's ``strings`` array. A node is
``{op,inputs,value,steps,full}``:
``op`` is an operator index or -1 for the root; ``inputs`` and ``value`` are
indices in ``strings``; ``full`` is its fully opened step count. Each step is
``[kind,op,child,before,after,condition,path]``. ``kind`` is 0 eval, 1 expand,
2 undefined; ``op`` is an operator index; ``child`` is a node index or -1;
``before`` and ``after`` index ``strings`` and describe the local focus rewrite;
``condition`` is a string index or null; ``path`` is the argument-index path in
the local node's current expression. The step order is execution order.

Decoding: count(node,known) sums 1 for each step unless its child is present
and that step's operator is not known; then add count(child,known). Memoize
per node and cut, but count each reference, since the DAG shares equal
applications. To fetch flattened page k..k+p, walk steps in order and use
these counts to skip entire child subtrees before k. Descend only into child
subtrees intersecting the page. Fetch a chunk only when descending into one
of its nodes. The root has op=-1 and is always loaded.
"""

from __future__ import annotations

import argparse
import ast
import json
import math
import os
import random
import re
import shlex
import shutil
import subprocess
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from opulse.config import Settings
from opulse.core import NAN, OperatorRegistry
from opulse.definition.parser import DefinitionParser
from opulse.expression.nodes import Call, Number
from opulse.expression.render import ExpressionRenderer
from opulse.runtime import PythonRuntime
from opulse.trace.tree import build_tree, flatten, operator_kind, verify_tree
from opulse.verify import Oracle, verify_trace
from opulse.worlds.present import Describer, alias, operator_names

OUT = ROOT / "docs/assets/data/scales"
MAX_FULL = 200_000  # verify_trace materializes and checks every rewrite
MAX_NODES = 8_000
MAX_FILE = 2_000_000
MAX_EXAMPLE = 6_000_000
MAX_TOTAL = 30_000_000
SPECS = {
    "int10": ("s10", "integer", 105, "configs/default.yaml", [3, 3, 3, 1]),
    "int100": ("s100", "integer", 102, "configs/default.yaml", [25, 20, 15, 15, 10, 10, 5]),
    "int1000": ("s1000", "integer", 103, "configs/large.yaml", [200, 170, 150, 120, 100, 80, 70, 50, 35, 25]),
    "int10000b": ("s10000", "integer", 105, "configs/large.yaml", [600, 700, 800, 900, 1000, 1000, 1000, 1000, 900, 800, 700, 600]),
    "str10": ("s10", "strings", 206, "configs/default.yaml", [4, 3, 3]),
    "str100": ("s100", "strings", 202, "configs/default.yaml", [35, 30, 20, 15]),
    "str1000": ("s1000", "strings", 203, "configs/default.yaml", [300, 250, 200, 150, 100]),
    "str10000": ("s10000", "strings", 211, "configs/large.yaml", [2500, 2000, 1600, 1300, 1000, 800, 500, 300]),
}
SAFE_INTEGER_SETS = {"int10000b"}
SCALES = [("s10", "≈10", [1, 10]), ("s100", "≈100", [10, 100]),
          ("s1000", "≈1000", [100, 1000]), ("s10000", "≈10000", [1000, 10000])]


def compact(data: object) -> bytes:
    return (json.dumps(data, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n").encode()


def finished(cache: Path, name: str) -> int | None:
    log = cache / f"{name}.log"
    source = cache / f"{name}.jsonl"
    if not log.exists() or not source.exists():
        return None
    lines = log.read_text().splitlines()
    if not lines:
        return None
    match = re.fullmatch(r"exit=0 seconds=(\d+)", lines[-1])
    return int(match[1]) if match else None


def funnel(cache: Path, name: str) -> dict:
    lines = (cache / f"{name}.log").read_text().splitlines()
    rows = [line.split(" done: ", 1)[1] for line in lines if re.search(r"layer \d+ done: ", line)]
    result = ast.literal_eval(rows[-1]) if rows else {"accepted": {}, "rejected": {}}
    return {key: result.get(key, {}) for key in ("accepted", "rejected")}


def closure(op, registry) -> list:
    seen, stack = {}, [op]
    while stack:
        current = stack.pop()
        if current.definition is None or current.func_id in seen:
            continue
        seen[current.func_id] = current
        stack.extend(registry.get(dep) for dep in current.dependencies if dep in registry)
    return list(seen.values())


def inputs_for(op) -> list[tuple]:
    options = {"int": (0, 1, 2, 3, 5), "str": ("a", "ab", "Ab", "xY", ""),
               "bool": (False, True)}
    columns = [options.get(kind, ()) for kind in op.parameter_types]
    if not all(columns):
        return []
    rng = random.Random(31337 + sum(ord(char) for char in op.func_id))
    results = [tuple(column[i % len(column)] for column in columns) for i in range(5)]
    results += [tuple(rng.choice(column) for column in columns) for _ in range(8)]
    return list(dict.fromkeys(results))


def count_cuts(root) -> list[int]:
    top = root.source.operator.recursive_layer or 0
    memo: dict[tuple[int, int], int] = {}
    for limit in range(top + 2):
        stack = [(root, False)]
        while stack:
            node, done = stack.pop()
            key = (id(node), limit)
            if key in memo:
                continue
            if not done:
                stack.append((node, True))
                for item in node.steps:
                    if item.child is not None and (item.step.operator.recursive_layer or 0) >= limit:
                        stack.append((item.child, False))
            else:
                memo[key] = sum(
                    memo[(id(item.child), limit)]
                    if item.child is not None and (item.step.operator.recursive_layer or 0) >= limit else 1
                    for item in node.steps
                )
    return [memo[(id(root), limit)] for limit in range(top + 2)]


def choose_middle(counts: list[int]) -> int:
    midpoint = (math.log(counts[0]) + math.log(counts[-1])) / 2
    return min(range(len(counts)), key=lambda limit: (abs(math.log(counts[limit]) - midpoint), -limit))


def candidates(registry, kind: str) -> list:
    defined = [op for op in registry if op.definition]
    top = max(op.recursive_layer or 0 for op in defined)
    pool = [op for op in defined if operator_kind(op) == kind and (op.recursive_layer or 0) >= top - 1]
    if len(defined) > 5_000:
        # The closure and its rewrite metadata share the 2 MB main-file cap.
        pool = [op for op in pool if len(closure(op, registry)) <= 4_500]
    if not pool:
        # Small seeded sets can lack a kind in their final two layers.
        fallback = [op for op in defined if operator_kind(op) == kind]
        if fallback:
            highest = max(op.recursive_layer or 0 for op in fallback)
            pool = [op for op in fallback if op.recursive_layer == highest]
    pool.sort(key=lambda op: (-len(closure(op, registry)), -(op.recursive_layer or 0), op.func_id))
    return pool[:18]


def pick(registry, settings, kind: str, prior: list[tuple[str, set[str], int]]):
    runtime = PythonRuntime(registry, settings.semantics.build())
    parser = DefinitionParser(settings.symbols, registry)
    best = None
    for op in candidates(registry, kind):
        op_closure = closure(op, registry)
        closure_ids = {item.func_id for item in op_closure}
        if len(registry) > 500 and any(
            len(closure_ids & chosen_ids) >= 0.95 * len(closure_ids | chosen_ids)
            for _, chosen_ids, _ in prior
        ):
            continue
        for values in inputs_for(op)[:7]:
            try:
                root = build_tree(Call(op, tuple(Number(value) for value in values)),
                                  registry, runtime, parser, max_nodes=MAX_NODES)
                if root.value is NAN:
                    continue
                counts = count_cuts(root)
                if counts[0] > MAX_FULL:
                    continue
                if any(max(counts[0], full) <= 1.05 * min(counts[0], full)
                       and (op.func_id in chosen_ids or chosen_id in closure_ids)
                       for chosen_id, chosen_ids, full in prior):
                    continue
                rank = (counts[0], len(op_closure), op.recursive_layer or 0)
                if best is None or rank > best[0]:
                    best = (rank, op, values, root, counts)
            except (RecursionError, ValueError, OverflowError, TypeError):
                continue
        if best is not None and best[0][0] >= (30_000 if len(registry) > 1000 else 2_000):
            break
    if best is None:
        raise ValueError(f"no usable {kind} target")
    return best[1:]


def export_example(scale: str, name: str, world: str, kind: str, original, settings,
                   prior: list[tuple[str, set[str], int]]):
    start = time.monotonic()
    op, values, _, _ = pick(original, settings, kind, prior)
    defined = closure(op, original)
    names = operator_names(defined, settings,
                           reserved=(item.symbol for item in original if item.definition is None))
    selected = {item.func_id for item in defined}
    registry = OperatorRegistry(
        replace(item, symbol=names[item.symbol], definition=alias(item.definition, names))
        if item.func_id in selected else item
        for item in original if item.definition is None or item.func_id in selected
    )
    target = registry.get(op.func_id)
    parser = DefinitionParser(settings.symbols, registry)
    runtime = PythonRuntime(registry, settings.semantics.build())
    oracle = Oracle(registry, settings.symbols, settings.semantics.build())
    renderer = ExpressionRenderer(settings.symbols)
    expression = Call(target, tuple(Number(value) for value in values))
    root = build_tree(expression, registry, runtime, parser, max_nodes=MAX_NODES)
    counts = count_cuts(root)
    if counts[0] > MAX_FULL:
        raise ValueError("chosen expression exceeds verified trace cap")
    nodes_verified = verify_tree(root, oracle)
    full = flatten(root)
    verify_trace(full, oracle)
    checked = []
    for limit, expected in enumerate(counts):
        if expected <= MAX_FULL:
            actual = (len(full.steps) if limit == 0 else
                      len(flatten(root, lambda item, cutoff=limit:
                                  item.definition is not None and
                                  (item.recursive_layer or 0) >= cutoff).steps))
            if actual != expected:
                raise AssertionError((name, kind, limit, expected, actual))
            checked.append(limit)
    if len(full.steps) != counts[0]:
        raise AssertionError("full count mismatch")
    sentence = Describer(registry, {item.symbol: item.symbol for item in registry}, parser).describe(target)
    by_layer = dict(sorted(Counter(item.recursive_layer for item in defined).items()))
    middle = choose_middle(counts)
    example_id = f"{name}-{kind if world == 'integer' else 'typed'}"
    text = lambda value: renderer.minimal(Number(value))
    header = {
        "id": example_id, "scale": scale, "set": name, "world": world,
        "kind": "typed" if world == "strings" else kind, "target_kind": kind,
        "target": target.symbol, "layer": target.recursive_layer,
        "closure_size": len(defined), "closure_by_layer": by_layer,
        "expression": renderer.minimal(expression), "value": text(root.value),
        "sentence": sentence.en, "sentence_zh": sentence.zh,
        "cut_table": [{"L": limit,
                       "label": ("Fully unfolded" if limit == 0 else
                                 "All operators known" if limit == len(counts) - 1 else
                                 f"Below layer {limit} known"),
                       "label_zh": ("完全展开" if limit == 0 else
                                    "所有算子均已知" if limit == len(counts) - 1 else
                                    f"第 {limit} 层以下算子已知"),
                       "steps": count} for limit, count in enumerate(counts)],
        "middle_cut": middle,
        "verification": {"nodes_verified": nodes_verified, "full_trace_steps": len(full.steps),
                         "full_trace_verified": True, "per_layer_counts_checked": checked,
                         "verified_with": "opulse.verify.verify_trace on the flattened fully unfolded trace and verify_tree on every node",
                         "seconds": round(time.monotonic() - start, 3)},
    }
    prior = OUT / scale / f"{example_id}.json"
    if prior.exists():
        old = json.loads(prior.read_text())["header"]
        if (old["expression"] == header["expression"] and
                old["verification"]["full_trace_steps"] == len(full.steps)):
            # Keep the first verified run's measured time so reruns are byte stable.
            header["verification"]["seconds"] = old["verification"]["seconds"]
    nodes = root.nodes()
    nodes.sort(key=lambda node: (node.operator.recursive_layer if node.operator else 10**6,
                                 renderer.minimal(node.source)))
    indices = {id(node): index for index, node in enumerate(nodes)}
    # Keep only atoms actually visited by this derivation.
    visited = {item.step.operator.func_id for node in nodes for item in node.steps}
    operators = [item for item in registry if item.func_id in selected or item.func_id in visited]
    op_indices = {item.func_id: index for index, item in enumerate(operators)}
    op_rows = [{"id": item.func_id, "symbol": item.symbol, "layer": item.recursive_layer,
                "kind": operator_kind(item), "arity": item.n_ary, "position": item.unary_position,
                "priority": item.priority, "associativity": item.associativity_direction,
                "definition": item.definition, "result_type": item.result_type,
                "parameter_types": item.parameter_types} for item in operators]
    rows = []
    for node in nodes:
        steps = []
        for item in node.steps:
            step = item.step
            steps.append([{"eval": 0, "expand": 1, "undefined": 2}[step.kind],
                          op_indices[step.operator.func_id],
                          indices[id(item.child)] if item.child is not None else -1,
                          renderer.minimal(step.before), renderer.minimal(step.after),
                          step.condition,
                          list(step.path)])
        rows.append({"op": op_indices[node.operator.func_id] if node.operator else -1,
                     "inputs": [text(value) for value in node.inputs],
                     "value": text(node.value), "steps": steps,
                     "full": count_cuts(node)[0] if node.operator else counts[0]})
    output_dir = OUT / scale
    output_dir.mkdir(parents=True, exist_ok=True)
    chunks, payloads = [], []

    def encode_chunk(start: int, end: int) -> bytes:
        strings, string_ids = [], {}

        def intern(value):
            if value not in string_ids:
                string_ids[value] = len(strings)
                strings.append(value)
            return string_ids[value]

        local = []
        for row in rows[start:end]:
            steps = [[step[0], step[1], step[2], intern(step[3]), intern(step[4]),
                      intern(step[5]) if step[5] is not None else None, step[6]]
                     for step in row["steps"]]
            local.append({"op": row["op"], "inputs": [intern(value) for value in row["inputs"]],
                          "value": intern(row["value"]), "steps": steps, "full": row["full"]})
        return compact({"strings": strings, "nodes": local})

    def add_chunk(start: int, end: int, layer: int, part: int) -> int:
        payload = encode_chunk(start, end)
        if len(payload) > MAX_FILE:
            if end - start == 1:
                raise ValueError(f"single node exceeds chunk cap: {name} layer {layer}")
            middle = (start + end) // 2
            part = add_chunk(start, middle, layer, part)
            return add_chunk(middle, end, layer, part)
        relative = (f"{example_id}/root.json" if layer == -1 else
                    f"{example_id}/layer-{layer}-{part}.json")
        payloads.append((relative, payload))
        chunks.append({"file": relative, "layer": layer, "start": start, "end": end,
                       "bytes": len(payload)})
        return part + 1

    begin = 0
    while begin < len(nodes):
        layer = nodes[begin].operator.recursive_layer if nodes[begin].operator else -1
        end = begin + 1
        while end < len(nodes) and (nodes[end].operator.recursive_layer if nodes[end].operator else -1) == layer:
            end += 1
        add_chunk(begin, end, layer, 0)
        begin = end
    data = {"schema": "opulse.scale-example/1", "header": header, "operators": op_rows,
            "root": indices[id(root)], "chunks": chunks}
    path = output_dir / f"{example_id}.json"
    payload = compact(data)
    if len(payload) > MAX_FILE or len(payload) + sum(len(part) for _, part in payloads) > MAX_EXAMPLE:
        raise ValueError(f"example too large: {path}; main={len(payload)} "
                         f"total={len(payload) + sum(len(part) for _, part in payloads)} "
                         f"nodes={len(nodes)} closure={len(defined)} full={counts[0]}")
    files = []
    stale_dir = output_dir / example_id
    if stale_dir.exists():
        for stale in stale_dir.glob("*.json"):
            stale.unlink()
    for relative, part in payloads:
        chunk_path = output_dir / relative
        chunk_path.parent.mkdir(parents=True, exist_ok=True)
        chunk_path.write_bytes(part)
        files.append(chunk_path)
    path.write_bytes(payload)
    files.append(path)
    summary = {key: header[key] for key in ("id", "set", "world", "kind", "target", "layer",
                                               "closure_size", "expression", "value")}
    summary.update(coarse_steps=counts[-1], middle_steps=counts[middle], full_steps=counts[0])
    print(f"{scale:7} {example_id:19} {target.symbol:7} L{target.recursive_layer} "
          f"closure={len(defined):4} steps={counts[-1]}/{counts[middle]}/{counts[0]} "
          f"files={len(files)} bytes={sum(item.stat().st_size for item in files)} "
          f"seconds={header['verification']['seconds']}")
    return summary, (op.func_id, selected, counts[0])


def generate(cache: Path, names: list[str]) -> None:
    cache.mkdir(parents=True, exist_ok=True)
    for name in names:
        if finished(cache, name) is not None:
            continue
        if (cache / f"{name}.jsonl").exists():
            print(f"{name}: partial cache exists; leaving it untouched", file=sys.stderr)
            continue
        _, _, _, config, _ = SPECS[name]
        if name in SAFE_INTEGER_SETS:
            config_path = cache / "large_safe60.yaml"
            config_path.write_text((ROOT / config).read_text().rstrip() +
                                   "\n  safety_timeout_ms: 600000\n  degenerate_budget: 60\n")
        command = generation_command(cache, name)
        started = time.monotonic()
        with (cache / f"{name}.log").open("w") as log:
            result = subprocess.run(command, cwd=ROOT, env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
                                    stdout=log, stderr=subprocess.STDOUT, check=False)
            log.write(f"exit={result.returncode} seconds={round(time.monotonic() - started)}\n")


def generation_command(cache: Path, name: str, *, recorded: bool = False) -> list[str]:
    _, world, seed, config, layers = SPECS[name]
    if recorded:
        # Keep the published command independent of the machine used to export it.
        cache = Path(".cache/opulse_scales")
    if name in SAFE_INTEGER_SETS:
        config = str(cache / "large_safe60.yaml")
    command = (["python", "-m", "opulse.cli.main"] if recorded else
               [sys.executable, "-c", "from opulse.cli.main import main; main()"])
    command += ["operators",
               "--config", config, "--seed", str(seed), "--dedup", "--out",
               str(cache / f"{name}.jsonl")]
    if world == "strings":
        command += ["--preset", "strings"]
    return command + ["--layers", *map(str, layers)]


def export_job(cache: Path, key: str, name: str, kinds: tuple[str, ...]) -> list[dict]:
    _, world, _, config, _ = SPECS[name]
    settings = Settings.load(ROOT / config)
    original = OperatorRegistry.from_jsonl(cache / f"{name}.jsonl")
    prior = []
    summaries = []
    for kind in kinds:
        summary, chosen = export_example(key, name, world, kind, original, settings, prior)
        summaries.append(summary)
        prior.append(chosen)
    return summaries


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    cli.add_argument("--only", nargs="+", choices=[row[0] for row in SCALES])
    cli.add_argument("--cache", type=Path, default=Path(os.getenv("OPULSE_SCALES_CACHE", "/tmp/opulse_scales")))
    cli.add_argument("--generate", action="store_true")
    args = cli.parse_args()
    args.cache = args.cache.resolve()
    chosen = args.only or [row[0] for row in SCALES]
    names = [name for name, spec in SPECS.items() if spec[0] in chosen]
    if args.generate:
        generate(args.cache, names)
    if "s10000" in chosen and finished(args.cache, "int10000b") is None:
        raise ValueError("required s10000 integer set is unfinished: int10000b")
    existing = {}
    index_path = OUT / "index.json"
    if index_path.exists():
        existing = {row["key"]: row for row in json.loads(index_path.read_text())["scales"]}
    scales = []
    jobs = []
    for key, label, range_ in SCALES:
        row = existing.get(key, {"key": key, "label": label, "range": range_, "sets": [], "examples": []})
        if key in chosen:
            row = {"key": key, "label": label, "range": range_, "sets": [], "examples": []}
            for name, (scale, world, seed, config, layers) in SPECS.items():
                if scale != key:
                    continue
                seconds = finished(args.cache, name)
                if seconds is None:
                    continue
                original = OperatorRegistry.from_jsonl(args.cache / f"{name}.jsonl")
                defined = [item for item in original if item.definition]
                row["sets"].append({"name": name, "world": world, "seed": seed,
                                    "config": config,
                                    "config_overrides": ({"operators.safety_timeout_ms": 600000,
                                                          "operators.degenerate_budget": 60}
                                                         if name in SAFE_INTEGER_SETS else {}),
                                    "generation_command": shlex.join(generation_command(args.cache, name,
                                                                                           recorded=True)),
                                    "layers": layers, "size": len(defined),
                                    "number_of_layers": len({item.recursive_layer for item in defined}),
                                    "generation_seconds": seconds, "funnel": funnel(args.cache, name)})
                kinds = ("simple", "branch", "recursive") if world == "integer" else ("simple",)
                jobs.append((key, name, kinds, row))
        scales.append(row)
    with ProcessPoolExecutor(max_workers=min(8, max(1, len(jobs)))) as pool:
        future_rows = [(pool.submit(export_job, args.cache, key, name, kinds), row)
                       for key, name, kinds, row in jobs]
        for future, row in future_rows:
            row["examples"].extend(future.result())
    for row in scales:
        if row["key"] in chosen:
            expected = {summary["id"] for summary in row["examples"]}
            for stale in (OUT / row["key"]).glob("*.json"):
                if stale.stem not in expected:
                    stale.unlink()
                    shutil.rmtree(stale.with_suffix(""), ignore_errors=True)
    OUT.mkdir(parents=True, exist_ok=True)
    unfinished = [name for name in SPECS if finished(args.cache, name) is None]
    index = {"schema": "opulse.scales/1", "scales": scales, "unfinished": unfinished}
    encoded = compact(index)
    if len(encoded) > MAX_FILE:
        raise ValueError("index exceeds file cap")
    index_path.write_bytes(encoded)
    total = sum(path.stat().st_size for path in OUT.rglob("*.json"))
    if total > MAX_TOTAL:
        raise ValueError("scales directory exceeds total cap")
    print(f"total={total} bytes; unfinished={','.join(unfinished) or 'none'}")


if __name__ == "__main__":
    main()
