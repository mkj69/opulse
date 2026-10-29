"""Build a sharded pretraining corpus (and optional probe data) from operator sets.

Layout of ``out``::

    manifest.json                 counts, token estimates, provenance, options
    splits.json                   per split: owned and mentioned operator func_ids
    <split>/<split>-00000.jsonl   documents, one {"text": ...} per line
    probe/<split>-00000.jsonl     probe records (with --probe)

Everything is a function of the operator sets, the settings and the options: generated
documents come in blocks with seeds derived from ``(seed, split, kind, block)``, documents
of a split are interleaved in a seeded order, and duplicates are dropped in that order. The
number of worker processes does not change any output byte.
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
import sqlite3
import tempfile
from dataclasses import dataclass, field
from itertools import count as counter
from pathlib import Path

from opulse.canary import CANARY, marked
from opulse.config import Settings
from opulse.core.registry import OperatorRegistry
from opulse.corpus.documents import SplitGenerator, load_tokenizer
from opulse.corpus.options import KINDS, CorpusOptions, kind_counts
from opulse.corpus.splits import split_operators
from opulse.expression.dataset import operator_set_hash, provenance
from opulse.expression.parallel import BlockPool, Prefetch, block_seed

logger = logging.getLogger(__name__)
GENERATED = ("values", "derivations")
MANIFEST_FORMAT = "opulse-corpus/1"


class CorpusState:
    """What a worker process needs: one generator per split."""

    def __init__(self, generators: dict[str, SplitGenerator]) -> None:
        self.generators = generators

    def run(self, task):
        split, kind, block, size, start = task
        return self.generators[split].run(kind, block, size, start)


def estimate_tokens(text: str) -> int:
    """Rough token count: four ASCII characters per token, one token per other character."""
    ascii_chars = len(text.encode("ascii", "ignore"))
    return (ascii_chars + 3) // 4 + (len(text) - ascii_chars)


class ShardWriter:
    """Writes JSON lines into numbered shards of at most ``shard_size`` lines."""

    def __init__(self, directory: Path, stem: str, shard_size: int, root: Path) -> None:
        self.directory, self.stem, self.shard_size, self.root = directory, stem, shard_size, root
        self.shards: list[dict] = []
        self._handle = None
        self._hash = None

    def write(self, row: dict, stats: dict) -> None:
        if self._handle is None or self.shards[-1]["documents"] >= self.shard_size:
            self._close()
            self.directory.mkdir(parents=True, exist_ok=True)
            path = self.directory / f"{self.stem}-{len(self.shards):05d}.jsonl"
            self._handle = open(path, "w", encoding="utf-8", newline="\n")  # noqa: SIM115 - closed by close()
            self._hash = hashlib.sha256()
            self.shards.append({"path": path.relative_to(self.root).as_posix(), "documents": 0, "chars": 0,
                                "bytes": 0, "tokens_estimate": 0})
        line = json.dumps(marked(row), ensure_ascii=False) + "\n"
        data = line.encode("utf-8")
        self._handle.write(line)
        self._hash.update(data)
        shard = self.shards[-1]
        shard["documents"] += 1
        for key in ("chars", "tokens_estimate", "tokens"):
            if key in stats:
                shard[key] = shard.get(key, 0) + stats[key]
        shard["bytes"] += len(data)

    def _close(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self.shards[-1]["sha256"] = self._hash.hexdigest()
            self._handle = None

    def close(self) -> list[dict]:
        self._close()
        return self.shards


class ExactDeduper:
    """Keep exact document text in memory, then spill to a temporary SQLite index."""

    def __init__(self, path: Path, memory_limit: int = 100_000) -> None:
        self.path = path
        self.memory_limit = memory_limit
        self.memory: set[str] = set()
        self.database: sqlite3.Connection | None = None

    def add(self, value: str) -> bool:
        """Return true if ``value`` was new."""
        if self.database is None:
            if value in self.memory:
                return False
            self.memory.add(value)
            if len(self.memory) >= self.memory_limit:
                self.database = sqlite3.connect(self.path)
                self.database.execute("CREATE TABLE seen (text TEXT PRIMARY KEY) WITHOUT ROWID")
                self.database.executemany("INSERT INTO seen VALUES (?)", ((text,) for text in self.memory))
                self.memory.clear()
            return True
        return self.database.execute("INSERT OR IGNORE INTO seen VALUES (?)", (value,)).rowcount == 1

    def close(self) -> None:
        if self.database is not None:
            self.database.close()


@dataclass
class _KindStream:
    kind: str
    requested: int
    source: object  # iterator of documents
    written: int = 0
    duplicates: int = 0
    exhausted: bool = False
    limit: int = 0
    seen: int = 0

    def next_unique(self, seen_texts: ExactDeduper | None) -> dict | None:
        while not self.exhausted:
            if self.seen >= self.limit:
                self.exhausted = True
                break
            document = self.source()
            self.seen += 1
            if seen_texts is not None:
                text = document["text"]
                if not seen_texts.add(text):
                    self.duplicates += 1
                    continue
            return document
        return None


@dataclass
class _Split:
    name: str
    path: Path
    registry: OperatorRegistry
    owned: list[str]
    mentioned: set[str] = field(default_factory=set)


def resolve_splits(settings: Settings, operator_sets: dict[str, Path], options: CorpusOptions) -> list[_Split]:
    """The splits and their operators, in output order."""
    if options.split == "set":
        if len(operator_sets) < 1:
            raise ValueError("--split set needs one --operators NAME=PATH per split")
        splits = []
        for name, path in operator_sets.items():
            registry = OperatorRegistry.from_jsonl(path)
            owned = sorted(op.func_id for op in registry if op.definition is not None
                           and (options.max_layer is None or (op.recursive_layer or 0) <= options.max_layer))
            splits.append(_Split(name, Path(path), registry, owned))
        return splits
    if len(operator_sets) != 1:
        raise ValueError(f"--split {options.split} reads one operator set; use --split set for several")
    (name, path), = operator_sets.items()
    registry = OperatorRegistry.from_jsonl(path)
    if options.split == "none":
        owned = sorted(op.func_id for op in registry if op.definition is not None
                       and (options.max_layer is None or (op.recursive_layer or 0) <= options.max_layer))
        return [_Split(name, Path(path), registry, owned)]
    assignment = split_operators(registry, options.split_ratios, options.seed, options.max_layer)
    return [_Split(split, Path(path), registry, owned) for split, owned in assignment.items()]


def build_corpus(settings: Settings, operator_sets: dict[str, Path], options: CorpusOptions, out: Path,
                 workers: int = 1) -> dict:
    """Write the corpus to ``out`` and return its manifest."""
    if workers < 1:
        raise ValueError("workers must be at least 1")
    splits = resolve_splits(settings, operator_sets, options)
    missing = [s.name for s in splits if s.name not in options.documents]
    if missing:
        raise ValueError(f"no document count for split(s) {missing}; give --documents N or NAME=N,...")
    unknown = sorted(set(options.documents) - {s.name for s in splits})
    if unknown:
        raise ValueError(f"document counts for unknown split(s) {unknown}")
    plans = {s.name: kind_counts(options.documents[s.name], options.mix) for s in splits}
    for split in splits:
        if not split.owned and options.documents[split.name] > 0:
            raise ValueError(f"split {split.name!r} has no defined operators")

    generators = {s.name: SplitGenerator(s.name, settings, s.registry, s.owned, options) for s in splits}
    for split in splits:
        generators[split.name].prepare([k for k in GENERATED if plans[split.name][k] > 0])
    state = CorpusState(generators)
    tokenizer = load_tokenizer(options.tokenizer)
    if options.tokenizer and tokenizer is None:
        logger.warning("transformers is not importable: probe spans and token counts use characters only")

    _prepare_output(out)
    split_reports: dict[str, dict] = {}
    with tempfile.TemporaryDirectory(prefix=".dedup-", dir=out) as temp_dir:
        seen_texts = ExactDeduper(Path(temp_dir) / "seen.sqlite") if options.dedup else None
        try:
            with BlockPool(state, workers) as pool:
                for split in splits:
                    split_reports[split.name] = _write_split(split, generators[split.name], plans[split.name], options,
                                                             pool, out, seen_texts, tokenizer)
        finally:
            if seen_texts is not None:
                seen_texts.close()

    _check_held_out(splits, options)
    splits_file = {s.name: marked({"owned": s.owned, "mentioned": sorted(s.mentioned)}) for s in splits}
    (out / "splits.json").write_text(json.dumps(splits_file, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    manifest = _manifest(settings, splits, options, split_reports, tokenizer)
    manifest["meta"] = {"canary": CANARY}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def _prepare_output(out: Path) -> None:
    """An empty directory, or one holding an earlier corpus, whose files are removed first."""
    out.mkdir(parents=True, exist_ok=True)
    existing = [p for p in out.rglob("*") if p.is_file()]
    if not existing:
        return
    if not (out / "manifest.json").is_file():
        raise ValueError(f"{out} is not empty and holds no corpus; choose a new output directory")
    for path in existing:
        if path.suffix == ".jsonl" or path.name in ("manifest.json", "splits.json"):
            path.unlink()


def _write_split(split: _Split, generator: SplitGenerator, plan: dict[str, int], options: CorpusOptions,
                 pool: BlockPool, out: Path, seen_texts: ExactDeduper | None, tokenizer) -> dict:
    streams: dict[str, _KindStream] = {}
    for kind in KINDS:
        if plan[kind] == 0:
            continue
        if kind in GENERATED:
            tasks = ((split.name, kind, block, options.block_size, block * options.block_size)
                     for block in counter())
            source = _flatten(Prefetch(pool, tasks))
        else:
            source = generator.static_documents(kind).__next__
        streams[kind] = _KindStream(kind, plan[kind], source, limit=4 * plan[kind] + 100)
    labels = [kind for kind in KINDS for _ in range(plan[kind])]
    random.Random(block_seed(options.seed, split.name, "order")).shuffle(labels)

    writer = ShardWriter(out / split.name, split.name, options.shard_size, out)
    probe_writer = ShardWriter(out / "probe", split.name, options.shard_size, out) if options.probe else None
    position = 0
    for kind in labels:
        stream = streams[kind]
        document = stream.next_unique(seen_texts)
        if document is None:
            continue
        stream.written += 1
        text = document["text"]
        stats = {"chars": len(text), "tokens_estimate": estimate_tokens(text)}
        if tokenizer is not None:
            stats["tokens"] = len(tokenizer(text, add_special_tokens=False)["input_ids"])
        writer.write({"text": text}, stats)
        split.mentioned.update(document["operators"])
        if probe_writer is not None and "probe" in document:
            probe = dict(document["probe"], id=position)
            probe_writer.write(probe, {"chars": len(text), "tokens_estimate": stats["tokens_estimate"]})
        position += 1
    shards = writer.close()
    probe_shards = probe_writer.close() if probe_writer is not None else []
    for stream in streams.values():
        if stream.written < stream.requested:
            logger.warning("split %s: %d of %d %s documents written (%d duplicates dropped)", split.name,
                           stream.written, stream.requested, stream.kind, stream.duplicates)
    report = {
        "operators": len(split.owned),
        "operators_mentioned": len(split.mentioned),
        "documents": sum(s["documents"] for s in shards),
        "chars": sum(s["chars"] for s in shards),
        "bytes": sum(s["bytes"] for s in shards),
        "tokens_estimate": sum(s["tokens_estimate"] for s in shards),
        "kinds": {k: {"requested": s.requested, "written": s.written, "duplicates_dropped": s.duplicates}
                  for k, s in streams.items()},
        "shards": shards,
    }
    if tokenizer is not None:
        report["tokens"] = sum(s.get("tokens", 0) for s in shards)
    if options.probe:
        report["probe"] = {"records": sum(s["documents"] for s in probe_shards), "shards": probe_shards}
    return report


def _flatten(prefetch: Prefetch):
    buffer: list = []

    def next_document():
        while not buffer:
            buffer.extend(reversed(prefetch.next()))
        return buffer.pop()

    return next_document


def _check_held_out(splits: list[_Split], options: CorpusOptions) -> None:
    """With --split operator, no held-out operator may appear in another split's documents."""
    if options.split != "operator":
        return
    for held in splits[1:]:
        for other in splits:
            if other is held:
                continue
            leaked = set(held.owned) & other.mentioned
            if leaked:
                raise AssertionError(f"operators of split {held.name!r} appear in split {other.name!r}: "
                                     f"{sorted(leaked)[:5]}")


def _manifest(settings: Settings, splits: list[_Split], options: CorpusOptions, reports: dict,
              tokenizer) -> dict:
    sets = {}
    for split in splits:
        prov = provenance(settings, split.registry, options.seed)
        sets.setdefault(str(split.path), {"operator_set": operator_set_hash(split.registry),
                                          "operators": len(split.registry),
                                          "defined_operators": sum(op.definition is not None for op in split.registry),
                                          "settings": prov["config"], "semantics": prov["semantics"],
                                          "opulse": prov["opulse"]})
    totals = {key: sum(r[key] for r in reports.values()) for key in ("documents", "chars", "bytes",
                                                                       "tokens_estimate")}
    if tokenizer is not None:
        totals["tokens"] = sum(r["tokens"] for r in reports.values())
    overlap = {}
    for split in splits:
        others = set().union(*(set(s.owned) for s in splits if s is not split)) if len(splits) > 1 else set()
        overlap[split.name] = len(split.mentioned & others)
    return {
        "format": MANIFEST_FORMAT,
        "seed": options.seed,
        "config_hash": options.config_hash(),
        "options": options.to_dict(),
        "operator_sets": sets,
        "splits": {split.name: dict(reports[split.name], operator_set=operator_set_hash(split.registry),
                                    mentions_of_other_splits=overlap[split.name])
                   for split in splits},
        "totals": totals,
        "token_estimate_rule": "ASCII characters / 4 + one token per non-ASCII character",
        "tokenizer": options.tokenizer if tokenizer is not None else None,
    }
