"""Named numeric starting worlds and their default generation settings."""

from __future__ import annotations

from opulse.core.primitives import CUSTOM, register_primitive

PRESETS = {
    "clock": {
        "atoms": ("add", "sub", "mul", "div", "mod", "neg", "reverse", "triangle",
                  "popcount", "digitsum"),
        "layers": (8, 4),
        "proportions": (0.5, 0.3, 0.2),
        "settings": {
            "semantics": {"mode": "modular", "modulus": 12},
            "operators": {"condition_min": 0, "condition_max": 11,
                          "reject_dead_branches": False},
            "expressions": {"value_min": 0, "value_max": 11},
        },
    },
    "successor": {
        "atoms": ("natural_succ", "natural_pred", "is_zero"),
        "layers": (8, 4),
        "proportions": (0.6, 0.4, 0.0),
        "settings": {
            "operators": {"condition_min": 0, "condition_max": 12},
            "recursion": {"style": "peano", "direct_bound": 5,
                          "step_down": "↓", "step_up": "↑",
                          "nonnegative": True,
                          "constant_min": 0, "constant_max": 0},
            "expressions": {"value_min": 0, "value_max": 12, "max_depth": 2},
        },
    },
    "integer": {
        "atoms": ("add", "sub", "mul", "div", "mod", "neg", "reverse", "triangle",
                  "popcount", "digitsum"),
        "layers": (8, 4),
        "proportions": (0.5, 0.3, 0.2),
        "settings": {},
    },
    "bits": {
        "atoms": ("bit_and", "bit_or", "bit_xor", "shift_left", "shift_right", "bit_count"),
        "layers": (8, 4),
        "proportions": (0.6, 0.4, 0.0),
        "settings": {
            "operators": {"condition_min": 0, "condition_max": 31},
            "recursion": {"style": "bits", "direct_bound": 31, "nonnegative": True,
                          "constant_min": 0, "constant_max": 0},
            "expressions": {"value_min": 0, "value_max": 31, "max_depth": 2},
        },
    },
}


def register_preset(name: str) -> None:
    """Register the atoms needed by a named world, idempotently."""
    if name not in PRESETS:
        raise ValueError(f"unknown preset {name!r}; choose from {', '.join(PRESETS)}")
    if name == "successor":
        definitions = (
            ("natural_succ", "↑", lambda a: a + 1 if a >= 0 else None,
             "a ↑ is a + 1 for a nonnegative integer; negative inputs give NaN."),
            ("natural_pred", "↓", lambda a: max(0, a - 1) if a >= 0 else None,
             "a ↓ is max(0, a - 1) for a nonnegative integer; negative inputs give NaN."),
            ("is_zero", "○", lambda a: int(a == 0) if a >= 0 else None,
             "a ○ is 1 when a is zero and 0 otherwise; negative inputs give NaN."),
        )
        for atom, symbol, compute, rule in definitions:
            if atom not in CUSTOM:
                register_primitive(atom, symbol, compute, rule=rule)
    if name == "bits":
        def nonnegative(fn):
            return lambda a, b: fn(a, b) if a >= 0 and b >= 0 else None

        definitions = (
            ("bit_and", "∧", nonnegative(lambda a, b: a & b), "a ∧ b is bitwise AND on nonnegative integers."),
            ("bit_or", "∨", nonnegative(lambda a, b: a | b), "a ∨ b is bitwise OR on nonnegative integers."),
            ("bit_xor", "⊻", nonnegative(lambda a, b: a ^ b), "a ⊻ b is bitwise XOR on nonnegative integers."),
            ("shift_left", "⇐", nonnegative(lambda a, b: a << b if b <= 31 else None),
             "a ⇐ b shifts nonnegative a left by b bits; counts above 31 give NaN."),
            ("shift_right", "⇒", nonnegative(lambda a, b: a >> b),
             "a ⇒ b shifts nonnegative a right by b bits."),
        )
        for atom, symbol, compute, rule in definitions:
            if atom not in CUSTOM:
                register_primitive(atom, symbol, compute, n_ary=2, position=None, rule=rule)
        if "bit_count" not in CUSTOM:
            register_primitive("bit_count", "♯", lambda a: a.bit_count() if a >= 0 else None,
                               rule="a ♯ counts the one bits of nonnegative a; negative inputs give NaN.")
