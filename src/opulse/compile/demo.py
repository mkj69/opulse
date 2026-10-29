"""The stitching experiment: compile operators separately, join their weights, compare.

``run(n)`` builds a small operator set, compiles every operator, and checks:

* (a) the network of ``▲₂`` stitched after the network of ``◆₁`` computes ``▲₂(◆₁(a), b)``;
* (b) for operators whose definitions call ``◆₁`` and ``▲₂``, the network compiled from the whole
  definition and the network stitched from the separately compiled parts agree with the
  interpreter and with each other, and how their sizes compare.

Run it with ``python -m opulse.compile`` (torch required).
"""

from __future__ import annotations

import itertools
from collections import Counter
from typing import TYPE_CHECKING

from opulse.bench.check import base_registry, prompt_registry
from opulse.compile.compiler import Compiler
from opulse.compile.values import Vocab

if TYPE_CHECKING:
    from opulse.compile.network import CompiledNetwork

DEFINITIONS = [
    "a ◆₁ = { (a % 5) * 3 }",
    "a ▲₂ b = { a - b, if a > b; b - a, else }",
    "a ★₃ b = { (a ◆₁) ▲₂ b }",
    "a ⬢₄ b = { (a ◆₁) ▲₂ (b ◆₁) }",
    "a ⬟₅ b = { ((a ◆₁) ▲₂ b) ◆₁ }",
    "a ⬡₆ = { (a ◆₁) ▲₂ 7 }",
    "a ♣₇ = { 1, if a % 6 == 0; (((a % 6) - 1) ♣₇) + 2, if a % 6 > 0; (((a % 6) + 1) ♣₇) - 1, if a % 6 < 0 }",
]


def operator_set(definitions=DEFINITIONS):
    """Base operations plus ``definitions``, with an oracle (the reference interpreter)."""
    from opulse.core.starting_sets import starting_registry

    base = base_registry(starting_registry())
    return prompt_registry(list(definitions), base)


def default_vocab(n: int) -> Vocab:
    return Vocab(-n, 2 * n - 1)


def summary(network: CompiledNetwork) -> dict:
    keep = ("layers", "d_model", "max_hidden", "total_hidden", "blocks", "nonzero_params", "params")
    return {key: network.stats()[key] for key in keep}


def _signatures(network: CompiledNetwork) -> Counter:
    return Counter(block.signature for block in network.blocks)


def run(n: int = 16, vocab: Vocab | None = None) -> dict:
    from opulse.compile.network import build_network, compact, stitch
    from opulse.compile.verify import verify

    vocab = vocab or default_vocab(n)
    ops = operator_set()
    oracle = ops.oracle
    by_symbol = {op.symbol: op for op in ops.registry if op.definition is not None}
    compiler = Compiler(oracle, vocab)
    networks = {symbol: build_network(compiler.compile(op)) for symbol, op in by_symbol.items()}
    domain = range(n)

    def value(symbol, *args):
        return oracle.evaluate(by_symbol[symbol], args).value

    results: dict = {"n": n, "vocab": [vocab.lo, vocab.hi], "operators": {}}
    for symbol, network in networks.items():
        op = by_symbol[symbol]
        rows = list(itertools.product(domain, repeat=op.n_ary))
        report = verify(network, oracle, rows, lambda row, op=op: oracle.evaluate(op, row).value)
        results["operators"][symbol] = {"definition": op.definition, **summary(network), "verify": report.to_dict()}

    f, g = networks["◆₁"], networks["▲₂"]
    out_f = lambda prefix: f"{prefix}.{f.output}"

    # The stitched form of each composite, and the rows and reference it is checked on.
    stitched = {
        "★₃": (stitch([("f", f), ("g", g)], {"g.in0_a": out_f("f")}, f"g.{g.output}", "★₃ stitched"),
               lambda a, b: value("▲₂", value("◆₁", a), b), lambda a, b: (a, b)),
        "⬢₄": (stitch([("f1", f), ("f2", f), ("g", g)], {"g.in0_a": out_f("f1"), "g.in1_b": out_f("f2")},
                      f"g.{g.output}", "⬢₄ stitched"),
               lambda a, b: value("▲₂", value("◆₁", a), value("◆₁", b)), lambda a, b: (a, b)),
        "⬟₅": (stitch([("f1", f), ("g", g), ("f2", f)], {"g.in0_a": out_f("f1"), "f2.in0_a": f"g.{g.output}"},
                      out_f("f2"), "⬟₅ stitched"),
               lambda a, b: value("◆₁", value("▲₂", value("◆₁", a), b)), lambda a, b: (a, b)),
        # ▲₂'s second input becomes an input of the stitched network, fed the constant 7.
        "⬡₆": (stitch([("f", f), ("g", g)], {"g.in0_a": out_f("f")}, f"g.{g.output}", "⬡₆ stitched"),
               lambda a: value("▲₂", value("◆₁", a), 7), lambda a: (a, 7)),
    }
    results["stitching"] = {}
    for symbol, (net, reference, row_of) in stitched.items():
        op = by_symbol[symbol]
        whole = networks[symbol]
        args = list(itertools.product(domain, repeat=op.n_ary))
        rows = [row_of(*a) for a in args]
        packed = compact(net)
        entry = {"definition": op.definition, "inputs": net.inputs}
        outputs = {}
        for label, network, network_rows in (("whole", whole, args), ("stitched", net, rows),
                                             ("stitched_compact", packed, rows)):
            lookup = dict(zip(network_rows, args))  # network input row -> operator arguments
            report = verify(network, oracle, network_rows,
                            lambda row, lookup=lookup, op=op: oracle.evaluate(op, lookup[row]).value)
            outputs[label] = network.run(network_rows)
            entry[label] = {**summary(network), "verify": report.to_dict()}
        entry["stitched_matches_part_reference"] = all(
            got == reference(*a) for got, a in zip(outputs["stitched"], args))
        entry["whole_equals_stitched"] = outputs["whole"] == outputs["stitched"] == outputs["stitched_compact"]
        entry["same_blocks"] = _signatures(whole) == _signatures(net)
        results["stitching"][symbol] = entry
    return results


def format_results(results: dict) -> str:
    lines = [(f"domain 0..{results['n'] - 1}, slot vocabulary {results['vocab'][0]}..{results['vocab'][1]}"
             " plus NaN and OOV"), "", "operator  layers  d_model  max_hidden  nonzero  exact outputs  slot checks"]
    for symbol, row in results["operators"].items():
        v = row["verify"]
        lines.append(f"{symbol:8s}  {row['layers']:6d}  {row['d_model']:7d}  {row['max_hidden']:10d}  "
                     f"{row['nonzero_params']:7d}  {v['output_exact']:>5d}/{v['rows']:<7d}  "
                     f"{v['slot_exact']}/{v['slot_checks']} wrong {v['slot_wrong']}")
    lines += ["", "composite  form              layers  d_model  max_hidden  nonzero  verified  equal  same blocks"]
    for symbol, entry in results["stitching"].items():
        for label in ("whole", "stitched", "stitched_compact"):
            row = entry[label]
            lines.append(f"{symbol:9s}  {label:16s}  {row['layers']:6d}  {row['d_model']:7d}  {row['max_hidden']:10d}"
                         f"  {row['nonzero_params']:7d}  {row['verify']['exact']!s:8s}  "
                         f"{entry['whole_equals_stitched']!s:5s}  {entry['same_blocks']}")
    return "\n".join(lines)


def run_trained(n: int = 16, vocab: Vocab | None = None, sigmas=(0.0, 0.05, 0.1, 0.2, 0.3, 0.4),
                seeds: int = 5, hidden=(64, 512)) -> dict:
    """Part (c): trained stand-ins for ``◆₁`` and ``▲₂``, stitched, then with weight noise."""
    import torch

    from opulse.compile.network import build_network, stitch
    from opulse.compile.trained import one_hot_error, perturb, train_operator

    vocab = vocab or default_vocab(n)
    ops = operator_set()
    oracle = ops.oracle
    by_symbol = {op.symbol: op for op in ops.registry if op.definition is not None}
    compiler = Compiler(oracle, vocab)
    compiled = {s: build_network(compiler.compile(by_symbol[s])) for s in ("◆₁", "▲₂")}
    trained = {"◆₁": train_operator(compiled["◆₁"], hidden[0]), "▲₂": train_operator(compiled["▲₂"], hidden[1])}
    rows1 = [(a,) for a in range(n)]
    rows2 = list(itertools.product(range(n), repeat=2))
    star = by_symbol["★₃"]

    def joined(f, g, snap=False):
        return stitch([("f", f), ("g", g)], {"g.in0_a": f"f.{f.output}"}, f"g.{g.output}", snap=snap)

    def accuracy(network, rows, op):
        expected = [vocab.index(oracle.evaluate(op, row).value) for row in rows]
        with torch.no_grad():
            got = network.tokens(network(network.embed(rows)), network.output).tolist()
        return sum(a == b for a, b in zip(got, expected)) / len(rows)

    def mean(values):
        return sum(values) / len(values)

    results: dict = {"n": n, "hidden": list(hidden), "modules": {}, "stitched": {}, "noise": []}
    for symbol, rows in (("◆₁", rows1), ("▲₂", rows2)):
        net = trained[symbol]
        results["modules"][symbol] = {**summary(net), "domain_accuracy": accuracy(net, rows, by_symbol[symbol]),
                                      "one_hot_error": one_hot_error(net, rows)}
    for label, f, g, snap in (("trained+trained", trained["◆₁"], trained["▲₂"], False),
                              ("trained+compiled", trained["◆₁"], compiled["▲₂"], False),
                              ("compiled+trained", compiled["◆₁"], trained["▲₂"], False),
                              ("trained+trained, snap", trained["◆₁"], trained["▲₂"], True)):
        net = joined(f, g, snap)
        results["stitched"][label] = {"accuracy": accuracy(net, rows2, star),
                                      "one_hot_error": one_hot_error(net, rows2)}
    for kind, parts in (("compiled", compiled), ("trained", trained)):
        for sigma in sigmas:
            acc_f, acc_g, acc_s, acc_snap = [], [], [], []
            for seed in range(seeds):
                f = perturb(parts["◆₁"], sigma, 2 * seed)
                g = perturb(parts["▲₂"], sigma, 2 * seed + 1)
                acc_f.append(accuracy(f, rows1, by_symbol["◆₁"]))
                acc_g.append(accuracy(g, rows2, by_symbol["▲₂"]))
                acc_s.append(accuracy(joined(f, g), rows2, star))
                acc_snap.append(accuracy(joined(f, g, snap=True), rows2, star))
            results["noise"].append({"modules": kind, "sigma": sigma, "diamond": mean(acc_f),
                                     "triangle": mean(acc_g), "stitched": mean(acc_s),
                                     "stitched_snap": mean(acc_snap),
                                     "product_of_parts": mean([a * b for a, b in zip(acc_f, acc_g)])})
    return results


def format_trained(results: dict) -> str:
    lines = [f"trained modules (hidden {results['hidden'][0]} and {results['hidden'][1]} units)"]
    for symbol, row in results["modules"].items():
        lines.append(f"  {symbol}: domain accuracy {row['domain_accuracy']:.3f}, "
                     f"largest one-hot error {row['one_hot_error']:.4f}")
    for label, row in results["stitched"].items():
        lines.append(f"  stitched {label}: accuracy {row['accuracy']:.3f}, "
                     f"largest one-hot error {row['one_hot_error']:.4f}")
    lines += ["", "weight noise  modules   sigma  ◆₁     ▲₂     product  stitched  stitched+snap"]
    for row in results["noise"]:
        lines.append(f"              {row['modules']:8s}  {row['sigma']:.2f}   {row['diamond']:.3f}  "
                     f"{row['triangle']:.3f}  {row['product_of_parts']:.3f}    {row['stitched']:.3f}     "
                     f"{row['stitched_snap']:.3f}")
    return "\n".join(lines)
