"""Adaptive curriculum selection and transcript metadata."""

import json

import pytest

from examples.curriculum.adapters import next_trl_row, next_verl_row, observe_reward
from examples.trl_multiturn.environment import OpulseGRPOEnv
from examples.verl_multiturn.interaction import TextInteraction
from opulse.cli.main import main
from opulse.env.curriculum import CurriculumEnv, CurriculumSampler, DifficultyCell


def _line(*, seed=7, outcomes=(True, False, True, False, True, True)):
    cells = [DifficultyCell(definitions_needed=n) for n in (1, 2, 3)]
    sampler = CurriculumSampler(lambda cell, task_seed: (cell, task_seed), cells,
                                seed=seed, window=4, min_observations=2)
    draws = []
    for outcome in outcomes:
        choice, task = sampler.sample()
        draws.append((choice, task))
        sampler.observe(outcome, choice=choice)
    return sampler, draws


def test_determinism_and_replay():
    first, draws = _line()
    second, other_draws = _line()
    assert draws == other_draws
    assert first.log == second.log
    fresh = CurriculumSampler(lambda cell, seed: None,
                              [DifficultyCell(definitions_needed=n) for n in (1, 2, 3)],
                              seed=7, window=4, min_observations=2)
    assert fresh.replay(json.loads(json.dumps(first.log)))
    assert fresh.log == first.log
    changed = json.loads(json.dumps(first.log))
    changed[1]["seed"] += 1
    fresh2 = CurriculumSampler(lambda cell, seed: None,
                               [DifficultyCell(definitions_needed=n) for n in (1, 2, 3)],
                               seed=7, window=4, min_observations=2)
    assert not fresh2.replay(changed)


def test_band_tracking_and_one_axis_expansion():
    start = DifficultyCell()
    definitions = DifficultyCell(definitions_needed=2)
    layer = DifficultyCell(operator_layer=2)
    diagonal = DifficultyCell(definitions_needed=2, operator_layer=2)
    sampler = CurriculumSampler(lambda cell, seed: cell, [start, definitions, layer, diagonal],
                                seed=2, window=4, min_observations=2)
    for _ in range(2):
        choice, _ = sampler.sample()
        assert choice.cell == start
        sampler.observe(True)
    assert sampler._available == {start, definitions, layer}
    for _ in range(20):
        choice, _ = sampler.sample()
        if choice.cell == definitions:
            sampler.observe(True)
        elif choice.cell == layer:
            sampler.observe(False)
        else:
            sampler.observe(True)
    assert diagonal in sampler._available
    assert sampler.rate(layer) == 0

    band = CurriculumSampler(lambda cell, seed: cell, [start, definitions],
                             seed=0, window=4, min_observations=2)
    for result in (True, True):
        choice, _ = band.sample()
        assert choice.cell == start
        band.observe(result)
    for result in (True, False):
        choice, _ = band.sample()
        assert choice.cell == definitions
        band.observe(result)
    for _ in range(4):
        choice, _ = band.sample()
        assert choice.cell == definitions
        band.observe(band.rate(definitions) <= 0.5)


def test_recursion_axis_expands_together():
    plain = DifficultyCell()
    recursive = DifficultyCell(recursion_allowed=True, recursion_bound=2)
    harder = DifficultyCell(recursion_allowed=True, recursion_bound=4)
    sampler = CurriculumSampler(lambda cell, seed: cell, [plain, recursive, harder],
                                min_observations=1, seed=1)
    for expected in (plain, recursive, harder):
        choice, _ = sampler.sample()
        assert choice.cell == expected
        sampler.observe(True)


class _TextTask:
    def __init__(self, cell):
        self.cell = cell
        self.seed = None
        self.reward = 0

    def reset(self, seed):
        self.seed = seed
        return "question"

    def step(self, action):
        self.reward = float(action == "correct")
        return "done", self.reward, True, {"answer": action}

    def transcript(self):
        return {"seed": self.seed, "reward": self.reward}


def test_environment_logs_cell_and_outcome():
    cell = DifficultyCell()
    env = CurriculumEnv(lambda chosen, seed: _TextTask(chosen), [cell], seed=3)
    assert env.reset() == "question"
    _, reward, done, info = env.step("correct")
    assert (reward, done) == (1.0, True)
    assert info["difficulty_cell"] == cell.to_dict()
    transcript = env.transcript()
    assert transcript["difficulty_cell"] == cell.to_dict()
    assert transcript["curriculum"]["success"] is True
    replay = CurriculumSampler(lambda c, s: None, [cell], seed=3)
    assert replay.replay(env.sampler.log)
    assert transcript["reward"] == 1.0


def test_multiturn_example_bridges_accept_wrapper():
    cell = DifficultyCell()

    def factory():
        return CurriculumEnv(lambda chosen, seed: _TextTask(chosen), [cell], seed=4)

    verl = TextInteraction(factory)
    assert verl.start_interaction(8) == "question"
    assert verl.generate_response("correct")[2] == 1.0
    assert verl.calculate_score() == 1.0
    trl = OpulseGRPOEnv(factory, iter([8]))
    assert trl.reset() == "question"
    assert "done" in trl.act("correct")
    assert trl.get_reward() == 1.0


def test_bench_tasks_and_rl_adapters():
    task = {"id": "one", "family": "compute", "prompt": "What is 1?", "answer": 1,
            "axes": {"definitions_needed": 2, "max_layer": 3, "expression_depth": 2,
                     "recursive_definitions": 1, "recursion_bound": 4, "branch_definitions": 1}}
    sampler = CurriculumSampler.from_tasks([task], seed=9, min_observations=1)
    choice, verl = next_verl_row(sampler)
    assert verl["extra_info"]["difficulty_cell"]["recursion_bound"] == 4
    observe_reward(sampler, choice, 1.0)
    choice, trl = next_trl_row(sampler)
    assert trl["difficulty_cell"] == choice.cell.to_dict()
    assert json.loads(trl["ground_truth"])["answer"] == 1
    observe_reward(sampler, choice, 0.0)


def test_cli_simulation(tmp_path, capsys):
    from opulse.canary import CANARY

    path = tmp_path / "curriculum.jsonl"
    assert main(["env", "curriculum", "--simulate", "--episodes", "300", "--seed", "3",
                 "--log", str(path)]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["replay_match"]
    assert 0.4 <= summary["tail_expected_success"] <= 0.7
    assert len(path.read_text().splitlines()) == 300
    assert all(json.loads(line)["meta"]["canary"] == CANARY for line in path.read_text().splitlines())


def test_invalid_cells():
    with pytest.raises(ValueError):
        DifficultyCell(recursion_bound=3)
