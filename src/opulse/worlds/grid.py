"""Small ARC-palette grids and their atomic operations.

Grid values are immutable rectangular tuples of rows. Zero is the background.
An empty crop is represented by a single zero cell, keeping every value a grid.
"""

from __future__ import annotations

from pathlib import Path

from opulse.core.primitives import CUSTOM, atom_records, register_primitive
from opulse.core.semantics import NAN

GRID_ATOMS = (
    "grid_rotate", "grid_reflect_h", "grid_reflect_v", "grid_transpose",
    "grid_wrap_right", "grid_wrap_down", "grid_shift_right", "grid_shift_down",
    "grid_recolour", "grid_overlay", "grid_crop", "grid_count", "grid_fill",
    "grid_equal",
)


def valid_grid(value: object) -> bool:
    return (
        isinstance(value, (tuple, list))
        and 1 <= len(value) <= 10
        and all(isinstance(row, (tuple, list)) for row in value)
        and 1 <= len(value[0]) <= 10
        and all(len(row) == len(value[0]) for row in value)
        and all(type(cell) is int and 0 <= cell <= 9 for row in value for cell in row)
    )


def grid(value):
    if not valid_grid(value):
        raise ValueError("grid needs 1 to 10 rectangular rows and columns of colours 0 to 9")
    return tuple(tuple(row) for row in value)


def rotate(value):
    return tuple(tuple(row) for row in zip(*value[::-1]))


def reflect_h(value):
    return tuple(tuple(reversed(row)) for row in value)


def reflect_v(value):
    return tuple(tuple(row) for row in value[::-1])


def transpose(value):
    return tuple(tuple(row) for row in zip(*value))


def translate(value, amount: int, *, axis: int, wrap: bool):
    height, width = len(value), len(value[0])
    result = [[0] * width for _ in range(height)]
    for y, row in enumerate(value):
        for x, colour in enumerate(row):
            ny, nx = (y + amount, x) if axis == 0 else (y, x + amount)
            if wrap:
                ny, nx = ny % height, nx % width
            if 0 <= ny < height and 0 <= nx < width:
                result[ny][nx] = colour
    return grid(result)


def recolour(value, code: int):
    if not 0 <= code <= 99:
        return NAN
    source, target = divmod(code, 10)
    return tuple(tuple(target if cell == source else cell for cell in row) for row in value)


def overlay(first, second):
    if len(first) != len(second) or len(first[0]) != len(second[0]):
        return NAN
    return tuple(tuple(b if b else a for a, b in zip(row_a, row_b))
                 for row_a, row_b in zip(first, second))


def crop(value):
    points = [(y, x) for y, row in enumerate(value) for x, cell in enumerate(row) if cell]
    if not points:
        return ((0,),)
    ys, xs = zip(*points)
    return tuple(tuple(row[min(xs):max(xs) + 1]) for row in value[min(ys):max(ys) + 1])


def count(value, colour: int):
    return sum(cell == colour for row in value for cell in row) if 0 <= colour <= 9 else NAN


def fill(value, colour: int):
    if not 0 <= colour <= 9:
        return NAN
    return tuple(tuple(cell if cell else colour for cell in row) for row in value)


def text(value) -> str:
    """Compact prompt display: rows of palette digits, separated by newlines."""
    return "\n".join("".join(map(str, row)) for row in value)


def register_grid() -> None:
    """Register every grid atom in the current process."""
    specs = (
        ("grid_rotate", "↻", rotate, ("grid",), "grid", "a ↻ rotates grid a clockwise by 90 degrees."),
        ("grid_reflect_h", "⇋", reflect_h, ("grid",), "grid", "a ⇋ reverses the columns of grid a."),
        ("grid_reflect_v", "↕", reflect_v, ("grid",), "grid", "a ↕ reverses the rows of grid a."),
        ("grid_transpose", "⤢", transpose, ("grid",), "grid", "a ⤢ exchanges rows and columns of grid a."),
        ("grid_wrap_right", "⇝", lambda a, b: translate(a, b, axis=1, wrap=True), ("grid", "int"), "grid", "a ⇝ b moves grid a right by b columns, wrapping at the edge."),
        ("grid_wrap_down", "⇟", lambda a, b: translate(a, b, axis=0, wrap=True), ("grid", "int"), "grid", "a ⇟ b moves grid a down by b rows, wrapping at the edge."),
        ("grid_shift_right", "⇢", lambda a, b: translate(a, b, axis=1, wrap=False), ("grid", "int"), "grid", "a ⇢ b moves grid a right by b columns and fills exposed cells with 0."),
        ("grid_shift_down", "⇣", lambda a, b: translate(a, b, axis=0, wrap=False), ("grid", "int",), "grid", "a ⇣ b moves grid a down by b rows and fills exposed cells with 0."),
        ("grid_recolour", "♧", recolour, ("grid", "int"), "grid", "a ♧ b replaces colour b / 10 rounded down with colour b % 10 in grid a; b outside 0 to 99 gives NaN."),
        ("grid_overlay", "▣", overlay, ("grid", "grid"), "grid", "a ▣ b places nonzero cells of b over a; unequal shapes give NaN."),
        ("grid_crop", "⌗", crop, ("grid",), "grid", "a ⌗ crops to the smallest box containing nonzero cells; an all-zero grid gives [[0]]."),
        ("grid_count", "№", count, ("grid", "int"), "int", "a № b counts cells of colour b in grid a; b outside 0 to 9 gives NaN."),
        ("grid_fill", "▧", fill, ("grid", "int"), "grid", "a ▧ b replaces zero cells of grid a with colour b; b outside 0 to 9 gives NaN."),
        ("grid_equal", "≣", lambda a, b: grid(a) == grid(b), ("grid", "grid"), "bool", "a ≣ b is true exactly when both grids have the same shape and colours."),
    )
    for name, symbol, fn, inputs, output, rule in specs:
        if name not in CUSTOM:
            register_primitive(name, symbol, fn, n_ary=len(inputs), position="postfix",
                               rule=rule, parameter_types=inputs, result_type=output)


def make_registry(seed: int = 34):
    from opulse.core.operator import Operator
    from opulse.core.registry import OperatorRegistry
    register_grid()
    return OperatorRegistry(Operator.from_dict(row) for row in atom_records(
        ("add", "sub", "mod", "neg", *GRID_ATOMS), seed=seed))


def encode_value(value):
    if value is NAN:
        return {"t": "nan"}
    if valid_grid(value):
        return {"t": "grid", "v": [list(row) for row in value]}
    if isinstance(value, bool):
        return {"t": "bool", "v": value}
    if isinstance(value, int):
        return {"t": "int", "v": value}
    raise TypeError(f"unsupported showcase value {value!r}")


GRID_ZH = {
    "add": "a + b 是整数加法。", "sub": "a - b 是整数减法。", "mod": "a % b 是余数，符号与 a 相同，b = 0 时得 NaN。",
    "neg": "- a 是 a 的相反数。",
    "grid_rotate": "a ↻ 把网格 a 顺时针转 90 度。", "grid_reflect_h": "a ⇋ 把网格 a 左右翻转。",
    "grid_reflect_v": "a ↕ 把网格 a 上下翻转。", "grid_transpose": "a ⤢ 交换网格 a 的行和列。",
    "grid_wrap_right": "a ⇝ b 把网格 a 向右循环移动 b 列，出界的格子从左边回来。",
    "grid_wrap_down": "a ⇟ b 把网格 a 向下循环移动 b 行，出界的格子从上边回来。",
    "grid_shift_right": "a ⇢ b 把网格 a 向右平移 b 列，空出的格子填 0。",
    "grid_shift_down": "a ⇣ b 把网格 a 向下平移 b 行，空出的格子填 0。",
    "grid_recolour": "a ♧ b 把颜色 b / 10（向下取整）换成颜色 b % 10，b 不在 0 到 99 时得 NaN。",
    "grid_overlay": "a ▣ b 把 b 的非零格子盖到 a 上，形状不同时得 NaN。",
    "grid_crop": "a ⌗ 裁到包含全部非零格子的最小矩形，全零网格得 [[0]]。",
    "grid_count": "a № b 数网格 a 中颜色 b 的格子，b 不在 0 到 9 时得 NaN。",
    "grid_fill": "a ▧ b 用颜色 b 填满网格 a 的零格，b 不在 0 到 9 时得 NaN。",
    "grid_equal": "a ≣ b 在两个网格形状和颜色都相同时为真。",
}


def _pattern(height, width, rule):
    return tuple(tuple(rule(y, x) % 10 for x in range(width)) for y in range(height))


SHOWCASE_GRIDS = (
    _pattern(3, 3, lambda y, x: 2 if (y, x) in ((0, 0), (1, 0), (2, 0), (2, 1)) else 0),  # an L
    _pattern(4, 4, lambda y, x: 1 if x == y else 3 if x + y == 3 else 0),  # two diagonals
    _pattern(5, 5, lambda y, x: 4 if (x + y) % 2 == 0 else 0),  # a checkerboard
    _pattern(6, 6, lambda y, x: 6 if y in (0, 5) or x in (0, 5) else (5 if (y, x) == (2, 3) else 0)),  # a frame
    _pattern(4, 7, lambda y, x: 7 if y == 1 else (8 if x == 5 else 0)),  # a cross of stripes
    _pattern(8, 8, lambda y, x: 9 if (y - 3.5) ** 2 + (x - 3.5) ** 2 < 7 else (1 if x == 0 else 0)),  # a disc
    _pattern(3, 5, lambda y, x: 3 if x == y + 1 or (y == 1 and x == 4) else 0),  # an arrow
    _pattern(5, 3, lambda y, x: (y + 1) if x == 1 else 0),  # a colour ladder
    _pattern(7, 6, lambda y, x: 2 if 1 <= y <= 3 and 1 <= x <= 3 else (5 if y >= 5 and x >= 4 else 0)),
)


def showcase_registry(seed: int = 34):
    """A seeded grid operator set grown over three layers."""
    from opulse.config import Settings
    from opulse.worlds.showcase import grow

    registry = make_registry(seed)
    settings = Settings()
    return settings, registry, grow("grid", settings, registry, seed)


def _grid_text(value, kind):
    if valid_grid(value) and kind in (None, "grid"):
        size = f"{len(value)}×{len(value[0])}"
        cells = "/".join("".join(map(str, row)) for row in value)
        return f"the {size} grid {cells}", f"{size} 网格 {cells}"
    return None


def showcase_spec():
    from opulse.worlds.showcase import WHY, WorldSpec, _literal_inputs

    def values(kind):
        if kind == "grid":
            return SHOWCASE_GRIDS
        if kind == "bool":
            return (True, False)
        return (2, 1, 3, 12, 47, 5, 0, 9, 24, 4, -1, 30)

    def settings_rows(settings):
        return [("grid size", "1 to 10 rows and columns", "Any rectangle up to 10 by 10 is a value.",
                 "任何不超过 10 乘 10 的矩形都是一个值。"),
                ("colours", "0 to 9", "Ten colours in the ARC palette; 0 is the empty background.",
                 "ARC 调色板的 10 种颜色，0 是空背景。"),
                ("recursion.direct_bound", settings.recursion.direct_bound,
                 "A recursive call repeats its grid step at most this many times; larger counts give NaN.",
                 "递归最多重复这么多步，更大的次数得 NaN。")]

    sample = ((1, 2), (3, 0))
    other = ((1, 0, 2), (3, 4, 0))
    return WorldSpec(
        "grid", "Grids", "网格", "vision", build=showcase_registry, values=values,
        encode=lambda value, kind=None: encode_value(value), atom_zh=GRID_ZH,
        atom_examples={"add": (2, 3), "sub": (4, 1), "mod": (7, 3), "neg": (3,),
                       "grid_rotate": (sample,), "grid_reflect_h": (sample,), "grid_reflect_v": (sample,),
                       "grid_transpose": (other,), "grid_wrap_right": (other, 2), "grid_wrap_down": (sample, 1),
                       "grid_shift_right": (other, 2), "grid_shift_down": (sample, 1),
                       "grid_recolour": (sample, 12), "grid_overlay": (sample, ((0, 5), (0, 0))),
                       "grid_crop": (((0, 0, 0), (0, 1, 0), (0, 0, 2)),), "grid_count": (sample, 2),
                       "grid_fill": (sample, 5), "grid_equal": (sample, sample)},
        domain=(("A value is a grid of 1 to 10 rows and columns with colours 0 to 9; 0 is the background.",
                 "取值是 1 到 10 行、1 到 10 列的网格，颜色为 0 到 9，0 是背景。"),
                ("Integers give shifts, colours, colour codes and recursive counts.",
                 "整数用作平移量、颜色、换色编码和递归次数。")),
        settings=settings_rows, why=WHY, seed=34, value_text=_grid_text, extra_inputs=_literal_inputs)


def export_world_showcase(world_name: str, out_path: str | Path) -> dict:
    """Write the grid showcase (see :mod:`opulse.worlds.showcase`)."""
    if world_name != "grid":
        raise ValueError(f"expected grid world, got {world_name!r}")
    from opulse.worlds.showcase import export_spec

    return export_spec(showcase_spec(), out_path)
