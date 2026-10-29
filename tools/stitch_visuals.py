"""Regenerate the data of the stitching essay (docs/stitching/index.md) by running the experiment.

    PYTHONPATH=src python tools/stitch_visuals.py              # everything (about 15 minutes on CPU)
    PYTHONPATH=src python tools/stitch_visuals.py --only noise # one part

Writes docs/assets/data/stitch/*.json, which docs/assets/js/stitch.js draws:

* ``operator.json``: the compiled network of ``a ◆₁ = (a % 5) * 3``, unit by unit, read from its
  weight matrices, and the token each slot holds for every input token;
* ``flow.json``: the stitched ``◆₁ → ▲₂`` network, every slot after every layer for all 256
  inputs, each compared with the reference interpreter;
* ``whole_vs_stitched.json``: block diagrams of whole and stitched compilations of four
  composites, with sizes and the comparison of outputs and weight blocks;
* ``noise.json``: accuracy under Gaussian weight noise for compiled and trained parts, alone,
  multiplied, stitched, and stitched with a snap layer (fixed seeds, many trials);
* ``generated.json``: every operator of a generated set, compiled and verified;
* ``summary.json``: the remaining numbers quoted in the text.

Torch is required. The script runs on the CPU and is deterministic.
"""

from __future__ import annotations

import argparse
import copy
import io
import itertools
import json
import math
import sys
import time
from collections import Counter
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import torch

from opulse.compile.compiler import COND, Compiler, Const
from opulse.compile.demo import default_vocab, operator_set
from opulse.compile.network import build_network, compact, stitch
from opulse.compile.trained import one_hot_error, perturb, train_operator
from opulse.compile.values import COND_LABELS, OOV
from opulse.compile.verify import _env_of, reference_value, verify
from opulse.core import OperatorRegistry
from opulse.core.semantics import NAN
from opulse.verify import Oracle

OUT = ROOT / "docs" / "assets" / "data" / "stitch"
WORK = ROOT / "outputs" / "stitch"
N = 16  # inputs range over 0 .. N-1
SIGMAS = (0.0, 0.025, 0.05, 0.075, 0.1, 0.125, 0.15, 0.2, 0.25, 0.3)
TRIALS = 50
GENERATED = {"layers": (20, 10, 6), "seed": 3, "n": 8, "lo": -16, "hi": 15}

torch.set_num_threads(max(1, min(16, torch.get_num_threads())))


def write(name: str, data) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)} ({path.stat().st_size // 1024} KB)")


def label(value) -> str:
    return "NaN" if value is NAN else "OOV" if value is OOV else str(value)


class Setup:
    def __init__(self) -> None:
        self.vocab = default_vocab(N)
        self.ops = operator_set()
        self.oracle = self.ops.oracle
        self.by = {op.symbol: op for op in self.ops.registry if op.definition is not None}
        self.compiler = Compiler(self.oracle, self.vocab)
        self.nets = {s: build_network(self.compiler.compile(op)) for s, op in self.by.items()}

    def value(self, symbol, *args):
        return self.oracle.evaluate(self.by[symbol], args).value

    def star(self, f=None, g=None, snap=False):
        f, g = f or self.nets["◆₁"], g or self.nets["▲₂"]
        return stitch([("f", f), ("g", g)], {"g.in0_a": f"f.{f.output}"}, f"g.{g.output}", "★₃ stitched", snap=snap)


# ----------------------------------------------------------------- (a) one operator as weights

def operator_data(s: Setup) -> dict:
    net = s.nets["◆₁"]
    vocab = s.vocab
    tokens = [vocab.label(i) for i in range(vocab.size)]
    order = [net.inputs[0], "s1", net.output]
    assert net.slots["s1"].text == "%(in0_a, 5)" and net.slots[net.output].text == "*(s1, 3)"
    blocks = []
    for layer_index, layer in enumerate(net.layers):
        (block,) = [b for b in net.blocks if b.layer == layer_index]
        read = net.slots[net.slots[block.write].reads[0]]
        write_slot = net.slots[block.write]
        up, bias, down = layer.up.weight.detach(), layer.up.bias.detach(), layer.down.weight.detach()
        units = []
        for u in range(*block.hidden):
            cols = torch.nonzero(up[u]).flatten().tolist()
            rows = torch.nonzero(down[:, u]).flatten().tolist()
            assert len(cols) == 1 and len(rows) == 1
            units.append({"in": cols[0] - read.start, "out": rows[0] - write_slot.start,
                          "w": float(up[u, cols[0]]), "b": float(bias[u]), "w_out": float(down[rows[0], u])})
        blocks.append({"op": block.label, "reads": read.name, "writes": write_slot.name, "units": units,
                       "params": int(up.numel() + bias.numel() + down.numel()),
                       "nonzero": int((up != 0).sum() + (bias != 0).sum() + (down != 0).sum())})
    values = vocab.values()
    with torch.no_grad():
        x = net.embed([(v,) for v in values])
        states = [x]
        for layer in net.layers:
            x = layer(x)
            states.append(x)
    rows = []
    for i, v in enumerate(values):
        held = [int(net.tokens(states[-1], name)[i]) for name in order]
        fired = []
        for layer_index, layer in enumerate(net.layers):
            with torch.no_grad():
                pre = layer.up(states[layer_index][i:i + 1])[0]
            fired.append({"unit": int(pre.argmax()), "pre_max": float(pre.max()),
                          "pre_second": float(pre.topk(2).values[1])})
        if v is OOV:
            ref = ["OOV", "OOV", "OOV"]
        else:
            mod = s.oracle.evaluate_expr(_mod_node(s), {"a": v}).value
            ref = [label(v), label(vocab.clamp(mod)), label(vocab.clamp(s.value("◆₁", v)))]
        rows.append({"input": i, "tokens": held, "labels": [tokens[t] for t in held], "ref": ref,
                     "fired": fired, "in_domain": isinstance(v, int) and 0 <= v < N})
    return {"definition": "a ◆₁ = { (a % 5) * 3 }", "tokens": tokens, "domain": [0, N - 1],
            "slots": [{"name": n, "text": t} for n, t in zip(order, ("a", "a % 5", "(a % 5) * 3"))],
            "blocks": blocks, "rows": rows}


def _mod_node(s: Setup):
    """The ``a % 5`` subexpression of ◆₁, as an AST node."""
    definition = s.oracle._definition_of(s.by["◆₁"])
    expr = definition.branches[0].expr  # (a % 5) * 3
    return expr.args[0]


# --------------------------------------------------------------- (b) slots of the stitched network

FLOW_LABELS = {
    "f.in0_a": ("a", "input"),
    "f.s1": ("a % 5", "◆₁"),
    "f.s2": ("x = a ◆₁", "◆₁"),
    "g.in1_b": ("b", "input"),
    "g.s2": ("x > b", "▲₂"),
    "g.s3": ("x - b", "▲₂"),
    "g.s4": ("b - x", "▲₂"),
    "g.s5": ("x ▲₂ b", "▲₂"),
}


def slot_trace(network, oracle, rows):
    """Per row and slot: the token after every layer, the reference value and the check status.

    The bookkeeping is the one of :func:`opulse.compile.verify.verify`; a slot whose branch the
    row does not reach is reported as ``dont_care``.
    """
    vocab = network.vocab
    with torch.no_grad():
        x = network.embed(rows)
        states = [x]
        for layer in network.layers:
            x = layer(x)
            states.append(x)
    final = states[-1]
    tokens = {name: network.tokens(final, name).tolist() for name in network.slots}

    def held(name, r):
        index = tokens[name][r]
        return index if network.slots[name].kind == COND else vocab.value(index)

    out = []
    for r, row in enumerate(rows):
        ref = dict(zip(network.inputs, row))
        checked = set(network.inputs)
        entry = {}
        for name, info in network.slots.items():
            if info.origin[0] == "input":
                entry[name] = {"ref": label(ref[name]), "status": "input"}
                continue
            env = {p: (b.value if isinstance(b, Const) else ref.get(b, OOV)) for p, b in _env_of(info.origin).items()}
            ref[name] = OOV if any(v is OOV for v in env.values()) else reference_value(oracle, info.origin, env)
            reached = not info.regions or any(
                all(isinstance(b, Const) or b in checked for b in refs)
                and tuple((True, b.value) if isinstance(b, Const) else (False, held(b, r)) for b in refs) in tuples
                for refs, tuples in info.regions)
            want = ref[name] if info.kind == COND else (vocab.index(ref[name]) if ref[name] is not OOV else None)
            if not reached:
                status = "dont_care"
            elif want is not None and tokens[name][r] == want:
                status = "exact"
                checked.add(name)
            else:
                status = "wrong"
            text = COND_LABELS[ref[name]] if info.kind == COND else label(ref[name])
            entry[name] = {"ref": text, "status": status}
        out.append(entry)
    return states, out


def flow_data(s: Setup) -> dict:
    net = s.star()
    rows = list(itertools.product(range(N), repeat=2))
    feed = [(a, b) for a, b in rows]
    states, trace = slot_trace(net, s.oracle, feed)
    written_by = {b.write: b.layer + 1 for b in net.blocks}
    slots = []
    for name, info in net.slots.items():
        text, part = FLOW_LABELS[name]
        slots.append({"name": name, "text": text, "part": part, "kind": info.kind, "start": info.start,
                      "size": info.size, "layer": written_by.get(name, 0), "reads": list(info.reads)})
    layers = []
    for k, layer in enumerate(net.layers):
        blocks = [b for b in net.blocks if b.layer == k]
        layers.append({"hidden": layer.up.out_features,
                       "blocks": [{"writes": b.write, "op": b.label, "hidden": b.hidden[1] - b.hidden[0]}
                                  for b in blocks]})
    data_rows = []
    counts = Counter()
    for r, (a, b) in enumerate(rows):
        per_slot = []
        for name, info in net.slots.items():
            # the token each slot holds after every layer (-1 while the slot is still empty)
            seq = []
            for st in states:
                block = st[r, info.start:info.stop]
                seq.append(int(block.argmax()) if float(block.abs().sum()) > 0 else -1)
            final = seq[-1]
            shown = COND_LABELS[final] if info.kind == COND else s.vocab.label(final)
            entry = trace[r][name]
            counts[entry["status"]] += 1
            exact_one_hot = bool(((block == 0) | (block == 1)).all() and float(block.sum()) == 1.0)
            per_slot.append([shown, entry["ref"], entry["status"], exact_one_hot])
        data_rows.append({"a": a, "b": b, "slots": per_slot})
    return {"inputs": net.inputs, "d_model": net.d_model, "slots": slots, "layers": layers, "rows": data_rows,
            "counts": dict(counts), "wired": {"g.in0_a": "f.s2"},
            "stats": net.stats()}


# ---------------------------------------------------------------- (c) whole versus stitched

def _cut_blocks(net) -> Counter:
    """Every block's weights as read from the network's layer matrices, independent of placement."""
    out = Counter()
    for b in net.blocks:
        layer = net.layers[b.layer]
        rows = torch.arange(*b.hidden)
        reads = net.slots[b.write].reads
        cols = torch.cat([torch.arange(net.slots[r].start, net.slots[r].stop) for r in reads]) if reads \
            else torch.zeros(0, dtype=torch.long)
        w = net.slots[b.write]
        with torch.no_grad():
            up = layer.up.weight[rows][:, cols]
            bias = layer.up.bias[rows]
            down = layer.down.weight[w.start:w.stop][:, rows]
            # nothing else in the layer may read or write through these units
            rest_up = layer.up.weight[rows].abs().sum() - up.abs().sum()
            rest_down = layer.down.weight[:, rows].abs().sum() - down.abs().sum()
        assert float(rest_up) == 0 and float(rest_down) == 0, b
        out[(b.kind, tuple(up.shape), up.numpy().tobytes(), bias.numpy().tobytes(), down.numpy().tobytes())] += 1
    return out


def _diagram(net) -> dict:
    layers = []
    for k, layer in enumerate(net.layers):
        blocks = []
        for b in sorted((b for b in net.blocks if b.layer == k), key=lambda b: b.hidden[0]):
            prefix = b.write.split(".")[0] if "." in b.write else ""
            text = net.slots[b.write].text
            blocks.append({"op": b.label, "kind": b.kind, "hidden": b.hidden[1] - b.hidden[0], "part": prefix,
                           "writes": b.write, "text": text})
        layers.append({"hidden": layer.up.out_features, "blocks": blocks})
    st = net.stats()
    return {"layers": layers, **{k: st[k] for k in ("d_model", "max_hidden", "total_hidden",
                                                    "nonzero_params", "params", "blocks")}}


def whole_vs_stitched_data(s: Setup) -> dict:
    f, g = s.nets["◆₁"], s.nets["▲₂"]
    of = lambda p: f"{p}.{f.output}"
    v = s.value
    cases = {
        "★₃": (stitch([("f", f), ("g", g)], {"g.in0_a": of("f")}, f"g.{g.output}"),
               lambda a, b: (a, b), lambda a, b: v("▲₂", v("◆₁", a), b), "(a ◆₁) ▲₂ b"),
        "⬢₄": (stitch([("f1", f), ("f2", f), ("g", g)], {"g.in0_a": of("f1"), "g.in1_b": of("f2")}, f"g.{g.output}"),
               lambda a, b: (a, b), lambda a, b: v("▲₂", v("◆₁", a), v("◆₁", b)), "(a ◆₁) ▲₂ (b ◆₁)"),
        "⬟₅": (stitch([("f1", f), ("g", g), ("f2", f)], {"g.in0_a": of("f1"), "f2.in0_a": f"g.{g.output}"}, of("f2")),
               lambda a, b: (a, b), lambda a, b: v("◆₁", v("▲₂", v("◆₁", a), b)), "((a ◆₁) ▲₂ b) ◆₁"),
        "⬡₆": (stitch([("f", f), ("g", g)], {"g.in0_a": of("f")}, f"g.{g.output}"),
               lambda a: (a, 7), lambda a: v("▲₂", v("◆₁", a), 7), "(a ◆₁) ▲₂ 7"),
    }
    out = {}
    for symbol, (stitched, row_of, reference, text) in cases.items():
        op = s.by[symbol]
        whole = s.nets[symbol]
        args = list(itertools.product(range(N), repeat=op.n_ary))
        feed = [row_of(*a) for a in args]
        packed = compact(stitched)
        entry = {"definition": text, "rows": len(args)}
        outputs = {}
        for name, net, rows in (("whole", whole, args), ("stitched", stitched, feed), ("compact", packed, feed)):
            lookup = dict(zip(rows, args))
            report = verify(net, s.oracle, rows, lambda row, lookup=lookup, op=op: s.oracle.evaluate(op, lookup[row]).value)
            outputs[name] = net.run(rows)
            entry[name] = {**_diagram(net), "exact": report.output_exact, "slot_checks": report.slot_checks,
                           "slot_wrong": report.slot_wrong, "one_hot": report.one_hot}
        entry["parts_reference"] = all(got == reference(*a) for got, a in zip(outputs["stitched"], args))
        entry["same_outputs"] = outputs["whole"] == outputs["stitched"] == outputs["compact"]
        sig = lambda net: Counter(b.signature for b in net.blocks)  # noqa: E731
        entry["same_blocks"] = sig(whole) == sig(stitched)
        # The same comparison on the assembled weight matrices: cut every block out of its layer
        # (its hidden units, the coordinates of the slots it reads and writes) and compare.
        entry["same_block_matrices"] = _cut_blocks(whole) == _cut_blocks(stitched)
        entry["same_block_matrices_compact"] = _cut_blocks(whole) == _cut_blocks(packed)
        entry["narrower"] = stitched.stats()["max_hidden"] / whole.stats()["max_hidden"]
        out[symbol] = entry
    return out


# ------------------------------------------------------------------- (d) noise and trained parts

def accuracy(network, rows, expected):
    with torch.no_grad():
        got = network.tokens(network(network.embed(rows)), network.output).tolist()
    return sum(a == b for a, b in zip(got, expected)) / len(rows)


def output_slot(network, rows):
    info = network.slots[network.output]
    with torch.no_grad():
        return network(network.embed(rows))[:, info.start:info.stop]


def mean_ci(values):
    n = len(values)
    m = sum(values) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in values) / (n - 1)) if n > 1 else 0.0
    half = 1.96 * sd / math.sqrt(n)
    return [round(m, 4), round(max(0.0, m - half), 4), round(min(1.0, m + half), 4)]


def noisy_snap(stitched, sigma, seed):
    """Noise on the snap layer only (the parts were perturbed before stitching)."""
    net = copy.deepcopy(stitched)
    snap_layers = {b.layer for b in net.blocks if b.kind == "snap"}
    generator = torch.Generator().manual_seed(seed)
    with torch.no_grad():
        for k in snap_layers:
            for p in net.layers[k].parameters():
                p.add_(sigma * torch.randn(p.shape, generator=generator) * (p != 0))
    return net


def noise_data(s: Setup) -> tuple[dict, dict]:
    vocab = s.vocab
    compiled = {"◆₁": s.nets["◆₁"], "▲₂": s.nets["▲₂"]}
    t0 = time.time()
    trained = {"◆₁": train_operator(compiled["◆₁"], 64, seed=0), "▲₂": train_operator(compiled["▲₂"], 512, seed=0)}
    train_seconds = time.time() - t0
    rows1 = [(a,) for a in range(N)]
    rows2 = list(itertools.product(range(N), repeat=2))
    rows_b = [(s.value("◆₁", a), b) for a, b in rows2]  # what ▲₂ receives inside the stitched network
    exp1 = [vocab.index(s.value("◆₁", a)) for (a,) in rows1]
    exp2 = [vocab.index(s.value("▲₂", a, b)) for a, b in rows2]
    exp_b = [vocab.index(s.value("▲₂", a, b)) for a, b in rows_b]
    exp_star = [vocab.index(s.value("★₃", a, b)) for a, b in rows2]

    summary = {"train_seconds": round(train_seconds, 1), "modules": {}, "stitched": {}}
    for symbol, rows, exp in (("◆₁", rows1, exp1), ("▲₂", rows2, exp2)):
        net = trained[symbol]
        summary["modules"][symbol] = {"hidden": net.layers[0].up.out_features,
                                      "accuracy": accuracy(net, rows, exp),
                                      "one_hot_error": one_hot_error(net, rows),
                                      "params": sum(p.numel() for p in net.parameters())}
    for name, f, g, snap in (("trained+trained", trained["◆₁"], trained["▲₂"], False),
                             ("trained+compiled", trained["◆₁"], compiled["▲₂"], False),
                             ("compiled+trained", compiled["◆₁"], trained["▲₂"], False),
                             ("trained+trained snap", trained["◆₁"], trained["▲₂"], True)):
        net = s.star(f, g, snap)
        summary["stitched"][name] = {"accuracy": accuracy(net, rows2, exp_star),
                                     "one_hot_error": one_hot_error(net, rows2)}
    summary["weight_rms"] = {
        kind: {sym: math.sqrt(float(sum((p.detach()[p != 0] ** 2).sum() for p in net.parameters()))
                              / float(sum(int((p != 0).sum()) for p in net.parameters())))
               for sym, net in parts.items()}
        for kind, parts in (("compiled", compiled), ("trained", trained))}

    series = {}
    probes = {}
    for kind, parts in (("compiled", compiled), ("trained", trained)):
        table = {key: [] for key in ("a", "b", "b_own", "product", "stitched", "snap", "snap_noisy",
                                     "noisy_a_clean_b", "clean_a_noisy_b")}
        for sigma in SIGMAS:
            acc = {key: [] for key in table}
            peaks = []
            for trial in range(TRIALS):
                f = perturb(parts["◆₁"], sigma, 2 * trial)
                g = perturb(parts["▲₂"], sigma, 2 * trial + 1)
                a = accuracy(f, rows1, exp1)
                b = accuracy(g, rows_b, exp_b)
                acc["a"].append(a)
                acc["b"].append(b)
                acc["b_own"].append(accuracy(g, rows2, exp2))
                acc["product"].append(a * b)
                acc["stitched"].append(accuracy(s.star(f, g), rows2, exp_star))
                snapped = s.star(f, g, snap=True)
                acc["snap"].append(accuracy(snapped, rows2, exp_star))
                acc["snap_noisy"].append(accuracy(noisy_snap(snapped, sigma, 10_000 + trial), rows2, exp_star))
                acc["noisy_a_clean_b"].append(accuracy(s.star(f, parts["▲₂"]), rows2, exp_star))
                acc["clean_a_noisy_b"].append(accuracy(s.star(parts["◆₁"], g), rows2, exp_star))
                if kind == "compiled" and sigma == 0.05:
                    peaks.append(output_slot(f, rows1).max(1).values)
            for key, column in table.items():
                column.append(mean_ci(acc[key]))
            if peaks:
                peak = torch.cat(peaks)
                probes["compiled_sigma_0.05_diamond_peak"] = {
                    "min": round(float(peak.min()), 3), "max": round(float(peak.max()), 3),
                    "share_outside_0.9_1.1": round(float(((peak < 0.9) | (peak > 1.1)).float().mean()), 3)}
            print(f"  {kind} sigma {sigma}: a {table['a'][-1][0]:.3f} b {table['b'][-1][0]:.3f} "
                  f"prod {table['product'][-1][0]:.3f} stitched {table['stitched'][-1][0]:.3f} "
                  f"snap {table['snap'][-1][0]:.3f}", flush=True)
        series[kind] = table
    summary["probes"] = probes
    return {"sigmas": list(SIGMAS), "trials": TRIALS, "series": series,
            "note": "mean and 95% interval (1.96 standard errors) over trials; trial t uses seeds 2t and 2t+1"}, summary


# ------------------------------------------------------------------ (e) generated operator set

def generated_data() -> dict:
    from opulse.cli.main import main as cli

    WORK.mkdir(parents=True, exist_ok=True)
    path = WORK / "ops.jsonl"
    layers = [str(x) for x in GENERATED["layers"]]
    with redirect_stdout(io.StringIO()):
        cli(["operators", "--out", str(path), "--layers", *layers, "--seed", str(GENERATED["seed"])])
    registry = OperatorRegistry.from_jsonl(path)
    oracle = Oracle(registry)
    from opulse.compile.values import Vocab

    vocab = Vocab(GENERATED["lo"], GENERATED["hi"])
    compiler = Compiler(oracle, vocab, max_blocks=5000)
    ops = []
    for op in registry:
        if op.definition is None:
            continue
        start = time.time()
        net = build_network(compiler.compile(op))
        rows = list(itertools.product(range(GENERATED["n"]), repeat=op.n_ary))
        report = verify(net, oracle, rows, lambda row, op=op: oracle.evaluate(op, row).value)
        st = net.stats()
        # rows whose exact answer lies outside lo .. hi: the network must answer OOV there
        ref_out = sum(vocab.clamp(oracle.evaluate(op, row).value) is OOV for row in rows)
        ops.append({"symbol": op.symbol, "ref_out_of_range": ref_out, "kind": op.definition_type.replace("_definition", ""),
                    "definition": op.definition, "arity": op.n_ary, "layers": st["layers"], "blocks": st["blocks"],
                    "nonzero": st["nonzero_params"], "max_hidden": st["max_hidden"], "rows": report.rows,
                    "exact": report.output_exact, "oov": report.output_oov, "wrong": report.output_wrong,
                    "slot_checks": report.slot_checks, "slot_wrong": report.slot_wrong,
                    "slot_dont_care": report.slot_dont_care, "seconds": round(time.time() - start, 1)})
        print(f"  {op.symbol} {ops[-1]['kind']} layers {st['layers']} exact {report.output_exact}/{report.rows}",
              flush=True)
    totals = {key: sum(o[key] for o in ops) for key in ("rows", "exact", "oov", "wrong", "slot_checks", "slot_wrong",
                                                        "slot_dont_care", "ref_out_of_range")}
    totals["operators"] = len(ops)
    totals["exact_everywhere"] = sum(o["oov"] == 0 and o["wrong"] == 0 for o in ops)
    totals["by_kind"] = {k: {"operators": sum(o["kind"] == k for o in ops),
                             "exact_everywhere": sum(o["kind"] == k and o["oov"] == 0 for o in ops)}
                         for k in ("simple", "branch", "recursive")}
    return {"settings": GENERATED, "operators": ops, "totals": totals}


# ---------------------------------------------------------------------------------- main

def nnsight_check(s: Setup) -> dict:
    try:
        import nnsight
        from nnsight import NNsight
    except ImportError as error:  # pragma: no cover
        return {"available": False, "error": str(error)}
    net = s.star()
    rows = [(5, 9)]
    model = NNsight(net)
    with model.trace(net.embed(rows)):
        first = model.layers[0].output.save()
    start, stop = net.slot_map["f.s1"]
    token = int(first[0, start:stop].argmax())
    return {"available": True, "version": nnsight.__version__, "row": rows[0],
            "slot": "f.s1", "after_layer_1": s.vocab.label(token)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", choices=["operator", "flow", "whole", "noise", "generated"], action="append")
    args = parser.parse_args(argv)
    parts = args.only or ["operator", "flow", "whole", "noise", "generated"]
    torch.manual_seed(0)
    s = Setup()
    summary_path = OUT / "summary.json"
    summary = json.loads(summary_path.read_text()) if summary_path.exists() else {}
    summary["vocab"] = [s.vocab.lo, s.vocab.hi, s.vocab.size]
    summary["torch"] = torch.__version__
    if "operator" in parts:
        write("operator.json", operator_data(s))
        summary["nnsight"] = nnsight_check(s)
    if "flow" in parts:
        write("flow.json", flow_data(s))
    if "whole" in parts:
        write("whole_vs_stitched.json", whole_vs_stitched_data(s))
        summary["single"] = {}
        for symbol, net in s.nets.items():
            op = s.by[symbol]
            rows = list(itertools.product(range(N), repeat=op.n_ary))
            report = verify(net, s.oracle, rows, lambda row, op=op: s.oracle.evaluate(op, row).value)
            summary["single"][symbol] = {"definition": op.definition, **net.stats(), "exact": report.output_exact,
                                         "rows": report.rows, "slot_checks": report.slot_checks,
                                         "slot_wrong": report.slot_wrong}
    if "noise" in parts:
        noise, trained = noise_data(s)
        write("noise.json", noise)
        summary["trained"] = trained
    if "generated" in parts:
        write("generated.json", generated_data())
    write("summary.json", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
