"""Value types shared by atoms, operators, and expression generation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ValueType:
    name: str
    element: ValueType | None = None
    size: int | None = None

    def __str__(self) -> str:
        if self.name == "list":
            return f"list[{self.element}]"
        return f"perm[{self.size}]" if self.name == "perm" else self.name


INT = ValueType("int")
BOOL = ValueType("bool")
STR = ValueType("str")
LIST_INT = ValueType("list", INT)
GRID = ValueType("grid")
NOTE = ValueType("note")
MELODY = ValueType("melody")


def _melody(value: object) -> bool:
    return isinstance(value, (tuple, list)) and all(
        isinstance(item, (tuple, list)) and len(item) == 2
        and isinstance(item[0], int) and not isinstance(item[0], bool)
        and 0 <= item[0] <= 127
        and isinstance(item[1], int) and not isinstance(item[1], bool)
        and item[1] > 0
        for item in value
    )
STATE = ValueType("state")
COLOUR = ValueType("colour")
DIRECTION = ValueType("direction")


def parse_type(text: str | ValueType) -> ValueType:
    if isinstance(text, ValueType):
        text = str(text)
    if text in ("int", "bool", "str", "grid", "note", "melody", "state", "colour", "direction"):
        return {"int": INT, "bool": BOOL, "str": STR, "grid": GRID, "note": NOTE, "melody": MELODY,
                "state": STATE, "colour": COLOUR, "direction": DIRECTION}[text]
    if text == "list[int]":
        return LIST_INT
    if text.startswith("perm[") and text.endswith("]"):
        size = int(text[5:-1])
        if size < 2:
            raise ValueError("a permutation needs at least two cards")
        return ValueType("perm", size=size)
    raise ValueError(f"unknown value type {text!r}")


def type_of(value: object) -> ValueType:
    if getattr(value, "__opulse_value_type__", None) in ("state", "colour", "direction"):
        return parse_type(value.__opulse_value_type__)
    from opulse.worlds.perm import Permutation

    if isinstance(value, Permutation):
        return ValueType("perm", size=len(value))
    if isinstance(value, bool):
        return BOOL
    if isinstance(value, int):
        return INT
    if isinstance(value, str):
        return STR
    if isinstance(value, (tuple, list)):
        from opulse.core.primitives import CUSTOM

        if "grid_rotate" in CUSTOM:
            from opulse.worlds.grid import valid_grid

            if valid_grid(value):
                return GRID
        if not value:
            return LIST_INT
        if _melody(value):
            return MELODY
        first = type_of(value[0])
        if any(type_of(item) != first for item in value[1:]):
            raise TypeError("list elements must have one type")
        return ValueType("list", first)
    raise TypeError(f"unsupported value {value!r}")


def matches(value: object, expected: ValueType | str) -> bool:
    expected = parse_type(expected)
    if expected == NOTE:
        return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 127
    if expected == MELODY:
        return _melody(value)
    if expected.name == "list" and isinstance(value, (tuple, list)) and not value:
        return True
    try:
        return type_of(value) == expected
    except TypeError:
        return False


def literal(value: object) -> str:
    from opulse.worlds.perm import Permutation

    if isinstance(value, Permutation):
        return "P[" + ", ".join(map(str, value)) + "]"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        import json

        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (tuple, list)):
        return "[" + ", ".join(literal(item) for item in value) + "]"
    return str(value)


def same_value(left: object, right: object) -> bool:
    """Compare values without treating a boolean as an integer."""
    from opulse.core.semantics import NAN

    if left is NAN or right is NAN:
        return left is right
    from opulse.worlds.perm import Permutation

    if isinstance(left, Permutation) or isinstance(right, Permutation):
        return isinstance(left, Permutation) and isinstance(right, Permutation) and tuple(left) == tuple(right)
    if isinstance(left, (tuple, list)) and isinstance(right, (tuple, list)):
        return len(left) == len(right) and all(
            same_value(a, b) for a, b in zip(left, right)
        )
    return type(left) is type(right) and left == right


def freeze(value: object) -> object:
    """Use immutable tuples for list values inside expression trees and caches."""
    from opulse.worlds.perm import Permutation

    if isinstance(value, Permutation):
        return value
    if isinstance(value, (list, tuple)):
        return tuple(freeze(item) for item in value)
    return value
