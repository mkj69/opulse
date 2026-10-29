"""Export completed cached generation runs for the visual tour growth widget.

Run from the repository root with PYTHONPATH=src. Failed or unfinished runs are
skipped. Each set writes a compact indexed graph and a matching definitions file;
the fourth node entry is its barycentrically ordered position within its layer.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path

from opulse.worlds.present import alias, operator_names

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/assets/data/scales_growth"
SEEDS = {"int10": 101, "int100": 102, "int1000": 103, "int10000b": 105,
         "str10": 206, "str100": 202, "str1000": 203, "str10000": 211}
LAYER_LINE = re.compile(r"layer (\d+) done: (\{.*\})")
FINISH = re.compile(r"exit=(\d+) seconds=(\d+(?:\.\d+)?)")


def read_log(path: Path) -> tuple[float, list[dict]] | None:
    lines = path.read_text(encoding="utf-8").splitlines()
    finish = FINISH.fullmatch(lines[-1]) if lines else None
    if finish is None or int(finish[1]) != 0:
        return None
    layers = []
    for line in lines:
        match = LAYER_LINE.search(line)
        if match:
            snapshot = ast.literal_eval(match[2])
            layers.append({"layer": int(match[1]), "accepted": snapshot["accepted"],
                           "rejected": snapshot["rejected"]})
    return float(finish[2]), layers


def export(name: str, cache: Path) -> Path | None:
    log = cache / f"{name}.log"
    source = cache / f"{name}.jsonl"
    if not log.exists() or not source.exists() or (record := read_log(log)) is None:
        print(f"skip {name}: no successful completed run")
        return None
    seconds, snapshots = record
    rows = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line.strip()]
    defined = [row for row in rows if row["definition"] is not None]
    if not defined or not snapshots:
        raise ValueError(f"{name}: missing definitions or layer log")
    if sum(snapshots[-1]["accepted"].values()) != len(defined):
        raise ValueError(f"{name}: log and operator set differ")
    names = operator_names([_Row(row["symbol"]) for row in defined],
                           reserved=(row["symbol"] for row in rows if row["definition"] is None))
    atoms = [row for row in rows if row["definition"] is None]
    ordered = atoms + sorted(defined, key=lambda row: (row["recursive_layer"], row["id"]))
    by_id = {row["func_id"]: i for i, row in enumerate(ordered)}
    layer_of = {row["func_id"]: (-1 if row["definition"] is None else row["recursive_layer"])
                for row in ordered}
    edges = []
    deps = {}
    for row in defined:
        source_id = row["func_id"]
        ids = sorted(set(row["dependencies"]) & by_id.keys(), key=lambda x: by_id[x])
        if row["definition_type"] == "recursive_definition" and source_id not in ids:
            ids.append(source_id)
        deps[source_id] = ids
        edges.extend((source_id, target) for target in ids)
    layers = sorted({row["recursive_layer"] for row in defined})
    kinds = {layer: Counter(row["definition_type"].split("_")[0] for row in defined
                            if row["recursive_layer"] == layer) for layer in layers}
    closure_bits = {}
    chain = {}
    layer_span = {}
    closure_hist = defaultdict(Counter)
    chain_hist = defaultdict(Counter)
    span_hist = defaultdict(Counter)
    largest = (None, -1)
    deepest = (None, -1)
    for row in ordered:
        if row["definition"] is None:
            closure_bits[row["func_id"]] = 0
            chain[row["func_id"]] = 0
            layer_span[row["func_id"]] = 0
            continue
        key = row["func_id"]
        below = [target for target in deps[key] if target != key]
        bits = 0
        for target in below:
            bits |= closure_bits[target] | (1 << by_id[target])
        closure_bits[key] = bits
        chain[key] = 1 + max((chain[target] for target in below), default=0)
        layer_span[key] = max((layer_span[target] + int(layer_of[target] != row["recursive_layer"])
                               for target in below if layer_of[target] >= 0), default=1)
        closure_size = bits.bit_count()
        layer = row["recursive_layer"]
        closure_hist[layer][closure_size] += 1
        chain_hist[layer][chain[key]] += 1
        span_hist[layer][layer_span[key]] += 1
        if closure_size > largest[1]:
            largest = (row, closure_size)
        if chain[key] > deepest[1]:
            deepest = (row, chain[key])
    labels = [-1, *layers]
    layer_index = {layer: i for i, layer in enumerate(labels)}
    ranges = []
    for layer in labels:
        indices = [i for i, row in enumerate(ordered)
                   if (-1 if row["definition"] is None else row["recursive_layer"]) == layer]
        ranges.append([min(indices), max(indices) + 1])
    layer_matrix = [[0] * len(labels) for _ in labels]
    bins = min(128, len(ordered))
    fine = [[0] * bins for _ in range(bins)]
    for src, target in edges:
        layer_matrix[layer_index[layer_of[src]]][layer_index[layer_of[target]]] += 1
        fine[by_id[src] * bins // len(ordered)][by_id[target] * bins // len(ordered)] += 1
    funnel = []
    previous_a = 0
    previous_r = Counter()
    for snapshot in snapshots:
        accepted = sum(snapshot["accepted"].values())
        rejected = Counter(snapshot["rejected"])
        rejected_total = sum(rejected.values())
        funnel.append({"layer": snapshot["layer"], "accepted": accepted - previous_a,
                       "rejected": rejected_total - sum(previous_r.values()),
                       "reasons": {reason: count - previous_r[reason] for reason, count in sorted(rejected.items())
                                   if count - previous_r[reason]},
                       "cumulative": {"accepted": accepted, "rejected": rejected_total,
                                      "reasons": dict(sorted(rejected.items()))}})
        previous_a, previous_r = accepted, rejected
    def example(pair):
        row, value = pair
        return {"symbol": names[row["symbol"]], "layer": row["recursive_layer"],
                "closure": closure_bits[row["func_id"]].bit_count(), "chain": chain[row["func_id"]],
                "layer_span": layer_span[row["func_id"]],
                "value": value}
    payload = {"set": name, "seed": SEEDS[name], "seconds": seconds, "size": len(defined),
               "layers": [{"layer": layer, "count": sum(kinds[layer].values()),
                           "kinds": {kind: kinds[layer][kind] for kind in ("simple", "branch", "recursive")},
                           "closure": sorted(closure_hist[layer].items()),
                           "chain": sorted(chain_hist[layer].items()),
                           "layer_span": sorted(span_hist[layer].items())} for layer in layers],
               "funnel": funnel, "rejected": dict(sorted(previous_r.items())),
               "proposed": len(defined) + sum(previous_r.values()), "edge_count": len(edges),
               "density": {"layers": labels, "layer_ranges": ranges, "layer_matrix": layer_matrix,
                           "bins": bins, "fine": fine,
                           "order": "atoms, then defined operators by layer and source index"},
               "largest_closure": example(largest), "deepest_chain": example(deepest)}
    # Alternate barycentric sweeps. Ties keep source order, so the export is stable.
    adjacent = [[] for _ in ordered]
    reverse = [[] for _ in ordered]
    for src, target in edges:
        a, b = by_id[src], by_id[target]
        if a != b:
            adjacent[a].append(b)
            reverse[b].append(a)
    groups = [[i for i, row in enumerate(ordered) if layer_of[row["func_id"]] == layer]
              for layer in labels]
    ranks = list(range(len(ordered)))
    for _ in range(4):
        for group in groups[1:]:
            group.sort(key=lambda i: (sum(ranks[j] for j in adjacent[i]) / len(adjacent[i])
                                      if adjacent[i] else ranks[i], ranks[i]))
            for rank, i in enumerate(group):
                ranks[i] = rank
        for group in reversed(groups[:-1]):
            group.sort(key=lambda i: (sum(ranks[j] for j in reverse[i]) / len(reverse[i])
                                      if reverse[i] else ranks[i], ranks[i]))
            for rank, i in enumerate(group):
                ranks[i] = rank
    graph_nodes = [[names.get(row["symbol"], row["symbol"]), layer_of[row["func_id"]],
                    {"atom": 0, "simple": 1, "branch": 2, "recursive": 3}[
                        "atom" if row["definition"] is None else row["definition_type"].split("_")[0]],
                    ranks[i]] for i, row in enumerate(ordered)]
    graph_edges = [value for src, target in edges for value in (by_id[src], by_id[target])]
    payload["graph"] = {"nodes": graph_nodes, "edges": graph_edges,
                        "definitions": f"{name}.definitions.json"}
    OUT.mkdir(parents=True, exist_ok=True)
    dest = OUT / f"{name}.json"
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(text.encode()) >= 3_000_000:
        raise ValueError(f"{name}: graph output exceeds 3 MB")
    definitions = [alias(row["definition"], names) if row["definition"] else None
                   for row in ordered]
    detail_text = json.dumps(definitions, ensure_ascii=False, separators=(",", ":"))
    if len(detail_text.encode()) >= 3_000_000:
        raise ValueError(f"{name}: definitions output exceeds 3 MB")
    dest.write_text(text, encoding="utf-8")
    (OUT / f"{name}.definitions.json").write_text(detail_text, encoding="utf-8")
    print(f"wrote {dest.relative_to(ROOT)}: {len(text.encode())} bytes")
    return dest


class _Row:
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path,
                        default=Path(os.environ.get("OPULSE_SCALES_CACHE", "/tmp/opulse_scales")))
    parser.add_argument("--only", nargs="+", choices=SEEDS)
    args = parser.parse_args()
    for name in args.only or SEEDS:
        export(name, args.cache)


if __name__ == "__main__":
    main()
