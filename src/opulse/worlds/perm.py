"""Permutations of labelled cards, represented by their destination positions.

``p[i]`` is the destination of the card that began at position ``i``. Thus
``compose(p, q)[i] == q[p[i]]``: first move by ``p``, then by ``q``.
"""

from __future__ import annotations

from pathlib import Path

from opulse.core.primitives import CUSTOM, register_primitive
from opulse.core.semantics import NAN


class Permutation(tuple):
    """A bijection of ``range(n)``. Instances stay distinct from integer lists."""

    def __new__(cls, positions):
        values = tuple(positions)
        if (len(values) < 2 or any(type(value) is not int for value in values)
                or set(values) != set(range(len(values)))):
            raise ValueError("a permutation must contain each position exactly once")
        return super().__new__(cls, values)


def swap(p: Permutation, pair: int) -> Permutation | object:
    """Swap cards at two positions encoded as ``first * n + second``."""
    n = len(p)
    first, second = divmod(pair, n)
    if not 0 <= first < n or not 0 <= second < n:
        return NAN
    return Permutation(second if x == first else first if x == second else x for x in p)


def rotate_left(p: Permutation) -> Permutation:
    n = len(p)
    return Permutation((x - 1) % n for x in p)


def rotate_right(p: Permutation) -> Permutation:
    n = len(p)
    return Permutation((x + 1) % n for x in p)


def reverse(p: Permutation) -> Permutation:
    n = len(p)
    return Permutation(n - 1 - x for x in p)


def compose(p: Permutation, q: Permutation) -> Permutation | object:
    if len(p) != len(q):
        return NAN
    return Permutation(q[x] for x in p)


def inverse(p: Permutation) -> Permutation:
    values = [0] * len(p)
    for card, position in enumerate(p):
        values[position] = card
    return Permutation(values)


def apply(p: Permutation, position: int) -> int | object:
    return p[position] if 0 <= position < len(p) else NAN


def register_perm(n: int = 5) -> tuple[str, ...]:
    """Register the permutation atoms for exactly ``n`` cards."""
    if not 2 <= n <= 26:
        raise ValueError("cards must be between 2 and 26")
    kind = f"perm[{n}]"
    specs = (
        ("swap", "⤨", swap, (kind, "int"), kind,
         f"a ⤨ b swaps cards at positions b / {n} and b % {n}, counting from zero; an invalid position gives NaN.", None),
        ("rotate_left", "⤺", rotate_left, (kind,), kind,
         "a ⤺ moves every card one position left, wrapping the first position to the last.", None),
        ("rotate_right", "↷", rotate_right, (kind,), kind,
         "a ↷ moves every card one position right, wrapping the last position to the first.", None),
        ("perm_reverse", "⥀", reverse, (kind,), kind,
         "a ⥀ reverses the positions of all cards.", None),
        ("perm_compose", "∘", compose, (kind, kind), kind,
         "a ∘ b moves each card by a first and then by b; the result at card i is b[a[i]].", None),
        ("perm_inverse", "⤾", inverse, (kind,), kind,
         "a ⤾ sends each card back to its original position; its value at i is the card at position i in a.", None),
        ("perm_apply", "◎", apply, (kind, "int"), "int",
         "a ◎ b is the final position of card b under a; an invalid card number gives NaN.", None),
        ("perm_equal", "≋", lambda a, b: a == b, (kind, kind), "bool",
         "a ≋ b is true exactly when both permutations send every card to the same position.",
         None),
    )
    names = ("add", "sub", "neg", *(item[0] for item in specs))
    for name, symbol, fn, inputs, output, rule, encode in specs:
        previous = CUSTOM.get(name)
        if previous is not None and previous.parameter_types == inputs:
            continue
        register_primitive(name, symbol, fn, n_ary=len(inputs), rule=rule,
                           parameter_types=inputs, result_type=output, z3=encode)
    return names


def _value(value):
    if value is NAN or value is None:
        return {"t": "nan"}
    if isinstance(value, Permutation):
        return {"t": "perm", "v": list(value)}
    if isinstance(value, bool):
        return {"t": "bool", "v": value}
    if isinstance(value, int):
        return {"t": "int", "v": value}
    raise TypeError(value)


PERM_ZH = {
    "add": "a + b 是整数加法。", "sub": "a - b 是整数减法。", "neg": "- a 是 a 的相反数。",
    "swap": "a ⤨ b 交换位置 b / 5 和 b % 5 上的两张卡片（位置从零数），位置无效时得 NaN。",
    "rotate_left": "a ⤺ 让每张卡片向左移一格，最左边的卡片绕到最右边。",
    "rotate_right": "a ↷ 让每张卡片向右移一格，最右边的卡片绕到最左边。",
    "perm_reverse": "a ⥀ 把所有卡片的位置顺序倒过来。",
    "perm_compose": "a ∘ b 先按 a 移动卡片，再按 b 移动。",
    "perm_inverse": "a ⤾ 把每张卡片送回原来的位置。",
    "perm_apply": "a ◎ b 是卡片 b 在 a 下最后到达的位置，卡片编号无效时得 NaN。",
    "perm_equal": "a ≋ b 在两个排列把每张卡片送到同一位置时为真。",
}


def showcase_registry(seed: int = 32):
    """A seeded operator set over five cards, grown over three layers."""
    from opulse.config import Settings
    from opulse.core.operator import Operator
    from opulse.core.primitives import atom_records
    from opulse.core.registry import OperatorRegistry
    from opulse.worlds.showcase import grow

    names = register_perm(5)
    registry = OperatorRegistry(Operator.from_dict(row) for row in atom_records(names, seed=seed))
    settings = Settings.from_dict({"recursion": {"style": "direct", "direct_bound": 3}})
    return settings, registry, grow("perm", settings, registry, seed)


def _perm_text(value, kind):
    if isinstance(value, Permutation):
        return "[" + ", ".join(map(str, value)) + "]"
    return None


def showcase_spec():
    from opulse.worlds.showcase import WHY, WorldSpec, _literal_inputs

    cards = (Permutation((1, 2, 0, 4, 3)), Permutation(range(5)), Permutation((4, 3, 2, 1, 0)),
             Permutation((1, 2, 3, 4, 0)), Permutation((0, 1, 4, 2, 3)), Permutation((2, 0, 1, 3, 4)),
             Permutation((3, 4, 0, 1, 2)))

    def values(kind):
        if kind.startswith("perm["):
            return cards
        if kind == "bool":
            return (True, False)
        return (7, 2, 13, 0, 3, 24, -1, 19, 4, -3, 1, 6)

    def settings_rows(settings):
        return [("cards", 5, "The number of cards; register_perm(n) accepts 2 to 26.",
                 "卡片张数，register_perm(n) 可取 2 到 26。"),
                ("recursion.direct_bound", settings.recursion.direct_bound,
                 "A recursive call repeats its card move at most this many times; larger counts give NaN.",
                 "递归最多重复这么多次移动，更大的次数得 NaN。")]

    p, q = Permutation((1, 2, 0, 4, 3)), Permutation((4, 3, 2, 1, 0))
    return WorldSpec(
        "perm", "Permutation cards", "排列卡片", "order", build=showcase_registry, values=values,
        encode=lambda value, kind=None: _value(value), atom_zh=PERM_ZH,
        atom_examples={"add": (2, 3), "sub": (4, 1), "neg": (3,), "swap": (p, 7), "rotate_left": (p,),
                       "rotate_right": (p,), "perm_reverse": (p,), "perm_compose": (p, q),
                       "perm_inverse": (p,), "perm_apply": (p, 2), "perm_equal": (p, q)},
        domain=(("A value is an arrangement of five cards. The list gives, for each card, the position it moves to.",
                 "取值是五张卡片的一种排列。列表给出每张卡片移到的位置。"),
                ("Integers choose positions and count recursive steps.", "整数用来选位置和数递归步数。")),
        settings=settings_rows, why=WHY, seed=32, value_text=_perm_text, extra_inputs=_literal_inputs)


def export_world_showcase(world_name: str, out_path: str | Path) -> dict:
    """Write the permutation showcase (see :mod:`opulse.worlds.showcase`)."""
    if world_name != "perm":
        raise ValueError(world_name)
    from opulse.worlds.showcase import export_spec

    return export_spec(showcase_spec(), out_path)
