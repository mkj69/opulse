"""Documents of a pretraining corpus, generated per split from verified records.

Four kinds:

* ``definitions``: definitions of the split's operators, one per line;
* ``values``: expressions with their values, ``expression = value``, one per line;
* ``derivations``: one expression and its verified step-by-step reduction, either as a chain
  (the expression, then one ``= expression`` line per step, all applications bracketed) or as
  the narrated solution of ``opulse expressions --cot en|zh``;
* ``descriptions``: the operator descriptions of ``opulse describe``.

Every expression value and every derivation comes from :class:`ExpressionDataset`, which checks
it against the reference interpreter before it is used.
"""

from __future__ import annotations

import copy
import dataclasses
import random

from opulse.bench.context import callees, closure
from opulse.config import Settings
from opulse.core.registry import OperatorRegistry
from opulse.core.semantics import NAN
from opulse.core.types import literal
from opulse.corpus.options import CorpusOptions
from opulse.corpus.spans import full_span
from opulse.expression.dataset import ExpressionDataset
from opulse.expression.generator import OperatorPool
from opulse.expression.nodes import from_dict
from opulse.expression.parallel import block_seed, build_runtime


def restrict_pool(pool: OperatorPool, allowed: set[str]) -> OperatorPool:
    """The pool without the defined operators outside ``allowed`` (base operations stay)."""
    changes = {}
    for f in dataclasses.fields(pool):
        value = getattr(pool, f.name)
        if isinstance(value, list):
            changes[f.name] = [op for op in value if op.definition is None or op.func_id in allowed]
    return dataclasses.replace(pool, **changes)


def _value(value):
    return None if value is NAN else value


class SplitGenerator:
    """Generates the documents of one split. Expression datasets are built on first use."""

    def __init__(self, name: str, settings: Settings, registry: OperatorRegistry, owned: list[str],
                 options: CorpusOptions) -> None:
        self.name = name
        self.settings = settings
        self.registry = registry
        self.owned = list(owned)
        self.owned_set = set(owned)
        self.options = options
        self._values = None
        self._derivations = None
        self._runtime = None
        self._tokenizer = None
        self._descriptions: dict[tuple[str, str], str] = {}
        self._order = None

    # ---------------------------------------------------------------- datasets
    def _dataset(self, cot: str) -> ExpressionDataset:
        o = self.options
        if self._runtime is None:
            self._runtime = build_runtime(self.registry, self.settings)
        dataset = ExpressionDataset(self.settings, self.registry, self._runtime, random.Random(0),
                                    max_layer=o.max_layer, keep_undefined=o.keep_undefined, cot=cot,
                                    cot_depth=o.cot_depth, cot_known_layers=o.cot_known_layers,
                                    cot_known=tuple(o.cot_known), seed=o.seed,
                                    operator_frequency=o.operator_frequency, frequency_seed=o.frequency_seed)
        base = OperatorPool.from_registry(self.registry, max_layer=o.max_layer)
        dataset.pool = restrict_pool(base, self.owned_set).with_frequency(o.operator_frequency, o.frequency_seed)
        if o.skeleton_weights:
            weights = dict(dataset.pool.weights or {op.func_id: 1.0 for op in dataset.pool.all()})
            for op in dataset.pool.all():
                if op.skeleton_id:
                    weights[op.func_id] *= o.skeleton_weights.get(op.skeleton_id, 1.0)
            dataset.pool.weights = weights
        if cot != "none":
            dataset.reducer.max_steps = o.max_steps
        return dataset

    @property
    def values_dataset(self) -> ExpressionDataset:
        if self._values is None:
            self._values = self._dataset("none")
        return self._values

    @property
    def derivations_dataset(self) -> ExpressionDataset:
        if self._derivations is None:
            style = self.options.derivation_style
            self._derivations = self._dataset("en" if style == "chain" else style)
        return self._derivations

    def prepare(self, kinds) -> None:
        """Build what the given kinds need (before worker processes are forked)."""
        if "values" in kinds:
            self.values_dataset  # noqa: B018 - built for its side effect
        if "derivations" in kinds:
            self.derivations_dataset  # noqa: B018

    def __getstate__(self):  # a spawned worker rebuilds datasets and caches
        state = dict(self.__dict__)
        state.update(_values=None, _derivations=None, _runtime=None, _tokenizer=None, _order=None)
        state.pop("_oracle", None)
        registry = copy.copy(self.registry)
        registry.__dict__ = {k: v for k, v in registry.__dict__.items()
                             if k in ("_by_id", "_by_key", "_select_cache")}
        state["registry"] = registry
        return state

    def order(self) -> dict[str, int]:
        """Position of every operator in an order where callees come first, read from the
        definitions themselves (not from stored dependency lists)."""
        if self._order is None:
            position: dict[str, int] = {}
            finished = 0
            for root in self.registry:
                if root.func_id in position:
                    continue
                position[root.func_id] = -1  # in progress: a self-call stops here
                stack = [(root, iter(callees(self.registry, root)))]
                while stack:
                    op, pending = stack[-1]
                    callee = next((c for c in pending if c.func_id not in position), None)
                    if callee is None:
                        stack.pop()
                        position[op.func_id] = finished
                        finished += 1
                    else:
                        position[callee.func_id] = -1
                        stack.append((callee, iter(callees(self.registry, callee))))
            self._order = position
        return self._order

    # ---------------------------------------------------------------- helpers
    def _mentioned(self, func_ids) -> set[str]:
        """``func_ids`` and the defined operators their definitions call."""
        found = set()
        for func_id in func_ids:
            op = self.registry.get(func_id)
            if op.definition is None:
                continue
            found.add(func_id)
            found.update(c.func_id for c in callees(self.registry, op) if c.definition is not None)
        return found

    def _prefix(self, trees) -> tuple[str, set[str]]:
        """The definitions block every tree needs (callees first), if definitions are prefixed."""
        if self.options.definitions != "prefix":
            return "", set()
        needed: dict[str, object] = {}
        for tree in trees:
            for op in closure(self.registry, tree):
                needed.setdefault(op.func_id, op)
        order = self.order()
        ops = sorted(needed.values(), key=lambda op: order[op.func_id])
        if not ops:
            return "", set()
        return "\n".join(op.definition for op in ops) + "\n\n", set(needed)

    # ---------------------------------------------------------------- documents
    def run(self, kind: str, block: int, count: int, start: int) -> list[dict]:
        seed = block_seed(self.options.seed, self.name, kind, block)
        if kind == "values":
            return [self._values_document(seed if i == 0 else None) for i in range(count)]
        if kind == "derivations":
            return [self._derivation_document(seed if i == 0 else None, start + i) for i in range(count)]
        raise ValueError(f"unknown generated kind {kind!r}")

    def _values_document(self, seed: int | None) -> dict:
        dataset = self.values_dataset
        if seed is not None:
            dataset.rng.seed(seed)
        records = list(dataset.records(self.options.expressions_per_document))
        trees = [from_dict(r["tree"], self.registry) for r in records]
        prefix, defined = self._prefix(trees)
        written = {fid for r in records for fid in r["used_operators"]
                   if self.registry.get(fid).definition is not None}
        text = prefix + "\n".join(self._value_line(r, tree) for r, tree in zip(records, trees))
        return {"text": text, "operators": sorted(written | self._mentioned(defined))}

    def _value_line(self, record: dict, tree) -> str:
        """``expression = value`` with every application bracketed (precedence is not stated anywhere
        in the corpus); numerals carry base markers only when the settings use other bases."""
        expr = self.settings.expressions
        if expr.random_numeral_base or expr.random_result_base or expr.numeral_base != 10 or expr.result_base != 10:
            return f"{self.values_dataset.marked.full(tree)} = {record['result_text']}"
        value = self.settings.symbols.nan if record["undefined"] else literal(record["result"])
        return f"{record['expression_full_brackets']} = {value}"

    def _derivation_document(self, seed: int | None, index: int) -> dict:
        dataset = self.derivations_dataset
        if seed is not None:
            dataset.rng.seed(seed)
        record = next(iter(dataset.records(1)))
        trace = dataset.last_trace
        prefix, defined = self._prefix([trace.source])
        renderer = dataset.plain
        if self.options.derivation_style == "chain":
            lines = [renderer.full(trace.source)] + [f"= {renderer.full(s.expression_after)}" for s in trace.steps]
            body = "\n".join(lines)
        else:
            body = record["cot"]
        text = prefix + body
        appearing = {s.operator.func_id for s in trace.steps if s.operator.definition is not None}
        document = {"text": text, "operators": sorted(appearing | self._mentioned(defined))}
        if self.options.probe:
            document["probe"] = self._probe(trace, text, len(prefix), body, index)
        return document

    def static_documents(self, kind: str):
        """Definition or description documents, endlessly, in passes over the split's operators.

        Each pass visits every operator once, in an order shuffled by the pass's own seed, and
        groups ``definitions_per_document`` operators per document (callees first)."""
        per = self.options.definitions_per_document
        order = self.order()
        passes = 0
        while self.owned:
            ids = sorted(self.owned)
            random.Random(block_seed(self.options.seed, self.name, kind, passes)).shuffle(ids)
            for i in range(0, len(ids), per):
                chunk = sorted(ids[i:i + per], key=order.get)
                if kind == "definitions":
                    text = "\n".join(self.registry.get(fid).definition for fid in chunk)
                else:
                    text = "\n\n".join(self.description(fid) for fid in chunk)
                yield {"text": text, "operators": sorted(self._mentioned(chunk))}
            passes += 1

    def description(self, func_id: str) -> str:
        langs = ("en", "zh") if self.options.description_lang == "both" else (self.options.description_lang,)
        return "\n".join(self._description(func_id, lang) for lang in langs)

    def _description(self, func_id: str, lang: str) -> str:
        """The description ``opulse describe`` writes, computed from the current definition (a
        stored description could name operators the definition no longer calls)."""
        key = (func_id, lang)
        if key not in self._descriptions:
            from opulse.language.describe import describe
            from opulse.verify import Oracle

            if getattr(self, "_oracle", None) is None:
                self._oracle = Oracle(self.registry, self.settings.symbols, self.settings.semantics.build())
            op = self.registry.get(func_id)
            self._descriptions[key] = describe(op, self._oracle._definition_of(op), self.registry, lang, "math")
        return self._descriptions[key]

    # ---------------------------------------------------------------- probe data
    def _probe(self, trace, text: str, offset: int, body: str, index: int) -> dict:
        """Character spans of every step's focus in ``text`` and its value by the reference interpreter."""
        dataset = self.derivations_dataset
        renderer, oracle = dataset.plain, dataset.oracle
        style = self.options.derivation_style
        locate = self._chain_locator(body) if style == "chain" else self._narration_locator(body)
        steps = []
        for step in trace.steps:
            expression_text = renderer.full(step.expression_before)
            where = locate(step.index, expression_text)
            start, end = full_span(renderer, step.expression_before, step.path, expression_text)
            value = oracle.evaluate(step.operator, step.inputs).value
            steps.append({"step": step.index, "kind": step.kind, "operator": step.operator.symbol,
                          "depth": step.depth, "start": offset + where + start, "end": offset + where + end,
                          "value": _value(value), "undefined": value is NAN})
        answer_text = renderer.full(trace.result)
        where = locate(len(trace.steps), answer_text)
        value = trace.value if trace.value is not None else NAN
        probe = {"id": index, "split": self.name, "style": style, "text": text,
                 "expression": renderer.full(trace.source), "value": _value(value), "undefined": value is NAN,
                 "steps": steps,
                 "answer": {"start": offset + where, "end": offset + where + len(answer_text),
                            "value": _value(value), "undefined": value is NAN}}
        for span in steps + [probe["answer"]]:
            if span["start"] < 0 or span["end"] > len(text):
                raise ValueError("probe span outside the text")
        if self.options.tokenizer:
            self._token_spans(probe)
        return probe

    @staticmethod
    def _chain_locator(body: str):
        """Line ``i`` holds the expression before step ``i``; the last line holds the answer."""
        starts, position = [], 0
        for line in body.split("\n"):
            starts.append(position)
            position += len(line) + 1
        lines = body.split("\n")

        def locate(index: int, expression_text: str) -> int:
            prefix = "" if index == 0 else "= "
            if lines[index] != prefix + expression_text:
                raise ValueError(f"chain line {index} does not hold the expected expression")
            return starts[index] + len(prefix)

        return locate

    @staticmethod
    def _narration_locator(body: str):
        """Paragraph ``i + 1`` quotes the expression before step ``i`` first; the last quotes the answer."""
        starts, position = [], 0
        paragraphs = body.split("\n\n")
        for paragraph in paragraphs:
            starts.append(position)
            position += len(paragraph) + 2

        def locate(index: int, expression_text: str) -> int:
            paragraph = paragraphs[index + 1]
            where = paragraph.index("`") + 1
            if paragraph[where:where + len(expression_text)] != expression_text:
                raise ValueError(f"narration paragraph {index + 1} does not quote the expected expression")
            return starts[index + 1] + where

        return locate

    def _token_spans(self, probe: dict) -> None:
        tokenizer = self.tokenizer()
        if tokenizer is None:
            return
        encoded = tokenizer(probe["text"], add_special_tokens=False, return_offsets_mapping=True)
        offsets = encoded["offset_mapping"]
        probe["tokens"] = len(offsets)
        for span in probe["steps"] + [probe["answer"]]:
            covering = [i for i, (s, e) in enumerate(offsets) if e > span["start"] and s < span["end"]]
            span["token_start"], span["token_end"] = (covering[0], covering[-1] + 1) if covering else (None, None)

    def tokenizer(self):
        if self._tokenizer is None:
            self._tokenizer = load_tokenizer(self.options.tokenizer) or False
        return self._tokenizer or None


def load_tokenizer(name: str | None):
    """A fast Hugging Face tokenizer, or None when ``transformers`` is not importable."""
    if not name:
        return None
    try:
        from transformers import AutoTokenizer
    except ImportError:
        return None
    return AutoTokenizer.from_pretrained(name, use_fast=True)
