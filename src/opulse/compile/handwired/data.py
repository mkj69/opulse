"""Small exact datasets shared by the injection and training experiments."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product

import torch

from opulse.compile.compiler import Const
from opulse.compile.values import OOV
from opulse.core.semantics import NAN


@dataclass(frozen=True)
class Example:
    symbol: str
    prompt: str
    operands: tuple[int, ...]
    answer: int
    operand_spans: tuple[tuple[int, int], ...]
    form: str


def examples(oracle, operator, values, *, longer: bool = True) -> list[Example]:
    """Render prefix notation and label it with the reference interpreter."""
    result = []
    for row in product(values, repeat=operator.n_ary):
        value = oracle.evaluate(operator, row).value
        if value is NAN or value is OOV:
            continue
        body = operator.symbol + " "
        spans = []
        for number in row:
            start = len(body)
            body += str(number)
            spans.append((start, len(body)))
            body += " "
        for form, prefix, suffix, answer in (
            ("direct", "", "= ", value),
            ("expression", "Compute ( ", ") + 1 = ", value + 1),
        ):
            if form == "expression" and not longer:
                continue
            prompt = prefix + body + suffix
            result.append(Example(operator.symbol, prompt, tuple(row), int(answer),
                                  tuple((a + len(prefix), b + len(prefix)) for a, b in spans), form))
    return result


def compiled_states(network, rows):
    """Return exact slot labels and the compiled residual after each layer."""
    with torch.no_grad():
        state = network.embed(rows)
        states = [state.clone()]
        for layer in network.layers:
            state = layer(state)
            states.append(state.clone())
    labels = {name: network.tokens(states[-1], name).clone() for name in network.slots}
    return states, labels


def slot_activity(network, labels):
    """Mark the rows where each compiled slot is reached and has an exact meaning."""
    count = len(next(iter(labels.values())))
    activity = {name: torch.zeros(count, dtype=torch.bool) for name in network.slots}
    for row in range(count):
        reached = set(network.inputs)
        for name, info in network.slots.items():
            active = name in reached or not info.regions
            for refs, tuples in info.regions:
                if active:
                    break
                if not all(isinstance(ref, Const) or ref in reached for ref in refs):
                    continue
                held = tuple((True, ref.value) if isinstance(ref, Const) else
                             (False, int(labels[ref][row]) if network.slots[ref].kind == "cond" else
                              network.vocab.value(int(labels[ref][row]))) for ref in refs)
                active = held in tuples
            activity[name][row] = active
            if active:
                reached.add(name)
    return activity


def tokenized_examples(tokenizer, items):
    """Align each numeric operand to one token in a fast tokenizer."""
    if not tokenizer.is_fast:
        raise ValueError("operand alignment requires a fast tokenizer")
    enc = tokenizer([item.prompt for item in items], padding=True, return_tensors="pt",
                    return_offsets_mapping=True)
    offsets = enc.pop("offset_mapping")
    positions = []
    for row, item in enumerate(items):
        found = []
        for left, right in item.operand_spans:
            matches = [i for i, (a, b) in enumerate(offsets[row].tolist()) if b > left and a < right]
            if len(matches) != 1:
                raise ValueError(f"operand {item.prompt[left:right]!r} needs one token")
            found.append(matches[0])
        positions.append(found)
    return enc, torch.tensor(positions, dtype=torch.long)
