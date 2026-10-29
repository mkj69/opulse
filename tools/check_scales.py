"""Independently verify published scale examples against Opulse's reference interpreter.

Reads only docs/assets/data/scales and the versioned library/configuration. The
flattened trace is walked from the published DAG with an explicit stack.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from opulse.analysis.coverage import selected_branch
from opulse.config import Settings
from opulse.core import NAN, OperatorRegistry
from opulse.core.operator import Operator
from opulse.core.presets import PRESETS, register_preset
from opulse.core.primitives import atom_records
from opulse.core.starting_sets import starting_registry
from opulse.core.types import same_value
from opulse.definition import ast
from opulse.definition.ast import render_condition
from opulse.definition.parser import DefinitionParser
from opulse.expression.nodes import Call, Number, from_ast, to_ast
from opulse.expression.render import ExpressionRenderer
from opulse.trace.reducer import _substitute_condition
from opulse.verify import Oracle

DATA = ROOT / "docs/assets/data/scales"
SCALE_ORDER = ("s10", "s100", "s1000", "s10000")


class Mismatch(AssertionError):
    pass


def require(ok, where, message):
    if not ok:
        raise Mismatch(f"{where}: {message}")


def check_text(text, tree, parser, renderer, where, field):
    """Check the actual grouping of a rewrite with published precedence."""
    try:
        parsed = parser.parse_expr(text, expression_mode=True)
    except Exception as exc:
        raise Mismatch(f"{where}: cannot parse {field} {text!r}: {exc}") from exc
    require(parsed == to_ast(tree), where,
            f"{field} {text!r} differs from expected {renderer.minimal(tree)!r}")


def subtree(tree, path):
    for slot in path:
        require(isinstance(tree, Call) and 0 <= slot < len(tree.args), "path", f"invalid slot {slot}")
        tree = tree.args[slot]
    return tree


def replace_at(tree, path, replacement):
    if not path:
        return replacement
    require(isinstance(tree, Call) and 0 <= path[0] < len(tree.args), "path", f"invalid slot {path[0]}")
    args = list(tree.args)
    args[path[0]] = replace_at(args[path[0]], path[1:], replacement)
    return Call(tree.operator, tuple(args))


def instantiate(body, env, oracle):
    if isinstance(body, ast.Var):
        return Number(env[body.name])
    if isinstance(body, ast.Num):
        return Number(body.value)
    if isinstance(body, ast.NaN):
        return Number(NAN)
    if isinstance(body, ast.Literal):
        return Number(body.value)
    if isinstance(body, ast.Search):
        return Number(oracle.evaluate_expr(body, env).value)
    return Call(oracle._resolve(body), tuple(instantiate(arg, env, oracle) for arg in body.args))


def read_example(path):
    main = json.loads(path.read_text(encoding="utf-8"))
    require(main.get("schema") == "opulse.scale-example/1", path.name, "wrong schema")
    nodes = []
    prior = 0
    for chunk in main["chunks"]:
        where = f"{main['header']['id']} chunk {chunk['file']}"
        require(chunk["start"] == prior and chunk["end"] > prior, where, "noncontiguous range")
        chunk_path = path.parent / chunk["file"]
        raw = chunk_path.read_bytes()
        require(len(raw) == chunk["bytes"], where, "byte count mismatch")
        payload = json.loads(raw)
        part = payload["nodes"]
        require(len(part) == chunk["end"] - prior, where, "node count mismatch")
        strings = payload.get("strings", main.get("strings"))
        require(isinstance(strings, list), where, "missing string table")
        for node in part:
            def string(index, strings=strings, where=where):
                require(type(index) is int and 0 <= index < len(strings), where, f"bad string index {index}")
                return strings[index]
            nodes.append({"op": node["op"], "inputs": [string(i) for i in node["inputs"]],
                          "value": string(node["value"]), "full": node["full"],
                          "steps": [(s[0], s[1], s[2], string(s[3]), string(s[4]),
                                     None if s[5] is None else string(s[5]), s[6]) for s in node["steps"]]})
        prior = chunk["end"]
    require(main["root"] == len(nodes) - 1, main["header"]["id"], "root index is not last")
    return main, nodes


def registry_for(main, data_dir):
    world = main["header"]["world"]
    require(world in ("integer", "strings"), main["header"]["id"], f"unknown world {world}")
    if world == "strings":
        register_preset("strings")
    index = json.loads((data_dir / "index.json").read_text(encoding="utf-8"))
    set_name = main["header"]["set"]
    sets = [item for scale in index["scales"] for item in scale["sets"] if item["name"] == set_name]
    require(len(sets) == 1, main["header"]["id"], "missing or duplicate set metadata")
    settings = Settings.load(ROOT / sets[0]["config"])
    operators = [Operator(func_id=row["id"], symbol=row["symbol"],
                          n_ary=row["arity"], unary_position=row["position"],
                          recursive_layer=row["layer"], definition=row["definition"],
                          priority=row["priority"], associativity_direction=row["associativity"],
                          parameter_types=row["parameter_types"], result_type=row["result_type"],
                          # The resolver asks for code metadata, but Oracle runs only text.
                          op_compute_func="published", op_count_func="published")
                 for row in main["operators"]]
    published_keys = {(op.symbol, op.n_ary, op.unary_position) for op in operators}
    if world == "integer":
        standard_atoms = list(starting_registry("integer"))
    else:
        standard_atoms = [Operator.from_dict(row) for row in atom_records(PRESETS["strings"])]
    registry = OperatorRegistry(operators)
    for atom in standard_atoms:
        if (atom.symbol, atom.n_ary, atom.unary_position) not in published_keys:
            registry.add(atom)
    parser = DefinitionParser(settings.symbols, registry)
    oracle = Oracle(registry, settings.symbols, settings.semantics.build())
    renderer = ExpressionRenderer(settings.symbols)
    for op in operators:
        if op.definition is not None:
            try:
                oracle._definition_of(op)
            except Exception as exc:
                raise Mismatch(f"{main['header']['id']} operator {op.symbol}: definition parse failed: {exc}") from exc
    return operators, parser, oracle, renderer


def literal(text, parser, registry, where):
    if text.startswith("-") and text[1:].isdigit():
        return int(text)
    try:
        value = from_ast(parser.parse_expr(text, expression_mode=True), registry)
    except Exception as exc:
        raise Mismatch(f"{where}: cannot parse literal {text!r}: {exc}") from exc
    require(isinstance(value, Number), where, f"expected a literal, got {text!r}")
    return value.value


def check_step(current, step, ops, parser, oracle, renderer, where):
    kind, op_index, _child, before, after, condition, path = step
    require(kind in (0, 1, 2), where, f"bad step kind {kind}")
    require(type(op_index) is int and 0 <= op_index < len(ops), where, f"bad operator index {op_index}")
    require(isinstance(path, list) and all(type(p) is int for p in path), where, "bad path")
    focus = subtree(current, path)
    op = ops[op_index]
    require(isinstance(focus, Call) and focus.operator is op, where,
            f"focus operator differs from {op.symbol}")
    require(all(isinstance(arg, Number) for arg in focus.args), where, "focus is not ready")
    check_text(before, focus, parser, renderer, where, "before")
    inputs = tuple(arg.value for arg in focus.args)
    want = oracle.evaluate(op, inputs).value
    if kind == 0:
        got = literal(after, parser, oracle.registry, where)
        require(same_value(got, want), where, f"eval after {after!r} != reference {want!r}")
        if condition is not None:
            definition = oracle._definition_of(op)
            branch = selected_branch(op, inputs, oracle)
            require(branch is not None and isinstance(definition.branches[branch].expr, ast.Search),
                    where, "eval condition without selected search")
        replacement = Number(got)
    elif kind == 2:
        require(op.definition is not None and selected_branch(op, inputs, oracle) is None,
                where, "undefined without an unselected definition")
        got = literal(after, parser, oracle.registry, where)
        require(got is NAN and want is NAN and condition is None, where, "invalid undefined result")
        replacement = Number(NAN)
    else:
        require(op.definition is not None, where, "base operator expanded")
        definition = oracle._definition_of(op)
        branch_index = selected_branch(op, inputs, oracle)
        require(branch_index is not None, where, "no branch selected")
        branch = definition.branches[branch_index]
        env = dict(zip(definition.parameters, inputs))
        expected_condition = (render_condition(_substitute_condition(branch.condition, env), parser.symbols)
                              if branch.condition is not None else None)
        require(condition == expected_condition, where,
                f"condition {condition!r} != selected branch {expected_condition!r}")
        replacement = instantiate(branch.expr, env, oracle)
        check_text(after, replacement, parser, renderer, where, "expand after")
        value = oracle.evaluate_expr(to_ast(replacement), {}).value
        require(same_value(value, want), where,
                f"selected branch value {value!r} != reference {want!r}")
    return replace_at(current, path, replacement), inputs


def source_for(index, nodes, ops, parser, oracle, root, where):
    row = nodes[index]
    if index == root:
        return from_ast(parser.parse_expr(where["expression"], expression_mode=True), oracle.registry)
    op_index = row["op"]
    require(type(op_index) is int and 0 <= op_index < len(ops), f"node {index}", "bad op index")
    op = ops[op_index]
    values = tuple(literal(text, parser, oracle.registry, f"node {index} input") for text in row["inputs"])
    require(len(values) == op.n_ary, f"node {index}", "wrong arity")
    return Call(op, tuple(Number(v) for v in values))


def check_example(path, walk=False):
    started = time.monotonic()
    main, nodes = read_example(Path(path))
    header = main["header"]
    name = header["id"]
    ops, parser, oracle, renderer = registry_for(main, Path(path).parents[1])
    root = main["root"]
    require(nodes[root]["op"] == -1, name, "root node has an operator")
    require(header["verification"]["nodes_verified"] == len(nodes), name,
            "verification nodes_verified mismatch")
    sources = [source_for(i, nodes, ops, parser, oracle, root, header) for i in range(len(nodes))]
    published_value = literal(header["value"], parser, oracle.registry, f"{name} header value")
    root_value = oracle.evaluate_expr(to_ast(sources[root]), {}).value
    require(same_value(root_value, published_value), name,
            f"expression value {root_value!r} != published {published_value!r}")
    for i, row in enumerate(nodes):
        where = f"{name} node {i}"
        current = sources[i]
        want = oracle.evaluate_expr(to_ast(current), {}).value
        stated = literal(row["value"], parser, oracle.registry, where)
        require(same_value(stated, want), where, f"value {stated!r} != interpreter {want!r}")
        for j, step in enumerate(row["steps"]):
            current, inputs = check_step(current, step, ops, parser, oracle, renderer, f"{where} step {j}")
            child = step[2]
            if child != -1:
                require(0 <= child < len(nodes) and step[0] == 0, f"{where} step {j}", "invalid child")
                require(nodes[child]["op"] == step[1], f"{where} step {j}", "child operator mismatch")
                expected_inputs = tuple(literal(s, parser, oracle.registry, f"node {child} input")
                                        for s in nodes[child]["inputs"])
                require(inputs == expected_inputs, f"{where} step {j}", "child inputs mismatch")
            elif step[0] == 0 and ops[step[1]].definition is not None:
                raise Mismatch(f"{where} step {j}: defined eval has no child")
        require(isinstance(current, Number) and same_value(current.value, want), where,
                "local trace does not finish at interpreter value")
    # Iterative dynamic programming. A child index is lower than its parent in
    # the published layer ordering, except for impossible same-layer cycles.
    cuts = header["cut_table"]
    top = header["layer"]
    require([row["L"] for row in cuts] == list(range(top + 2)), name, "cut levels incomplete")
    for limit in range(top + 2):
        counts = count_cut(nodes, ops, limit, name)
        if limit == 0:
            for i, node in enumerate(nodes):
                require(node["full"] == counts[i], f"{name} node {i}",
                        f"full {node['full']} != recomputed {counts[i]}")
            require(header["verification"]["full_trace_steps"] == counts[root], name,
                    "verification full_trace_steps mismatch")
        require(cuts[limit]["steps"] == counts[root], name,
                f"cut L={limit}: {cuts[limit]['steps']} != recomputed {counts[root]}")
    walked = 0
    if walk:
        current = sources[root]
        stack = [(root, 0, ())]
        while stack:
            node_index, j, prefix = stack.pop()
            local = nodes[node_index]["steps"]
            if j == len(local):
                continue
            step = local[j]
            stack.append((node_index, j + 1, prefix))
            if step[2] >= 0:
                stack.append((step[2], 0, prefix + tuple(step[6])))
                continue
            global_step = (*step[:6], list(prefix + tuple(step[6])))
            current, _ = check_step(current, global_step, ops, parser, oracle, renderer,
                                    f"{name} flat step {walked} node {node_index} local step {j}")
            walked += 1
        require(isinstance(current, Number) and same_value(current.value, published_value), name,
                "flat trace final value mismatch")
        require(walked == cuts[0]["steps"], name,
                f"flat steps {walked} != full count {cuts[0]['steps']}")
    return {"example": name, "nodes": len(nodes), "steps": walked,
            "seconds": time.monotonic() - started, "result": "PASS"}


def count_cut(nodes, ops, limit, name):
    counts = [None] * len(nodes)
    visiting = set()
    for start in range(len(nodes)):
        stack = [(start, False)]
        while stack:
            i, done = stack.pop()
            if counts[i] is not None:
                continue
            if not done:
                require(i not in visiting, f"{name} node {i}", "DAG cycle")
                visiting.add(i)
                stack.append((i, True))
                for step in nodes[i]["steps"]:
                    child = step[2]
                    if child >= 0 and ops[step[1]].recursive_layer >= limit:
                        require(child < len(nodes), f"{name} node {i}", f"bad child {child}")
                        if counts[child] is None:
                            require(child not in visiting, f"{name} node {i}", f"cycle through child {child}")
                            stack.append((child, False))
            else:
                counts[i] = sum(counts[s[2]] if s[2] >= 0 and ops[s[1]].recursive_layer >= limit else 1
                                for s in nodes[i]["steps"])
                visiting.remove(i)
    return counts


def worker(task):
    path, walk = task
    started = time.monotonic()
    try:
        return check_example(path, walk)
    except Exception as exc:  # noqa: BLE001 - report every worker failure with its example
        return {"example": Path(path).stem, "nodes": 0, "steps": 0,
                "seconds": time.monotonic() - started, "result": f"FAIL {exc}"}


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    cli.add_argument("--only", nargs="+", choices=SCALE_ORDER)
    cli.add_argument("--data", type=Path, default=DATA)
    cli.add_argument("--jobs", type=int, default=min(16, os.cpu_count() or 1))
    args = cli.parse_args(argv)
    data_dir = args.data
    started = time.monotonic()
    index = json.loads((data_dir / "index.json").read_text(encoding="utf-8"))
    require(index.get("schema") == "opulse.scales/1", "index", "wrong schema")
    chosen = set(args.only or SCALE_ORDER)
    tasks = []
    for scale in index["scales"]:
        if scale["key"] not in chosen:
            continue
        examples = scale["examples"]
        if args.only:
            require(examples, scale["key"], "selected scale has no published examples")
        for summary in examples:
            tasks.append((str(data_dir / scale["key"] / f"{summary['id']}.json"), True))
    require(tasks, "index", "no examples selected")
    with ProcessPoolExecutor(max_workers=min(16, max(1, args.jobs))) as pool:
        futures = [pool.submit(worker, task) for task in tasks]
        rows = [future.result() for future in as_completed(futures)]
    order = {Path(path).stem: i for i, (path, _) in enumerate(tasks)}
    rows.sort(key=lambda row: order[row["example"]])
    print(f"{'example':22} {'nodes':>7} {'steps':>9} {'seconds':>9} result")
    for row in rows:
        print(f"{row['example']:22} {row['nodes']:7} {row['steps']:9} {row['seconds']:9.2f} {row['result']}")
    print(f"total {time.monotonic() - started:.2f}s")
    return 1 if any(row["result"] != "PASS" for row in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
