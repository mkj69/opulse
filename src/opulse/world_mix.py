"""Deterministic allocation and ordering of records from named worlds."""

from __future__ import annotations

import hashlib
import math
import random
import re


def parse_world_mix(text: str) -> dict[str, float]:
    weights = {}
    for part in text.split(","):
        name, separator, value = part.strip().partition(":")
        if not separator or name in (".", "..") or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", name) \
                or name in weights:
            raise ValueError("world mix expects distinct NAME:WEIGHT entries")
        try:
            weight = float(value)
        except ValueError:
            raise ValueError(f"invalid world weight {value!r}") from None
        if not math.isfinite(weight) or weight < 0:
            raise ValueError("world weights must be finite and nonnegative")
        weights[name] = weight
    if not weights or sum(weights.values()) <= 0:
        raise ValueError("world weights must have a positive total")
    return weights


def world_schedule(count: int, weights: dict[str, float], seed: int) -> list[str]:
    """Allocate by largest remainder, then shuffle a seeded schedule."""
    if count < 0:
        raise ValueError("count must be nonnegative")
    total = sum(weights.values())
    if not weights or total <= 0 or any(not math.isfinite(w) or w < 0 for w in weights.values()):
        raise ValueError("world weights must be finite, nonnegative, and have positive total")
    exact = {name: count * weight / total for name, weight in weights.items()}
    amounts = {name: math.floor(value) for name, value in exact.items()}
    remainder = count - sum(amounts.values())
    for name in sorted(weights, key=lambda item: (-(exact[item] - amounts[item]), item))[:remainder]:
        amounts[name] += 1
    schedule = [name for name in sorted(amounts) for _ in range(amounts[name])]
    random.Random(seed).shuffle(schedule)
    return schedule


def world_seed(seed: int, name: str) -> int:
    return int.from_bytes(hashlib.sha256(f"{seed}:{name}".encode()).digest()[:8], "big")
