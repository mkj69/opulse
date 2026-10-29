"""The text environment interface shared by every Opulse environment.

An environment is driven by two calls:

* ``reset(seed)`` starts an episode and returns the first observation (text);
* ``step(action)`` takes the agent's action (text) and returns
  ``(observation, reward, done, info)``.

The same seed and the same actions always give the same observations and
rewards. Every episode is recorded; :meth:`TextEnv.transcript` returns it as a
JSON-ready dict that :mod:`opulse.env.replay` can replay and score again.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from opulse.core.registry import OperatorRegistry

# A line that starts with an action keyword; markdown decoration before it is ignored.
_ACTION_LINE = re.compile(r"^[\s*_>#`]*([A-Za-z]+)\b(.*)$")


class EnvError(RuntimeError):
    """The environment was used out of order (for example ``step`` before ``reset``)."""


@dataclass
class Action:
    keyword: str  # upper case, e.g. "QUERY"
    argument: str  # the rest of the action, stripped


def parse_action(text: str, keywords: tuple[str, ...]) -> Action | None:
    """The last line of ``text`` that starts with one of ``keywords`` (any case).

    Text before that line (reasoning) is ignored. When the keyword stands alone on
    its line, the following non-empty lines are its argument, so
    ``SUBMIT`` followed by a definition on the next line is accepted.
    """
    lines = (text or "").replace("\r", "").split("\n")
    end = text.rfind("</think>") if text else -1
    if end >= 0:
        lines = text[end + len("</think>"):].split("\n")
    for index in range(len(lines) - 1, -1, -1):
        match = _ACTION_LINE.match(lines[index])
        if match is None or match.group(1).upper() not in keywords:
            continue
        argument = match.group(2).strip().strip("*_:`").strip()  # markdown such as **SUBMIT**:
        if not argument:
            argument = " ".join(line.strip() for line in lines[index + 1:] if line.strip())
        return Action(match.group(1).upper(), argument.strip().strip("`").strip())
    return None


def registry_fingerprint(registry: OperatorRegistry) -> str:
    """A short hash of an operator set (symbols, shapes and definitions), stored in transcripts."""
    digest = hashlib.sha256()
    for op in registry:
        digest.update(f"{op.func_id}\t{op.symbol}\t{op.n_ary}\t{op.unary_position}\t{op.definition}\n".encode())
    return digest.hexdigest()[:16]


@dataclass
class Episode:
    """The record of one episode."""

    env: str
    seed: int
    config: dict
    operators_fingerprint: str
    observation: str = ""  # the first observation
    steps: list[dict] = field(default_factory=list)
    reward: float = 0.0  # sum of the step rewards
    done: bool = False
    info: dict = field(default_factory=dict)  # what the agent does not see (the answer, statistics)

    def to_dict(self) -> dict:
        return {"env": self.env, "seed": self.seed, "config": self.config,
                "operators_fingerprint": self.operators_fingerprint, "observation": self.observation,
                "steps": self.steps, "reward": self.reward, "done": self.done, "info": self.info}


class TextEnv:
    """Base class: turn budget, episode bookkeeping and the transcript."""

    name = "text"

    def __init__(self, registry: OperatorRegistry, turn_budget: int) -> None:
        if turn_budget < 1:
            raise ValueError("turn_budget must be at least 1")
        self.registry = registry
        self.turn_budget = turn_budget
        self._episode: Episode | None = None
        self._fingerprint = registry_fingerprint(registry)

    # ------------------------------------------------------------------ API
    def config(self) -> dict:
        """The options that, with the operator set and a seed, define an episode."""
        raise NotImplementedError

    def reset(self, seed: int = 0) -> str:
        self._episode = Episode(self.name, int(seed), self.config(), self._fingerprint)
        observation = self._start(int(seed))
        self._episode.observation = observation
        return observation

    def step(self, action: str) -> tuple[str, float, bool, dict]:
        episode = self._episode
        if episode is None:
            raise EnvError("call reset() before step()")
        if episode.done:
            raise EnvError("the episode is over; call reset()")
        observation, reward, done, info = self._act(action)
        turns_used = len(episode.steps) + 1
        if not done and turns_used >= self.turn_budget:
            done = True
            observation += "\nNo turns left. The episode is over."
            info["end"] = "turn budget"
        info["turns_used"] = turns_used
        episode.steps.append({"turn": turns_used, "action": action, "observation": observation,
                              "reward": reward, "done": done, "info": info})
        episode.reward += reward
        episode.done = done
        if done:
            episode.info.update(self._summary())
        return observation, reward, done, info

    def transcript(self) -> dict:
        if self._episode is None:
            raise EnvError("no episode yet")
        return self._episode.to_dict()

    @property
    def turns_left(self) -> int:
        return self.turn_budget - (len(self._episode.steps) if self._episode else 0)

    # ------------------------------------------------------------ subclasses
    def _start(self, seed: int) -> str:
        raise NotImplementedError

    def _act(self, action: str) -> tuple[str, float, bool, dict]:
        raise NotImplementedError

    def _summary(self) -> dict:
        return {}
