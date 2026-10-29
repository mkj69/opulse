"""Logic world atoms and a reproducible showcase made from generated operators."""

from __future__ import annotations

from itertools import product
from pathlib import Path

from opulse.config import Settings
from opulse.core.operator import Operator
from opulse.core.presets import PRESETS, register_preset
from opulse.core.primitives import atom_records
from opulse.core.registry import OperatorRegistry
from opulse.core.semantics import NAN
from opulse.definition import ast
from opulse.definition.parser import DefinitionParser
from opulse.worlds import preset_config
from opulse.worlds.present import alias


def _value(value):
    if value is NAN:
        return {"t": "nan"}
    if isinstance(value, bool):
        return {"t": "bool", "v": value}
    if isinstance(value, int):
        return {"t": "int", "v": value}
    raise TypeError(f"logic showcase cannot encode {value!r}")


def _circuit(operator: Operator, parser: DefinitionParser, aliases: dict[str, str]) -> dict:
    """A small directed graph of the rendered definition for the browser."""
    definition = parser.parse(operator.definition)
    nodes = [{"id": name, "label": name, "kind": "input", "inputs": []}
             for name in definition.parameters]
    counter = 0

    def node(label: str, kind: str, inputs: list[str]) -> str:
        nonlocal counter
        counter += 1
        key = f"g{counter}"
        nodes.append({"id": key, "label": alias(label, aliases), "kind": kind,
                      "inputs": inputs})
        return key

    def expr(item: ast.Expr) -> str:
        if isinstance(item, ast.Var):
            return item.name
        if isinstance(item, ast.Num):
            return node(str(item.value), "constant", [])
        if isinstance(item, ast.Literal):
            return node(str(item.value).lower(), "constant", [])
        if isinstance(item, ast.NaN):
            return node("NaN", "constant", [])
        kind = "feedback" if item.symbol == operator.symbol else "gate"
        return node(item.symbol, kind, [expr(arg) for arg in item.args])

    def guard(item: ast.Condition) -> str:
        if isinstance(item, ast.Truth):
            return expr(item.expr)
        if isinstance(item, ast.Compare):
            return node(item.op, "guard", [expr(item.left), expr(item.right)])
        if isinstance(item, ast.Not):
            return node("¬", "guard", [guard(item.operand)])
        return node("and" if isinstance(item, ast.And) else "or", "guard",
                    [guard(item.left), guard(item.right)])

    branches = []
    for branch in definition.branches:
        branches.append({"root": expr(branch.expr),
                         "guard": guard(branch.condition) if branch.condition else None})
    output = branches[0]["root"] if len(branches) == 1 else node(
        "select", "choice", [branch["root"] for branch in branches]
        + [branch["guard"] for branch in branches if branch["guard"]])
    return {"nodes": nodes, "output": output, "branches": branches}


def showcase_registry(seed: int = 40):
    """A seeded logic operator set grown over three layers."""
    from opulse.worlds.showcase import grow

    register_preset("logic")
    registry = OperatorRegistry(Operator.from_dict(row) for row in atom_records(PRESETS["logic"], seed=seed))
    settings = Settings.load(preset_config("logic"))
    return settings, registry, grow("logic", settings, registry, seed)


def _truth_rows(op, tools):
    domains = tuple((False, True) if kind == "bool" else range(-4, 5) for kind in op.parameter_types)
    return [{"inputs": [_value(item) for item in values],
             "output": _value(tools.oracle.evaluate(op, values).value)}
            for values in product(*domains)]


def showcase_spec():
    from opulse.worlds.showcase import WHY, WorldSpec, _literal_inputs

    def extra(op, row, tools):
        row["truth_table"] = _truth_rows(op, tools)
        row["circuit"] = _circuit(op, tools.parser, tools.names)

    def step_extra(step, record, tools):
        record["signal"] = _value(tools.oracle.evaluate(step.operator, step.inputs).value)

    def values(kind):
        return (True, False) if kind == "bool" else (2, 0, -3, 1, 3, -1, 4, -2, 5)

    def settings_rows(settings):
        return [("preset", "logic", "The preset that selects these atoms.", "选择这些原子的预设。"),
                ("recursion.direct_bound", settings.recursion.direct_bound,
                 "A recursive call repeats its step at most this many times; larger counts give NaN.",
                 "递归最多重复这么多步，更大的次数得 NaN。"),
                ("operators.max_if_branches", settings.operators.max_if_branches,
                 "The largest number of cases in a branch definition.", "分支定义最多的情形数。")]

    zh = {"add": "a + b 是整数加法。", "sub": "a - b 是整数减法。", "neg": "- a 是 a 的相反数。",
          "logic_and": "a ⋀ b 在 a 和 b 都为真时为真。", "logic_or": "a ⋁ b 在 a 或 b 为真时为真。",
          "logic_not": "¬ a 在 a 为假时为真。", "logic_implies": "a → b 只在 a 为真而 b 为假时为假。",
          "logic_xor": "a ≢ b 在 a 和 b 真假不同时为真。", "logic_equal": "a ⇔ b 在 a 和 b 真假相同时为真。"}
    return WorldSpec(
        "logic", "Logic", "逻辑", "logic", build=showcase_registry, values=values,
        encode=lambda value, kind=None: _value(value), atom_zh=zh,
        atom_examples={"add": (2, 3), "sub": (1, 4), "neg": (3,), "logic_and": (True, False),
                       "logic_or": (True, False), "logic_not": (True,), "logic_implies": (True, False),
                       "logic_xor": (True, False), "logic_equal": (False, False)},
        domain=(("Values are the truth values true and false, plus integers that count recursive steps.",
                 "取值是真和假两个真值，另有整数用来数递归步数。"),),
        settings=settings_rows, why=WHY, seed=40, operator_extra=extra, step_extra=step_extra,
        extra_inputs=_literal_inputs)


def export_world_showcase(world_name: str, out_path: str | Path) -> dict:
    """Write the logic showcase (see :mod:`opulse.worlds.showcase`)."""
    if world_name != "logic":
        raise ValueError(f"unknown world {world_name!r}")
    from opulse.worlds.showcase import export_spec

    return export_spec(showcase_spec(), out_path)
