"""Value domain and base operations (docs/reference/semantics.md, sections 1-3).

Every backend gets its base operations from :class:`Semantics`, so there is a
single implementation of the arithmetic. Values are Python ints or the
undefined value :data:`NAN`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from opulse.core.operator import BINARY, POSTFIX, PREFIX

DEFAULT_BOUND = 2**31 - 1
EXACT = "exact"
LEGACY = "legacy"
MODULAR = "modular"
MODES = (EXACT, LEGACY, MODULAR)


class _Undefined:
    """The undefined value. A singleton; compare with ``is``."""

    _instance: _Undefined | None = None

    def __new__(cls) -> _Undefined:  # noqa: PYI034 - keep Python 3.10 dependency-free
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "NaN"

    def __reduce__(self):  # keep the singleton across pickling (multiprocessing)
        return (_Undefined, ())

    def __bool__(self) -> bool:
        raise TypeError("the undefined value has no truth value; test it with `is NAN`")


NAN = _Undefined()


def is_nan(value: object) -> bool:
    return value is NAN


def sign(x: int) -> int:
    return (x > 0) - (x < 0)


def trunc_div(a: int, b: int) -> int:
    """Quotient rounded toward zero; ``b`` must be non-zero."""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


def _decimal_digits(n: int) -> list[int]:
    """Decimal digits of a non-negative ``n``, least significant first.

    Arithmetic rather than ``str(n)``: Python refuses to convert integers with more than
    4300 digits to text, and values are unbounded when ``semantics.bound`` is null.
    """
    digits = []
    while True:
        n, d = divmod(n, 10)
        digits.append(d)
        if n == 0:
            return digits


def reverse_digits(n: int) -> int:
    """Decimal digits of a non-negative ``n`` reversed (leading zeros dropped)."""
    result = 0
    for d in _decimal_digits(n):
        result = result * 10 + d
    return result


def digit_sum(n: int) -> int:
    return sum(_decimal_digits(n))


# (symbol, n_ary, position) -> semantic name of the base operation.
BASE_OPERATIONS: dict[tuple[str, int, str | None], str] = {
    ("+", BINARY, None): "add",
    ("-", BINARY, None): "sub",
    ("*", BINARY, None): "mul",
    ("/", BINARY, None): "div",
    ("%", BINARY, None): "mod",
    ("-", 1, PREFIX): "neg",
    ("@", 1, POSTFIX): "reverse",
    ("#", 1, PREFIX): "triangle",
    ("$", 1, POSTFIX): "popcount",
    ("&", 1, PREFIX): "digitsum",
    # Atoms: numbers built from successor/predecessor and from bits.
    ("⁺", 1, POSTFIX): "succ",
    ("⁻", 1, POSTFIX): "pred",
    ("«", 1, POSTFIX): "double",
    ("»", 1, POSTFIX): "half",
    ("°", 1, POSTFIX): "parity",
    ("defined", 1, PREFIX): "defined",
}

# Base-operation sets available as starting registries or exported JSONL files.
DOMAINS: dict[str, tuple[str, ...]] = {
    "integer": ("add", "sub", "mul", "div", "mod", "neg", "reverse", "triangle", "popcount", "digitsum"),
    "atomic": ("succ", "pred", "neg", "double", "half", "parity"),
}


@dataclass(frozen=True)
class Semantics:
    """Numeric mode, bound and optional modulus; builds base operations."""

    mode: str = EXACT
    bound: int | None = DEFAULT_BOUND
    max_string_length: int = 256
    max_list_length: int = 256
    modulus: int | None = None

    def __post_init__(self) -> None:
        if self.mode not in MODES:
            raise ValueError(f"semantics.mode must be one of {MODES}, got {self.mode!r}")
        if self.bound is not None and type(self.bound) is not int:
            raise ValueError("semantics.bound must be an integer or null")
        if self.mode == LEGACY and self.bound is None:
            raise ValueError("legacy mode folds results by the bound, so a bound is required")
        if self.mode == MODULAR and (type(self.modulus) is not int or self.modulus < 2):
            raise ValueError("modular mode requires semantics.modulus >= 2")
        if self.mode != MODULAR and self.modulus is not None:
            raise ValueError("semantics.modulus requires modular mode")
        if self.bound is not None and self.bound <= 0:
            raise ValueError("semantics.bound must be positive or null")
        for name in ("max_string_length", "max_list_length"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"semantics.{name} must be a non-negative integer")

    # ----------------------------------------------------------- range check
    def check(self, value: int):
        """Apply the bound to a base-operation result (section 2)."""
        if self.mode == MODULAR:
            return value % self.modulus
        bound = self.bound
        if bound is None or -bound <= value <= bound:
            return value
        if self.mode == EXACT:
            return NAN
        return value % bound if value > 0 else -(abs(value) % bound)

    # ------------------------------------------------------- base operations
    def operations(self) -> dict[str, Callable]:
        """Semantic name -> function on V (section 3); defined is the NaN exception."""
        check = self.check
        legacy = self.mode == LEGACY
        bound = self.bound

        def add(a, b):
            return NAN if a is NAN or b is NAN else check(a + b)

        def sub(a, b):
            return NAN if a is NAN or b is NAN else check(a - b)

        def mul(a, b):
            return NAN if a is NAN or b is NAN else check(a * b)

        def div(a, b):
            if a is NAN or b is NAN:
                return NAN
            if b == 0:
                if not legacy:
                    return NAN
                b = 1
            return check(trunc_div(a, b))

        def mod(a, b):
            if a is NAN or b is NAN:
                return NAN
            if b == 0:
                if not legacy:
                    return NAN
                b = 1
            return check(a - b * trunc_div(a, b))

        def neg(a):
            return NAN if a is NAN else check(-a)

        def magnitude(a: int) -> int:
            return abs(a) % bound if legacy else abs(a)

        def reverse(a):
            if a is NAN:
                return NAN
            result = reverse_digits(magnitude(a))
            if legacy:
                return result % bound if a > 0 else -(result % bound)
            return check(sign(a) * result)

        def triangle(a):
            if a is NAN:
                return NAN
            n = magnitude(a)
            result = n * (n + 1) // 2
            if legacy:
                return result % bound if a > 0 else -(result % bound)
            return check(sign(a) * result)

        def popcount(a):
            if a is NAN:
                return NAN
            return check(abs(a).bit_count())

        def digitsum(a):
            if a is NAN:
                return NAN
            result = digit_sum(magnitude(a))
            if legacy:
                return result % bound if a > 0 else -(result % bound)
            return check(sign(a) * result)

        def succ(a):
            return NAN if a is NAN else check(a + 1)

        def pred(a):
            return NAN if a is NAN else check(a - 1)

        def double(a):
            return NAN if a is NAN else check(2 * a)

        def half(a):
            return NAN if a is NAN else check(trunc_div(a, 2))

        def parity(a):
            return NAN if a is NAN else check(abs(a) % 2)

        def defined(a):
            return 0 if a is NAN else 1

        table = {
            "add": add, "sub": sub, "mul": mul, "div": div, "mod": mod,
            "neg": neg, "reverse": reverse, "triangle": triangle,
            "popcount": popcount, "digitsum": digitsum,
            "succ": succ, "pred": pred, "double": double, "half": half, "parity": parity,
            "defined": defined,
        }
        from opulse.core.primitives import CUSTOM

        for name, primitive in CUSTOM.items():  # user-registered atoms (opulse.core.primitives)
            table[name] = _custom_atom(primitive, self)
        return table

    def to_dict(self) -> dict:
        result = {"mode": self.mode, "bound": self.bound}
        if self.modulus is not None:
            result["modulus"] = self.modulus
        if self.max_string_length != 256 or self.max_list_length != 256:
            result.update(max_string_length=self.max_string_length, max_list_length=self.max_list_length)
        return result


def _custom_atom(primitive, semantics: Semantics) -> Callable:
    """Check input types, propagate NaN, and bound a registered atom's result."""
    from opulse.core.types import matches

    def atom(*args):
        if any(a is NAN for a in args):
            return NAN
        if not all(matches(arg, kind) for arg, kind in zip(args, primitive.parameter_types)):
            return NAN
        result = primitive.compute(*args)
        if result is NAN or result is None:
            return NAN
        if not matches(result, primitive.result_type):
            raise TypeError(f"atom {primitive.name!r} returned the wrong value type: {result!r}")
        if isinstance(result, int) and not isinstance(result, bool):
            return semantics.check(result)
        if isinstance(result, str):
            return result if len(result) <= semantics.max_string_length else NAN
        if isinstance(result, (tuple, list)):
            from opulse.worlds.perm import Permutation

            if isinstance(result, Permutation):
                return result
            return tuple(result) if len(result) <= semantics.max_list_length else NAN
        return result

    return atom


def base_operation_name(symbol: str, n_ary: int, unary_position: str | None) -> str | None:
    return BASE_OPERATIONS.get((symbol, n_ary, unary_position if n_ary == 1 else None))
