# Curriculum adapters

`adapters.py` creates one task row at a time for the existing verl and TRL examples.
The caller grades the learner response and records the reward before drawing the next
row. The same `CurriculumSampler` instance must receive every outcome in a training
stream.

This example converts one sampled benchmark task to the verl row format and updates
the sampler after exact grading.

```python
from examples.curriculum.adapters import next_verl_row, observe_reward
from opulse.env import CurriculumSampler

sampler = CurriculumSampler.from_tasks(tasks, seed=7)
choice, row = next_verl_row(sampler)
reward = grade_verl(row, model_response)
observe_reward(sampler, choice, reward)
```

Here `tasks` contains records from `opulse bench build`, and `grade_verl` uses the
same exact reward function as `examples/verl/reward.py`.

This example builds a row with the columns expected by the TRL bridge and then
records its outcome.

```python
from examples.curriculum.adapters import next_trl_row, observe_reward

choice, row = next_trl_row(sampler)
reward = grade_trl(row, model_response)
observe_reward(sampler, choice, reward)
```

Here `grade_trl` uses a reward function from `examples/trl/bridge.py`. Both row
formats include `difficulty_cell`. The sampler log records each selected cell,
task seed, index, and success value. Replay the log with a fresh sampler initialized
from the same task records and seed.
