"""Train a small causal transformer on exact Opulse examples, on CPU."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
from transformers import GPT2Config, GPT2LMHeadModel

from opulse.compile import Compiler, Vocab
from opulse.compile.demo import operator_set
from opulse.compile.handwired.data import compiled_states, examples, slot_activity
from opulse.compile.network import build_network
from opulse.compile.verify import verify

DEFAULT_DEFINITION = "a ◆₁ = { (a % 3) + 1 }"


def setup(definition=DEFAULT_DEFINITION, symbol="◆₁", lo=0, hi=9, values=range(8)):
    values = list(values)
    ops = operator_set(definition if isinstance(definition, (list, tuple)) else [definition])
    operator = next(op for op in ops.registry if op.symbol == symbol and op.definition is not None)
    network = build_network(Compiler(ops.oracle, Vocab(lo, hi), input_values=values).compile(operator))
    items = examples(ops.oracle, operator, values, longer=False)
    if any(network.vocab.index(item.answer) == network.vocab.oov_index for item in items):
        raise ValueError("answers fall outside the compiled vocabulary")
    from itertools import product

    rows = list(product(values, repeat=operator.n_ary))
    report = verify(network, ops.oracle, rows, lambda row: ops.oracle.evaluate(operator, row).value)
    if not report.exact or report.slot_oov:
        raise ValueError(f"compiled network is not exact on selected rows: {report.to_dict()}")
    return ops, operator, network, items


def character_vocab(items):
    chars = sorted(set("".join(item.prompt + str(item.answer) for item in items)))
    return {char: i + 1 for i, char in enumerate(chars)}  # 0 is padding


def encode(items, chars):
    texts = [item.prompt + str(item.answer) for item in items]
    width = max(map(len, texts))
    ids = torch.zeros(len(items), width, dtype=torch.long)
    masks = torch.zeros_like(ids)
    labels = torch.full_like(ids, -100)
    positions = []
    for row, (item, full) in enumerate(zip(items, texts)):
        ids[row, :len(full)] = torch.tensor([chars[char] for char in full])
        masks[row, :len(full)] = 1
        labels[row, len(item.prompt):len(full)] = ids[row, len(item.prompt):len(full)]
        positions.append(len(item.prompt) - 1)
    return ids, masks, labels, torch.tensor(positions)


def train(out, *, definition=DEFAULT_DEFINITION, symbol="◆₁", lo=0, hi=9,
          values=range(8), steps=20, hidden=32, layers=2, heads=2, seed=0, lr=3e-3,
          definitions=None, symbols=None):
    torch.manual_seed(seed)
    torch.set_num_threads(1)
    definitions = list(definitions) if definitions is not None else [definition]
    symbols = list(symbols) if symbols is not None else [symbol]
    if not symbols:
        raise ValueError("at least one operator must be selected")
    by_symbol = {}
    items = []
    training_rows = []
    for selected in symbols:
        _, _, compiled, selected_items = setup(definitions, selected, lo, hi, values)
        selected_train = [i for i in range(len(selected_items)) if i % 4 != 0]
        selected_test = [i for i in range(len(selected_items)) if i % 4 == 0]
        if not selected_train or not selected_test:
            raise ValueError("each operator needs at least two examples for a train and test split")
        by_symbol[selected] = (compiled, selected_items, selected_train, selected_test)
        training_rows.extend(len(items) + i for i in selected_train)
        items.extend(selected_items)
    chars = character_vocab(items)
    ids, masks, labels, _ = encode(items, chars)
    config = GPT2Config(vocab_size=len(chars) + 1, n_positions=ids.shape[1] + 4,
                        n_embd=hidden, n_layer=layers, n_head=heads, pad_token_id=0,
                        bos_token_id=0, eos_token_id=0)
    model = GPT2LMHeadModel(config)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr)
    losses = []
    for _ in range(steps):
        model.train()
        optimizer.zero_grad()
        loss = model(input_ids=ids[training_rows], attention_mask=masks[training_rows],
                     labels=labels[training_rows]).loss
        loss.backward()
        optimizer.step()
        losses.append(float(loss.detach()))
    model.eval()
    slot_records = {}
    for selected, (compiled, selected_items, selected_train, selected_test) in by_symbol.items():
        states, slot_labels = compiled_states(compiled, [item.operands for item in selected_items])
        activity = slot_activity(compiled, slot_labels)
        slot_records[selected] = {"labels": {name: label.tolist() for name, label in slot_labels.items()},
                                  "active": {name: mask.tolist() for name, mask in activity.items()},
                                  "slot_map": {name: list(span) for name, span in compiled.slot_map.items()},
                                  "slot_text": {name: info.text for name, info in compiled.slots.items()},
                                  "train_indices": selected_train, "test_indices": selected_test,
                                  "compiled_layers": len(states) - 1}
    metadata = {"definition": definitions[0], "symbol": symbols[0], "definitions": definitions,
                "symbols": symbols, "lo": lo, "hi": hi,
                "values": list(values), "chars": chars, "losses": losses,
                "training": {"seed": seed, "steps": steps, "learning_rate": lr, "hidden": hidden,
                             "layers": layers, "heads": heads},
                "examples": [{"symbol": item.symbol, "prompt": item.prompt, "operands": list(item.operands),
                              "answer": item.answer} for item in items], "operators": slot_records}
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(out / "model", safe_serialization=True)
    from opulse.canary import marked

    (out / "metadata.json").write_text(json.dumps(marked(metadata), ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="handwired_small")
    parser.add_argument("--definition", default=DEFAULT_DEFINITION)
    parser.add_argument("--symbol", default="◆₁")
    parser.add_argument("--definitions-file", help="JSON array of definitions to train together")
    parser.add_argument("--symbols", help="comma separated symbols selected from the definitions")
    parser.add_argument("--lo", type=int, default=0)
    parser.add_argument("--hi", type=int, default=9)
    parser.add_argument("--values", type=int, default=8, help="operand values from zero to this count")
    parser.add_argument("--steps", type=int, default=20)
    parser.add_argument("--hidden", type=int, default=32)
    parser.add_argument("--layers", type=int, default=2)
    parser.add_argument("--heads", type=int, default=2)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)
    definitions = json.loads(Path(args.definitions_file).read_text(encoding="utf-8")) if args.definitions_file else None
    symbols = args.symbols.split(",") if args.symbols else None
    result = train(args.out, definition=args.definition, symbol=args.symbol, lo=args.lo, hi=args.hi,
                   values=range(args.values), steps=args.steps, hidden=args.hidden, layers=args.layers,
                   heads=args.heads, seed=args.seed, definitions=definitions, symbols=symbols)
    print(json.dumps({"examples": len(result["examples"]), "steps": len(result["losses"]),
                      "out": args.out}))


if __name__ == "__main__":
    main()
