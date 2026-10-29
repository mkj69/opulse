"""Options of a corpus build and their canonical form (for the manifest's config hash)."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass, field

KINDS = ("definitions", "values", "derivations", "descriptions")
DEFINITION_MODES = ("separate", "prefix", "none")
DERIVATION_STYLES = ("chain", "en", "zh")
DESCRIPTION_LANGS = ("en", "zh", "both")
SPLIT_MODES = ("none", "operator", "set")


@dataclass(frozen=True)
class CorpusOptions:
    seed: int = 0
    documents: dict[str, int] = field(default_factory=lambda: {"train": 1000})
    mix: dict[str, float] = field(default_factory=lambda: {"definitions": 1.0, "values": 4.0,
                                                           "derivations": 2.0, "descriptions": 0.0})
    definitions: str = "separate"
    definitions_per_document: int = 8
    expressions_per_document: int = 8
    derivation_style: str = "chain"
    description_lang: str = "en"
    max_layer: int | None = None
    keep_undefined: bool = False
    operator_frequency: str = "uniform"
    frequency_seed: int = 0
    skeleton_weights: dict[str, float] = field(default_factory=dict)
    cot_depth: int | None = None
    cot_known_layers: int = 0
    cot_known: tuple[str, ...] = ()
    max_steps: int = 200
    split: str = "none"
    split_ratios: dict[str, float] = field(default_factory=lambda: {"train": 0.8, "val": 0.1, "test": 0.1})
    dedup: bool = True
    shard_size: int = 100_000
    block_size: int = 20
    probe: bool = False
    tokenizer: str | None = None

    def __post_init__(self) -> None:
        unknown = set(self.mix) - set(KINDS)
        if unknown:
            raise ValueError(f"unknown document kinds in the mix: {sorted(unknown)}; known: {', '.join(KINDS)}")
        if any(w < 0 for w in self.mix.values()) or sum(self.mix.values()) <= 0:
            raise ValueError("mix weights must be non-negative and not all zero")
        if self.definitions not in DEFINITION_MODES:
            raise ValueError(f"definitions must be one of {DEFINITION_MODES}")
        if self.definitions == "none" and (self.mix.get("definitions", 0) > 0 or self.mix.get("descriptions", 0) > 0):
            raise ValueError("--definitions none leaves out every definition: the mix must give "
                             "definitions and descriptions weight 0")
        if self.derivation_style not in DERIVATION_STYLES:
            raise ValueError(f"derivation style must be one of {DERIVATION_STYLES}")
        if self.description_lang not in DESCRIPTION_LANGS:
            raise ValueError(f"description language must be one of {DESCRIPTION_LANGS}")
        if self.split not in SPLIT_MODES:
            raise ValueError(f"split must be one of {SPLIT_MODES}")
        for name in set(self.documents) | set(self.split_ratios):
            if name in (".", "..") or re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", name) is None:
                raise ValueError(f"invalid split name {name!r}")
        if any(not math.isfinite(weight) for weight in (*self.mix.values(), *self.split_ratios.values())):
            raise ValueError("mix weights and split ratios must be finite")
        if any(not math.isfinite(weight) or weight < 0 for weight in self.skeleton_weights.values()):
            raise ValueError("skeleton weights must be finite and nonnegative")
        for name, value in (("definitions per document", self.definitions_per_document),
                            ("expressions per document", self.expressions_per_document),
                            ("max steps", self.max_steps), ("shard size", self.shard_size),
                            ("block size", self.block_size)):
            if value < 1:
                raise ValueError(f"{name} must be at least 1")
        if any(n < 0 for n in self.documents.values()):
            raise ValueError("document counts must be non-negative")
        if self.probe and self.mix.get("derivations", 0) <= 0:
            raise ValueError("probe data comes from derivation documents: give derivations a positive weight")
        expressions_active = self.mix.get("values", 0) > 0 or self.mix.get("derivations", 0) > 0
        if not expressions_active and (self.operator_frequency != "uniform" or self.frequency_seed or
                                       self.keep_undefined or self.max_layer is not None):
            raise ValueError("expression sampling options need values or derivations in --mix")
        if self.mix.get("values", 0) <= 0 and self.expressions_per_document != 8:
            raise ValueError("--expressions-per-document needs values in --mix")
        if self.mix.get("derivations", 0) <= 0 and (self.cot_depth is not None or self.cot_known_layers or
                                                    self.cot_known or self.derivation_style != "chain" or
                                                    self.max_steps != 200):
            raise ValueError("derivation options need derivations in --mix")
        if self.mix.get("definitions", 0) <= 0 and self.mix.get("descriptions", 0) <= 0 and \
                self.definitions_per_document != 8:
            raise ValueError("--definitions-per-document needs definitions or descriptions in --mix")
        if self.mix.get("descriptions", 0) <= 0 and self.description_lang != "en":
            raise ValueError("--description-lang needs descriptions in --mix")

    def to_dict(self) -> dict:
        data = asdict(self)
        data["cot_known"] = sorted(self.cot_known)
        if not self.skeleton_weights:
            data.pop("skeleton_weights")
        return data

    def config_hash(self) -> str:
        text = json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(text.encode()).hexdigest()[:16]


def kind_counts(total: int, mix: dict[str, float]) -> dict[str, int]:
    """Documents per kind: ``total`` divided by weight, largest remainders first (ties by kind order)."""
    weights = {kind: mix.get(kind, 0.0) for kind in KINDS}
    largest = max(weights.values())
    normalized = {kind: weight / largest for kind, weight in weights.items()}
    scale = sum(normalized.values())
    exact = {kind: total * weight / scale for kind, weight in normalized.items()}
    counts = {kind: int(value) for kind, value in exact.items()}
    left = total - sum(counts.values())
    order = sorted(KINDS, key=lambda kind: (-(exact[kind] - counts[kind]), KINDS.index(kind)))
    for kind in order[:left]:
        counts[kind] += 1
    return counts


def parse_weights(text: str, what: str) -> dict[str, float]:
    """``"a=1,b=2.5"`` -> ``{"a": 1.0, "b": 2.5}`` (order kept)."""
    result: dict[str, float] = {}
    for part in text.split(","):
        if not part.strip():
            continue
        name, sep, value = part.partition("=")
        if not sep:
            raise ValueError(f"{what}: expected NAME=NUMBER, got {part!r}")
        try:
            result[name.strip()] = float(value)
        except ValueError:
            raise ValueError(f"{what}: {value!r} is not a number") from None
    if not result:
        raise ValueError(f"{what}: empty")
    return result
