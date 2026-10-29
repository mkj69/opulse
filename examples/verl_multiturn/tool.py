"""Stateful verl 0.9.1 BaseTool adapter for Opulse text environments."""

from __future__ import annotations

from uuid import uuid4

from examples.verl_multiturn.interaction import TextInteraction
from opulse.env import BlackBoxEnv, SelfPlayEnv

try:
    from verl.tools.base_tool import BaseTool
    from verl.tools.schemas import ToolResponse
except ModuleNotFoundError as exc:  # Keep the episode adapter importable without verl.
    if exc.name != "verl":
        raise
    BaseTool = object

    class ToolResponse:
        def __init__(self, text: str = "") -> None:
            self.text = text


def environment(config: dict):
    """Build a fresh environment for one rollout."""
    options = dict(config.get("env_options", {}))
    operators = config["operators"]
    settings = config.get("settings")
    if config.get("env", "blackbox") == "blackbox":
        return BlackBoxEnv.from_files(operators, settings, **options)
    if config["env"] == "selfplay":
        if "turn_budget" in options:
            options["attempts"] = options.pop("turn_budget")
        return SelfPlayEnv.from_files(operators, settings, **options)
    raise ValueError("env must be blackbox or selfplay")


class OpulseStepTool(BaseTool):
    """Apply one model action to the rollout's TextEnv.

    verl 0.9.1 calls create and release around *each* tool invocation. The
    AgentData object passed to execute lasts for the full rollout, so it holds
    the episode and keeps parallel rollouts isolated.
    """

    def __init__(self, config: dict, tool_schema) -> None:
        if BaseTool is object:
            self.config = config
            self.tool_schema = tool_schema
            self.name = tool_schema["function"]["name"]
        else:
            super().__init__(config, tool_schema)

    async def create(self, instance_id: str | None = None, **kwargs) -> tuple[str, ToolResponse]:
        return instance_id or uuid4().hex, ToolResponse()

    async def execute(self, instance_id: str, parameters: dict, **kwargs) -> tuple[ToolResponse, float, dict]:
        agent_data = kwargs["agent_data"]
        interaction = getattr(agent_data, "_opulse_interaction", None)
        if interaction is None:
            seed = int(agent_data.tools_kwargs[self.name]["create_kwargs"]["seed"])
            interaction = TextInteraction(lambda: environment(self.config))
            interaction.start_interaction(seed)
            agent_data._opulse_interaction = interaction
        if getattr(agent_data, "_opulse_done", False):
            return ToolResponse(text="The episode is over."), 0.0, {"done": True}
        action = parameters.get("action", "")
        if not isinstance(action, str):
            action = str(action)
        done, observation, reward, info = interaction.generate_response(action)
        if done:
            agent_data._opulse_done = True
            observation += "\nThe episode is over. Do not call the tool again."
        return ToolResponse(text=observation), reward, {"done": done, "info": info,
                                                          "episode_reward": interaction.calculate_score()}

    async def calc_reward(self, instance_id: str, **kwargs) -> float:
        interaction = getattr(kwargs.get("agent_data"), "_opulse_interaction", None)
        return interaction.calculate_score() if interaction is not None else 0.0

    async def release(self, instance_id: str, **kwargs) -> None:
        pass
