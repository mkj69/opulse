"""Collect exact multi turn trajectories for GRPO style training.

``run_rollout`` accepts any model callable from chat messages to an action string.
``openai_chat_model`` adapts an OpenAI compatible chat endpoint. Each trajectory
contains the original prompt, model actions, per turn rewards and a replayable
Opulse transcript. No model runs when this module is imported.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from urllib.request import Request, urlopen

from opulse.env import TextEnv


def run_rollout(env: TextEnv, seed: int, model: Callable[[list[dict]], str]) -> dict:
    """Play one episode and return all model and environment turns."""
    first = env.reset(seed)
    messages = [{"role": "user", "content": first}]
    turns = []
    done = False
    while not done:
        action = model(list(messages))
        if not isinstance(action, str):
            raise TypeError("model must return an action string")
        observation, reward, done, info = env.step(action)
        turns.append({"action": action, "observation": observation, "reward": reward,
                      "done": done, "info": info})
        messages.extend([{"role": "assistant", "content": action},
                         {"role": "user", "content": observation}])
    return {"seed": seed, "prompt": [{"role": "user", "content": first}],
            "turns": turns, "turn_rewards": [turn["reward"] for turn in turns],
            "reward": env.transcript()["reward"], "messages": messages,
            "transcript": env.transcript()}


def run_group(env_factory: Callable[[], TextEnv], seed: int, model: Callable[[list[dict]], str],
              generations: int) -> list[dict]:
    """Collect several trajectories from the same seed for one GRPO group."""
    if generations < 1:
        raise ValueError("generations must be positive")
    return [run_rollout(env_factory(), seed, model) for _ in range(generations)]


def openai_chat_model(base_url: str, model: str, api_key: str = "EMPTY", *,
                      temperature: float = 0.0, max_tokens: int = 512):
    """Return a callable that sends messages to an OpenAI compatible endpoint."""
    url = base_url.rstrip("/") + "/chat/completions"

    def generate(messages: list[dict]) -> str:
        payload = json.dumps({"model": model, "messages": messages, "temperature": temperature,
                              "max_tokens": max_tokens}).encode("utf-8")
        request = Request(url, data=payload, headers={"Content-Type": "application/json",
                                                      "Authorization": f"Bearer {api_key}"})
        with urlopen(request, timeout=120) as response:
            result = json.load(response)
        return result["choices"][0]["message"]["content"]

    return generate
