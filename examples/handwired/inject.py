"""Run the untrained residual injection study on a locally cached causal LM."""

from __future__ import annotations

import argparse
import json
from itertools import product
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from opulse.compile import Compiler, Vocab
from opulse.compile.demo import operator_set
from opulse.compile.handwired.data import examples, tokenized_examples
from opulse.compile.handwired.injection import (
    Injection,
    ReadAdapter,
    WriteAdapter,
    evaluate,
    fit_probe_from_prompts,
    fit_writer_from_prompts,
)
from opulse.compile.network import build_network
from opulse.compile.verify import verify


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="hf-internal-testing/tiny-random-LlamaForCausalLM")
    parser.add_argument("--definition", default="a ◆₁ = { (a % 3) + 1 }")
    parser.add_argument("--symbol", default="◆₁")
    parser.add_argument("--values", type=int, default=6)
    parser.add_argument("--lo", type=int, default=0)
    parser.add_argument("--hi", type=int, default=9)
    parser.add_argument("--read-layer", type=int, default=0)
    parser.add_argument("--write-layer", type=int, default=1)
    parser.add_argument("--reader", choices=("token", "probe"), default="token")
    parser.add_argument("--writer", choices=("unembedding", "linear"), default="unembedding")
    parser.add_argument("--alpha", type=float, default=1.0)
    parser.add_argument("--out", default="handwired_injection.json")
    args = parser.parse_args(argv)
    torch.set_num_threads(1)
    model = AutoModelForCausalLM.from_pretrained(args.model, local_files_only=True).eval().cpu()
    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True, use_fast=True)
    tokenizer.pad_token = tokenizer.eos_token or tokenizer.unk_token
    ops = operator_set([args.definition])
    operator = next(op for op in ops.registry if op.symbol == args.symbol and op.definition is not None)
    vocab = Vocab(args.lo, args.hi)
    network = build_network(Compiler(ops.oracle, vocab, input_values=range(args.values)).compile(operator))
    rows = list(product(range(args.values), repeat=operator.n_ary))
    check = verify(network, ops.oracle, rows, lambda row: ops.oracle.evaluate(operator, row).value)
    if not check.exact or check.slot_oov:
        raise ValueError(f"compiled network is not exact on selected rows: {check.to_dict()}")
    items = examples(ops.oracle, operator, range(args.values))
    if not items:
        raise ValueError("no defined examples")
    # Fit adapters only on the direct prompts, then evaluate both prompt forms.
    fit_items = [item for item in items if item.form == "direct"]
    token_ids = {}
    for item in items:
        enc, positions = tokenized_examples(tokenizer, [item])
        for i, value in enumerate(item.operands):
            token = int(enc["input_ids"][0, positions[0, i]])
            if value in token_ids and token_ids[value] != token:
                raise ValueError("one operand value has context dependent token identities")
            token_ids[value] = token
    hidden_size = model.get_output_embeddings().weight.shape[1]
    reader = ReadAdapter(vocab, network.inputs, mode=args.reader, token_ids=token_ids,
                         hidden_size=hidden_size)
    if args.reader == "probe":
        fit_probe_from_prompts(reader, model, tokenizer, fit_items, args.read_layer)
    answer_ids = {}
    for value in range(vocab.lo, vocab.hi + 1):
        a = tokenizer("= ", return_tensors="pt")["input_ids"]
        b = tokenizer("= " + str(value), return_tensors="pt")["input_ids"]
        if b.shape[1] == a.shape[1] + 1 and torch.equal(a[0], b[0, :-1]):
            answer_ids[value] = int(b[0, -1])
    if args.writer == "unembedding":
        writer = WriteAdapter.from_unembedding(network, model, answer_ids, args.alpha)
    else:
        writer = WriteAdapter(vocab, hidden_size, mode="linear", alpha=args.alpha)
        fit_writer_from_prompts(writer, network, model, tokenizer, fit_items, args.write_layer)
    injection = Injection(model, network, reader, writer, args.read_layer, args.write_layer)
    report = evaluate(injection, tokenizer, items)
    report["config"] = vars(args)
    report["compiled_stats"] = network.stats()
    report["compiled_verification"] = check.to_dict()
    report["note"] = "Next token scores only. No model weights are changed."
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"examples": len(items), "baseline_accuracy": report["baseline_accuracy"],
                      "injected_accuracy": report["injected_accuracy"], "out": args.out}))


if __name__ == "__main__":
    main()
