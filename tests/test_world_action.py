"""Action simulator, skill replay, prompt checks, and showcase contract."""


import json
from dataclasses import replace
from pathlib import Path

import pytest

from opulse.bench.check import answer_from_prompt as bench_answer_from_prompt
from opulse.bench.check import check_tasks
from opulse.core.primitives import (
    CUSTOM,
    atom_records,
    register_primitive,
    unregister_primitive,
)
from opulse.core.registry import OperatorRegistry
from opulse.core.semantics import NAN, Semantics
from opulse.core.types import matches
from opulse.worlds.action import (
    ACTION_RULES,
    Colour,
    Direction,
    Skill,
    State,
    _examples_states,
    answer_from_prompt,
    apply_atom,
    bounded_equivalence,
    bounded_law_check,
    check_steps,
    check_task,
    decode,
    describe_skill,
    encode,
    export_world_showcase,
    generate_skills,
    initial_state,
    make_task,
    register_action_atoms,
    render_state,
    run_skill,
    select_examples,
)


def test_state_rules_and_gravity():
    state = initial_state()
    assert state.width == state.height == 8
    assert state.max_height == 4
    small = initial_state(6, 7, 1)
    assert (small.width, small.height, small.max_height) == (6, 7, 1)
    assert all(len(stack) <= 1 for stack in small.stacks)
    assert apply_atom("front_colour", state) == Colour("P")
    assert apply_atom("front_height", state) == 1
    assert apply_atom("holding", state) is False
    picked = apply_atom("pick", state)
    assert picked.held == "P"
    assert picked.stacks[state.index(2, 1)] == ()
    assert apply_atom("pick", picked) is NAN
    turned = apply_atom("turn_left", picked)
    placed = apply_atom("place", turned)
    assert placed.stacks[state.index(1, 0)] == ("P",)
    assert placed.held is None
    assert apply_atom("held_colour", placed) is NAN
    assert apply_atom("front_colour", turned) is NAN
    assert apply_atom("front_height", replace(state, robot=(7, 7))) is NAN
    assert apply_atom("forward", replace(state, robot=(7, 7))) is NAN
    assert apply_atom("forward", replace(state, robot=(3, 3))) is NAN
    assert apply_atom("front_water", replace(state, robot=(3, 3))) is True
    assert apply_atom("front_wall", replace(state, robot=(7, 7))) is True
    assert apply_atom("turn_right", NAN) is NAN
    assert state.stacks[state.index(2, 1)] == ("P",)


def test_craft_bridge_stack_limit_and_reach():
    state = initial_state()
    bench = replace(state, robot=(3, 2), facing=Direction("S"))
    crafted = apply_atom("craft", bench)
    assert crafted.held == "bridge_kit"
    assert crafted.stacks[state.index(3, 3)] == ()
    assert apply_atom("craft", crafted) is NAN
    at_water = replace(crafted, robot=(3, 3), facing=Direction("E"))
    bridged = apply_atom("place", at_water)
    assert bridged.bridges == ((4, 3),)
    crossed = apply_atom("forward", bridged)
    assert crossed.robot == (4, 3)
    assert apply_atom("place", bridged) is NAN
    full = replace(state, robot=(1, 1), held="R",
                   stacks=tuple(("Y",) * state.max_height if i == state.index(2, 1)
                                else stack for i, stack in enumerate(state.stacks)))
    assert apply_atom("place", full) is NAN
    assert full.stacks[state.index(2, 1)] == ("Y",) * 4
    assert state.stacks[state.index(3, 3)] == ("R", "B")
    assert apply_atom("craft", state) is NAN
    wrong = list(state.stacks)
    wrong[state.index(3, 3)] = ("R", "Y")
    assert apply_atom("craft", replace(bench, stacks=tuple(wrong))) is NAN
    tools = list(state.tools)
    tools[state.index(2, 1)] = "bridge_kit"
    picked_tool = apply_atom("pick", replace(state, tools=tuple(tools)))
    assert picked_tool.held == "bridge_kit"
    assert picked_tool.tools[state.index(2, 1)] == ""
    assert picked_tool.stacks[state.index(2, 1)] == ("P",)


@pytest.fixture
def action_atoms():
    names = register_action_atoms()
    try:
        yield names
    finally:
        for name in names:
            unregister_primitive(name)


def test_state_schema_and_typed_atoms(action_atoms):
    state = initial_state()
    assert State.from_dict(state.to_dict()) == state
    assert decode(encode(state)) == state
    assert matches(state, "state")
    assert matches(Colour("R"), "colour")
    assert matches(Direction("N"), "direction")
    assert not matches("R", "colour")
    names = action_atoms
    assert set(names) == set(ACTION_RULES) | {
        "front_wall", "front_water", "front_colour", "holding", "held_colour", "front_height"
    }
    assert all(CUSTOM[name].z3 is None for name in names)
    assert Semantics().operations()["front_colour"](state) == Colour("P")
    assert Semantics().operations()["forward"](NAN) is NAN
    assert len(atom_records(names)) == len(names)
    assert "robot:" in render_state(state)


def test_undefined_observation_propagates_through_branch():
    state = replace(initial_state(), robot=(2, 1), facing=Direction("E"))
    skill = Skill("▲₉₉", 1, "branch", "turn_left", "turn_right", "front_colour", "R")
    value, trace = run_skill(skill, state, {skill.name: skill})
    assert value is NAN
    assert trace[-1]["kind"] == "undefined"


def test_recursion_sentence_checks_the_guard_before_repeating():
    skill = Skill("▲₉₉", 1, "recursion", "turn_right", guard="front_height", expected=0, bound=4)
    assert describe_skill(skill) == (
        "Turn right until the cell ahead has no blocks, at most 4 times.",
        "反复向右转，直到正前方没有积木，最多 4 次。")


def test_custom_state_action_is_usable_by_generator():
    register_primitive("action_wait_test", "⌁", lambda state: state,
                       rule="Wait one turn without changing the world.",
                       position="postfix", parameter_types=("state",), result_type="state")
    try:
        skills = generate_skills(seed=4, count=20,
                                 action_names=("action_wait_test", "turn_left", "turn_right"))
        library = {skill.name: skill for skill in skills}
        assert any("action_wait_test" in (skill.first, skill.second) for skill in skills)
        for skill in skills:
            state = initial_state()
            output, trace = run_skill(skill, state, library)
            assert encode(output) == trace[-1]["value"]
        task = make_task(skills[0], initial_state(), library)
        assert check_task(task)
    finally:
        unregister_primitive("action_wait_test")


def test_every_skill_replays_exactly():
    skills = generate_skills()
    assert len(skills) == 100
    assert {skill.kind for skill in skills} == {"composition", "branch", "recursion"}
    assert max(skill.layer for skill in skills) >= 4
    assert len({(skill.kind, skill.first, skill.second, skill.guard, skill.expected,
                 skill.bound if skill.kind == "recursion" else 0) for skill in skills}) == 100
    library = {skill.name: skill for skill in skills}
    assert any(skill.first in library or skill.second in library for skill in skills)
    for skill in skills:
        cases = select_examples(skill, library)
        assert len(cases) == 3
        assert any(output is not NAN for _, output, _ in cases)
        for state, output, steps in cases:
            assert check_steps(skill, state, library, steps)
            assert run_skill(skill, state, library, unfold=False)[0] == output
            current = state
            for step in steps:
                if step["focus"] in {spec[0] for spec in ACTION_RULES.values()}:
                    atom = next(name for name, spec in ACTION_RULES.items()
                                if spec[0] == step["focus"])
                    current = apply_atom(atom, current)
                if step["value"]["t"] == "state":
                    assert decode(step["value"]) == current
                elif step["kind"] == "undefined":
                    if step["focus"] not in {spec[0] for spec in ACTION_RULES.values()}:
                        current = NAN
                    assert current is NAN
            assert decode(steps[-1]["value"]) == output
    for skill in skills[::11]:
        state = _examples_states()[2]
        expected = run_skill(skill, state, library)[0]
        for depth in range(5):
            result, trace = run_skill(skill, state, library, max_unfold_depth=depth)
            assert result == expected
            assert decode(trace[-1]["value"]) == expected


def test_prompt_rederivation_properties_and_bounded_check():
    skills = generate_skills()
    library = {skill.name: skill for skill in skills}
    states = _examples_states()
    for question in ("state", "held_colour", "block_count_front", "robot_x", "robot_y"):
        for skill in (skills[0], skills[1], skills[2], skills[51]):
            task = make_task(skill, states[2], library, question)
            assert check_task(task)
            assert answer_from_prompt(task["prompt"]) == task["answer"]
            assert bench_answer_from_prompt(task, OperatorRegistry()) == task["answer"]
            assert check_tasks([task], OperatorRegistry()) == []
    task = make_task(skills[0], states[0], library)
    changed = task.copy()
    changed["answer"] = {"t": "int", "v": 7}
    assert not check_task(changed)
    assert check_tasks([changed], OperatorRegistry())
    result = bounded_equivalence(skills[0], skills[0], states, library)
    assert result["method"] == "bounded_exhaustive_simulation"
    assert result["equivalent"] is True
    assert result["states_checked"] == len(states)
    assert bounded_law_check("left_right_inverse")["holds"] is True
    assert bounded_law_check("four_left_turns")["states_checked"] == len(states)


def test_showcase_schema_determinism_and_reference(tmp_path):
    a = tmp_path / "one" / "action.json"
    b = tmp_path / "two" / "action.json"
    data = export_world_showcase("action", a, seeds=1)
    export_world_showcase("action", b, seeds=1)
    assert a.read_bytes() == b.read_bytes()
    assert data["world"] == "action" and data["dimension"] == "action"
    assert len(data["operators"]) == 100
    names = [op["name"] for op in data["operators"]]
    assert names[0].endswith("₁") and len(set(names)) == len(names)
    assert len({name[0] for name in names[:8]}) >= 2
    assert all({"symbol", "rule", "plain", "plain_zh", "example"} <= atom.keys() for atom in data["atoms"])
    library = {skill.name: skill for skill in generate_skills()}
    for index, operator in enumerate(data["operators"]):
        assert operator["plain"] and operator["plain_zh"]
        records = json.loads((a.parent / data["steps"] / f"{index}.json").read_text())
        assert len(records) == len(operator["examples"]) == (10 if operator["featured"] else 3)
        for example, steps in zip(operator["examples"], records):
            state = decode(example["inputs"][0])
            output, trace = run_skill(library[operator["name"]], state, library)
            assert encode(output) == example["output"] and trace == steps
    total = sum(path.stat().st_size for path in (a.parent / "action").rglob("*.json"))
    assert total + a.stat().st_size < 5_000_000
    committed = json.loads(Path("docs/assets/data/worlds/action.json").read_text())
    assert committed["operators"] == data["operators"]
