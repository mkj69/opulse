"""Range handling and labels for opt-in reference interpreter checks."""

from __future__ import annotations


def resolve_range(configured, cli, bound: int | None) -> tuple[int, int] | None:
    selected = cli if cli is not None else configured
    if selected is None:
        return None
    if len(selected) != 2 or any(type(value) is not int for value in selected):
        raise ValueError("solver.fallback_range needs two integers")
    lo, hi = selected
    if lo > hi:
        raise ValueError("fallback range lower limit exceeds upper limit")
    if bound is not None:
        lo, hi = max(lo, -bound), min(hi, bound)
    if lo > hi:
        raise ValueError("fallback range has no inputs within the semantics bound")
    return lo, hi


def checked_label(domain: tuple[int, int] | list[int]) -> str:
    return f"checked on range [{domain[0]}, {domain[1]}]"
