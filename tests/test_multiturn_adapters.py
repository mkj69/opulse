"""Multi-turn adapters preserve the text environment's exact rewards."""

import asyncio
from itertools import count
from types import SimpleNamespace

from conftest import INITIAL_OPERATORS

from examples.env.rollout import run_group, run_rollout
from examples.trl_multiturn.environment import OpulseGRPOEnv
from examples.verl_multiturn import tool as verl_tool
from examples.verl_multiturn.interaction import TextInteraction
from examples.verl_multiturn.reward import compute_score
from opulse.core import OperatorRegistry
from opulse.env import TextEnv

INITIAL = INITIAL_OPERATORS
ACTIONS = ["QUERY 2", "SUBMIT answer"]


class ScriptEnv(TextEnv):
    name = "script"

    def __init__(self):
        super().__init__(OperatorRegistry.from_jsonl(INITIAL), 2)

    def config(self):
        return {"turn_budget": 2}

    def _start(self, seed):
        return f"seed {seed}"

    def _act(self, action):
        if action == ACTIONS[0]:
            return "query result", 0.25, False, {"action": "query"}
        if action == ACTIONS[1]:
            return "accepted", 1.0, True, {"action": "submit"}
        return "invalid", 0.0, False, {"action": "invalid"}


def expected_episode():
    env = ScriptEnv()
    first = env.reset(7)
    steps = [env.step(action) for action in ACTIONS]
    return first, steps, env.transcript()


def test_interaction_drives_full_episode():
    first, steps, transcript = expected_episode()
    interaction = TextInteraction(ScriptEnv)
    assert interaction.start_interaction(7) == first
    for action, (observation, reward, done, info) in zip(ACTIONS, steps):
        assert interaction.generate_response(action) == (done, observation, reward, info)
    assert interaction.calculate_score() == transcript["reward"] == 1.25
    assert interaction.finalize_interaction() == transcript


def test_verl_tool_preserves_step_rewards(monkeypatch):
    _, steps, transcript = expected_episode()
    monkeypatch.setattr(verl_tool, "environment", lambda config: ScriptEnv())
    schema = {"function": {"name": "opulse_step"}}
    tool = verl_tool.OpulseStepTool({"operators": "unused"}, schema)
    agent_data = SimpleNamespace(tools_kwargs={"opulse_step": {"create_kwargs": {"seed": 7}}})

    async def play():
        rewards = []
        for action, expected in zip(ACTIONS, steps):
            instance_id, _ = await tool.create()
            response, reward, metadata = await tool.execute(instance_id, {"action": action}, agent_data=agent_data)
            assert response.text.startswith(expected[0])
            assert metadata["done"] == expected[2]
            rewards.append(reward)
            await tool.release(instance_id)
        return rewards

    assert asyncio.run(play()) == [step[1] for step in steps]
    assert agent_data._opulse_interaction.calculate_score() == transcript["reward"]
    assert compute_score("opulse_env", "", "", {"tool_rewards": [step[1] for step in steps]}) == 1.25


def test_trl_environment_preserves_episode_reward():
    first, steps, transcript = expected_episode()
    adapter = OpulseGRPOEnv(ScriptEnv, count(0))
    assert adapter.reset(seed=7) == first
    for action, expected in zip(ACTIONS, steps):
        assert adapter.act(action).startswith(expected[0])
    assert adapter.turn_rewards == [step[1] for step in steps]
    assert adapter.get_reward() == transcript["reward"]
    assert adapter.act("QUERY 1") == "The episode is over."
    assert adapter.get_reward() == transcript["reward"]


def test_rollout_loop_with_stub_model():
    first, steps, transcript = expected_episode()
    seen = []

    def model(messages):
        seen.append(messages)
        return ACTIONS[len(seen) - 1]

    rollout = run_rollout(ScriptEnv(), 7, model)
    assert rollout["prompt"] == [{"role": "user", "content": first}]
    assert rollout["turn_rewards"] == [step[1] for step in steps]
    assert rollout["reward"] == transcript["reward"]
    assert rollout["transcript"] == transcript
    assert seen[1][-1] == {"role": "user", "content": steps[0][0]}

    group = run_group(ScriptEnv, 7, lambda messages: ACTIONS[(len(messages) - 1) // 2], 2)
    assert [item["reward"] for item in group] == [1.25, 1.25]
