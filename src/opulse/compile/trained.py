"""Trained stand-ins for compiled operators, and how their errors compose when stitched.

:func:`train_operator` fits one residual MLP layer by gradient descent so that, on every input
token combination, it writes the same output token as the compiled network of an operator. The
result has the same slot interface (input slots, one output slot), so :func:`~opulse.compile.
network.stitch` joins trained modules exactly as it joins compiled ones.

A trained module writes an approximate one-hot vector. :func:`one_hot_error` measures how far it
is from the exact one, and :func:`perturb` adds Gaussian noise to the weights, to see how errors
of separately correct modules combine after stitching.
"""

from __future__ import annotations

import copy
import itertools

import torch

from opulse.compile.network import BlockInfo, CompiledNetwork, SlotInfo


def table_rows(network: CompiledNetwork) -> list[tuple]:
    """Every combination of input values (all tokens, including NaN and OOV)."""
    return list(itertools.product(network.vocab.values(), repeat=len(network.inputs)))


def train_operator(network: CompiledNetwork, hidden: int, *, seed: int = 0, lr: float = 3e-3,
                   max_steps: int = 20_000, extra_steps: int = 2_000, verbose: bool = False) -> CompiledNetwork:
    """One trained layer with the interface of ``network`` that reproduces its output table.

    Training uses mean squared error between the written output slot and the exact one-hot
    token, over all input combinations, and stops ``extra_steps`` after every combination is
    decoded correctly (argmax).
    """
    torch.manual_seed(seed)
    vocab = network.vocab
    names = [*network.inputs, network.output]
    slots, offset = {}, 0
    for name in names:
        info = network.slots[name]
        slots[name] = SlotInfo(name, info.kind, offset, info.size, info.origin, info.text,
                               list(info.regions) if name == network.output else [])
        offset += info.size
    rows = table_rows(network)
    with torch.no_grad():
        target_tokens = network.tokens(network(network.embed(rows)), network.output)
    out = slots[network.output]
    result = CompiledNetwork(f"{network.name} trained", vocab, offset, [hidden], slots, network.inputs,
                             network.output, [BlockInfo(network.output, "trained", "trained", 0, (0, hidden), ())])
    layer = result.layers[0]
    read_mask = torch.zeros(offset)
    for name in network.inputs:
        read_mask[slots[name].start:slots[name].stop] = 1.0
    write_mask = torch.zeros(offset)
    write_mask[out.start:out.stop] = 1.0
    with torch.no_grad():
        layer.up.weight.mul_(read_mask)
        layer.down.weight.mul_(write_mask[:, None])
    x = result.embed(rows)
    target = torch.zeros(len(rows), out.size)
    target[torch.arange(len(rows)), target_tokens] = 1.0
    optimizer = torch.optim.Adam(layer.parameters(), lr=lr)
    solved_at = None
    for step in range(max_steps):
        y = layer(x)[:, out.start:out.stop]
        loss = ((y - target) ** 2).sum(1).mean()
        optimizer.zero_grad()
        loss.backward()
        layer.up.weight.grad.mul_(read_mask)  # the layer reads only the input slots
        layer.down.weight.grad.mul_(write_mask[:, None])  # and writes only the output slot
        optimizer.step()
        if step % 100 == 0:
            accuracy = float((y.argmax(1) == target_tokens).float().mean())
            if verbose:
                print(step, float(loss), accuracy)
            if accuracy == 1.0 and solved_at is None:
                solved_at = step
            if solved_at is not None and step >= solved_at + extra_steps:
                break
    if solved_at is None:
        raise RuntimeError(f"training did not reach 100% on the table of {network.name}")
    return result


def one_hot_error(network: CompiledNetwork, rows, name: str | None = None) -> float:
    """Largest absolute difference between a slot and the nearest exact one-hot vector."""
    name = name or network.output
    info = network.slots[name]
    with torch.no_grad():
        block = network(network.embed(rows))[:, info.start:info.stop]
    exact = torch.zeros_like(block)
    exact[torch.arange(len(block)), block.argmax(1)] = 1.0
    return float((block - exact).abs().max())


def perturb(network: CompiledNetwork, sigma: float, seed: int) -> CompiledNetwork:
    """A copy with Gaussian noise of standard deviation ``sigma`` on every non-zero weight."""
    generator = torch.Generator().manual_seed(seed)
    noisy = copy.deepcopy(network)
    with torch.no_grad():
        for parameter in noisy.parameters():
            mask = parameter != 0
            parameter.add_(sigma * torch.randn(parameter.shape, generator=generator) * mask)
    return noisy
