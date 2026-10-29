"""Read, execute and write a compiled operator through causal LM residual hooks."""

from __future__ import annotations

from dataclasses import dataclass

import torch
from torch import nn
from torch.nn import functional as F


def layers_of(model):
    if hasattr(model, "model") and hasattr(model.model, "layers"):
        return model.model.layers
    if hasattr(model, "transformer") and hasattr(model.transformer, "h"):
        return model.transformer.h
    raise ValueError("expected a Llama, Qwen or GPT2 style causal LM")


def _hidden(output):
    return output[0] if isinstance(output, tuple) else output


def _replace(output, hidden):
    return (hidden, *output[1:]) if isinstance(output, tuple) else hidden


def ridge_map(features, targets, penalty=1e-3):
    """Fit an affine map with a regularized least squares solution."""
    x = torch.cat((features.float(), torch.ones(len(features), 1)), dim=-1)
    y = targets.float()
    reg = penalty * torch.eye(x.shape[1])
    reg[-1, -1] = 0
    weights = torch.linalg.solve(x.T @ x + reg, x.T @ y)
    return weights[:-1].T, weights[-1]


class ReadAdapter(nn.Module):
    """Turn operand token identities or fitted residual probes into one hot slots."""

    def __init__(self, vocab, inputs, *, mode="token", token_ids=None, hidden_size=None):
        super().__init__()
        self.vocab = vocab
        self.inputs = inputs
        self.mode = mode
        if mode == "token":
            if token_ids is None:
                raise ValueError("token reader needs a value to token id mapping")
            self.token_ids = {int(value): int(token) for value, token in token_ids.items()}
        elif mode == "probe":
            if hidden_size is None:
                raise ValueError("probe reader needs hidden_size")
            self.probe = nn.Linear(hidden_size, vocab.size)
        else:
            raise ValueError(f"unknown reader {mode!r}")

    def fit(self, states, values, penalty=1e-3):
        if self.mode != "probe":
            raise ValueError("fit is for probe readers")
        target = F.one_hot(torch.tensor([self.vocab.index(int(v)) for v in values]),
                           self.vocab.size).float()
        weight, bias = ridge_map(states, target, penalty)
        with torch.no_grad():
            self.probe.weight.copy_(weight)
            self.probe.bias.copy_(bias)

    def forward(self, hidden, input_ids, positions):
        batch = torch.arange(input_ids.shape[0], device=input_ids.device)[:, None]
        if self.mode == "token":
            ids = input_ids[batch, positions]
            indices = torch.full_like(ids, -1)
            for value, token in self.token_ids.items():
                indices = torch.where(ids == token, self.vocab.index(value), indices)
            if bool((indices < 0).any()):
                raise ValueError("operand token is not in the token reader mapping")
        else:
            vectors = hidden[batch, positions]
            indices = self.probe(vectors.float()).argmax(-1)
        return F.one_hot(indices, self.vocab.size).to(hidden.dtype)


class WriteAdapter(nn.Module):
    """Map the compiled output slot into the target residual width."""

    def __init__(self, vocab, hidden_size, *, mode="unembedding", alpha=1.0, directions=None):
        super().__init__()
        self.vocab = vocab
        self.mode = mode
        self.alpha = alpha
        if mode == "unembedding":
            if directions is None or directions.shape != (vocab.size, hidden_size):
                raise ValueError("unembedding writer needs one direction per slot token")
            self.register_buffer("directions", directions.detach().float().clone())
        elif mode == "linear":
            self.linear = nn.Linear(vocab.size, hidden_size)
        else:
            raise ValueError(f"unknown writer {mode!r}")

    @classmethod
    def from_unembedding(cls, network, model, answer_token_ids, alpha=1.0):
        weights = model.get_output_embeddings().weight.detach()
        directions = torch.zeros(network.vocab.size, weights.shape[1], device=weights.device)
        for value in range(network.vocab.lo, network.vocab.hi + 1):
            if value in answer_token_ids:
                directions[network.vocab.index(value)] = weights[answer_token_ids[value]]
        return cls(network.vocab, weights.shape[1], alpha=alpha, directions=directions)

    def fit(self, slots, target_deltas, penalty=1e-3):
        if self.mode != "linear":
            raise ValueError("fit is for linear writers")
        weight, bias = ridge_map(slots, target_deltas, penalty)
        with torch.no_grad():
            self.linear.weight.copy_(weight)
            self.linear.bias.copy_(bias)

    def forward(self, slot):
        if self.mode == "linear":
            return self.alpha * self.linear(slot.float()).to(slot.dtype)
        return self.alpha * (slot.float() @ self.directions).to(slot.dtype)


@dataclass
class Injection:
    model: nn.Module
    network: nn.Module
    reader: ReadAdapter
    writer: WriteAdapter
    read_layer: int
    write_layer: int

    def __post_init__(self):
        stack = layers_of(self.model)
        if not 0 <= self.read_layer <= self.write_layer < len(stack):
            raise ValueError("read and write layers must be ordered and inside the model")
        self.last_values = None

    def _compute(self, hidden, ids, positions):
        tokens = self.reader(hidden, ids, positions)
        self.last_inputs = [[self.network.vocab.value(int(index)) for index in row]
                            for row in tokens.argmax(-1)]
        x = torch.zeros(len(ids), self.network.d_model, dtype=self.network._dtype(), device=hidden.device)
        for index, name in enumerate(self.network.inputs):
            info = self.network.slots[name]
            x[:, info.start:info.stop] = tokens[:, index]
        output = self.network(x)
        self.last_values = self.network.decode(output, self.network.output)
        info = self.network.slots[self.network.output]
        return self.writer(output[:, info.start:info.stop])

    def forward(self, input_ids, positions, attention_mask=None):
        """Run one forward pass with temporary plain Torch hooks."""
        stack = layers_of(self.model)
        pending = {}

        def read_hook(_module, _args, output):
            pending["delta"] = self._compute(_hidden(output), input_ids, positions)
            if self.read_layer == self.write_layer:
                return write_hook(_module, _args, output)
            return output

        def write_hook(_module, _args, output):
            state = _hidden(output).clone()
            ends = attention_mask.sum(-1) - 1 if attention_mask is not None else input_ids.new_full((len(input_ids),),
                                                                                                     input_ids.shape[1] - 1)
            state[torch.arange(len(state), device=state.device), ends] += pending["delta"].to(state.dtype)
            return _replace(output, state)

        handles = [stack[self.read_layer].register_forward_hook(read_hook)]
        if self.write_layer != self.read_layer:
            handles.append(stack[self.write_layer].register_forward_hook(write_hook))
        try:
            return self.model(input_ids=input_ids, attention_mask=attention_mask)
        finally:
            for handle in handles:
                handle.remove()


def nnsight_forward(injection, input_ids, positions, attention_mask=None):
    """Trace the same insertion with nnsight's local intervention API."""
    from nnsight import NNsight

    traced = NNsight(injection.model)
    stack = layers_of(traced)
    with traced.trace(input_ids=input_ids, attention_mask=attention_mask):
        read_output = stack[injection.read_layer].output
        read_state = read_output[0] if isinstance(read_output, tuple) else read_output
        delta = injection._compute(read_state, input_ids, positions)
        target = stack[injection.write_layer]
        out = target.output
        state = out[0] if isinstance(out, tuple) else out
        ends = attention_mask.sum(-1) - 1 if attention_mask is not None else input_ids.new_full((len(input_ids),),
                                                                                                 input_ids.shape[1] - 1)
        edited = state.clone()
        edited[torch.arange(len(input_ids)), ends] += delta
        if isinstance(out, tuple):
            target.output = (edited, *out[1:])
        else:
            target.output = edited
        logits = traced.output.logits.save()
    return logits.value if hasattr(logits, "value") else logits


def capture_layer(model, input_ids, layer, attention_mask=None):
    """Get one residual tensor at a chosen block output."""
    captured = {}

    def hook(_module, _args, output):
        captured["state"] = _hidden(output).detach().clone()

    handle = layers_of(model)[layer].register_forward_hook(hook)
    try:
        with torch.no_grad():
            model(input_ids=input_ids, attention_mask=attention_mask)
    finally:
        handle.remove()
    return captured["state"]


def fit_probe_from_prompts(reader, model, tokenizer, items, layer):
    """Fit known operand values to their residual vectors at the read layer."""
    from opulse.compile.handwired.data import tokenized_examples

    vectors, values = [], []
    for item in items:
        enc, positions = tokenized_examples(tokenizer, [item])
        state = capture_layer(model, enc["input_ids"], layer, enc["attention_mask"])
        for index, value in enumerate(item.operands):
            vectors.append(state[0, positions[0, index]])
            values.append(value)
    reader.fit(torch.stack(vectors), values)


def fit_writer_from_prompts(writer, network, model, tokenizer, items, layer):
    """Fit output slots to the residual change at a correct answer token."""
    features, targets = [], []
    for item in items:
        prompt = tokenizer(item.prompt, return_tensors="pt")
        answer = tokenizer(item.prompt + str(item.answer), return_tensors="pt")
        pids, aids = prompt["input_ids"], answer["input_ids"]
        if aids.shape[1] <= pids.shape[1] or not torch.equal(aids[0, :pids.shape[1]], pids[0]):
            raise ValueError("answer tokenization must extend the prompt")
        before = capture_layer(model, pids, layer)[0, -1]
        after = capture_layer(model, aids, layer)[0, pids.shape[1]]
        slot = network(network.embed([item.operands]))
        info = network.slots[network.output]
        features.append(slot[0, info.start:info.stop].detach())
        targets.append(after - before)
    writer.fit(torch.stack(features), torch.stack(targets))


def evaluate(injection, tokenizer, items):
    """Score single next answer tokens before and after insertion."""
    from opulse.compile.handwired.data import tokenized_examples

    records = []
    model = injection.model
    model.eval()
    for item in items:
        enc, positions = tokenized_examples(tokenizer, [item])
        ids, mask = enc["input_ids"], enc["attention_mask"]
        continuation = tokenizer(item.prompt + str(item.answer), return_tensors="pt")["input_ids"]
        if not torch.equal(continuation[0, :ids.shape[1]], ids[0]) or continuation.shape[1] != ids.shape[1] + 1:
            raise ValueError("evaluation requires a single answer token after the prompt")
        expected = int(continuation[0, -1])
        with torch.no_grad():
            base = model(input_ids=ids, attention_mask=mask).logits[0, -1]
            edited = injection.forward(ids, positions, mask).logits[0, -1]
        records.append({"symbol": item.symbol, "prompt": item.prompt, "operands": list(item.operands),
                        "answer": item.answer,
                        "form": item.form, "read_values": [str(v) for v in injection.last_inputs[0]],
                        "read_correct": tuple(injection.last_inputs[0]) == item.operands,
                        "compiled_value": str(injection.last_values[0]),
                        "baseline_correct": int(base.argmax()) == expected,
                        "injected_correct": int(edited.argmax()) == expected,
                        "baseline_logprob": float(base.log_softmax(-1)[expected]),
                        "injected_logprob": float(edited.log_softmax(-1)[expected])})
    return {"examples": records, "reader_accuracy": sum(row["read_correct"] for row in records) / len(records),
            "baseline_accuracy": sum(row["baseline_correct"] for row in records) / len(records),
            "injected_accuracy": sum(row["injected_correct"] for row in records) / len(records)}
