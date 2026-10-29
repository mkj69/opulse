"""Writing integers in an arbitrary base, optionally tagged with a base marker.

A numeral-base marker is a registered prefix operator with ``is_base == n``;
``⊺⇮1A`` then means "the digits 1A read in base n". Markers are pure notation:
they have no compute code and never appear inside operator definitions.
"""

from __future__ import annotations

from opulse.core.registry import OperatorRegistry
from opulse.core.semantics import NAN


def to_base(value: int, base: int, digits: str) -> str:
    if not 2 <= base <= len(digits):
        raise ValueError(f"base {base} outside 2..{len(digits)}")
    if value == 0:
        return digits[0]
    sign = "-" if value < 0 else ""
    value = abs(value)
    out = []
    while value:
        value, remainder = divmod(value, base)
        out.append(digits[remainder])
    return sign + "".join(reversed(out))


def from_base(text: str, base: int, digits: str) -> int:
    if not 2 <= base <= len(digits):
        raise ValueError(f"base {base} outside 2..{len(digits)}")
    sign = -1 if text.startswith("-") else 1
    body = text[1:] if sign < 0 else text
    if not body or "-" in body:
        raise ValueError(f"invalid numeral {text!r}")
    value = 0
    for char in body:
        try:
            index = digits.index(char)
        except ValueError:
            raise ValueError(f"digit {char!r} invalid in base {base}") from None
        if index >= base:
            raise ValueError(f"digit {char!r} invalid in base {base}")
        value = value * base + index
    return sign * value


class NumeralWriter:
    """Formats integers as ``<marker><digits>`` using the registry's base markers."""

    def __init__(self, registry: OperatorRegistry, digits: str, use_markers: bool = True,
                 nan: str = "NaN") -> None:
        self.digits = digits
        self.use_markers = use_markers
        self.nan = nan
        self._markers = {op.is_base: op.symbol for op in registry if op.is_base is not None}

    def write(self, value, base: int = 10) -> str:
        if value is NAN:
            return self.nan
        if not isinstance(value, int) or isinstance(value, bool):
            from opulse.core.types import literal

            return literal(value)
        body = to_base(abs(value), base, self.digits)
        marker = self._markers.get(base, "") if self.use_markers else ""
        # The sign goes before the marker: "-⊺⇮1A" reads as unary minus applied to a marked numeral.
        return f"{'-' if value < 0 else ''}{marker}{body}"
