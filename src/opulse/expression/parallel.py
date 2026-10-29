"""Deterministic parallel generation in fixed-size blocks.

Records are produced in *blocks* of ``block_size`` records. Block ``k`` is generated from its
own seed, :func:`block_seed` ``(seed, k)``, by one worker, and blocks are written in the order
of ``k``. The output therefore depends on the seed and the block size only: one worker and
``N`` workers write the same bytes. Every record is still verified by the reference oracle
in the worker that produces it, before the block is returned.

Workers are processes. On platforms with ``fork`` the parent builds the generation state once
and the workers inherit it; elsewhere each worker builds it from a picklable description.
"""

from __future__ import annotations

import hashlib
import json
import multiprocessing
import random
from collections import deque
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

from opulse.config import Settings
from opulse.core.registry import OperatorRegistry

_STATE = None  # the generation state of a worker process


def block_seed(*parts) -> int:
    """A 64-bit seed for one block, derived from the run seed and the block's coordinates."""
    text = "opulse-block:" + ":".join(str(part) for part in parts)
    return int(hashlib.sha256(text.encode()).hexdigest()[:16], 16)


def _init_worker(state) -> None:
    global _STATE
    _STATE = state


def _run_task(task):
    return _STATE.run(task)


class BlockPool:
    """Runs ``state.run(task)`` for a stream of tasks and returns results in task order.

    ``workers <= 1`` runs every task in the calling process. Otherwise at most ``window``
    tasks per worker are outstanding, so an unbounded task stream needs bounded memory.
    """

    def __init__(self, state, workers: int = 1, window: int = 4) -> None:
        self.state = state
        self.workers = max(1, int(workers))
        self.window = max(1, window) * self.workers
        self._pool = None

    def __enter__(self) -> BlockPool:  # noqa: PYI034
        if self.workers > 1:
            methods = multiprocessing.get_all_start_methods()
            if "fork" in methods:
                global _STATE
                _STATE = self.state  # inherited by the forked workers
                context = multiprocessing.get_context("fork")
                self._pool = context.Pool(self.workers)
            else:
                context = multiprocessing.get_context("spawn")
                self._pool = context.Pool(self.workers, initializer=_init_worker, initargs=(self.state,))
        return self

    def __exit__(self, *exc) -> None:
        if self._pool is not None:
            # Every result the caller needed has been received; prefetched blocks are dropped.
            self._pool.terminate()
            self._pool.join()
            self._pool = None

    def map(self, tasks: Iterable) -> Iterator:
        """Results of ``tasks`` in order; tasks are submitted lazily."""
        if self._pool is None:
            for task in tasks:
                yield self.state.run(task)
            return
        pending: deque = deque()
        iterator = iter(tasks)
        exhausted = False
        while True:
            while not exhausted and len(pending) < self.window:
                try:
                    task = next(iterator)
                except StopIteration:
                    exhausted = True
                    break
                pending.append(self._pool.apply_async(_run_task, (task,)))
            if not pending:
                return
            yield pending.popleft().get()


class Prefetch:
    """An ordered stream over a :class:`BlockPool` that several consumers can interleave.

    ``tasks`` may be infinite; up to ``window`` results are requested ahead of consumption.
    """

    def __init__(self, pool: BlockPool, tasks: Iterable, window: int | None = None) -> None:
        self.pool = pool
        self.tasks = iter(tasks)
        self.window = window or (2 * pool.workers)
        self.pending: deque = deque()

    def _fill(self) -> None:
        while len(self.pending) < self.window:
            try:
                task = next(self.tasks)
            except StopIteration:
                return
            if self.pool._pool is None:
                self.pending.append(_Ready(self.pool.state.run(task)))
                return  # in-process: compute only what is consumed
            self.pending.append(self.pool._pool.apply_async(_run_task, (task,)))

    def next(self):
        self._fill()
        if not self.pending:
            raise StopIteration
        return self.pending.popleft().get()


@dataclass
class _Ready:
    value: object

    def get(self):
        return self.value


# ---------------------------------------------------------------------- expressions
@dataclass
class ExpressionJob:
    """What ``opulse expressions --workers`` needs to rebuild its dataset in a worker."""

    settings: Settings
    operators: Path
    seed: int
    block_size: int
    dataset_options: dict = field(default_factory=dict)
    cython_build_dir: Path | None = None
    _dataset: object = field(default=None, repr=False)

    def __getstate__(self):  # a spawned worker rebuilds the dataset
        state = dict(self.__dict__)
        state["_dataset"] = None
        return state

    def dataset(self):
        if self._dataset is None:
            from opulse.expression.dataset import ExpressionDataset

            registry = OperatorRegistry.from_jsonl(self.operators)
            runtime = build_runtime(registry, self.settings, self.cython_build_dir)
            self._dataset = ExpressionDataset(self.settings, registry, runtime, random.Random(self.seed),
                                              seed=self.seed, **self.dataset_options)
            self._dataset.provenance["block_size"] = self.block_size
        return self._dataset

    def run(self, task) -> str:
        """Block ``index`` of ``count`` records, as JSON lines."""
        index, count = task
        dataset = self.dataset()
        dataset.rng.seed(block_seed(self.seed, index))
        records = dataset.records(count, start_id=index * self.block_size)
        return "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records)


def build_runtime(registry: OperatorRegistry, settings: Settings, cython_build_dir: Path | None = None):
    semantics = settings.semantics.build()
    if cython_build_dir:
        from opulse.runtime.cython_backend import CythonRuntime

        return CythonRuntime(registry, cython_build_dir, semantics)
    from opulse.runtime import PythonRuntime

    return PythonRuntime(registry, semantics)


def block_tasks(count: int, block_size: int) -> list[tuple[int, int]]:
    """``(block index, records in the block)`` covering ``count`` records."""
    if block_size < 1:
        raise ValueError("block size must be at least 1")
    return [(index, min(block_size, count - index * block_size))
            for index in range((count + block_size - 1) // block_size)]


def write_expressions(job: ExpressionJob, count: int, out: Path, workers: int,
                      progress: Callable[[int], None] | None = None) -> int:
    """Write ``count`` records to ``out`` with ``workers`` processes; returns the number written."""
    job.dataset()  # build once in the parent: forked workers inherit it
    written = 0
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as handle, BlockPool(job, workers) as pool:
        for (index, size), lines in zip(block_tasks(count, job.block_size),
                                        pool.map(block_tasks(count, job.block_size))):
            handle.write(lines)
            written += size
            if progress is not None:
                progress(written)
    return written
