"""Train a small causal language model from Opulse text JSONL on CPU."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True, help="JSONL with a text field")
    parser.add_argument("--tokenizer", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--architecture", choices=("gpt2", "llama"), default="gpt2")
    parser.add_argument("--steps", type=int, default=1000)
    parser.add_argument("--block-size", type=int, default=256)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--learning-rate", type=float, default=0.0003)
    parser.add_argument("--smoke", action="store_true", help="three CPU steps with a tiny model")
    args = parser.parse_args(argv)

    import torch
    from transformers import (
        AutoTokenizer,
        GPT2Config,
        GPT2LMHeadModel,
        LlamaConfig,
        LlamaForCausalLM,
    )

    random.seed(0)
    torch.manual_seed(0)
    torch.set_num_threads(2)
    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer, use_fast=True)
    if args.smoke:
        args.steps = 3
        args.block_size = 32
        args.batch_size = 2
        layers, hidden, heads = 2, 64, 2
    else:
        layers, hidden, heads = 6, 384, 6
    if args.steps < 1 or args.block_size < 2 or args.batch_size < 1:
        parser.error("steps, batch size and block size must be positive; block size must be at least 2")

    token_ids = []
    with args.corpus.open(encoding="utf-8") as source:
        for line in source:
            if line.strip():
                value = json.loads(line)["text"]
                token_ids.extend(tokenizer.encode(value, add_special_tokens=False))
                token_ids.append(tokenizer.eos_token_id)
    if len(token_ids) < 3:
        parser.error("corpus needs at least two text tokens and an end token")
    block = min(args.block_size, len(token_ids) - 1)
    examples = [token_ids[start:start + block] for start in range(0, len(token_ids) - block + 1, block)]
    if not examples:
        parser.error("corpus is too short")

    if args.architecture == "gpt2":
        config = GPT2Config(vocab_size=len(tokenizer), n_positions=block, n_ctx=block,
                            n_embd=hidden, n_layer=layers, n_head=heads,
                            bos_token_id=tokenizer.bos_token_id, eos_token_id=tokenizer.eos_token_id)
        model = GPT2LMHeadModel(config)
    else:
        config = LlamaConfig(vocab_size=len(tokenizer), max_position_embeddings=block,
                             hidden_size=hidden, intermediate_size=hidden * 4,
                             num_hidden_layers=layers, num_attention_heads=heads,
                             num_key_value_heads=heads, bos_token_id=tokenizer.bos_token_id,
                             eos_token_id=tokenizer.eos_token_id, pad_token_id=tokenizer.pad_token_id)
        model = LlamaForCausalLM(config)
    model.train()
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate)
    for step in range(args.steps):
        batch = torch.tensor([examples[(step * args.batch_size + offset) % len(examples)]
                              for offset in range(args.batch_size)], dtype=torch.long)
        optimizer.zero_grad()
        loss = model(input_ids=batch, labels=batch).loss
        loss.backward()
        optimizer.step()
        print(f"step {step + 1}: loss {loss.item():.4f}", flush=True)
    args.out.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(args.out)
    tokenizer.save_pretrained(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
