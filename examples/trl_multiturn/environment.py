"""TRL 1.16.0 GRPO ``environment_factory`` adapter for Opulse."""

from __future__ import annotations

from collections.abc import Callable
from itertools import count

from opulse.env import BlackBoxEnv, SelfPlayEnv, TextEnv


class OpulseGRPOEnv:
    """One environment instance per GRPO rollout."""

    def __init__(self, env_factory: Callable[[], TextEnv], seeds) -> None:
        self._env_factory = env_factory
        self._seeds = seeds
        self._env: TextEnv | None = None
        self._done = False
        self._reward = 0.0
        self.turn_rewards: list[float] = []

    def reset(self, seed: int | None = None, **kwargs) -> str:
        """Start one episode and return its first observation."""
        self._env = self._env_factory()
        self._done = False
        self._reward = 0.0
        self.turn_rewards = []
        return self._env.reset(next(self._seeds) if seed is None else int(seed))

    def act(self, action: str) -> str:
        """Apply one action and return the next observation.

        Args:
            action: A QUERY or SUBMIT action from the Opulse instructions.

        Returns:
            The environment observation after the action.
        """
        if self._env is None:
            raise RuntimeError("call reset before act")
        if self._done:
            return "The episode is over."
        observation, reward, self._done, _ = self._env.step(action)
        self._reward += reward
        self.turn_rewards.append(reward)
        if self._done:
            observation += "\nThe episode is over. Do not call the tool again."
        return observation

    def get_reward(self) -> float:
        """Return the sum of exact environment step rewards."""
        return self._reward


def make_env_factory(operators: str, settings: str | None = None, *, env: str = "blackbox",
                     first_seed: int = 0, **options):
    """Return a no-argument factory for ``GRPOTrainer(environment_factory=...)``."""
    seeds = count(first_seed)

    def build_env() -> TextEnv:
        if env == "blackbox":
            return BlackBoxEnv.from_files(operators, settings, **options)
        if env == "selfplay":
            selfplay_options = dict(options)
            if "turn_budget" in selfplay_options:
                selfplay_options["attempts"] = selfplay_options.pop("turn_budget")
            return SelfPlayEnv.from_files(operators, settings, **selfplay_options)
        raise ValueError("env must be blackbox or selfplay")

    return lambda: OpulseGRPOEnv(build_env, seeds)
