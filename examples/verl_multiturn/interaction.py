"""TextEnv episode lifecycle shared by the verl tool adapter.

The names mirror the older verl Interaction interface, while the tool adapter
in ``tool.py`` uses the BaseTool interface present in verl 0.9.1.
"""

from __future__ import annotations

from collections.abc import Callable

from opulse.env import TextEnv


class TextInteraction:
    """Own one deterministic environment episode."""

    def __init__(self, env_factory: Callable[[], TextEnv]) -> None:
        self.env_factory = env_factory
        self.env: TextEnv | None = None

    def start_interaction(self, seed: int) -> str:
        self.env = self.env_factory()
        return self.env.reset(seed)

    def generate_response(self, action: str) -> tuple[bool, str, float, dict]:
        if self.env is None:
            raise RuntimeError("call start_interaction before generate_response")
        observation, reward, done, info = self.env.step(action)
        return done, observation, reward, info

    def calculate_score(self) -> float:
        if self.env is None:
            raise RuntimeError("call start_interaction before calculate_score")
        return float(self.env.transcript()["reward"])

    def finalize_interaction(self) -> dict:
        if self.env is None:
            raise RuntimeError("call start_interaction before finalize_interaction")
        transcript = self.env.transcript()
        self.env = None
        return transcript
