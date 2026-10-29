"""Rebuild environments from transcripts, replay recorded actions and score episodes."""

from __future__ import annotations

import json

from opulse.config import Settings
from opulse.core.registry import OperatorRegistry
from opulse.env.base import TextEnv, registry_fingerprint
from opulse.env.blackbox import BlackBoxEnv
from opulse.env.selfplay import SelfPlay, SelfPlayEnv

ENVIRONMENTS = ("blackbox", "selfplay")


def make_env(name: str, config: dict, registry: OperatorRegistry | None = None,
             settings: Settings | None = None) -> TextEnv:
    """The environment a transcript's ``env`` and ``config`` describe.

    ``registry`` and ``settings`` override the files named in ``config``.
    """
    if name not in ENVIRONMENTS:
        raise ValueError(f"unknown environment {name!r}; choose from {ENVIRONMENTS}")
    operators, config_path = config.get("operators"), config.get("settings")
    if registry is None:
        if not operators:
            raise ValueError("the transcript names no operator file; pass the operator set")
        registry = OperatorRegistry.from_jsonl(operators)
    if settings is None:
        settings = Settings.load(config_path) if config_path else Settings()
    if name == "blackbox":
        exhaustive = {int(k): v for k, v in (config.get("exhaustive_range") or {}).items()}
        return BlackBoxEnv(registry, settings, layer=config.get("layer"), kinds=tuple(config["kinds"]),
                           query_budget=config["query_budget"], turn_budget=config["turn_budget"],
                           submissions=config["submissions"], domain=tuple(config["domain"]),
                           callees=config["callees"], shaping=config["shaping"], rlimit=config["rlimit"],
                           timeout_ms=config["timeout_ms"],
                           exhaustive_range=exhaustive, operators_path=operators, config_path=config_path)
    selfplay = SelfPlay(registry, settings, visible=config["visible"], max_layer=config.get("max_layer"),
                        questions=config["questions"], question_depth=config["question_depth"],
                        allow_nan=config["allow_nan"], operators_path=operators, config_path=config_path)
    return SelfPlayEnv(selfplay, attempts=config["attempts"])


def replay(transcript: dict, env: TextEnv | None = None, registry: OperatorRegistry | None = None,
           settings: Settings | None = None) -> dict:
    """Run the recorded actions again and compare observations and rewards.

    Returns ``{"seed", "recorded_reward", "reward", "match", "steps", "mismatch"}``; ``match`` is
    true when every observation and reward is reproduced.
    """
    env = env or make_env(transcript["env"], transcript["config"], registry, settings)
    fingerprint = registry_fingerprint(env.registry)
    result = {"env": transcript["env"], "seed": transcript["seed"], "recorded_reward": transcript.get("reward"),
              "reward": 0.0, "steps": 0, "match": True, "mismatch": None}
    if transcript.get("operators_fingerprint") not in (None, fingerprint):
        result.update(match=False, mismatch="the operator set differs from the one recorded")
    observation = env.reset(transcript["seed"])
    if observation != transcript.get("observation"):
        result.update(match=False, mismatch=result["mismatch"] or "first observation")
    done = False
    for step in transcript.get("steps", []):
        if done:
            result.update(match=False, mismatch=result["mismatch"] or f"turn {step['turn']}: episode already over")
            break
        observation, reward, done, info = env.step(step["action"])
        result["reward"] += reward
        result["steps"] += 1
        if observation != step["observation"] or reward != step["reward"] or done != step["done"] \
                or _json(info) != _json(step.get("info")):
            result.update(match=False, mismatch=result["mismatch"] or f"turn {step['turn']}")
    if transcript.get("done") is not None and done != transcript["done"]:
        result.update(match=False, mismatch=result["mismatch"] or "end of episode")
    final = env.transcript()
    if "reward" in transcript and transcript["reward"] != final["reward"]:
        result.update(match=False, mismatch=result["mismatch"] or "total reward")
    if "info" in transcript and _json(transcript["info"]) != _json(final["info"]):
        result.update(match=False, mismatch=result["mismatch"] or "episode summary")
    result["solved"] = bool(final["info"].get("solved", final["info"].get("valid", False)))
    return result


def _json(value):
    """``value`` as it reads back from a JSON transcript (tuples become lists, keys strings)."""
    return json.loads(json.dumps(value, ensure_ascii=False))


def score_transcripts(transcripts: list[dict], registry: OperatorRegistry | None = None,
                      settings: Settings | None = None) -> tuple[list[dict], dict]:
    """Replay every transcript; return per-episode results and a summary."""
    envs: dict = {}
    results = []
    for transcript in transcripts:
        key = (transcript["env"], repr(sorted(transcript["config"].items())))
        if key not in envs:
            envs[key] = make_env(transcript["env"], transcript["config"], registry, settings)
        results.append(replay(transcript, envs[key]))
    n = len(results)
    summary = {
        "episodes": n,
        "mean_reward": sum(r["reward"] for r in results) / n if n else 0.0,
        "solved": sum(r["solved"] for r in results),
        "reproduced": sum(r["match"] for r in results),
        "mean_turns": sum(r["steps"] for r in results) / n if n else 0.0,
    }
    return results, summary
