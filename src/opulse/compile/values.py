"""Token vocabularies of compiled networks and the value rules their blocks implement.

A compiled network stores every intermediate value in its own slot of the residual stream. An
integer slot holds one token out of ``lo .. hi`` plus two extra tokens: ``NaN`` (the value is
undefined, as in the reference semantics) and ``OOV`` (the value is a defined integer outside
``lo .. hi``, so the network no longer knows it). A condition slot holds one of ``F``, ``T``,
``NaN`` (the condition compared an undefined value) and ``OOV`` (it compared an unknown value).

The functions here state, on single tokens, what each block computes. The compiler uses them to
fill lookup tables, and the verifier holds the network to the reference interpreter.
"""

from __future__ import annotations

from dataclasses import dataclass

from opulse.core.semantics import NAN


class _OutOfVocabulary:
    """A defined integer outside the vocabulary range. A singleton; compare with ``is``."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "OOV"

    def __reduce__(self):
        return (_OutOfVocabulary, ())


OOV = _OutOfVocabulary()

# Condition tokens, in slot order.
FALSE, TRUE, COND_NAN, COND_OOV = 0, 1, 2, 3
COND_LABELS = ("F", "T", "NaN", "OOV")
COND_SIZE = 4


@dataclass(frozen=True)
class Vocab:
    """Integer tokens ``lo .. hi`` followed by ``NaN`` and ``OOV``."""

    lo: int
    hi: int

    def __post_init__(self) -> None:
        if self.hi < self.lo:
            raise ValueError("vocabulary needs lo <= hi")

    @property
    def size(self) -> int:
        return self.hi - self.lo + 3

    @property
    def nan_index(self) -> int:
        return self.hi - self.lo + 1

    @property
    def oov_index(self) -> int:
        return self.hi - self.lo + 2

    def clamp(self, value):
        """The value a slot can hold: integers outside the range become OOV."""
        if value is NAN or value is OOV:
            return value
        return value if self.lo <= value <= self.hi else OOV

    def index(self, value) -> int:
        value = self.clamp(value)
        if value is NAN:
            return self.nan_index
        if value is OOV:
            return self.oov_index
        return value - self.lo

    def value(self, index: int):
        if index == self.nan_index:
            return NAN
        if index == self.oov_index:
            return OOV
        if not 0 <= index < self.nan_index:
            raise IndexError(f"token {index} outside the vocabulary")
        return self.lo + index

    def values(self) -> list:
        return [self.value(index) for index in range(self.size)]

    def label(self, index: int) -> str:
        value = self.value(index)
        return repr(value) if value is NAN or value is OOV else str(value)


# ----------------------------------------------------------------- value rules
# An abstract value is (is_const, value). Constants are folded at compile time and stay exact;
# every other value lives in a slot and is clamped to the vocabulary.

def apply_atom(primitive, args: tuple, vocab: Vocab, *, defined: bool = False):
    """One base operation on abstract values."""
    if all(is_const for is_const, _ in args):
        return True, primitive(*(value for _, value in args))
    values = [value for _, value in args]
    if len(values) == 1:
        (value,) = values
        if value is OOV:
            return False, vocab.clamp(1) if defined else OOV
        return False, vocab.clamp(primitive(value))  # primitive decides NaN (``defined`` maps it to 0)
    if any(value is NAN for value in values):
        return False, NAN  # every binary base operation propagates NaN
    if any(value is OOV for value in values):
        return False, OOV
    return False, vocab.clamp(primitive(*values))


def compare(op, left, right):
    """A comparison on abstract values, as a condition token."""
    is_const = left[0] and right[0]
    a, b = left[1], right[1]
    if a is NAN or b is NAN:
        return is_const, COND_NAN
    if a is OOV or b is OOV:
        return is_const, COND_OOV
    return is_const, TRUE if op(a, b) else FALSE


def logic_and(left, right):
    token = {FALSE: FALSE, TRUE: right[1], COND_NAN: COND_NAN, COND_OOV: COND_OOV}[left[1]]
    return left[0] and right[0], token


def logic_or(left, right):
    token = {TRUE: TRUE, FALSE: right[1], COND_NAN: COND_NAN, COND_OOV: COND_OOV}[left[1]]
    return left[0] and right[0], token


def logic_not(operand):
    token = {FALSE: TRUE, TRUE: FALSE}.get(operand[1], operand[1])
    return operand[0], token


def select(cond_token: int, then_value, else_value):
    """``then`` if the condition holds, ``else`` if it fails, otherwise NaN or OOV."""
    if cond_token == TRUE:
        return then_value
    if cond_token == FALSE:
        return else_value
    return NAN if cond_token == COND_NAN else OOV
