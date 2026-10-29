"""Three typed worlds, each evaluated through the package's registered atoms."""

from opulse.core.presets import register_preset
from opulse.core.semantics import NAN, Semantics
from opulse.worlds.perm import Permutation
from opulse.worlds.grid import grid


def build() -> dict:
    worlds = [
        ("strings", "Strings", "str", "mIx", ("str_reverse", "str_upper"),
         ("↶", "⇧"), ("Reverse", "Uppercase"), ("xIm", "XIM")),
        ("perm", "Permutations", "perm", Permutation((1, 3, 4, 0, 2)),
         ("rotate_right", "perm_reverse"), ("↷", "⥀"),
         ("Rotate right", "Reverse positions"),
         (Permutation((2, 4, 0, 1, 3)), Permutation((2, 0, 4, 3, 1)))),
        ("grid", "Grids", "grid", grid(((1, 0, 2), (0, 3, 0))),
         ("grid_rotate", "grid_reflect_h"), ("↻", "⇋"),
         ("Rotate clockwise", "Reflect columns"),
         (grid(((0, 1), (3, 0), (0, 2))), grid(((1, 0), (0, 3), (2, 0))))),
    ]
    result = []
    for world, title, value_type, initial, atoms, symbols, verbs, expected in worlds:
        register_preset(world)
        operations = Semantics().operations()
        first = operations[atoms[0]](initial)
        second = operations[atoms[1]](first)
        assert first == expected[0] and second == expected[1]
        assert first is not NAN and second is not NAN
        def encode(value):
            if value_type == "str":
                return value
            if value_type == "grid":
                return [list(row) for row in value]
            return list(value)

        cards = None
        if value_type == "perm":
            cards = []
            for permutation in (initial, first, second):
                order = [None] * len(permutation)
                for card, destination in enumerate(permutation):
                    order[destination] = card + 1
                assert sorted(order) == list(range(1, len(permutation) + 1))
                cards.append(order)

        result.append({"id": world, "title": title, "type": value_type,
                       "atoms": list(atoms), "symbols": list(symbols),
                       "verbs": list(verbs),
                       "values": [encode(initial), encode(first), encode(second)],
                       "cards": cards})
    return {"worlds": result}
