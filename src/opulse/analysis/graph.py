"""Expose registry dependencies for inspection without changing evaluation order.

Edges point from a caller to the operator it uses. Recursive self-calls are
shown explicitly, while layer ordering ignores those intentional self-loops.
"""

from __future__ import annotations

import json
from collections import defaultdict

from opulse.core.operator import RECURSIVE
from opulse.core.registry import OperatorRegistry


def dependency_graph(registry: OperatorRegistry) -> dict:
    """Return JSON-compatible nodes and edges, rejecting missing IDs and cycles."""
    nodes = []
    edges = []
    for op in registry:
        nodes.append({
            "func_id": op.func_id, "symbol": op.symbol, "n_ary": op.n_ary,
            "unary_position": op.unary_position, "definition_type": op.definition_type,
            "recursive_layer": op.recursive_layer or 0, "definition": op.definition,
            "base": op.is_primitive, "max_path_depth": op.max_path_depth,
            "max_edge_count": op.max_edge_count,
            **{key: value for key, value in op.to_dict().items()
               if key.startswith(("nl_description", "propert", "complexity")) and value is not None},
        })
        for dep in op.dependencies:
            if dep not in registry:
                raise ValueError(f"unknown dependency {dep!r} of {op.func_id!r}")
            if dep == op.func_id:
                if op.definition_type != RECURSIVE:
                    raise ValueError(f"non-recursive self-dependency: {op.func_id}")
                continue
            edges.append({"source": op.func_id, "target": dep})
        if op.definition_type == RECURSIVE:
            edges.append({"source": op.func_id, "target": op.func_id})
    graph = {"nodes": nodes, "edges": edges}
    topological_layers(graph)
    outgoing: dict[str, set[str]] = defaultdict(set)
    incoming: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        outgoing[edge["source"]].add(edge["target"])
        incoming[edge["target"]].add(edge["source"])
    for node in nodes:
        key = node["func_id"]
        seen: set[str] = set()
        stack = list(outgoing[key] - {key})
        while stack:
            dep = stack.pop()
            if dep not in seen:
                seen.add(dep)
                stack.extend(outgoing[dep] - {dep} - seen)
        node.update(in_degree=len(incoming[key]), out_degree=len(outgoing[key]),
                    transitive_dependencies=len(seen))
    return graph


def topological_layers(graph: dict) -> list[list[str]]:
    """Group IDs by dependency depth, with callees in earlier groups."""
    ids = {node["func_id"] for node in graph["nodes"]}
    dependencies = {key: set() for key in ids}
    for edge in graph["edges"]:
        source, target = edge["source"], edge["target"]
        if source not in ids or target not in ids:
            raise ValueError(f"edge references unknown node: {source} -> {target}")
        if source != target:
            dependencies[source].add(target)
    layers: list[list[str]] = []
    remaining = set(ids)
    while remaining:
        ready = sorted(key for key in remaining if not dependencies[key] & remaining)
        if not ready:
            raise ValueError("dependency graph has a cycle apart from self-loops")
        layers.append(ready)
        remaining.difference_update(ready)
    return layers


def to_dot(graph: dict) -> str:
    """Render clustered Graphviz DOT with safely quoted labels and IDs."""
    topological_layers(graph)
    by_layer: dict[int, list[dict]] = defaultdict(list)
    for node in graph["nodes"]:
        by_layer[node["recursive_layer"]].append(node)
    lines = ["digraph dependencies {", "  rankdir=LR;", "  graph [fontname=\"sans-serif\"];",
             "  node [fontname=\"sans-serif\"]; "]
    for layer, nodes in sorted(by_layer.items()):
        lines.extend([f"  subgraph cluster_{layer} {{", f"    label={json.dumps(f'Layer {layer}')};"])
        for node in sorted(nodes, key=lambda item: item["func_id"]):
            lines.append(f'    {json.dumps(node["func_id"])} '
                         f'[label={json.dumps(node["symbol"], ensure_ascii=False)}, '
                         f'tooltip={json.dumps(node["func_id"])}];')
        lines.append("  }")
    for edge in graph["edges"]:
        lines.append(f'  {json.dumps(edge["source"])} -> {json.dumps(edge["target"])};')
    return "\n".join([*lines, "}", ""])
