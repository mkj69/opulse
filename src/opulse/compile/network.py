"""Torch form of compiled programs: a residual stack of MLP layers with a slot map.

The residual stream is a concatenation of slots. Each slot holds a one-hot token. Layer ``k``
computes ``x + down(relu(up(x)))``; every block of a program is placed in the first layer after
all slots it reads have been written, and blocks in the same layer share one MLP (their hidden
units are concatenated). There is one stream position and no attention.

:func:`stitch` and :func:`compact` work on the weight matrices of finished networks, not on
programs: stitching copies each network's layers into a wider stream and lets one network's
input slot occupy the coordinates of another network's output slot.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

import numpy as np
import torch
from torch import nn

from opulse.compile.compiler import COND, INT, Const, Program
from opulse.compile.values import COND_LABELS, OOV, Vocab


@dataclass
class SlotInfo:
    name: str
    kind: str
    start: int
    size: int
    origin: tuple
    text: str = ""
    regions: list = field(default_factory=list)
    reads: tuple = ()  # slots read by the block that writes this slot (empty for inputs)
    dont_care: bool = False  # the writing block reads a don't-care constant

    @property
    def stop(self) -> int:
        return self.start + self.size


@dataclass
class BlockInfo:
    write: str
    kind: str
    label: str
    layer: int
    hidden: tuple[int, int]  # unit range inside the layer
    signature: tuple = field(repr=False)  # the block's weights, for comparing networks


class Layer(nn.Module):
    def __init__(self, d_model: int, d_hidden: int) -> None:
        super().__init__()
        self.up = nn.Linear(d_model, d_hidden)
        self.down = nn.Linear(d_hidden, d_model, bias=False)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return x + self.down(torch.relu(self.up(x)))


class CompiledNetwork(nn.Module):
    """A compiled or stitched network. ``slots`` maps slot names to stream coordinates."""

    def __init__(self, name: str, vocab: Vocab, d_model: int, layer_widths: list[int],
                 slots: dict[str, SlotInfo], inputs: list[str], output: str,
                 blocks: list[BlockInfo]) -> None:
        super().__init__()
        self.name = name
        self.vocab = vocab
        self.d_model = d_model
        self.layers = nn.ModuleList(Layer(d_model, width) for width in layer_widths)
        self.slots = slots
        self.inputs = list(inputs)
        self.output = output
        self.blocks = blocks

    # ------------------------------------------------------------ inspection
    @property
    def slot_map(self) -> dict[str, tuple[int, int]]:
        """Slot name -> (start, stop) coordinates in the residual stream."""
        return {name: (info.start, info.stop) for name, info in self.slots.items()}

    def stats(self) -> dict:
        widths = [layer.up.out_features for layer in self.layers]
        dense = sum(p.numel() for p in self.parameters())
        nonzero = sum(int((p != 0).sum()) for p in self.parameters())
        return {"layers": len(self.layers), "d_model": self.d_model, "slots": len(self.slots),
                "max_hidden": max(widths, default=0), "total_hidden": sum(widths),
                "blocks": len(self.blocks), "params": dense, "nonzero_params": nonzero}

    # --------------------------------------------------------------- running
    def embed(self, rows) -> torch.Tensor:
        """Residual streams with the input slots set to one-hot tokens; ``rows`` holds input tuples."""
        rows = [tuple(row) for row in rows]
        x = torch.zeros(len(rows), self.d_model, dtype=self._dtype())
        for position, name in enumerate(self.inputs):
            start = self.slots[name].start
            index = torch.tensor([self.vocab.index(row[position]) for row in rows])
            x[torch.arange(len(rows)), start + index] = 1.0
        return x

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        for layer in self.layers:
            x = layer(x)
        return x

    def tokens(self, x: torch.Tensor, name: str) -> torch.Tensor:
        """Token index held by one slot (argmax of its coordinates), for each row."""
        info = self.slots[name]
        return x[:, info.start:info.stop].argmax(dim=1)

    def decode(self, x: torch.Tensor, name: str) -> list:
        info = self.slots[name]
        if info.kind == COND:
            return [COND_LABELS[int(i)] for i in self.tokens(x, name)]
        return [self.vocab.value(int(i)) for i in self.tokens(x, name)]

    @torch.no_grad()
    def run(self, rows) -> list:
        """Output values for each input tuple (an int, NaN or OOV)."""
        return self.decode(self(self.embed(rows)), self.output)

    def _dtype(self) -> torch.dtype:
        return self.layers[0].up.weight.dtype if len(self.layers) else torch.float32


# ------------------------------------------------------------------ assembly

def build_network(program: Program, dtype: torch.dtype = torch.float32) -> CompiledNetwork:
    """Lay out the slots, schedule the blocks into layers and set the weights."""
    slots: dict[str, SlotInfo] = {}
    offset = 0
    for name, slot in program.slots.items():
        slots[name] = SlotInfo(name, slot.kind, offset, slot.size, slot.origin, slot.text, list(slot.regions))
        offset += slot.size
    depth = {name: 0 for name in program.inputs}
    layers: list[list] = []
    for block in program.blocks:
        layer = 1 + max((depth[read] for read in block.reads), default=0)
        depth[block.write] = layer
        while len(layers) < layer:
            layers.append([])
        layers[layer - 1].append(block)
        slots[block.write].reads = block.reads
        slots[block.write].dont_care = block.dont_care
    network = CompiledNetwork(program.name, program.vocab, offset, [sum(b.hidden for b in blocks) for blocks in layers],
                              slots, program.inputs, program.output, [])
    with torch.no_grad():
        for index, (layer, blocks) in enumerate(zip(network.layers, layers)):
            up = np.zeros((layer.up.out_features, offset))
            bias = np.zeros(layer.up.out_features)
            down = np.zeros((offset, layer.up.out_features))
            unit = 0
            for block in blocks:
                columns = np.concatenate([np.arange(slots[r].start, slots[r].stop) for r in block.reads]) \
                    if block.reads else np.zeros(0, dtype=int)
                rows = np.arange(unit, unit + block.hidden)
                up[np.ix_(rows, columns)] = block.w_in
                bias[rows] = block.b_in
                out = slots[block.write]
                down[np.ix_(np.arange(out.start, out.stop), rows)] = block.w_out
                network.blocks.append(BlockInfo(block.write, block.kind, block.label, index,
                                                (unit, unit + block.hidden), block.signature()))
                unit += block.hidden
            layer.up.weight.copy_(torch.tensor(up))
            layer.up.bias.copy_(torch.tensor(bias))
            layer.down.weight.copy_(torch.tensor(down))
    return network.to(dtype)


# ------------------------------------------------------------------ stitching

def _rename_ref(ref, mapping: dict):
    return mapping.get(ref, ref) if isinstance(ref, str) else ref


def _rename_origin(origin: tuple, mapping: dict) -> tuple:
    if origin[0] in ("expr", "cond", "frame"):
        return (origin[0], origin[1], {k: _rename_ref(v, mapping) for k, v in origin[2].items()})
    if origin[0] == "chain":
        return (origin[0], origin[1], origin[2], {k: _rename_ref(v, mapping) for k, v in origin[3].items()})
    return origin


def stitch(parts: list[tuple[str, CompiledNetwork]], wiring: dict[str, str], output: str,
           name: str = "stitched", snap: bool = False) -> CompiledNetwork:
    """Join separately compiled networks into one, without changing any weight value.

    ``parts`` is a list of ``(prefix, network)`` in execution order. Slot ``s`` of the part with
    prefix ``p`` is called ``p.s`` in the result. ``wiring`` maps an input slot of a later part to
    a slot of an earlier part (``{"g.in0_a": "f.s7"}``); that input then reads the earlier slot
    directly, so no copy layer is needed. Unwired inputs become inputs of the result, in order.
    Layers are placed one part after the other, so the depth is the sum of the part depths.

    With ``snap=True`` each wired slot first passes through one extra layer that rounds every
    coordinate to 0 or 1 (exactly, for values below 0.375 or above 0.625) and writes a fresh
    slot, which the later part reads instead. Exact one-hot inputs pass through unchanged.
    """
    vocab = parts[0][1].vocab
    if any(net.vocab != vocab for _, net in parts):
        raise ValueError("stitched networks must share one vocabulary")
    slots, inputs, offset = {}, [], 0
    coordinates: list[np.ndarray] = []
    snaps: list[list[tuple[str, str]]] = []  # per part: (source slot, snapped slot) layers before it
    snapped: dict[str, str] = {}
    for prefix, net in parts:
        index = np.zeros(net.d_model, dtype=int)
        before: list[tuple[str, str]] = []
        renamed = {}
        for slot in net.slots:
            full = f"{prefix}.{slot}"
            target = wiring.get(full, full)
            if target != full and snap:
                if target not in snapped:
                    source = slots[target]
                    snapped[target] = f"{target}~snap"
                    slots[snapped[target]] = SlotInfo(snapped[target], source.kind, offset, source.size,
                                                      source.origin, source.text, list(source.regions),
                                                      (target,), source.dont_care)
                    offset += source.size
                    before.append((target, snapped[target]))
                target = snapped[target]
            renamed[slot] = target
        for slot, info in net.slots.items():
            full = f"{prefix}.{slot}"
            target = renamed[slot]
            if target != full:  # a wired input: reuse the coordinates of the slot it reads
                source = slots[target]
                if (source.kind, source.size) != (info.kind, info.size):
                    raise ValueError(f"cannot wire {full} ({info.kind}) to {target} ({source.kind})")
                index[info.start:info.stop] = np.arange(source.start, source.stop)
                continue
            slots[full] = SlotInfo(full, info.kind, offset, info.size, _rename_origin(info.origin, renamed),
                                   info.text,
                                   [(tuple(_rename_ref(r, renamed) for r in refs), tuples)
                                    for refs, tuples in info.regions],
                                   tuple(renamed[r] for r in info.reads), info.dont_care)
            index[info.start:info.stop] = np.arange(offset, offset + info.size)
            if info.origin[0] == "input":
                inputs.append(full)
            offset += info.size
        coordinates.append(index)
        snaps.append(before)
    widths = []
    for (_, net), before in zip(parts, snaps):
        if before:
            widths.append(sum(2 * slots[source].size for source, _ in before))
        widths.extend(layer.up.out_features for layer in net.layers)
    result = CompiledNetwork(name, vocab, offset, widths, slots, inputs, output, [])
    dtype = parts[0][1]._dtype()
    result.to(dtype)
    with torch.no_grad():
        target_layers = iter(result.layers)
        layer_index = 0
        for (prefix, net), index, before in zip(parts, coordinates, snaps):
            if before:
                new = next(target_layers)
                new.up.weight.zero_()
                new.up.bias.zero_()
                new.down.weight.zero_()
                unit = 0
                for source, target in before:
                    src, dst = slots[source], slots[target]
                    for i in range(src.size):  # out = relu(4x - 1.5) - relu(4x - 2.5)
                        new.up.weight[unit, src.start + i] = 4.0
                        new.up.bias[unit] = -1.5
                        new.up.weight[unit + 1, src.start + i] = 4.0
                        new.up.bias[unit + 1] = -2.5
                        new.down.weight[dst.start + i, unit] = 1.0
                        new.down.weight[dst.start + i, unit + 1] = -1.0
                        unit += 2
                    result.blocks.append(BlockInfo(target, "snap", "snap", layer_index,
                                                   (unit - 2 * src.size, unit), ("snap", src.size)))
                layer_index += 1
            columns = torch.tensor(index)
            for k, layer in enumerate(net.layers):
                new = next(target_layers)
                new.up.weight.zero_()
                new.down.weight.zero_()
                new.up.weight[:, columns] = layer.up.weight
                new.up.bias.copy_(layer.up.bias)
                new.down.weight[columns, :] = layer.down.weight
                for block in net.blocks:
                    if block.layer == k:
                        result.blocks.append(BlockInfo(f"{prefix}.{block.write}", block.kind, block.label,
                                                       layer_index, block.hidden, block.signature))
                layer_index += 1
    return result


def compact(network: CompiledNetwork) -> CompiledNetwork:
    """Merge layers that do not depend on each other, reading only the weight matrices.

    A layer reads the coordinates with a non-zero column in ``up`` and writes those with a
    non-zero row in ``down``. Each layer moves to the first position after every layer that
    writes something it reads; layers at the same position are joined into one wider MLP.
    """
    reads, writes = [], []
    for layer in network.layers:
        reads.append(set(torch.nonzero(layer.up.weight.abs().sum(0)).flatten().tolist()))
        writes.append(set(torch.nonzero(layer.down.weight.abs().sum(1)).flatten().tolist()))
    position, written_at = [], {}
    for k in range(len(network.layers)):
        p = 1 + max((written_at[c] for c in reads[k] if c in written_at), default=0)
        position.append(p)
        for c in writes[k]:
            written_at[c] = p
    groups: dict[int, list[int]] = {}
    for k, p in enumerate(position):
        groups.setdefault(p, []).append(k)
    order = sorted(groups)
    widths = [sum(network.layers[k].up.out_features for k in groups[p]) for p in order]
    result = CompiledNetwork(network.name, network.vocab, network.d_model, widths, copy.deepcopy(network.slots),
                             network.inputs, network.output, [])
    result.to(network._dtype())
    with torch.no_grad():
        for new_index, (p, new) in enumerate(zip(order, result.layers)):
            unit = 0
            for k in groups[p]:
                old = network.layers[k]
                h = old.up.out_features
                new.up.weight[unit:unit + h] = old.up.weight
                new.up.bias[unit:unit + h] = old.up.bias
                new.down.weight[:, unit:unit + h] = old.down.weight
                for block in network.blocks:
                    if block.layer == k:
                        result.blocks.append(BlockInfo(block.write, block.kind, block.label, new_index,
                                                       (unit + block.hidden[0], unit + block.hidden[1]),
                                                       block.signature))
                unit += h
    return result


__all__ = [
    "INT",
    "OOV",
    "BlockInfo",
    "CompiledNetwork",
    "Const",
    "Layer",
    "SlotInfo",
    "build_network",
    "compact",
    "stitch",
]
