"""Assign precedence (``priority``, larger binds tighter) and associativity.

Invariant: all operators sharing a priority level share one associativity, so
the minimal-bracket renderer is unambiguous. Prefix operators may only join
right-associative levels and postfix operators left-associative ones; binary
operators may join any level. Each operator either joins an existing
compatible level or opens a new one, chosen uniformly among the options.

Operators that already have a priority (the hand-written initial set) are
kept; the legacy script reassigned those too. Operators with three or more
arguments are written in call form, which delimits itself; they get no
priority.
"""

from __future__ import annotations

import random
from collections.abc import Iterable

from opulse.core.operator import BINARY, PREFIX, Operator

LEFT, RIGHT = "left", "right"


def assign_priorities(operators: Iterable[Operator], rng: random.Random,
                      max_levels: int | None = None) -> None:
    operators = list(operators)
    levels: dict[int, str] = {
        op.priority: op.associativity_direction for op in operators if op.priority is not None
    }
    for op in operators:
        if op.priority is not None or op.n_ary > BINARY:
            continue
        if op.n_ary == BINARY:
            wanted = None
        else:
            wanted = RIGHT if op.unary_position == PREFIX else LEFT
        options = [level for level, assoc in levels.items() if wanted in (None, assoc)]
        new_level = max(levels, default=0) + 1
        can_open = max_levels is None or len(levels) < max_levels
        if can_open or not options:
            options.append(new_level)
        op.priority = rng.choice(options)
        if op.priority == new_level:
            levels[new_level] = wanted or rng.choice((LEFT, RIGHT))
        op.associativity_direction = levels[op.priority]
