# Action world

A robot moves through a block map with walls, water, stacks and a crafting bench. Its atoms turn and move it, pick up and place objects, craft bridge kits, and inspect its hand or the cell ahead.

An action reaches only the cell directly in front of the robot. `forward` cannot enter a wall or open water. `pick` takes the top block or a tool. `place` adds a held block to the top of a supported column. This placement implements gravity because a block cannot remain above an empty space. A column cannot exceed `max_height`. Placing a bridge kit over water makes that cell traversable. A bench with `R` and `B`, or `Y` and `G`, as its top two blocks can craft a bridge kit when the hand is empty. An illegal action returns `NaN`, and every enclosing skill returns `NaN`.

Observations inspect the hand or the cell in front. They are `front_wall`, `front_water`, `front_colour`, `holding`, `held_colour`, and `front_height`. A missing colour and a height outside the map are undefined. These observations do not reveal other cells.

The `state` value has the encoding `{"t":"state","v":{...}}`. Its `v` object contains integer `width`, `height`, and `max_height`; `terrain` as an array of strings with one character per cell; sparse `stacks` entries with `x`, `y`, and bottom to top `blocks`; sparse `tools` entries with `x`, `y`, and `name`; `bridges` as coordinate pairs; and `robot` with `x`, `y`, `facing`, and `held`. Facing is one of `N`, `E`, `S`, or `W`. The held value is null, a block object with `kind` and `colour`, or a tool object with `kind` and `name`. Colours use `{"t":"colour","v":"R"}` when returned by an observation. Undefined uses `{"t":"nan"}`.

```python
from opulse.worlds.action import initial_state, apply_atom

state = initial_state()
turned = apply_atom("turn_right", state)
next_state = apply_atom("forward", turned)
```

This example turns the robot south and then moves it onto the floor cell below its start.

`generate_skills(seed=36, count=100)` grows state to state skills in several layers. A composition executes two actions or skills in order. A branch chooses one from an observation. A bounded recursion repeats a skill until its observation matches or its bound is reached. `run_skill` returns the exact final value and a derivation containing every intermediate state. Set `unfold=False` to apply a known skill as one step, or set `max_unfold_depth` to control how many layers are opened. `make_task` writes the needed skill rule records and the compact state grid into a prompt. `answer_from_prompt` parses those records and recomputes the answer without the original library. `check_steps` compares a proposed derivation with exact replay.

`generate_skills` accepts `action_names` and `guards` to choose its atoms. A custom atom must first be registered with a `state` input and a matching result type. The action simulator calls that registered atom during replay.

The showcase contains 100 skills with three examples each, and ten examples for each of five featured skills. Derivations live in individual files under `docs/assets/data/worlds/action/steps`. `export_world_showcase("action", path)` regenerates the files. The renderer loads Three.js version 0.170.0 as an ES module and uses a top down grid when WebGL is unavailable. z3 does not encode state transitions here. `bounded_equivalence` checks a finite supplied set of start states. `bounded_law_check` checks the turn inverse and four turn laws on generated start states. Both report their method and scope.
