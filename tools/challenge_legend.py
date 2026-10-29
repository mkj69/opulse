"""Build the three reproducible int1000 legend puzzles and their shared-DAG traces.

Run ``PYTHONPATH=$PWD/src python tools/challenge_legend.py --cache /tmp/opulse_scales``.
The cache must be outside the repo and match the SHA-256 of the completed
``int1000`` command in ``docs/assets/data/scales/index.json``. The published
``legend.json`` keeps schema ``opulse.challenge/1``. A ``steps_ref`` has
``{format:"opulse.scale-example/1",path:"legend/<id>/",count:N}``, relative to
``docs/assets/data/challenge/``. Read ``<path>/index.json``; its ``operators``,
``root``, and ``chunks`` have exactly the shared-DAG layout documented in
``tools/docs_scales.py``. Chunk file paths are relative to ``index.json``;
``root.json`` is last. ``count`` excludes the initial expression. Each inline
``coarse_steps`` array includes the initial expression with ``rule:null``, as
on the small challenge ladder; ``coarse_step_count`` excludes that row.
``variant.steps_ref`` points to a separate DAG in the same puzzle directory.
The one-rule variant changes one low-layer token; ``affected_rules`` counts
closure rules transitively dependent on it, including the edited rule.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import docs_scales as scales
from tools.challenge_explanations import add_explanation
from tools.challenge_quality import validate_tier
from opulse.config import Settings
from opulse.core import NAN, OperatorRegistry
from opulse.definition.codegen import compile_definition, registry_resolver
from opulse.definition.parser import DefinitionParser
from opulse.expression.nodes import Call, Number
from opulse.expression.render import ExpressionRenderer
from opulse.runtime import PythonRuntime
from opulse.trace.tree import build_tree, flatten, verify_tree, operator_kind
from opulse.verify import Oracle, verify_trace
from opulse.worlds.present import alias, operator_names

OUT = ROOT / "docs/assets/data/challenge"
CACHE_SHA256 = "628515743e5788c9c86415a8c3a8cd014a6e6899b1547de02386676607ea64b5"
RECIPES = (
    ("○₉₈₉", "▲₃₀₆", "♠₈₂₇", "●₈₂₆", "○₉₄₆", "■₉₇₉", "☆₈₉₄", "△₈₂₁"),
    ("♤₉₈₃", "♦₉₄₁", "♣₉₅₀", "♠₉₉₇", "♡₉₂₆"),
    ("♧₉₆₈", "☆₉₃₆", "♣₉₇₁", "◇₉₉₂", "♠₉₇₃", "♠₉₅₃"),
)

EDITED_SYMBOLS = ("▲₃₀₆", "♣₂₁₉", "△₃")


def load_set(cache: Path):
    source = cache / "int1000.jsonl"
    index = json.loads((ROOT / "docs/assets/data/scales/index.json").read_text())
    record = next(row for row in index["scales"] if row["key"] == "s1000")
    spec = next(row for row in record["sets"] if row["name"] == "int1000")
    assert spec["seed"] == 103 and spec["config"] == "configs/large.yaml"
    assert spec["layers"] == [200, 170, 150, 120, 100, 80, 70, 50, 35, 25]
    assert "--dedup" in spec["generation_command"]
    assert scales.finished(cache, "int1000") is not None
    assert hashlib.sha256(source.read_bytes()).hexdigest() == CACHE_SHA256, "int1000 cache differs"
    original = OperatorRegistry.from_jsonl(source)
    defined = [op for op in original if op.definition]
    assert len(defined) == 1000
    assert [Counter(op.recursive_layer for op in defined)[i] for i in range(10)] == spec["layers"]
    settings = Settings.load(ROOT / spec["config"])
    names = operator_names(defined, settings, reserved=(op.symbol for op in original if not op.definition))
    registry = OperatorRegistry(
        replace(op, symbol=names[op.symbol], definition=alias(op.definition, names))
        if op.definition else op for op in original
    )
    return registry, settings, spec


def named(registry, symbol):
    return next(op for op in registry if op.symbol == symbol)


def question(registry, number):
    plus = registry.find("+", 2)
    if number == 1:
        zero_chain = Call(named(registry, "■₉₇₉"), (
            Call(named(registry, "○₉₄₆"), (
                Call(named(registry, "●₈₂₆"), (
                    Call(named(registry, "♠₈₂₇"), (Number(0),)),)),)), Number(0)))
        terms = (Call(named(registry, "○₉₈₉"), (Number(2),)),
                 Call(named(registry, "▲₃₀₆"), (Number(29),)),
                 zero_chain,
                 Call(named(registry, "☆₈₉₄"), (Number(0),)),
                 Call(named(registry, "△₈₂₁"), (Number(0), Number(2))))
        result = terms[0]
        for term in terms[1:]:
            result = Call(plus, (result, term))
        return result
    if number == 2:
        factors = (Call(named(registry, "♣₉₅₀"), (Number(2),)),
                   Call(named(registry, "♦₉₄₁"), (Number(2),)),
                   Call(plus, (Number(1), Call(named(registry, "♣₉₅₀"), (Number(0),)))),
                   Call(named(registry, "♡₉₂₆"), (
                       Call(named(registry, "♤₉₈₃"), (
                           Call(named(registry, "♠₉₉₇"), (Number(1), Number(1))),)),)))
        result = factors[0]
        for factor in factors[1:]:
            result = Call(registry.find("*", 2), (result, factor))
        return result
    if number == 3:
        return Call(named(registry, "♧₉₆₈"), (
            Call(named(registry, "☆₉₃₆"), (Number(0),)),
            Call(named(registry, "♣₉₇₁"), (
                Call(named(registry, "◇₉₉₂"), (
                    Call(named(registry, "♠₉₇₃"), (Number(1),)),)),
                Call(named(registry, "♠₉₅₃"), (Number(1),))))))
    raise ValueError(number)


def closure_of(ids, registry):
    selected = {op.func_id: op for ident in ids for op in scales.closure(registry.get(ident), registry)}
    return sorted(selected.values(), key=lambda op: (op.recursive_layer, op.func_id))


def step_count(root):
    memo = {}
    def visit(node):
        key = id(node)
        if key not in memo:
            memo[key] = sum(visit(item.child) if item.child is not None else 1 for item in node.steps)
        return memo[key]
    return visit(root)


def page_steps(trace, renderer):
    return [{"expr": renderer.full(trace.source), "rule": None}] + [
        {"expr": renderer.full(step.expression_after), "rule": step.operator.symbol}
        for step in trace.steps
    ]


def mutated_registry(registry, settings, op, new_text):
    changed = replace(op, definition=new_text)
    draft = OperatorRegistry(changed if item.func_id == op.func_id else item for item in registry)
    oracle = Oracle(draft, settings.symbols, settings.semantics.build())
    generated = compile_definition(oracle._definition_of(changed), changed.func_id,
                                   registry_resolver(draft), changed.parameter_types, changed.result_type)
    changed = replace(changed, op_compute_func=generated.compute, op_count_func=generated.count)
    return OperatorRegistry(changed if item.func_id == op.func_id else item for item in registry)


def value(node, runtime):
    if isinstance(node, Number):
        return node.value
    args = tuple(value(arg, runtime) for arg in node.args)
    return runtime.compute(node.operator)(*args)


def rebind(node, registry):
    if isinstance(node, Number):
        return node
    return Call(registry.get(node.operator.func_id), tuple(rebind(arg, registry) for arg in node.args))


def variant_text(number, before):
    if number == 1:
        old, new = "a < 29", "a <= 29"
    elif number == 2:
        old, new = "- 77, if", "- 78, if"
    elif number == 3:
        old, new = "a + a", "a - a"
    else:
        raise ValueError(number)
    assert before.count(old) == 1
    return before.replace(old, new, 1)


def affected_count(rules, ident):
    reverse = {op.func_id: set() for op in rules}
    for op in rules:
        for dependency in op.dependencies:
            if dependency in reverse and dependency != op.func_id:
                reverse[dependency].add(op.func_id)
    affected, pending = {ident}, [ident]
    while pending:
        for dependent in reverse[pending.pop()]:
            if dependent not in affected:
                affected.add(dependent)
                pending.append(dependent)
    return len(affected)


def choose_variant(registry, settings, source, rules, answer, number):
    op = named(registry, EDITED_SYMBOLS[number-1])
    after = variant_text(number, op.definition)
    changed = mutated_registry(registry, settings, op, after)
    runtime = PythonRuntime(changed, settings.semantics.build())
    result = value(source, runtime)
    assert isinstance(result, int) and not isinstance(result, bool)
    assert abs(result-answer) >= 3
    tree = build_tree(rebind(source, changed), changed, runtime,
                      DefinitionParser(settings.symbols, changed), max_nodes=8000)
    assert 20_000 <= step_count(tree) <= 300_000 and tree.value == result
    affected = affected_count(rules, op.func_id)
    assert affected >= 100
    return changed, tree, op, after, affected


def export_dag(root, registry, settings, path, ident, question_text, defined_ids):
    """Write the exact scale-example shared-DAG node and chunk representation."""
    renderer = ExpressionRenderer(settings.symbols)
    nodes = root.nodes()
    nodes.sort(key=lambda node: (node.operator.recursive_layer if node.operator else 10**6,
                                 renderer.minimal(node.source)))
    indices = {id(node): i for i, node in enumerate(nodes)}
    visited = {item.step.operator.func_id for node in nodes for item in node.steps}
    operators = [op for op in registry if op.definition is None or op.func_id in visited
                 or op.func_id in defined_ids]
    op_ids = {op.func_id: i for i, op in enumerate(operators)}
    op_rows = [{"id": op.func_id, "symbol": op.symbol, "layer": op.recursive_layer,
                "kind": operator_kind(op), "arity": op.n_ary, "position": op.unary_position,
                "priority": op.priority, "associativity": op.associativity_direction,
                "definition": op.definition, "result_type": op.result_type,
                "parameter_types": op.parameter_types} for op in operators]
    memo = {}
    def count(node):
        key = id(node)
        if key not in memo:
            memo[key] = sum(count(item.child) if item.child else 1 for item in node.steps)
        return memo[key]
    rows = []
    for node in nodes:
        rows.append({"op": op_ids[node.operator.func_id] if node.operator else -1,
                     "inputs": [renderer.minimal(Number(x)) for x in node.inputs],
                     "value": renderer.minimal(Number(node.value)), "full": count(node),
                     "steps": [[{"eval": 0, "expand": 1, "undefined": 2}[item.step.kind],
                                op_ids[item.step.operator.func_id],
                                indices[id(item.child)] if item.child else -1,
                                renderer.minimal(item.step.before), renderer.minimal(item.step.after),
                                item.step.condition, list(item.step.path)] for item in node.steps]})
    path.mkdir(parents=True, exist_ok=True)
    for stale in path.glob("*.json"):
        stale.unlink()
    chunks = []
    def write_chunk(start, end, layer, part):
        strings, string_ids = [], {}
        def intern(s):
            if s not in string_ids:
                string_ids[s] = len(strings)
                strings.append(s)
            return string_ids[s]
        local = []
        for row in rows[start:end]:
            local.append({"op": row["op"], "inputs": [intern(s) for s in row["inputs"]],
                          "value": intern(row["value"]), "full": row["full"],
                          "steps": [[step[0], step[1], step[2], intern(step[3]), intern(step[4]),
                                     intern(step[5]) if step[5] is not None else None, step[6]]
                                    for step in row["steps"]]})
        payload = scales.compact({"strings": strings, "nodes": local})
        if len(payload) > scales.MAX_FILE:
            if end-start == 1:
                raise ValueError("single DAG node exceeds chunk cap")
            mid = (start+end)//2
            part = write_chunk(start, mid, layer, part)
            return write_chunk(mid, end, layer, part)
        filename = "root.json" if layer == -1 else f"layer-{layer}-{part}.json"
        (path / filename).write_bytes(payload)
        chunks.append({"file": filename, "layer": layer, "start": start, "end": end,
                       "bytes": len(payload)})
        return part+1
    begin = 0
    while begin < len(nodes):
        layer = nodes[begin].operator.recursive_layer if nodes[begin].operator else -1
        end = begin+1
        while end < len(nodes) and nodes[end].operator and nodes[end].operator.recursive_layer == layer:
            end += 1
        write_chunk(begin, end, layer, 0)
        begin = end
    main = {"schema": "opulse.scale-example/1", "header": {
        "id": ident, "expression": question_text,
        "value": renderer.minimal(Number(root.value)),
        "verification": {"full_trace_verified": True, "full_trace_steps": count(root),
                         "nodes_verified": len(nodes)}},
        "operators": op_rows, "root": indices[id(root)], "chunks": chunks}
    (path / "index.json").write_bytes(scales.compact(main))
    return sum(file.stat().st_size for file in path.glob("*.json"))


def generate(cache: Path):
    original, settings, spec = load_set(cache)
    renderer = ExpressionRenderer(settings.symbols)
    puzzles = []
    for number, symbols in enumerate(RECIPES, 1):
        registry = original
        ids = tuple(named(registry, symbol).func_id for symbol in symbols)
        parser = DefinitionParser(settings.symbols, registry)
        runtime = PythonRuntime(registry, settings.semantics.build())
        oracle = Oracle(registry, settings.symbols, settings.semantics.build())
        ident = f"legend-{number:02d}"
        source = question(registry, number)
        question_text = renderer.full(source)
        root = build_tree(source, registry, runtime, parser, max_nodes=8000)
        count = step_count(root)
        assert 20_000 <= count <= 300_000 and isinstance(root.value, int)
        rules = closure_of(ids, registry)
        question_ids = set(ids)
        coarse = flatten(root, lambda op: op.func_id in question_ids)
        verify_trace(coarse, oracle)
        assert len(coarse.steps) < 40
        varied, variant_root, edited, after, affected = choose_variant(
            registry, settings, source, rules, root.value, number)
        variant_oracle = Oracle(varied, settings.symbols, settings.semantics.build())
        variant_coarse = flatten(variant_root, lambda op: op.func_id in question_ids)
        verify_trace(variant_coarse, variant_oracle)
        assert len(variant_coarse.steps) < 40
        for current, current_oracle in ((root, oracle), (variant_root, variant_oracle)):
            verify_tree(current, current_oracle)
            full = flatten(current)
            assert len(full.steps) == step_count(current)
            verify_trace(full, current_oracle)
        base_path = OUT / "legend" / ident
        defined_ids = {op.func_id for op in rules}
        base_size = export_dag(root, registry, settings, base_path, ident, question_text, defined_ids)
        variant_size = export_dag(variant_root, varied, settings, base_path / "variant", ident,
                                  question_text, defined_ids)
        total = base_size + variant_size
        assert total < 4_000_000, (ident, total)
        row = {"id": ident, "level": "legend", "set": {"name": "int1000",
               "operators": 1000, "seed": 103, "command": spec["generation_command"]},
               "rules": [{"symbol": op.symbol, "text": op.definition,
                          "hint": f"Apply {op.symbol} using this definition.",
                          "layer": op.recursive_layer+1} for op in rules],
               "question": question_text, "answer": root.value,
               "steps_ref": {"format": "opulse.scale-example/1",
                             "path": f"legend/{ident}/", "count": count},
               "step_count": count, "coarse_steps": page_steps(coarse, renderer),
               "coarse_step_count": len(coarse.steps), "verified": True,
               "variant": {"rule_index": rules.index(edited), "before": edited.definition,
                           "after": after, "answer": variant_root.value,
                           "affected_rules": affected, "verified": True,
                           "steps_ref": {"format": "opulse.scale-example/1",
                                         "path": f"legend/{ident}/variant/",
                                         "count": step_count(variant_root)},
                           "step_count": step_count(variant_root),
                           "coarse_steps": page_steps(variant_coarse, renderer),
                           "coarse_step_count": len(variant_coarse.steps)},
               "data_bytes": total}
        puzzles.append(add_explanation(row))
        print(ident, question_text, len(rules), count, len(coarse.steps), root.value,
              variant_root.value, affected, total, flush=True)
    validate_tier(puzzles)
    from tools.example_atoms import annotate
    data = annotate({"schema": "opulse.challenge/1", "challenges": puzzles})
    (OUT / "legend.json").write_bytes(scales.compact(data))
    return data


def main():
    cli = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    cli.add_argument("--cache", type=Path, default=Path("/tmp/opulse_scales"))
    cli.add_argument("--check", action="store_true", help="regenerate and compare all published bytes")
    args = cli.parse_args()
    files = [OUT / "legend.json", *(OUT / "legend").rglob("*.json")]
    previous = {path.relative_to(OUT): path.read_bytes() for path in files} if args.check else None
    generate(args.cache.resolve())
    if previous is not None:
        current = {path.relative_to(OUT): path.read_bytes() for path in
                   [OUT / "legend.json", *(OUT / "legend").rglob("*.json")]}
        assert current == previous, "published legend data differs from the generator"


if __name__ == "__main__":
    main()
