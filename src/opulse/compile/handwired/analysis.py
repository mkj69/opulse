"""Probe, patch and compare trained transformer states with compiled slots."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
from torch.nn import functional as F
from transformers import GPT2LMHeadModel

from opulse.compile.handwired.data import compiled_states, slot_activity
from opulse.compile.handwired.injection import ridge_map
from opulse.compile.handwired.train_small import encode, setup
from opulse.compile.values import COND_LABELS


def linear_cka(x, y):
    """Centered linear CKA across examples."""
    x, y = x.float() - x.float().mean(0), y.float() - y.float().mean(0)
    xy = (x.T @ y).square().sum()
    xx = (x.T @ x).square().sum().sqrt()
    yy = (y.T @ y).square().sum().sqrt()
    return float(xy / (xx * yy)) if bool(xx > 0 and yy > 0) else 0.0


def _states(model, ids, masks, positions):
    captured = []

    def save(_module, _args, output):
        state = output[0] if isinstance(output, tuple) else output
        captured.append(state.detach())

    handles = [model.transformer.drop.register_forward_hook(save)]
    handles.extend(block.register_forward_hook(save) for block in model.transformer.h)
    with torch.no_grad():
        try:
            model(input_ids=ids, attention_mask=masks)
        finally:
            for handle in handles:
                handle.remove()
    batch = torch.arange(len(ids))
    return [state[batch, positions] for state in captured]


def _probe(train_states, test_states, train_labels, test_labels, n_classes):
    target = F.one_hot(train_labels, n_classes).float()
    weight, bias = ridge_map(train_states, target)
    pred = test_states @ weight.T + bias
    return float((pred.argmax(-1) == test_labels).float().mean())


def _patch(model, ids, masks, positions, items, chars, oracle, operator, network,
           slot_labels, activity, states, train_idx, layer):
    """Transplant a decoded intermediate slot component and score its answer effect."""
    if len(items) < 2:
        return []
    records = []
    projections = {}
    for clean_idx, clean in enumerate(items):
        pair = next(((j, name) for j, item in enumerate(items)
                     if item.operands[1:] == clean.operands[1:] and item.operands[0] != clean.operands[0]
                     and len(item.prompt) == len(clean.prompt)
                     and oracle.evaluate(operator, item.operands).value != clean.answer
                     for name in network.slots
                     if name not in network.inputs and name != network.output
                     and activity[name][clean_idx] and activity[name][j]
                     and slot_labels[name][clean_idx] != slot_labels[name][j]), None)
        if pair is None:
            continue
        donor_idx, slot_name = pair
        donor = items[donor_idx]
        expected = oracle.evaluate(operator, donor.operands).value
        if str(clean.answer) not in chars or str(expected) not in chars or expected == clean.answer:
            continue
        if slot_name not in projections:
            fit_rows = train_idx[activity[slot_name][train_idx]]
            if len(fit_rows) < 2:
                continue
            labels = slot_labels[slot_name]
            target = F.one_hot(labels[fit_rows], network.slots[slot_name].size).float()
            weight, _ = ridge_map(states[layer + 1][fit_rows], target)
            gram = weight @ weight.T
            projections[slot_name] = weight.T @ torch.linalg.solve(
                gram + 1e-3 * torch.eye(len(gram)), weight)
        delta = (states[layer + 1][donor_idx] - states[layer + 1][clean_idx]) @ projections[slot_name]
        answer_position = int(positions[clean_idx])
        with torch.no_grad():
            clean_ids = ids[clean_idx:clean_idx + 1]
            clean_mask = masks[clean_idx:clean_idx + 1]
            baseline = model(input_ids=clean_ids, attention_mask=clean_mask).logits[0, positions[clean_idx]]

            def replace(_module, _args, output, answer_position=answer_position, delta=delta):
                state = output[0].clone() if isinstance(output, tuple) else output.clone()
                state[:, answer_position] += delta
                return (state, *output[1:]) if isinstance(output, tuple) else state

            handle = model.transformer.h[layer].register_forward_hook(replace)
            try:
                patched = model(input_ids=clean_ids, attention_mask=clean_mask).logits[0, positions[clean_idx]]
            finally:
                handle.remove()
        old, new = chars[str(clean.answer)], chars[str(expected)]
        def label(index, slot_name=slot_name):
            return (COND_LABELS[index] if network.slots[slot_name].kind == "cond"
                    else network.vocab.label(index))

        records.append({"clean": list(clean.operands), "counterfactual": list(donor.operands),
                        "slot": slot_name,
                        "clean_slot_value": label(int(slot_labels[slot_name][clean_idx])),
                        "counterfactual_slot_value": label(int(slot_labels[slot_name][donor_idx])),
                        "position": answer_position,
                        "expected_answer": int(expected), "clean_answer": clean.answer,
                        "baseline_margin": float(baseline[new] - baseline[old]),
                        "patched_margin": float(patched[new] - patched[old])})
    return records


def analyze(run_dir, out=None, *, symbol=None):
    torch.set_num_threads(1)
    run_dir = Path(run_dir)
    meta = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
    model = GPT2LMHeadModel.from_pretrained(run_dir / "model", local_files_only=True).eval()
    symbol = symbol or meta["symbol"]
    if symbol not in meta["symbols"]:
        raise ValueError(f"operator {symbol!r} was not in this training run")
    ops, operator, network, items = setup(meta["definitions"], symbol, meta["lo"], meta["hi"],
                                          meta["values"])
    chars = meta["chars"]
    ids, masks, _labels, positions = encode(items, chars)
    rows = [item.operands for item in items]
    compiled, slot_labels = compiled_states(network, rows)
    activity = slot_activity(network, slot_labels)
    # The model and probes use the same held out operand rows.
    split = meta["operators"][symbol]
    train_idx = torch.tensor(split["train_indices"], dtype=torch.long)
    test_idx = torch.tensor(split["test_indices"], dtype=torch.long)
    if not len(train_idx) or not len(test_idx):
        raise ValueError("at least two examples are needed for held out probes")
    sites = {"answer_position": positions}
    for position in range(min(len(item.prompt) for item in items)):
        sites[f"token_{position}"] = torch.full_like(positions, position)
    for operand in range(operator.n_ary):
        sites[f"operand_{operand}"] = torch.tensor([item.operand_spans[operand][0] for item in items])
    probes = {}
    all_states = {}
    for site, site_positions in sites.items():
        states = _states(model, ids, masks, site_positions)
        all_states[site] = states
        probes[site] = {}
        for name, labels in slot_labels.items():
            classes = network.slots[name].size
            train_rows = train_idx[activity[name][train_idx]]
            test_rows = test_idx[activity[name][test_idx]]
            probes[site][name] = [_probe(state[train_rows], state[test_rows], labels[train_rows],
                                           labels[test_rows], classes) if len(train_rows) and len(test_rows)
                                   else None for state in states]
    masked_compiled = []
    for state in compiled:
        clean = state.clone()
        for name, info in network.slots.items():
            clean[~activity[name], info.start:info.stop] = 0
        masked_compiled.append(clean)
    similarity = [[linear_cka(state, reference) for reference in masked_compiled]
                  for state in all_states["answer_position"]]
    alignment = {name: {"compiled_layer": next((block.layer + 1 for block in network.blocks
                                                  if block.write == name), 0),
                        "best_trained_layer": max(range(len(probes["answer_position"][name])),
                                                  key=lambda layer: probes["answer_position"][name][layer]
                                                  if probes["answer_position"][name][layer] is not None else -1)
                        if any(value is not None for value in probes["answer_position"][name]) else None,
                        "accuracy": max((value for value in probes["answer_position"][name]
                                         if value is not None), default=None)}
                 for name in network.slots}
    patching = {str(layer): _patch(model, ids, masks, positions, items, chars, ops.oracle, operator,
                                  network, slot_labels, activity, all_states["answer_position"], train_idx, layer)
                for layer in range(len(model.transformer.h))}
    with torch.no_grad():
        logits = model(input_ids=ids, attention_mask=masks).logits
    answer_correct = []
    for row, item in enumerate(items):
        start = len(item.prompt)
        stop = start + len(str(item.answer))
        predicted = logits[row, start - 1:stop - 1].argmax(-1)
        answer_correct.append(bool(torch.equal(predicted, ids[row, start:stop])))
    report = {"symbol": symbol, "examples": len(items), "train_examples": len(train_idx),
              "test_examples": len(test_idx),
              "train_answer_accuracy": sum(answer_correct[i] for i in train_idx) / len(train_idx),
              "test_answer_accuracy": sum(answer_correct[i] for i in test_idx) / len(test_idx),
              "probe_accuracy": probes, "linear_cka": similarity, "layer_alignment": alignment,
              "activation_patching": patching,
              "note": "Probe accuracy is held out by operand row. Patching transplants the probe row space "
                      "component for a selected compiled intermediate slot at the answer position."}
    default_dir = "report" if symbol == meta["symbol"] else f"report_{symbol}"
    out = Path(out or run_dir / default_dir)
    out.mkdir(parents=True, exist_ok=True)
    from opulse.canary import marked

    (out / "report.json").write_text(json.dumps(marked(report), ensure_ascii=False, indent=2), encoding="utf-8")
    _plots(report, out)
    return report


def _plots(report, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    names = list(report["layer_alignment"])
    matrix = [[float("nan") if value is None else value
               for value in report["probe_accuracy"]["answer_position"][name]] for name in names]
    fig, ax = plt.subplots(figsize=(max(5, len(matrix[0])), max(3, len(names) * .35)))
    im = ax.imshow(matrix, vmin=0, vmax=1, aspect="auto")
    ax.set(xlabel="Trained layer", ylabel="Compiled slot", title="Held out slot probe accuracy")
    ax.set_yticks(range(len(names)), names)
    fig.colorbar(im, ax=ax)
    fig.tight_layout()
    fig.savefig(out / "probes.png", dpi=130)
    plt.close(fig)
    fig, ax = plt.subplots()
    im = ax.imshow(report["linear_cka"], vmin=0, vmax=1, aspect="auto")
    ax.set(xlabel="Compiled layer", ylabel="Trained layer", title="Linear CKA")
    fig.colorbar(im, ax=ax)
    fig.tight_layout()
    fig.savefig(out / "cka.png", dpi=130)
    plt.close(fig)
    patch = report["activation_patching"]
    xs = [int(key) for key in patch]
    ys = [sum(row["patched_margin"] > row["baseline_margin"] for row in patch[str(x)]) / len(patch[str(x)])
          if patch[str(x)] else 0 for x in xs]
    fig, ax = plt.subplots()
    ax.bar(xs, ys)
    ax.set(xlabel="Patched trained layer", ylabel="Fraction with increased target margin",
           ylim=(0, 1), title="Counterfactual activation patching")
    fig.tight_layout()
    fig.savefig(out / "patching.png", dpi=130)
    plt.close(fig)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir")
    parser.add_argument("--out")
    parser.add_argument("--symbol")
    args = parser.parse_args(argv)
    result = analyze(args.run_dir, args.out, symbol=args.symbol)
    default_dir = "report" if result["symbol"] == json.loads(
        (Path(args.run_dir) / "metadata.json").read_text(encoding="utf-8"))["symbol"] else f"report_{result['symbol']}"
    print(json.dumps({"examples": result["examples"], "output": str(Path(args.out or Path(args.run_dir) / default_dir))}))


if __name__ == "__main__":
    main()
