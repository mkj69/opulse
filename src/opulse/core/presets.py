"""Opt-in typed atom sets for strings, integer lists, logic, permutations, and relations."""

from __future__ import annotations

from opulse.core.primitives import CUSTOM, Primitive, register_primitive
from opulse.core.semantics import NAN, base_operation_name

PRESETS = {
    "logic": (
        "add", "sub", "neg", "logic_and", "logic_or", "logic_not",
        "logic_implies", "logic_xor", "logic_equal",
    ),
    "perm": ("add", "sub", "neg", "swap", "rotate_left", "rotate_right",
             "perm_reverse", "perm_compose", "perm_inverse", "perm_apply", "perm_equal"),
    "grid": ("add", "sub", "mod", "neg", "grid_rotate", "grid_reflect_h",
             "grid_reflect_v", "grid_transpose", "grid_wrap_right", "grid_wrap_down",
             "grid_shift_right", "grid_shift_down", "grid_recolour", "grid_overlay",
             "grid_crop", "grid_count", "grid_fill", "grid_equal"),
    "pitch": ("add", "sub", "mod", "neg", *(
        "pitch_transpose", "pitch_octave_up", "pitch_octave_down", "pitch_interval",
        "pitch_invert", "pitch_retrograde", "pitch_scale_step", "pitch_major_triad",
        "pitch_minor_triad", "pitch_repeat", "pitch_concat", "pitch_melody_equal",
        "pitch_note_equal")),
    "strings": (
        "add",
        "sub",
        "mod",
        "neg",
        "str_concat",
        "str_length",
        "str_reverse",
        "str_first",
        "str_drop",
        "str_upper",
        "str_lower",
        "str_equal",
    ),
    "lists": (
        "add",
        "sub",
        "mod",
        "neg",
        "list_cons",
        "list_head",
        "list_tail",
        "list_length",
        "list_append",
        "list_sum",
        "list_at",
        "list_equal",
    ),
    "rel": ("add", "sub", "mod", "neg", "rel_parent", "rel_colleague",
            "rel_neighbour", "rel_equal"),
}

_REGISTERED: dict[str, Primitive] = {}


def register_preset(name: str, *, cards: int = 5) -> None:
    """Register a world's atoms in the current Python process."""
    if name not in PRESETS:
        raise ValueError(f"unknown preset {name!r}")
    if name == "pitch":
        from opulse.worlds.pitch import register_pitch

        register_pitch()
        return
    if name == "grid":
        from opulse.worlds.grid import register_grid

        register_grid()
        return
    if name == "rel":
        from opulse.worlds.rel import register_atoms

        register_atoms()
        return
    if name == "perm":
        from opulse.worlds.perm import register_perm

        register_perm(cards)
        return
    if name == "logic":
        specs = (
            ("logic_and", "⋀", lambda a, b: a and b, ("bool", "bool"), "bool",
             "a ⋀ b is true exactly when both a and b are true.",
             lambda a, b: __import__("z3").And(a, b)),
            ("logic_or", "⋁", lambda a, b: a or b, ("bool", "bool"), "bool",
             "a ⋁ b is true exactly when a or b is true.",
             lambda a, b: __import__("z3").Or(a, b)),
            ("logic_not", "¬", lambda a: not a, ("bool",), "bool",
             "¬ a is true exactly when a is false.",
             lambda a: __import__("z3").Not(a)),
            ("logic_implies", "→", lambda a, b: not a or b, ("bool", "bool"), "bool",
             "a → b is false exactly when a is true and b is false.",
             lambda a, b: __import__("z3").Implies(a, b)),
            ("logic_xor", "≢", lambda a, b: a != b, ("bool", "bool"), "bool",
             "a ≢ b is true exactly when a and b differ.",
             lambda a, b: __import__("z3").Xor(a, b)),
            ("logic_equal", "⇔", lambda a, b: a == b, ("bool", "bool"), "bool",
             "a ⇔ b is true exactly when a and b have the same truth value.",
             lambda a, b: a == b),
        )
    elif name == "strings":
        specs = (
            (
                "str_concat",
                "⊕",
                lambda a, b: a + b,
                ("str", "str"),
                "str",
                "a ⊕ b joins string a followed by string b.",
                lambda a, b: __import__("z3").Concat(a, b),
            ),
            (
                "str_length",
                "ℓ",
                len,
                ("str",),
                "int",
                "a ℓ is the number of characters in string a.",
                lambda a: __import__("z3").Length(a),
            ),
            (
                "str_reverse",
                "↶",
                lambda a: a[::-1],
                ("str",),
                "str",
                "a ↶ reverses the characters in string a.",
                None,
            ),
            (
                "str_first",
                "⌑",
                lambda a: a[:1],
                ("str",),
                "str",
                "a ⌑ is its first character, or the empty string when a is empty.",
                lambda a: __import__("z3").SubString(a, 0, 1),
            ),
            (
                "str_drop",
                "⇥",
                lambda a: a[1:],
                ("str",),
                "str",
                "a ⇥ removes its first character; the empty string stays empty.",
                lambda a: __import__("z3").SubString(a, 1, __import__("z3").Length(a)),
            ),
            (
                "str_upper",
                "⇧",
                str.upper,
                ("str",),
                "str",
                "a ⇧ changes each lowercase letter in a to uppercase.",
                None,
            ),
            (
                "str_lower",
                "⇩",
                str.lower,
                ("str",),
                "str",
                "a ⇩ changes each uppercase letter in a to lowercase.",
                None,
            ),
            (
                "str_equal",
                "≡",
                lambda a, b: a == b,
                ("str", "str"),
                "bool",
                "a ≡ b is true exactly when strings a and b have the same characters.",
                lambda a, b: a == b,
            ),
        )
    else:
        specs = (
            (
                "list_cons",
                "⊲",
                lambda a, b: (a, *b),
                ("int", "list[int]"),
                "list[int]",
                "a ⊲ b places integer a before the elements of list b.",
                lambda a, b: __import__("z3").Concat(__import__("z3").Unit(a), b),
            ),
            (
                "list_head",
                "⌃",
                lambda a: a[0] if a else NAN,
                ("list[int]",),
                "int",
                "a ⌃ is the first integer in a; an empty list gives NaN.",
                None,
            ),
            (
                "list_tail",
                "⌄",
                lambda a: a[1:],
                ("list[int]",),
                "list[int]",
                "a ⌄ removes the first element of a; an empty list stays empty.",
                lambda a: __import__("z3").SubSeq(a, 1, __import__("z3").Length(a)),
            ),
            (
                "list_length",
                "ℒ",
                len,
                ("list[int]",),
                "int",
                "a ℒ is the number of integers in list a.",
                lambda a: __import__("z3").Length(a),
            ),
            (
                "list_append",
                "⊞",
                lambda a, b: (*a, *b),
                ("list[int]", "list[int]"),
                "list[int]",
                "a ⊞ b joins list a followed by list b.",
                lambda a, b: __import__("z3").Concat(a, b),
            ),
            (
                "list_sum",
                "Σ",
                sum,
                ("list[int]",),
                "int",
                "a Σ is the sum of the integers in list a.",
                None,
            ),
            (
                "list_at",
                "⊙",
                lambda a, b: a[b] if 0 <= b < len(a) else NAN,
                ("list[int]", "int"),
                "int",
                ("a ⊙ b is element b of a, counting from zero; "
                 "an invalid index gives NaN."),
                None,
            ),
            (
                "list_equal",
                "≍",
                lambda a, b: a == b,
                ("list[int]", "list[int]"),
                "bool",
                ("a ≍ b is true exactly when lists a and b have the same "
                 "elements in order."),
                lambda a, b: a == b,
            ),
        )
    for atom_name, symbol, fn, inputs, output, rule, encode in specs:
        existing = CUSTOM.get(atom_name)
        if existing is not None:
            if existing is _REGISTERED.get(atom_name):
                continue
            raise ValueError(f"preset atom {atom_name!r} collides with a registered atom")
        _REGISTERED[atom_name] = register_primitive(
                atom_name,
                symbol,
                fn,
                n_ary=len(inputs),
                rule=rule,
                parameter_types=inputs,
                result_type=output,
                z3=encode,
            )


def register_for_symbol(
    symbol: str, parameter_types: tuple[str, ...] | list[str] | None,
    primitive_name: str | None = None,
    n_ary: int | None = None,
    unary_position: str | None = None,
    result_type: str = "int",
) -> None:
    """Load a preset when its persisted typed initial operator is encountered."""
    if primitive_name is not None:
        from opulse.core.primitives import BUILT_IN_RULES

        permutation_types = [kind for kind in (parameter_types or ()) if kind.startswith("perm[")]
        if permutation_types and primitive_name in PRESETS["perm"]:
            from opulse.core.types import parse_type

            register_preset("perm", cards=parse_type(permutation_types[0]).size)
        for preset_name, atom_names in PRESETS.items():
            if primitive_name in atom_names and primitive_name not in BUILT_IN_RULES:
                if preset_name != "perm" or not permutation_types:
                    register_preset(preset_name)
                break
        if primitive_name not in BUILT_IN_RULES and primitive_name not in CUSTOM:
            from opulse.presets import PRESETS as NUMERIC_PRESETS, register_preset as register_numeric_preset

            for preset_name, preset in NUMERIC_PRESETS.items():
                if primitive_name in preset["atoms"]:
                    register_numeric_preset(preset_name)
                    break
        if primitive_name not in BUILT_IN_RULES and primitive_name not in CUSTOM:
            raise ValueError(f"unknown primitive {primitive_name!r}; load its plugin first")
        actual = base_operation_name(symbol, n_ary, unary_position)
        if actual != primitive_name:
            raise ValueError(f"primitive {primitive_name!r} does not match symbol {symbol!r}")
        if primitive_name in CUSTOM:
            primitive = CUSTOM[primitive_name]
            if (tuple(parameter_types or ("int",) * n_ary) != primitive.parameter_types
                    or result_type != primitive.result_type):
                raise ValueError(f"primitive {primitive_name!r} has a different type signature")
        return
    if parameter_types is None or all(kind == "int" for kind in parameter_types):
        return
    if symbol in {"♯", "⇈", "⇊", "⟷", "⇅", "⟲", "♬", "△", "▽", "⥁", "⋈", "≎", "≐"}:
        if "pitch_scale_step" not in CUSTOM:
            register_preset("pitch")
        return
    if "grid" in parameter_types:
        register_preset("grid")
        return
    if symbol in {"⋀", "⋁", "¬", "→", "≢", "⇔"} and "bool" in parameter_types:
        register_preset("logic")
    elif symbol in {"⊕", "↶", "⌑", "⇥", "⇧", "⇩"} or (
        symbol == "ℓ" and tuple(parameter_types) == ("str",)
    ):
        register_preset("strings")
    elif symbol in {"⊲", "⌃", "⌄", "⊞", "Σ", "⊙", "ℒ", "≍"}:
        register_preset("lists")
    elif symbol == "≡":
        register_preset("strings" if parameter_types[0] == "str" else "lists")
    elif symbol in {"⤨", "⤺", "↷", "⥀", "∘", "⤾", "◎", "≋"} and any(
        kind.startswith("perm[") for kind in parameter_types
    ):
        from opulse.core.types import parse_type

        cards = next(parse_type(kind).size for kind in parameter_types if kind.startswith("perm["))
        register_preset("perm", cards=cards)
    elif symbol in {"↟", "↝", "↔", "≟"}:
        register_preset("rel")
