"""Optional adapter to the gymnasium API (``pip install gymnasium``).

    from opulse.env import BlackBoxEnv
    from opulse.env.gym import to_gymnasium

    env = to_gymnasium(BlackBoxEnv.from_files("ops.jsonl"))
    observation, info = env.reset(seed=3)
    observation, reward, terminated, truncated, info = env.step("QUERY 2 5")

Observations and actions are strings. ``terminated`` is true when the episode ended by a
submission; ``truncated`` is true when it ended because the turn budget ran out.
"""

from __future__ import annotations

from opulse.env.base import TextEnv

MAX_TEXT = 1_000_000


def to_gymnasium(env: TextEnv):
    """Wrap ``env`` as a ``gymnasium.Env``; raises ImportError when gymnasium is missing."""
    import gymnasium
    from gymnasium import spaces

    class OpulseTextEnv(gymnasium.Env):
        metadata = {"render_modes": []}  # noqa: RUF012 - the gymnasium convention

        def __init__(self, inner: TextEnv) -> None:
            self.inner = inner
            # Operator symbols can be any Unicode character: allow the whole Basic Multilingual Plane.
            charset = frozenset(chr(c) for c in (*range(0x20, 0xD800), *range(0xE000, 0x10000))) | {"\n", "\t"}
            self.observation_space = spaces.Text(max_length=MAX_TEXT, charset=charset)
            self.action_space = spaces.Text(max_length=MAX_TEXT, charset=charset)

        def reset(self, *, seed: int | None = None, options: dict | None = None):
            super().reset(seed=seed)
            return self.inner.reset(0 if seed is None else seed), {}

        def step(self, action: str):
            observation, reward, done, info = self.inner.step(action)
            truncated = done and info.get("end") == "turn budget"
            return observation, reward, done and not truncated, truncated, info

        def transcript(self) -> dict:
            return self.inner.transcript()

    return OpulseTextEnv(env)
