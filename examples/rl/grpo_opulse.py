"""Minimal single-GPU GRPO on Opulse benchmark tasks.

Rollouts come from an in-process vLLM engine; the policy is a Hugging Face model trained on the
same GPU, and its weights are copied into vLLM after every update. The reward is the Opulse
grader (``opulse.bench.score.score_response``): 1 for a correct final answer, else 0.

One update per rollout batch (on-policy, so the PPO ratio is 1): the loss is
``-A * log p`` summed over completion tokens and divided by the number of completion tokens,
with group-normalised advantages and no KL term. Groups whose rewards are all equal carry no
signal and are skipped.

    python examples/rl/grpo_opulse.py --model Qwen/Qwen3-0.6B --train train.jsonl \
        --test small=small_full.jsonl --test mid=mid_full.jsonl --out runs/grpo
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path

os.environ.setdefault("VLLM_ENABLE_V1_MULTIPROCESSING", "0")  # keep the engine in this process
os.environ.setdefault("VLLM_USE_FLASHINFER_SAMPLER", "0")  # its kernels need nvcc at run time

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from torch.utils.checkpoint import checkpoint
from vllm import LLM, SamplingParams

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from opulse.bench.score import score_response


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True)
    p.add_argument("--train", type=Path, nargs="+", required=True)
    p.add_argument("--test", action="append", default=[], help="NAME=tasks.jsonl (greedy accuracy is logged)")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--steps", type=int, default=200)
    p.add_argument("--prompts", type=int, default=32, help="prompts per step")
    p.add_argument("--samples", type=int, default=8, help="rollouts per prompt")
    p.add_argument("--lr", type=float, default=1e-6)
    p.add_argument("--max-new", type=int, default=1024)
    p.add_argument("--micro", type=int, default=2, help="sequences per backward pass (logits are vocab-sized)")
    p.add_argument("--eval-every", type=int, default=20)
    p.add_argument("--save-every", type=int, default=100)
    p.add_argument("--vllm-memory", type=float, default=0.25)
    p.add_argument("--thinking", action="store_true", help="let the chat template enable thinking")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--reward", choices=("outcome", "steps", "progress"), default="outcome",
                   help="steps: (share of lines that are checked single rewrites + outcome) / 2; "
                        "progress: (checked single rewrites / reference derivation length + outcome) / 2")
    p.add_argument("--operators", type=Path, default=None, help="operator file of the training tasks (steps reward)")
    return p.parse_args()


def graded(task: dict, completion) -> bool:
    """Correct final answer in a completion that was not cut off."""
    return completion.finish_reason != "length" and score_response(task, completion.text)["correct"]


def read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    args = parse_args()
    random.seed(args.seed)
    torch.manual_seed(args.seed)
    args.out.mkdir(parents=True, exist_ok=True)
    train = [task for path in args.train for task in read(path)]
    tests = {name: read(Path(path)) for name, path in (item.split("=", 1) for item in args.test)}

    tok = AutoTokenizer.from_pretrained(args.model)

    def chat(task: dict) -> str:
        return tok.apply_chat_template([{"role": "user", "content": task["prompt"]}], tokenize=False,
                                       add_generation_prompt=True, enable_thinking=args.thinking)

    llm = LLM(args.model, gpu_memory_utilization=args.vllm_memory, max_model_len=4096, seed=args.seed,
              enable_prefix_caching=True,
              compilation_config={"cudagraph_capture_sizes": [1, 2, 4, 8, 16, 32, 64, 128, 256]})
    policy = AutoModelForCausalLM.from_pretrained(args.model, torch_dtype=torch.float32).cuda()
    policy.gradient_checkpointing_enable()
    policy.config.use_cache = False
    opt = torch.optim.AdamW(policy.parameters(), lr=args.lr, betas=(0.9, 0.95), weight_decay=0.0)
    amp = torch.autocast("cuda", dtype=torch.bfloat16)

    def chunk_loss(hidden, targets, weights):
        with amp:
            logits = policy.lm_head(hidden)
        return (torch.nn.functional.cross_entropy(logits.float(), targets, reduction="none") * weights).sum()

    def sync() -> None:
        state = {name: tensor.to(torch.bfloat16) for name, tensor in policy.state_dict().items()}

        def load(worker):
            worker.model_runner.model.load_weights(weights=list(state.items()))

        llm.collective_rpc(load)
        llm.reset_prefix_cache()

    def evaluate(step: int, log) -> None:
        greedy = SamplingParams(temperature=0.0, max_tokens=args.max_new)
        record = {"step": step, "eval": {}}
        for name, tasks in tests.items():
            outs = llm.generate([chat(t) for t in tasks], greedy, use_tqdm=False)
            correct = [graded(t, o.outputs[0]) for t, o in zip(tasks, outs)]
            record["eval"][name] = sum(correct) / len(correct)
            with (args.out / f"eval_{name}_step{step}.jsonl").open("w", encoding="utf-8") as sink:
                for t, o, c in zip(tasks, outs, correct):
                    sink.write(json.dumps({"id": t["id"], "correct": c, "response": o.outputs[0].text},
                                          ensure_ascii=False) + "\n")
        log.write(json.dumps(record) + "\n")
        log.flush()
        print(record, flush=True)

    step_checker = None
    if args.reward in ("steps", "progress"):
        from opulse.cli.bench import step_checker_for
        from opulse.cli.operators import DEFAULT_CONFIG

        step_checker = step_checker_for(args.operators, DEFAULT_CONFIG)

    def reward(task: dict, completion) -> float:
        outcome = float(graded(task, completion))
        if step_checker is None or task.get("format") != "steps" or completion.finish_reason == "length":
            return outcome
        try:
            report = step_checker(task, completion.text)
            credit = report["progress"] if args.reward == "progress" else report["credit"]
        except Exception as exc:  # noqa: BLE001 - a grader failure must not stop training
            print(f"step check failed on {task['id']}: {exc!r}", flush=True)
            credit = 0.0
        return (credit + outcome) / 2

    log = (args.out / "log.jsonl").open("a", encoding="utf-8")
    t0 = time.time()
    evaluate(0, log)
    sampling = SamplingParams(temperature=1.0, top_p=1.0, max_tokens=args.max_new, n=args.samples)
    order = []
    for step in range(1, args.steps + 1):
        if len(order) < args.prompts:
            order = random.sample(train, len(train))
        batch, order = order[:args.prompts], order[args.prompts:]
        prompts = [chat(t) for t in batch]
        t_step = time.time()
        outs = llm.generate(prompts, sampling, use_tqdm=False)
        rows = []  # (prompt ids, completion ids, advantage)
        rewards, lengths, truncated, live = [], [], 0, 0
        for task, prompt, out in zip(batch, prompts, outs):
            r = torch.tensor([reward(task, c) for c in out.outputs])
            rewards.append(r.mean().item())
            live += bool(r.std() > 0)
            lengths += [len(c.token_ids) for c in out.outputs]
            truncated += sum(c.finish_reason == "length" for c in out.outputs)
            if r.std() == 0:
                continue
            adv = (r - r.mean()) / (r.std() + 1e-6)
            prompt_ids = out.prompt_token_ids
            for c, a in zip(out.outputs, adv.tolist()):
                if a != 0 and c.token_ids:  # a zero advantage carries no signal
                    rows.append((prompt_ids, list(c.token_ids), a))
        n_tokens = sum(len(c) for _, c, _ in rows)
        t_gen = time.time()
        policy.train()
        for start in range(0, len(rows), args.micro):
            chunk = rows[start:start + args.micro]
            seqs = [p + c for p, c, _ in chunk]
            width = max(map(len, seqs))
            ids = torch.full((len(chunk), width), tok.pad_token_id or 0)
            mask = torch.zeros((len(chunk), width), dtype=torch.long)
            weight = torch.zeros((len(chunk), width))
            for j, ((p, c, a), seq) in enumerate(zip(chunk, seqs)):
                ids[j, :len(seq)] = torch.tensor(seq)
                mask[j, :len(seq)] = 1
                weight[j, len(p) - 1:len(seq) - 1] = a  # position t predicts token t + 1
            ids, mask, weight = ids.cuda(), mask.cuda(), weight.cuda()
            keep = weight[:, :-1] != 0
            with amp:
                hidden = policy.model(input_ids=ids, attention_mask=mask).last_hidden_state[:, :-1][keep]
            targets, weights = ids[:, 1:][keep], weight[:, :-1][keep]
            # Vocabulary-sized logits are computed in chunks and recomputed in the backward pass.
            loss = sum(checkpoint(chunk_loss, hidden[i:i + 512], targets[i:i + 512], weights[i:i + 512],
                                  use_reentrant=False) for i in range(0, len(targets), 512))
            if torch.is_tensor(loss):
                (loss / max(n_tokens, 1)).backward()
        if rows:
            torch.nn.utils.clip_grad_norm_(policy.parameters(), 1.0)
            opt.step()
            opt.zero_grad(set_to_none=True)
        if rows:
            sync()
        record = {"step": step, "reward": sum(rewards) / len(rewards),
                  "live_groups": live / len(batch),
                  "mean_len": sum(lengths) / len(lengths), "truncated": truncated / len(lengths),
                  "gen_sec": round(t_gen - t_step), "train_sec": round(time.time() - t_gen),
                  "sec": round(time.time() - t0)}
        log.write(json.dumps(record) + "\n")
        log.flush()
        print(record, flush=True)
        if step % args.eval_every == 0 or step == args.steps:
            evaluate(step, log)
        if args.save_every and (step % args.save_every == 0 or step == args.steps):
            policy.save_pretrained(args.out / f"step{step}", safe_serialization=True)
            tok.save_pretrained(args.out / f"step{step}")


if __name__ == "__main__":
    main()
