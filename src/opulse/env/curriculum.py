"""Seeded curriculum selection for text episodes and benchmark task pools."""

from __future__ import annotations

import random
from collections import defaultdict, deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any

from opulse.env.base import EnvError


@dataclass(frozen=True, order=True)
class DifficultyCell:
    """Structural task axes. Zero means that an axis is absent or disabled."""

    definitions_needed: int = 1
    operator_layer: int = 1
    expression_depth: int = 1
    recursion_allowed: bool = False
    recursion_bound: int = 0
    branches: int = 0

    def __post_init__(self) -> None:
        values = asdict(self)
        if any(isinstance(value, bool) or value < 0 for key, value in values.items()
               if key != "recursion_allowed"):
            raise ValueError("difficulty axes must be nonnegative integers")
        if not self.recursion_allowed and self.recursion_bound:
            raise ValueError("recursion_bound requires recursion_allowed")

    @classmethod
    def from_task(cls, task: Mapping[str, Any], *, recursion_bound: int = 0) -> DifficultyCell:
        """Read measured bench axes; a generation bound may be supplied for older tasks."""
        axes = task["axes"]
        recursive = bool(axes.get("recursive_definitions", 0))
        bound = int(axes.get("recursion_bound", recursion_bound)) if recursive else 0
        return cls(int(axes["definitions_needed"]), int(axes["max_layer"]),
                   int(axes["expression_depth"]), recursive, bound,
                   int(axes.get("branches", axes.get("branch_definitions", 0))))

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CurriculumChoice:
    cell: DifficultyCell
    seed: int
    index: int

    def to_dict(self) -> dict:
        return {"cell": self.cell.to_dict(), "seed": self.seed, "index": self.index}


class CurriculumSampler:
    """Choose cells using recent binary outcomes, then draw a task from that cell.

    ``tasks`` may be a mapping of cells to nonempty task sequences, or a callable
    ``(cell, seed) -> task`` with an explicit ``cells`` sequence. Only one choice
    may be outstanding. Record its outcome before requesting the next one.
    """

    def __init__(self, tasks: Mapping[DifficultyCell, Sequence] | Callable[[DifficultyCell, int], Any],
                 cells: Sequence[DifficultyCell] | None = None, *, seed: int = 0,
                 target_band: tuple[float, float] = (0.4, 0.7), window: int = 20,
                 min_observations: int = 5) -> None:
        if not 0 <= target_band[0] < target_band[1] <= 1:
            raise ValueError("target_band must satisfy 0 <= low < high <= 1")
        if window < 1 or not 1 <= min_observations <= window:
            raise ValueError("window must be positive and contain min_observations")
        if callable(tasks):
            if not cells:
                raise ValueError("callable task sources require cells")
            self._source = tasks
        else:
            pools = {cell: tuple(pool) for cell, pool in tasks.items()}
            if not pools or any(not pool for pool in pools.values()):
                raise ValueError("task pools must be nonempty")
            if cells is not None and set(cells) != set(pools):
                raise ValueError("cells must match task pool keys")
            cells = tuple(pools)
            self._source = lambda cell, draw_seed: pools[cell][draw_seed % len(pools[cell])]
        self.cells = tuple(sorted(set(cells)))
        if not self.cells:
            raise ValueError("at least one difficulty cell is required")
        self.seed = int(seed)
        self.target_band = (float(target_band[0]), float(target_band[1]))
        self.window = window
        self.min_observations = min_observations
        self._rng = random.Random(seed)
        self._history = {cell: deque(maxlen=window) for cell in self.cells}
        self._available = {self.cells[0]}
        self._neighbor_cache: dict[DifficultyCell, tuple[DifficultyCell, ...]] = {}
        self._pending: CurriculumChoice | None = None
        self.log: list[dict] = []

    @classmethod
    def from_tasks(cls, tasks: Sequence[Mapping[str, Any] | Any], *, recursion_bound: int = 0,
                   **options) -> CurriculumSampler:
        """Group existing bench JSONL records by their measured structural axes."""
        pools: dict[DifficultyCell, list] = defaultdict(list)
        for task in tasks:
            record = task.to_dict() if hasattr(task, "to_dict") else task
            pools[DifficultyCell.from_task(record, recursion_bound=recursion_bound)].append(record)
        return cls(pools, **options)

    def rate(self, cell: DifficultyCell) -> float | None:
        outcomes = self._history[cell]
        return sum(outcomes) / len(outcomes) if outcomes else None

    def _neighbors(self, cell: DifficultyCell) -> list[DifficultyCell]:
        """Find immediate outward neighbors in the supplied cell lattice."""
        if cell in self._neighbor_cache:
            return list(self._neighbor_cache[cell])
        fields = ("definitions_needed", "operator_layer", "expression_depth", "branches")
        neighbors = []
        for axis in fields:
            higher = [other for other in self.cells if all(
                getattr(other, name) == getattr(cell, name) for name in fields if name != axis)
                and other.recursion_allowed == cell.recursion_allowed
                and other.recursion_bound == cell.recursion_bound
                and getattr(other, axis) > getattr(cell, axis)]
            if higher:
                neighbors.append(min(higher, key=lambda other: getattr(other, axis)))
        if not cell.recursion_allowed:
            recursive = [other for other in self.cells if other.recursion_allowed
                         and all(getattr(other, name) == getattr(cell, name) for name in fields)]
        else:
            recursive = [other for other in self.cells if other.recursion_allowed
                         and other.recursion_bound > cell.recursion_bound
                         and all(getattr(other, name) == getattr(cell, name) for name in fields)]
        if recursive:
            neighbors.append(min(recursive, key=lambda other: other.recursion_bound))
        self._neighbor_cache[cell] = tuple(neighbors)
        return neighbors

    def _expand(self) -> None:
        for cell in sorted(self._available):
            outcomes = self._history[cell]
            if len(outcomes) >= self.min_observations and self.rate(cell) > self.target_band[1]:
                self._available.update(self._neighbors(cell))

    def choose(self) -> CurriculumChoice:
        """Reserve a cell and a source seed without drawing the task yet."""
        if self._pending is not None:
            raise EnvError("record the pending curriculum outcome before choosing again")
        self._expand()
        low, high = self.target_band
        sampled = [cell for cell in self._available if len(self._history[cell]) < self.min_observations]
        band = [cell for cell in self._available if self.rate(cell) is not None
                and low <= self.rate(cell) <= high]
        if band:
            candidates = band
        elif sampled:
            candidates = sampled
        else:
            unmastered = [cell for cell in self._available if self.rate(cell) <= high]
            candidates = unmastered or list(self._available)
        cell = self._rng.choice(sorted(candidates))
        choice = CurriculumChoice(cell, self._rng.randrange(2**63), len(self.log))
        self._pending = choice
        return choice

    def task(self, choice: CurriculumChoice) -> Any:
        if choice != self._pending:
            raise EnvError("choice is not pending")
        return self._source(choice.cell, choice.seed)

    def sample(self) -> tuple[CurriculumChoice, Any]:
        choice = self.choose()
        try:
            return choice, self.task(choice)
        except Exception:
            self._pending = None
            raise

    def observe(self, success: bool, *, choice: CurriculumChoice | None = None) -> dict:
        if self._pending is None or (choice is not None and choice != self._pending):
            raise EnvError("no matching curriculum choice is pending")
        if not isinstance(success, bool):
            raise TypeError("success must be a boolean")
        selected = self._pending
        self._history[selected.cell].append(success)
        event = {**selected.to_dict(), "success": success}
        self.log.append(event)
        self._pending = None
        self._expand()
        return event

    def replay(self, log: Sequence[Mapping[str, Any]]) -> bool:
        """Reproduce cell and seed choices from a fresh sampler and recorded outcomes."""
        if self.log or self._pending is not None:
            raise EnvError("replay requires a fresh sampler")
        for event in log:
            choice = self.choose()
            if choice.to_dict() != {key: event[key] for key in ("cell", "seed", "index")}:
                return False
            self.observe(event["success"], choice=choice)
        return True


class CurriculumEnv:
    """Wrap a cell-aware factory of TextEnv-like tasks with one shared curriculum."""

    name = "curriculum"

    def __init__(self, source: Callable[[DifficultyCell, int], Any], cells: Sequence[DifficultyCell],
                 *, seed: int = 0, target_band: tuple[float, float] = (0.4, 0.7),
                 window: int = 20, min_observations: int = 5,
                 success: Callable[[dict], bool] | None = None) -> None:
        self.sampler = CurriculumSampler(source, cells, seed=seed, target_band=target_band,
                                         window=window, min_observations=min_observations)
        self._success = success or (lambda transcript: transcript["reward"] > 0)
        self._env = None
        self._choice: CurriculumChoice | None = None
        self._event: dict | None = None
        self._episode_seed: int | None = None

    def reset(self, seed: int | None = None) -> str:
        if self._choice is not None and self._event is None:
            raise EnvError("finish the current curriculum episode before reset")
        choice, env = self.sampler.sample()
        self._choice, self._env, self._event = choice, env, None
        self._episode_seed = choice.seed if seed is None else int(seed)
        try:
            return env.reset(self._episode_seed)
        except Exception:
            self.sampler._pending = None
            self._choice = None
            raise

    def step(self, action: str) -> tuple[str, float, bool, dict]:
        if self._env is None or self._choice is None:
            raise EnvError("call reset() before step()")
        if self._event is not None:
            raise EnvError("the episode is over; call reset()")
        observation, reward, done, info = self._env.step(action)
        info = {**info, "difficulty_cell": self._choice.cell.to_dict()}
        if done:
            self._event = self.sampler.observe(bool(self._success(self._env.transcript())),
                                               choice=self._choice)
        return observation, reward, done, info

    def transcript(self) -> dict:
        if self._env is None or self._choice is None:
            raise EnvError("no episode yet")
        source = self._env.transcript()
        return {"env": self.name, "difficulty_cell": self._choice.cell.to_dict(),
                "episode_seed": self._episode_seed,
                "curriculum": self._event or self._choice.to_dict(),
                "reward": source["reward"], "done": source.get("done", self._event is not None),
                "source": source}
