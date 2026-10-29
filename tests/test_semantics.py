"""Spec section 9, obligation 1: base operations match docs/reference/semantics.md section 3."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from opulse.core.semantics import (
    DEFAULT_BOUND,
    EXACT,
    LEGACY,
    NAN,
    Semantics,
    trunc_div,
)

B = DEFAULT_BOUND
EX = Semantics(EXACT).operations()
LG = Semantics(LEGACY).operations()
UNBOUNDED = Semantics(EXACT, None).operations()
ints = st.integers(min_value=-10**12, max_value=10**12)


@pytest.mark.parametrize("name,args,expected", [
    ("add", (2, 3), 5), ("sub", (2, 3), -1), ("mul", (-4, 6), -24),
    ("div", (7, 2), 3), ("div", (-7, 2), -3), ("div", (7, -2), -3), ("div", (-7, -2), 3), ("div", (0, 5), 0),
    ("div", (5, 0), NAN), ("mod", (5, 0), NAN),
    ("mod", (7, 3), 1), ("mod", (-7, 3), -1), ("mod", (7, -3), 1), ("mod", (-7, -3), -1), ("mod", (6, 3), 0),
    ("neg", (5,), -5), ("neg", (0,), 0),
    ("reverse", (120,), 21), ("reverse", (-123,), -321), ("reverse", (0,), 0), ("reverse", (7,), 7),
    ("triangle", (4,), 10), ("triangle", (-4,), -10), ("triangle", (0,), 0),
    ("popcount", (7,), 3), ("popcount", (-7,), 3), ("popcount", (0,), 0), ("popcount", (1024,), 1),
    ("digitsum", (1234,), 10), ("digitsum", (-1234,), -10), ("digitsum", (0,), 0),
    ("succ", (-1,), 0), ("succ", (B,), NAN), ("pred", (0,), -1), ("pred", (-B,), NAN),
    ("double", (-7,), -14), ("double", (B // 2 + 1,), NAN),
    ("half", (7,), 3), ("half", (-7,), -3), ("half", (-1,), 0), ("half", (B,), B // 2),
    ("parity", (7,), 1), ("parity", (-7,), 1), ("parity", (-8,), 0), ("parity", (0,), 0),
    ("defined", (7,), 1), ("defined", (NAN,), 0),
])
def test_exact_table(name, args, expected):
    assert EX[name](*args) is expected if expected is NAN else EX[name](*args) == expected


@pytest.mark.parametrize("name", [name for name in EX if name != "defined"])
def test_nan_propagates(name):
    arity = 2 if name in {"add", "sub", "mul", "div", "mod"} else 1
    for i in range(arity):
        args = [3] * arity
        args[i] = NAN
        assert EX[name](*args) is NAN
        assert LG[name](*args) is NAN


def test_defined_does_not_propagate_nan_in_legacy_mode():
    assert LG["defined"](NAN) == 0


def test_bound_edges():
    assert EX["add"](B - 1, 1) == B
    assert EX["add"](B, 1) is NAN
    assert EX["sub"](-B, 1) is NAN
    assert EX["mul"](-1, B) == -B
    assert EX["triangle"](70000) is NAN  # 70000*70001/2 > 2^31-1
    assert UNBOUNDED["add"](B, 1) == B + 1


def test_legacy_quirks():
    assert LG["add"](B, 5) == 5  # (B + 5) mod B
    assert LG["sub"](-B, 5) == -5
    assert LG["add"](B, 0) == B  # exactly B is in range
    assert LG["div"](7, 0) == 7  # zero divisor counts as 1
    assert LG["mod"](7, 0) == 0
    assert LG["reverse"](0) == 0


@given(ints, ints)
def test_division_identity(a, b):
    q, r = UNBOUNDED["div"](a, b), UNBOUNDED["mod"](a, b)
    if b == 0:
        assert q is NAN and r is NAN
        return
    assert a == b * q + r
    assert abs(r) < abs(b)
    assert r == 0 or (r > 0) == (a > 0)
    assert q == trunc_div(a, b)
    assert q == int(a / b) or abs(a) > 2**53  # matches C/legacy truncation where floats are exact


@given(st.integers(min_value=-10**6, max_value=10**6))
def test_unary_definitions(a):
    sgn = (a > 0) - (a < 0)
    assert UNBOUNDED["triangle"](a) == sgn * abs(a) * (abs(a) + 1) // 2
    assert UNBOUNDED["digitsum"](a) == sgn * sum(map(int, str(abs(a))))
    assert UNBOUNDED["reverse"](a) == sgn * int(str(abs(a))[::-1])
    assert UNBOUNDED["popcount"](a) == abs(a).bit_count()
    assert UNBOUNDED["neg"](a) == -a


def test_nan_is_a_singleton_without_truth_value():
    import pickle

    assert pickle.loads(pickle.dumps(NAN)) is NAN
    with pytest.raises(TypeError):
        bool(NAN)
    assert repr(NAN) == "NaN"


def test_legacy_requires_bound():
    with pytest.raises(ValueError):
        Semantics(LEGACY, None)
    with pytest.raises(ValueError):
        Semantics("other")


def test_every_base_result_is_bound_checked():
    """Review finding: ``22 »`` with bound 10 is 11, outside the bound (literals may exceed B)."""
    exact = Semantics(EXACT, 10).operations()
    legacy = Semantics(LEGACY, 10).operations()
    assert exact["half"](20) == 10 and exact["half"](22) is NAN and exact["half"](-22) is NAN
    assert legacy["half"](22) == 1 and legacy["half"](-22) == -1


def test_decimal_operations_on_huge_unbounded_integers():
    """Review finding: str(int) refuses more than 4300 digits."""
    ops = UNBOUNDED
    assert ops["reverse"](10**5000) == 1
    assert ops["digitsum"](10**5000) == 1
    assert ops["reverse"](1200) == 21 and ops["digitsum"](-987) == -24
