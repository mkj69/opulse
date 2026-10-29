"""Deterministic block world and generated state-to-state skills.

The simulator is pure: an action returns a new State or the shared NAN value.
This makes illegal actions propagate through composition exactly like other
undefined Opulse values. No external game engine is involved.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, replace
from pathlib import Path

from opulse.core.semantics import NAN

COLOURS = ("R", "B", "Y", "G", "P", "O")
DIRECTIONS = ("N", "E", "S", "W")
VECTORS = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}
RECIPES = {frozenset(("R", "B")): "bridge_kit",
           frozenset(("Y", "G")): "bridge_kit"}
ACTION_RULES = {
    "forward": ("⟶", "Move one cell forward if it is inside the map and is traversable.",
                "Move the robot one cell forward." , "机器人向前移动一格。"),
    "turn_left": ("⤹", "Turn the robot one quarter turn left.",
                  "Turn the robot left.", "机器人向左转四分之一圈。"),
    "turn_right": ("↱", "Turn the robot one quarter turn right.",
                   "Turn the robot right.", "机器人向右转四分之一圈。"),
    "pick": ("⤒", "Pick the top block or tool from the cell directly ahead if the hand is empty.",
             "Pick up the object in front.", "拾起正前方格子的物品。"),
    "place": ("⤓", "Place a held block on the front stack, or use a bridge kit on front water.",
              "Place the held object in front.", "把手中的物品放在正前方。"),
    "craft": ("⚒", "At a front bench, consume its top two recipe colours and make a bridge kit in an empty hand.",
              "Craft a bridge kit at the bench.", "在工作台用两块配方积木制作桥梁工具。"),
}
OBS_RULES = {
    "front_wall": ("▤", "True if the front cell is outside the map or a wall.",
                   "Check whether the cell ahead is a wall or outside the map.",
                   "查看正前方是否为墙或在地图外。"),
    "front_water": ("≈", "True if the front cell is water without a bridge.",
                    "Check whether open water is ahead.", "查看正前方是否为未架桥的水面。"),
    "front_colour": ("◈", "The colour of the top front block, or undefined when there is none.",
                     "Read the top block colour ahead.", "读取正前方顶部积木的颜色。"),
    "holding": ("⊚", "True if the robot holds a block or tool.",
                "Check whether the robot holds an object.", "查看机器人是否拿着物品。"),
    "held_colour": ("◐", "The held block colour, or undefined when no block is held.",
                    "Read the held block colour.", "读取手中积木的颜色。"),
    "front_height": ("▥", "The front stack height, or undefined outside the map.",
                     "Count the blocks ahead.", "数出正前方格子的积木数量。"),
}
ATOM_TYPES = {name: ("state", "state") for name in ACTION_RULES}
ATOM_TYPES.update({"front_wall": ("state", "bool"), "front_water": ("state", "bool"),
                   "front_colour": ("state", "colour"), "holding": ("state", "bool"),
                   "held_colour": ("state", "colour"), "front_height": ("state", "int")})


class Colour(str):
    __opulse_value_type__ = "colour"

    def __new__(cls, value: str):
        if value not in COLOURS:
            raise ValueError("unknown block colour")
        return str.__new__(cls, value)


class Direction(str):
    __opulse_value_type__ = "direction"

    def __new__(cls, value: str):
        if value not in DIRECTIONS:
            raise ValueError("unknown direction")
        return str.__new__(cls, value)


@dataclass(frozen=True)
class State:
    """A sparse world value with row-major, gravity-settled stacks."""

    __opulse_value_type__ = "state"
    width: int
    height: int
    max_height: int
    terrain: tuple[str, ...]
    stacks: tuple[tuple[str, ...], ...]
    tools: tuple[str, ...]
    bridges: tuple[tuple[int, int], ...]
    robot: tuple[int, int]
    facing: Direction
    held: str | None = None

    def __post_init__(self) -> None:
        if not 1 <= self.width <= 32 or not 1 <= self.height <= 32:
            raise ValueError("map dimensions must be from 1 to 32")
        if not 1 <= self.max_height <= 16:
            raise ValueError("stacking limit must be from 1 to 16")
        if len(self.terrain) != self.height or any(len(row) != self.width for row in self.terrain):
            raise ValueError("terrain dimensions do not match map")
        if any(set(row) - set(".#~B") for row in self.terrain):
            raise ValueError("unknown terrain")
        if len(self.stacks) != self.width * self.height or len(self.tools) != len(self.stacks):
            raise ValueError("object dimensions do not match map")
        if any(len(stack) > self.max_height or any(c not in COLOURS for c in stack)
               for stack in self.stacks):
            raise ValueError("invalid block stack")
        if any(tool not in ("", "bridge_kit") for tool in self.tools):
            raise ValueError("unknown tool")
        if self.facing not in DIRECTIONS:
            raise ValueError("unknown facing direction")
        if any((self.terrain[y][x] == "#" or
                (self.terrain[y][x] == "~" and (x, y) not in self.bridges)) and
               (self.stacks[self.index(x, y)] or self.tools[self.index(x, y)])
               for y in range(self.height) for x in range(self.width)):
            raise ValueError("objects need a supporting floor or bench")
        if any(not self.inside(x, y) or self.terrain[y][x] != "~" for x, y in self.bridges):
            raise ValueError("bridges must span water")
        if not self.inside(*self.robot) or self.terrain[self.robot[1]][self.robot[0]] == "#":
            raise ValueError("robot is outside traversable terrain")
        if self.terrain[self.robot[1]][self.robot[0]] == "~" and self.robot not in self.bridges:
            raise ValueError("robot needs a bridge over water")
        if self.held not in (*COLOURS, "bridge_kit", None):
            raise ValueError("unknown held item")

    def inside(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def index(self, x: int, y: int) -> int:
        return y * self.width + x

    def front(self) -> tuple[int, int]:
        dx, dy = VECTORS[self.facing]
        return self.robot[0] + dx, self.robot[1] + dy

    def to_dict(self) -> dict:
        blocks = [{"x": i % self.width, "y": i // self.width, "blocks": list(stack)}
                  for i, stack in enumerate(self.stacks) if stack]
        tools = [{"x": i % self.width, "y": i // self.width, "name": tool}
                 for i, tool in enumerate(self.tools) if tool]
        held = None if self.held is None else (
            {"kind": "block", "colour": self.held} if self.held in COLOURS
            else {"kind": "tool", "name": self.held})
        return {"width": self.width, "height": self.height, "max_height": self.max_height,
                "terrain": list(self.terrain), "stacks": blocks, "tools": tools,
                "bridges": [list(p) for p in self.bridges],
                "robot": {"x": self.robot[0], "y": self.robot[1],
                          "facing": str(self.facing), "held": held}}

    @classmethod
    def from_dict(cls, data: dict) -> State:
        width, height = data["width"], data["height"]
        stacks = [()] * (width * height)
        tools = [""] * (width * height)
        for item in data["stacks"]:
            stacks[item["y"] * width + item["x"]] = tuple(item["blocks"])
        for item in data["tools"]:
            tools[item["y"] * width + item["x"]] = item["name"]
        robot = data["robot"]
        held = robot["held"]
        return cls(width, height, data["max_height"], tuple(data["terrain"]), tuple(stacks),
                   tuple(tools), tuple(tuple(p) for p in data["bridges"]),
                   (robot["x"], robot["y"]), Direction(robot["facing"]),
                   None if held is None else held.get("colour", held.get("name")))


def initial_state(width: int = 8, height: int = 8, max_height: int = 4) -> State:
    terrain = [["." for _ in range(width)] for _ in range(height)]
    if width >= 6 and height >= 6:
        for y in range(1, height - 1):
            terrain[y][width // 2] = "~"
        terrain[3][3] = "B"
        terrain[height - 2][1] = "#"
        terrain[1][width - 2] = "#"
    stacks = [()] * (width * height)
    if width >= 6 and height >= 6:
        stacks[3 * width + 3] = ("R", "B")[:max_height]
        stacks[2 * width + 2] = ("Y", "G")[:max_height]
        stacks[1 * width + 2] = ("P",)
    robot = (1, 1) if width > 2 and height > 2 else (0, 0)
    return State(width, height, max_height, tuple("".join(row) for row in terrain),
                 tuple(stacks), ("",) * (width * height), (), robot, Direction("E"))


def apply_atom(name: str, state: State | object):
    """Apply one registered rule; illegal actions give NAN without changing state."""
    if state is NAN:
        return NAN
    if not isinstance(state, State):
        return NAN
    if name not in ATOM_TYPES:
        from opulse.core.primitives import CUSTOM
        from opulse.core.semantics import Semantics

        primitive = CUSTOM.get(name)
        if primitive is None or primitive.parameter_types != ("state",):
            return NAN
        return Semantics().operations()[name](state)
    x, y = state.front()
    inside = state.inside(x, y)
    terrain = state.terrain[y][x] if inside else None
    index = state.index(x, y) if inside else None
    if name == "front_wall":
        return not inside or terrain == "#"
    if name == "front_water":
        return inside and terrain == "~" and (x, y) not in state.bridges
    if name == "holding":
        return state.held is not None
    if name == "held_colour":
        return Colour(state.held) if state.held in COLOURS else NAN
    if name == "front_colour":
        return Colour(state.stacks[index][-1]) if inside and state.stacks[index] else NAN
    if name == "front_height":
        return len(state.stacks[index]) if inside else NAN
    if name == "turn_left":
        return replace(state, facing=Direction(DIRECTIONS[(DIRECTIONS.index(state.facing) - 1) % 4]))
    if name == "turn_right":
        return replace(state, facing=Direction(DIRECTIONS[(DIRECTIONS.index(state.facing) + 1) % 4]))
    if not inside or terrain == "#":
        return NAN
    if name == "forward":
        if terrain == "~" and (x, y) not in state.bridges:
            return NAN
        return replace(state, robot=(x, y))
    if name == "pick":
        if state.held is not None or terrain == "~":
            return NAN
        if state.tools[index]:
            tools = list(state.tools)
            held, tools[index] = tools[index], ""
            return replace(state, tools=tuple(tools), held=held)
        if not state.stacks[index]:
            return NAN
        stacks = list(state.stacks)
        held = stacks[index][-1]
        stacks[index] = stacks[index][:-1]
        return replace(state, stacks=tuple(stacks), held=held)
    if name == "place":
        if state.held is None:
            return NAN
        if state.held == "bridge_kit":
            if terrain != "~" or (x, y) in state.bridges:
                return NAN
            return replace(state, bridges=tuple(sorted((*state.bridges, (x, y)))), held=None)
        if terrain == "~" and (x, y) not in state.bridges:
            return NAN
        if len(state.stacks[index]) >= state.max_height or state.tools[index]:
            return NAN
        stacks = list(state.stacks)
        stacks[index] = (*stacks[index], state.held)
        return replace(state, stacks=tuple(stacks), held=None)
    if name == "craft":
        if terrain != "B" or state.held is not None or len(state.stacks[index]) < 2:
            return NAN
        ingredients = state.stacks[index][-2:]
        tool = RECIPES.get(frozenset(ingredients))
        if tool is None:
            return NAN
        stacks = list(state.stacks)
        stacks[index] = stacks[index][:-2]
        return replace(state, stacks=tuple(stacks), held=tool)
    raise KeyError(name)


def register_action_atoms() -> tuple[str, ...]:
    """Opt in to action atoms in the shared typed atom registry."""
    from opulse.core.primitives import CUSTOM, register_primitive

    for name, (symbol, rule, _, _) in {**ACTION_RULES, **OBS_RULES}.items():
        if name not in CUSTOM:
            register_primitive(name, symbol, lambda state, n=name: apply_atom(n, state),
                               rule=rule, position="postfix", parameter_types=("state",),
                               result_type=ATOM_TYPES[name][1])
    return (*ACTION_RULES, *OBS_RULES)


def encode(value: object) -> dict:
    if value is NAN:
        return {"t": "nan"}
    if isinstance(value, State):
        return {"t": "state", "v": value.to_dict()}
    if isinstance(value, Colour):
        return {"t": "colour", "v": str(value)}
    if isinstance(value, Direction):
        return {"t": "direction", "v": str(value)}
    if isinstance(value, bool):
        return {"t": "bool", "v": value}
    if isinstance(value, int):
        return {"t": "int", "v": value}
    raise TypeError(f"cannot encode {value!r}")


def decode(value: dict):
    kind = value["t"]
    if kind == "nan":
        return NAN
    if kind == "state":
        return State.from_dict(value["v"])
    if kind == "colour":
        return Colour(value["v"])
    if kind == "direction":
        return Direction(value["v"])
    if kind in ("bool", "int"):
        return value["v"]
    raise ValueError(f"unknown action value {kind}")


def render_state(state: State) -> str:
    """Compact prompt form: terrain and stack top with height at each cell."""
    rows = []
    for y in range(state.height):
        cells = []
        for x in range(state.width):
            n = state.index(x, y)
            ground = state.terrain[y][x]
            if (x, y) in state.bridges:
                ground = "="
            stack = state.stacks[n]
            object_text = f"{stack[-1]}{len(stack)}" if stack else ("T" if state.tools[n] else ".")
            cells.append(ground + object_text)
        rows.append(" ".join(cells))
    return "\n".join(rows) + (f"\nrobot: ({state.robot[0]},{state.robot[1]}) "
                               f"{state.facing}, held: {state.held or 'empty'}")


@dataclass(frozen=True)
class Skill:
    name: str
    layer: int
    kind: str
    first: str
    second: str = ""
    guard: str = ""
    expected: object = True
    bound: int = 0

    def record(self) -> dict:
        return {"name": self.name, "layer": self.layer, "kind": self.kind,
                "first": self.first, "second": self.second, "guard": self.guard,
                "expected": self.expected, "bound": self.bound}

    @classmethod
    def from_record(cls, record: dict) -> Skill:
        return cls(**record)

    def definition(self) -> str:
        if self.kind == "composition":
            body = f"{self.first} then {self.second}"
        elif self.kind == "branch":
            body = f"{self.first}, if {self.guard} = {self.expected}; {self.second}, else"
        else:
            body = f"repeat {self.first} until {self.guard} = {self.expected}; at most {self.bound} times"
        return f"s {self.name} = {{ {body} }}"


def generate_skills(seed: int = 36, count: int = 100,
                    action_names: tuple[str, ...] | None = None,
                    guards: tuple[tuple[str, object], ...] | None = None) -> list[Skill]:
    """Grow a deterministic, layered library from chosen typed action atoms."""
    rng = random.Random(seed)
    actions = action_names or tuple(ACTION_RULES)
    guards = guards or (("front_wall", True), ("front_water", True), ("holding", True),
                        ("front_height", 0), ("front_colour", "R"), ("held_colour", "B"))
    from opulse.core.primitives import CUSTOM

    for action in actions:
        if action not in ACTION_RULES and not (action in CUSTOM and
                CUSTOM[action].parameter_types == ("state",) and CUSTOM[action].result_type == "state"):
            raise ValueError(f"{action} is not a registered state action")
    for guard, _ in guards:
        if guard not in OBS_RULES and not (guard in CUSTOM and
                CUSTOM[guard].parameter_types == ("state",) and
                CUSTOM[guard].result_type in ("bool", "int", "colour")):
            raise ValueError(f"{guard} is not a registered state observation")
    from opulse.config import OperatorSettings
    from opulse.generation.symbols import ShapeIndexFactory

    taken = {spec[0] for spec in (*ACTION_RULES.values(), *OBS_RULES.values())}
    naming = ShapeIndexFactory(OperatorSettings(), random.Random(seed))
    naming.reserve(taken)
    skills = []
    seen_bodies: set[tuple] = set()

    def body_key(member: Skill) -> tuple:
        return (member.kind, member.first, member.second,
                member.guard if member.kind != "composition" else "",
                member.expected if member.kind != "composition" else None,
                member.bound if member.kind == "recursion" else 0)

    for i in range(count):
        layer = 1 + i // 25
        kind = ("composition", "branch", "recursion")[i % 3]
        name = naming.new_symbol()
        naming.reserve(name)
        older = [s.name for s in skills if s.layer < layer]
        base = actions[(i * 5 + rng.randrange(len(actions))) % len(actions)]
        first = older[(i * 7 + seed) % len(older)] if older and i % 2 == 0 else base
        second = actions[(i + rng.randrange(len(actions))) % len(actions)]
        if older and i % 5 == 0:
            second = older[(i * 3 + seed) % len(older)]
        if kind == "branch" and second == first and len(actions) > 1:
            second = next(action for action in actions if action != first)
        guard, expected = guards[(i + rng.randrange(len(guards))) % len(guards)]
        skill = Skill(name, layer, kind, first, second if kind != "recursion" else "",
                      guard if kind != "composition" else "", expected, 2 + i % 3)
        # Keep each published skill executable on at least one generated start state.
        trial = {item.name: item for item in (*skills, skill)}
        if not any(run_skill(skill, state, trial, unfold=False)[0] is not NAN
                   for state in _examples_states()):
            safe = next((action for action in ("turn_left", "turn_right", *actions)
                         if action in actions and all(apply_atom(action, state) is not NAN
                                                      for state in _examples_states())), None)
            if safe is not None:
                other = "turn_right" if safe == "turn_left" and "turn_right" in actions else safe
                total_guard = next(((guard, expected) for guard, expected in guards
                                    if all(apply_atom(guard, state) is not NAN
                                           for state in _examples_states())), None)
                skill = replace(skill, first=safe, second=other if kind != "recursion" else "",
                                guard=total_guard[0] if total_guard and kind != "composition"
                                else skill.guard,
                                expected=total_guard[1] if total_guard else skill.expected)
        if body_key(skill) in seen_bodies:
            pool = (*actions, *older)
            for attempt in range(1, 201):
                guard_name, guard_value = guards[(i + attempt) % len(guards)]
                candidate = replace(skill, first=pool[(i + attempt) % len(pool)],
                                    second=pool[(i * 3 + attempt * 2) % len(pool)]
                                    if kind != "recursion" else "",
                                    guard=guard_name if kind != "composition" else "",
                                    expected=guard_value, bound=2 + (i + attempt) % 3)
                if body_key(candidate) in seen_bodies or (kind == "branch" and
                                                            candidate.first == candidate.second):
                    continue
                trial[candidate.name] = candidate
                if any(run_skill(candidate, state, trial, unfold=False)[0] is not NAN
                       for state in _examples_states()):
                    skill = candidate
                    break
        skills.append(skill)
        seen_bodies.add(body_key(skill))
    return skills


def _guard(skill: Skill, state: State):
    observed = apply_atom(skill.guard, state)
    if observed is NAN:
        return None, observed
    return observed == skill.expected, observed


def run_skill(skill: Skill | str, state: State | object, library: dict[str, Skill],
              *, unfold: bool = True, max_unfold_depth: int | None = None) -> tuple[object, list[dict]]:
    """Reduce one skill, recording each exact intermediate State."""
    if isinstance(skill, str):
        skill = library[skill]
    if max_unfold_depth is not None and max_unfold_depth < 0:
        raise ValueError("max_unfold_depth must be non-negative")
    if state is NAN:
        return NAN, [{"kind": "undefined", "expression": skill.name,
                      "focus": skill.name, "value": encode(NAN),
                      "note": "An undefined input stays undefined.",
                      "note_zh": "未定义的输入仍为未定义。"}]
    if not unfold or max_unfold_depth == 0:
        result, _ = run_skill(skill, state, library, unfold=True)
        return result, [{"kind": "eval" if result is not NAN else "undefined",
                         "expression": skill.name, "focus": skill.name,
                         "value": encode(result), "note": "Apply the known skill in one step.",
                         "note_zh": "把已知技能作为一步执行。"}]
    steps = []

    def add(kind: str, expression: str, focus: str, value: object, note: str, note_zh: str,
            observation: object | None = None) -> None:
        row = {"kind": kind, "expression": expression, "focus": focus,
               "value": encode(value), "note": note, "note_zh": note_zh}
        if observation is not None:
            row["observation"] = encode(observation)
        steps.append(row)

    def visit(ref: str, current: object, depth: int):
        if current is NAN:
            return NAN
        if depth > 30:
            raise RuntimeError("skill call graph is too deep")
        from opulse.core.primitives import CUSTOM

        if ref in ACTION_RULES or (ref in CUSTOM and CUSTOM[ref].result_type == "state" and
                                   CUSTOM[ref].parameter_types == ("state",)):
            next_state = apply_atom(ref, current)
            kind = "undefined" if next_state is NAN else "atom"
            spec = ACTION_RULES.get(ref)
            symbol = spec[0] if spec else CUSTOM[ref].symbol
            add(kind, symbol, symbol,
                next_state, spec[1] if spec else CUSTOM[ref].rule,
                spec[3] if spec else CUSTOM[ref].rule)
            return next_state
        inner = library[ref]
        if max_unfold_depth is not None and depth >= max_unfold_depth:
            result, _ = run_skill(inner, current, library)
            add("undefined" if result is NAN else "eval", inner.name, inner.name, result,
                "Apply this known skill as one step.", "把这个已知技能作为一步执行。")
            return result
        add("expand", inner.definition(), inner.name, current,
            "Unfold this skill definition.", "展开这个技能的定义。")
        if inner.kind == "composition":
            result = visit(inner.first, current, depth + 1)
            result = visit(inner.second, result, depth + 1)
        elif inner.kind == "branch":
            matched, observed = _guard(inner, current)
            add("eval", inner.definition(), inner.guard, current,
                f"Observe {inner.guard} = {observed}.", f"观察到 {inner.guard} = {observed}。",
                observed)
            result = NAN if matched is None else visit(inner.first if matched else inner.second,
                                                       current, depth + 1)
        else:
            result = current
            for repetition in range(inner.bound):
                matched, observed = _guard(inner, result)
                add("eval", inner.definition(), inner.guard, result,
                    f"Check stop condition after {repetition} repeats: {observed}.",
                    f"重复 {repetition} 次后检查停止条件：{observed}。", observed)
                if matched is None:
                    result = NAN
                    break
                if matched:
                    break
                result = visit(inner.first, result, depth + 1)
                if result is NAN:
                    break
        add("undefined" if result is NAN else "eval", inner.name, inner.name, result,
            "The skill finishes with this state." if result is not NAN else "The skill is undefined.",
            "技能执行后得到这个状态。" if result is not NAN else "这个技能未定义。")
        return result

    return visit(skill.name, state, 0), steps


def _examples_states() -> list[State]:
    """Fixed states cover walls, water, bench, held items, colours and map edges."""
    base = initial_state()
    cases = [
        replace(base, robot=(1, 1), facing=Direction("E")),
        replace(base, robot=(1, 1), facing=Direction("E"), held="R"),
        replace(base, robot=(3, 2), facing=Direction("S")),
        replace(base, robot=(3, 3), facing=Direction("E"), held="bridge_kit"),
        replace(base, robot=(3, 3), facing=Direction("E")),
        replace(base, robot=(7, 7), facing=Direction("E")),
        replace(base, robot=(3, 2), facing=Direction("S"), held="B"),
        replace(base, robot=(3, 4), facing=Direction("N")),
        replace(base, robot=(2, 1), facing=Direction("E")),
        replace(base, robot=(5, 4), facing=Direction("W")),
        replace(base, bridges=((4, 3),), robot=(3, 3), facing=Direction("E")),
    ]
    tools = list(base.tools)
    tools[base.index(2, 1)] = "bridge_kit"
    cases.append(replace(base, tools=tuple(tools)))
    positions = ((1, 1), (2, 2), (3, 2), (3, 4), (4, 0), (7, 7),
                 (2, 1), (5, 4), (0, 0), (6, 3))
    for i in range(30):
        pos = positions[i % len(positions)]
        if base.terrain[pos[1]][pos[0]] == "~":
            pos = (1, 1)
        held = (None, "R", "B", "bridge_kit", "Y")[i % 5]
        cases.append(replace(base, robot=pos, facing=Direction(DIRECTIONS[(i // 2) % 4]), held=held))
    return cases


def _signature(skill: Skill, steps: list[dict], result: object) -> tuple:
    observations = tuple(row.get("observation", {}).get("v") for row in steps
                         if row.get("focus") == skill.guard and "observation" in row)
    return (result is NAN, observations[:2], len(observations),
            sum(row["kind"] == "atom" for row in steps))


def select_examples(skill: Skill, library: dict[str, Skill], count: int = 3) -> list[tuple[State, object, list[dict]]]:
    choices = []
    for state in _examples_states():
        output, steps = run_skill(skill, state, library)
        previous = encode(state)
        inert = 0
        for step in steps:
            if step["kind"] == "atom" and step["value"] == previous:
                inert += 1
            previous = step["value"]
        choices.append((state, output, steps, inert))
    choices.sort(key=lambda choice: choice[3] != 0)
    first_defined = next((choice for choice in choices if choice[1] is not NAN and choice[3] == 0), None)
    if first_defined is None:
        first_defined = next((choice for choice in choices if choice[1] is not NAN), None)
    if first_defined is not None:
        choices.remove(first_defined)
        choices.insert(0, first_defined)
    selected = []
    seen = set()
    for choice in choices:
        sig = _signature(skill, choice[2], choice[1])
        if sig not in seen:
            selected.append(choice)
            seen.add(sig)
        if len(selected) == count:
            return [choice[:3] for choice in selected]
    for choice in choices:
        if choice not in selected:
            selected.append(choice)
        if len(selected) == count:
            break
    return [choice[:3] for choice in selected]


def _dependencies(skill: Skill, library: dict[str, Skill], found: dict[str, Skill]) -> None:
    if skill.name in found:
        return
    for ref in (skill.first, skill.second):
        if ref in library:
            _dependencies(library[ref], library, found)
    found[skill.name] = skill


def make_task(skill: Skill, state: State, library: dict[str, Skill], question: str = "state") -> dict:
    """Make a prompt whose rule records suffice to rederive its answer."""
    closure: dict[str, Skill] = {}
    _dependencies(skill, library, closure)
    from opulse.core.primitives import CUSTOM

    custom_names = {ref for member in closure.values() for ref in (member.first, member.second, member.guard)
                    if ref in CUSTOM and ref not in ACTION_RULES and ref not in OBS_RULES}
    outcome, steps = run_skill(skill, state, library)
    lines = ["Action world rules:",
             "The robot can act only on the cell in front of it.",
             "A placed block falls to the top of its column and cannot exceed max_height.",
             "A bridge kit placed over water makes that cell traversable.",
             "At a bench, top R and B or top Y and G craft one bridge kit.",
             "Illegal actions are undefined and stay undefined through a skill."]
    lines += [f"  - {name} {spec[0]}: {spec[1]}" for name, spec in
              {**ACTION_RULES, **OBS_RULES}.items()]
    lines += [f"  - {name} {CUSTOM[name].symbol}: {CUSTOM[name].rule}"
              for name in sorted(custom_names)]
    lines += ["Skill rules:"]
    lines += [s.definition() for s in closure.values()]
    lines += ["Rule records:"]
    lines += [json.dumps(s.record(), ensure_ascii=False, sort_keys=True) for s in closure.values()]
    lines += ["Start state:", render_state(state),
              "State record: " + json.dumps(state.to_dict(), ensure_ascii=False, sort_keys=True),
              f"Question: Apply {skill.name}. Report {question}."]
    return {"family": "action", "context": "full", "id": f"action-{skill.name}-{question}",
            "prompt": "\n".join(lines), "skill": skill.name, "question": question,
            "answer": encode(_property(outcome, question)), "steps": steps}


def _property(outcome: object, question: str):
    if outcome is NAN or question == "state":
        return outcome
    if question == "held_colour":
        return Colour(outcome.held) if outcome.held in COLOURS else NAN
    if question == "block_count_front":
        x, y = outcome.front()
        return len(outcome.stacks[outcome.index(x, y)]) if outcome.inside(x, y) else NAN
    if question == "robot_x":
        return outcome.robot[0]
    if question == "robot_y":
        return outcome.robot[1]
    raise ValueError("unknown question")


def answer_from_prompt(prompt: str) -> dict:
    """Rebuild rules and state solely from visible prompt records."""
    for name, spec in {**ACTION_RULES, **OBS_RULES}.items():
        if f"  - {name} {spec[0]}: {spec[1]}" not in prompt.splitlines():
            raise ValueError(f"the prompt omits the rule of {name}")
    records = []
    for line in prompt.splitlines():
        if line.startswith('{"bound":'):
            records.append(Skill.from_record(json.loads(line)))
    state_line = next(line for line in prompt.splitlines() if line.startswith("State record: "))
    state = State.from_dict(json.loads(state_line[len("State record: "):]))
    question_line = next(line for line in prompt.splitlines() if line.startswith("Question: Apply "))
    words = question_line.split()
    name, question = words[2].rstrip("."), words[-1].rstrip(".")
    library = {skill.name: skill for skill in records}
    from opulse.core.primitives import CUSTOM

    custom_names = {ref for member in records for ref in (member.first, member.second, member.guard)
                    if ref in CUSTOM and ref not in ACTION_RULES and ref not in OBS_RULES}
    for atom_name in custom_names:
        atom = CUSTOM[atom_name]
        if f"  - {atom_name} {atom.symbol}: {atom.rule}" not in prompt.splitlines():
            raise ValueError(f"the prompt omits the rule of {atom_name}")
    shown = prompt.split("Skill rules:\n", 1)[1].split("\nRule records:\n", 1)[0].splitlines()
    if shown != [skill.definition() for skill in records]:
        raise ValueError("visible skill definitions differ from rule records")
    outcome, _ = run_skill(name, state, library)
    return encode(_property(outcome, question))


def check_task(task: dict) -> bool:
    return answer_from_prompt(task["prompt"]) == task["answer"]


def check_steps(skill: Skill, state: State, library: dict[str, Skill], steps: list[dict]) -> bool:
    """Exact process grading against an independently replayed derivation."""
    return steps == run_skill(skill, state, library)[1]


def bounded_equivalence(left: Skill, right: Skill, states: list[State],
                        library: dict[str, Skill]) -> dict:
    """A bounded simulation check, never a z3 proof."""
    for state in states:
        a, _ = run_skill(left, state, library, unfold=False)
        b, _ = run_skill(right, state, library, unfold=False)
        if encode(a) != encode(b):
            return {"method": "bounded_exhaustive_simulation", "equivalent": False,
                    "counterexample": encode(state)}
    return {"method": "bounded_exhaustive_simulation", "equivalent": True,
            "states_checked": len(states), "scope": "provided generated start states"}


def bounded_law_check(law: str, states: list[State] | None = None) -> dict:
    """Check a named turning law on every state of a finite generated set."""
    if law not in ("left_right_inverse", "four_left_turns"):
        raise ValueError("unknown action law")
    cases = _examples_states() if states is None else states
    actions = ("turn_left", "turn_right") if law == "left_right_inverse" else ("turn_left",) * 4
    for state in cases:
        result = state
        for action in actions:
            result = apply_atom(action, result)
        if result != state:
            return {"method": "bounded_exhaustive_simulation", "law": law,
                    "holds": False, "counterexample": encode(state)}
    return {"method": "bounded_exhaustive_simulation", "law": law,
            "holds": True, "states_checked": len(cases),
            "scope": "finite generated start states"}


ACTION_PHRASES = {
    "forward": ("move forward", "向前走一格"),
    "turn_left": ("turn left", "向左转"),
    "turn_right": ("turn right", "向右转"),
    "pick": ("pick up what is ahead", "拿起正前方的东西"),
    "place": ("place the held object ahead", "把手里的东西放到正前方"),
    "craft": ("craft a bridge kit at the bench ahead", "在正前方的工作台做一个桥梁工具"),
}
COLOUR_NAMES = {"R": ("red", "红"), "B": ("blue", "蓝"), "Y": ("yellow", "黄"), "G": ("green", "绿"),
                "P": ("purple", "紫"), "O": ("orange", "橙")}


def _condition(guard: str, expected) -> tuple[str, str]:
    if guard == "front_wall":
        return (("the cell ahead is a wall or outside the map", "正前方是墙或在地图外") if expected
                else ("the cell ahead is open", "正前方可以走"))
    if guard == "front_water":
        return (("open water is ahead", "正前方是没架桥的水面") if expected
                else ("no open water is ahead", "正前方不是没架桥的水面"))
    if guard == "holding":
        return (("the robot holds something", "机器人手里有东西") if expected
                else ("the robot's hand is empty", "机器人空着手"))
    if guard == "front_height":
        if expected == 0:
            return ("the cell ahead has no blocks", "正前方没有积木")
        return (f"the stack ahead has {expected} blocks", f"正前方有 {expected} 块积木")
    if guard == "front_colour":
        en, zh = COLOUR_NAMES.get(expected, (str(expected), str(expected)))
        return (f"the top block ahead is {en}", f"正前方顶上的积木是{zh}色")
    if guard == "held_colour":
        en, zh = COLOUR_NAMES.get(expected, (str(expected), str(expected)))
        return (f"the robot holds a {en} block", f"机器人拿着{zh}色积木")
    return (f"{guard} is {expected}", f"{guard} 为 {expected}")


def _doing(ref: str) -> tuple[str, str]:
    if ref in ACTION_PHRASES:
        return ACTION_PHRASES[ref]
    from opulse.core.primitives import CUSTOM

    if ref in CUSTOM:
        return (f"apply {CUSTOM[ref].symbol}", f"执行 {CUSTOM[ref].symbol}")
    return (f"do {ref}", f"执行 {ref}")


def describe_skill(skill: Skill) -> tuple[str, str]:
    """One English and one Chinese sentence read from the skill record."""
    first, first_zh = _doing(skill.first)
    if skill.kind == "composition":
        second, second_zh = _doing(skill.second)
        return (f"{first[0].upper()}{first[1:]}, then {second}.", f"先{first_zh}，再{second_zh}。")
    condition, condition_zh = _condition(skill.guard, skill.expected)
    if skill.kind == "branch":
        second, second_zh = _doing(skill.second)
        return (f"If {condition}, {first}; otherwise {second}.",
                f"如果{condition_zh}，就{first_zh}；否则{second_zh}。")
    return (f"{first[0].upper()}{first[1:]} until {condition}, at most {skill.bound} times.",
            f"反复{first_zh}，直到{condition_zh}，最多 {skill.bound} 次。")


ATOM_ZH = {"forward": "如果前方一格在地图内并且能走，就向前走一格。",
           "turn_left": "原地向左转四分之一圈。", "turn_right": "原地向右转四分之一圈。",
           "pick": "空手时拿起正前方格子最上面的积木或工具。",
           "place": "把手里的积木放到正前方那一摞的最上面，或把桥梁工具放到正前方的水面上。",
           "craft": "正前方的工作台最上面两块是配方颜色时，用它们做出一个桥梁工具。",
           "front_wall": "正前方在地图外或是墙时为真。", "front_water": "正前方是没架桥的水面时为真。",
           "front_colour": "正前方最上面积木的颜色，没有积木时无定义。",
           "holding": "机器人手里有积木或工具时为真。", "held_colour": "手里积木的颜色，手里不是积木时无定义。",
           "front_height": "正前方那一摞积木的块数，在地图外时无定义。"}


def _behaviour(skill: Skill, library: dict) -> tuple:
    return tuple(json.dumps(encode(run_skill(skill, state, library, unfold=False)[0]), sort_keys=True)
                 for state in _examples_states()[:16])


def _metrics(skills: list[Skill], library: dict) -> dict:
    from collections import Counter

    prints = [_behaviour(skill, library) for skill in skills]
    forms = Counter(skill.kind for skill in skills)
    return {"operators": len(skills),
            "forms": {"composition": forms.get("composition", 0), "branching": forms.get("branch", 0),
                      "recursion": forms.get("recursion", 0)},
            "behaviours": len(set(prints)), "constant": sum(len(set(p)) == 1 for p in prints),
            "layers": {str(layer): n for layer, n in sorted(Counter(skill.layer for skill in skills).items())},
            "_prints": prints}


def _atom_example(name: str):
    base = initial_state()
    states = {"forward": replace(base, robot=(1, 1), facing=Direction("S")),
              "turn_left": replace(base, robot=(1, 1), facing=Direction("E")),
              "turn_right": replace(base, robot=(1, 1), facing=Direction("E")),
              "pick": replace(base, robot=(1, 1), facing=Direction("E")),
              "place": replace(base, robot=(1, 1), facing=Direction("E"), held="R"),
              "craft": replace(base, robot=(3, 2), facing=Direction("S")),
              "held_colour": replace(base, robot=(1, 1), facing=Direction("E"), held="B")}
    state = states.get(name, replace(base, robot=(1, 1), facing=Direction("E")))
    return state, apply_atom(name, state)


def export_world_showcase(world_name: str, out_path: str | Path, seeds: int = 3) -> dict:
    """Write the action showcase for ``seeds`` libraries; the first goes to ``out_path``."""
    if world_name != "action":
        raise ValueError("this exporter only produces the action world")
    import shutil

    from opulse.worlds.metrics import add_novelty

    path = Path(out_path)
    root = path.parent
    root.mkdir(parents=True, exist_ok=True)
    folder = root / "action"
    folder.mkdir(parents=True, exist_ok=True)
    if (folder / "steps").exists():
        shutil.rmtree(folder / "steps")
    for stale in folder.glob("seed-*.json"):
        stale.unlink()
    numbers = [36 + 101 * index for index in range(seeds)]
    paths = [path] + [root / "action" / f"seed-{n}.json" for n in numbers[1:]]
    atoms = []
    for name, spec in {**ACTION_RULES, **OBS_RULES}.items():
        state, output = _atom_example(name)
        atoms.append({"symbol": spec[0], "name": name, "arity": 1,
                      "signature": "state → " + ATOM_TYPES[name][1],
                      "rule": spec[1], "plain": spec[1], "plain_zh": ATOM_ZH[name],
                      "params": [{"name": "s", "type": "state"}], "result_type": ATOM_TYPES[name][1],
                      "example": {"expression": f"{spec[0]}(s)", "inputs": [encode(state)], "output": encode(output)}})
    shared = Path(__file__).resolve().parents[3] / "docs/assets/data/atoms/action.json"
    if shared.exists():
        published = json.loads(shared.read_text(encoding="utf-8"))
        records = published if isinstance(published, list) else published.get("atoms", [])
        by_symbol = {item["symbol"]: item for item in records}
        for atom in atoms:
            if atom["symbol"] in by_symbol:
                atom.update({key: value for key, value in by_symbol[atom["symbol"]].items()
                             if key in {"name", "arity", "signature", "plain", "plain_zh", "example"}})
    results = []
    for seed in numbers:
        skills = generate_skills(seed=seed)
        library = {s.name: s for s in skills}
        step_dir = root / "action" / "steps" / str(seed)
        step_dir.mkdir(parents=True, exist_ok=True)
        operators = []
        for index, skill in enumerate(skills):
            featured = index < 5
            plain, plain_zh = describe_skill(skill)
            uses = [ref for ref in (skill.first, skill.second) if ref in library]
            row = {"name": skill.name, "definition": skill.definition(), "plain": plain, "plain_zh": plain_zh,
                   "params": [{"name": "s", "type": "state"}], "result_type": "state",
                   "layer": skill.layer, "kind": "branching" if skill.kind == "branch" else skill.kind,
                   "featured": featured, "uses": uses, "rule": skill.record(), "examples": []}
            detailed = []
            for state, output, steps in select_examples(skill, library, 10 if featured else 3):
                row["examples"].append({"expression": f"{skill.name}(s)", "inputs": [encode(state)],
                                        "output": encode(output)})
                detailed.append(steps)
            (step_dir / f"{index}.json").write_text(
                json.dumps(detailed, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            operators.append(row)
        # The simulator's skills are not core Operators, so interest's value-table scorer
        # cannot evaluate them. Select varied, readable state transformations instead.
        from collections import Counter

        rejected = Counter({key: 0 for key in ("undefined", "constant", "near_constant", "no_effect",
                            "unused_argument", "atom_equivalent", "duplicate",
                            "cancelled_constant", "long_sentence", "opaque_sentence", "alias")})
        eligible, seen = [], set()
        for row in operators:
            outputs = [json.dumps(ex["output"], sort_keys=True) for ex in row["examples"]]
            changed = sum(ex["output"] != ex["inputs"][0] for ex in row["examples"])
            row["interest"] = {"score": round(changed / len(outputs), 6) if outputs else 0.0,
                               "method": "sampled_state_change", "defined_share": 1.0}
            if not outputs or all(ex["output"]["t"] == "nan" for ex in row["examples"]):
                rejected["undefined"] += 1
            elif changed == 0:
                rejected["no_effect"] += 1
            elif changed / len(outputs) <= 0.2:
                rejected["near_constant"] += 1
            elif len(set(outputs)) == 1:
                rejected["constant"] += 1
            elif "turn left, then turn right" in row["plain"].lower() or "turn right, then turn left" in row["plain"].lower():
                rejected["cancelled_constant"] += 1
            elif len(row["plain"].split()) > 22:
                rejected["long_sentence"] += 1
            elif tuple(outputs) in seen:
                rejected["duplicate"] += 1
            else:
                seen.add(tuple(outputs))
                eligible.append(row)
        eligible.sort(key=lambda row: (-row["interest"]["score"], row["layer"],
                     len(row["plain"].split())))
        selected = []
        for form in ("composition", "branching", "recursion"):
            match = next((row for row in eligible if row["kind"] == form), None)
            if match:
                selected.append(match)
        for form in ("composition", "branching", "recursion"):
            selected.extend(row for row in eligible if row["kind"] == form and row not in selected
                            and sum(item["kind"] == form for item in selected) < 8)
        selected = selected[:24]
        for row in eligible:
            if len(selected) >= 24:
                break
            if row not in selected:
                selected.append(row)
        curated = [row["name"] for row in selected]
        data = {"world": "action", "seed": seed, "steps": f"action/steps/{seed}/", "title": "Action",
                "title_zh": "行动", "dimension": "action", "atoms": atoms,
                "domain": [{"en": "A value is the state of an 8×8 block map: terrain, block stacks, tools, bridges "
                                  "and a robot with a position, a facing and one hand.",
                            "zh": "取值是一张 8×8 积木地图的状态：地形、积木堆、工具、桥，以及一个有位置、朝向和一只手的机器人。"}],
                "settings": [{"key": "initial_state(width, height, max_height)", "value": "8, 8, 4",
                              "en": "The map size and the highest allowed stack.",
                              "zh": "地图大小和一摞积木允许的最大高度。"},
                             {"key": "generate_skills(action_names, guards)", "value": "6 actions, 6 observations",
                              "en": "The actions and observations that skills are grown from.",
                              "zh": "生成技能时使用的动作和观察。"}],
                "why": {"en": "These atoms are one example. Atoms are chosen by the user: any state action or "
                              "observation with a rule can be registered, and skills grow from it in the same way.",
                        "zh": "这些原子只是一个例子。原子由用户自己选：任何写得出规则的状态动作或观察都能注册，技能会用同样的方式从它长出来。"},
                "operators": operators, "curated": curated, "curation_rejected": dict(rejected),
                "curation_target": 24,
                "curation_not_selected": len(operators) - len(curated) - sum(rejected.values()),
                "z3": "not_expressible", "checks": "bounded_exhaustive_simulation",
                "metrics": _metrics(skills, library)}
        results.append(data)
    add_novelty([data["metrics"] for data in results])
    listing = [{"seed": data["seed"], "file": str(p.relative_to(root)), "metrics": data["metrics"]}
               for data, p in zip(results, paths)]
    for data, p in zip(results, paths):
        data["seeds"] = listing
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return results[0]
