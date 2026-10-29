"""Generated operator names and arities.

Shape and index names use neutral glyphs and serial indices. Legacy random
symbols keep the whole symbol set prefix-free (no symbol is a prefix of
another), so any run of adjacent legacy symbols splits in exactly one way.
:func:`uniquely_decodable` checks the general property.

The legacy alphabet is the union of named character sets (``symbol_sets``, see
:data:`NAMED_SETS`: readable symbols that common fonts draw), characters listed
directly (``symbol_chars``), and, for advanced use, raw Unicode ranges
(``symbol_blocks``, hex ``start-end``). With
``exclude_confusable`` (default) characters whose Unicode name marks them as
look-alikes are removed: minus/division/asterisk/set-minus signs (they read as
``- / * \\``), anything named EQUAL/LESS-THAN/GREATER-THAN/EQUIVALENT
(they read as comparisons inside ``if`` conditions), bars and dots.
"""

from __future__ import annotations

import random
import unicodedata
from functools import cache

from opulse.config import DEFAULT_ARITY_WEIGHTS, OperatorSettings
from opulse.core.operator import BINARY, POSTFIX, PREFIX, UNARY

CONFUSABLE_NAME_PARTS = (
    "MINUS SIGN", "PLUS SIGN", "DIVISION SLASH", "ASTERISK OPERATOR", "SET MINUS", "DIVIDES",
    "EQUAL", "IDENTICAL", "EQUIVALENT", "LESS-THAN", "GREATER-THAN", "PRECEDES", "SUCCEEDS",
    "VERTICAL", "PARALLEL", "RATIO", "PROPORTION", "COLON", "ELLIPSIS", "MIDLINE",
    "BULLET OPERATOR", "DOT OPERATOR", "RING OPERATOR", "TILDE OPERATOR",
)


# Named character sets for operator symbols. Each set holds symbols that common fonts draw and
# that do not look like ASCII letters, digits, arithmetic or comparison signs.
NAMED_SETS: dict[str, str] = {
    "circled": "⊕⊗⊝",
    "squared": "⊞⊟⊠",
    "logic": "∧∨⊻⊼⊽¬∀∃∄",
    "sets": "∩∪⊂⊃∈∋∉⊎⊓⊔",
    "calculus": "∑∏∐∫∮√∛∜∞∂∇∆",
    "arrows": "←→↑↓↔↕↖↗↘↙⇐⇒⇑⇓⇔↦↩↪↺↻⇄⇆",
    "shapes": "■□▲△▼▽◆◇●○★☆",
    "suits": "♠♣♥♦♤♧♡♢",
    # Greek capitals that do not look like Latin letters (no Α Β Ε Ζ Η Ι Κ Μ Ν Ο Ρ Τ Υ Χ).
    "greek": "ΓΔΘΛΞΠΣΦΨΩ",
}
NAMED_SETS["math"] = "".join(NAMED_SETS[k] for k in ("circled", "squared", "logic", "sets", "calculus"))

# These sets denote visual shapes rather than established mathematical operations.
SHAPE_SETS = {name: NAMED_SETS[name] for name in ("shapes", "suits")}


class ShapeIndexFactory:
    """Names made from a drawn shape and a serial index, independent of the draft."""

    def __init__(self, settings: OperatorSettings, rng: random.Random | None = None) -> None:
        self.settings = settings
        self.rng = rng or random.Random()
        unknown = set(settings.shape_sets) - set(SHAPE_SETS)
        if unknown:
            raise ValueError(f"unknown operators.shape_sets {sorted(unknown)}; choose from {sorted(SHAPE_SETS)}")
        shapes = "".join(SHAPE_SETS[name] for name in settings.shape_sets) + settings.shape_chars
        self.alphabet = tuple(dict.fromkeys(shapes))
        self.index_chars = settings.index_chars
        if not self.alphabet or any(unicodedata.category(c) not in ("So", "Sm") or
                                    c in "(){};,=<>!" for c in self.alphabet):
            raise ValueError("shape characters must be Unicode operator or other symbols")
        if len(set(self.index_chars)) < 2 or len(set(self.index_chars)) != len(self.index_chars) or any(
                not c.isalnum() for c in self.index_chars):
            raise ValueError("index_chars needs at least two distinct letters or digits")
        self._taken: set[str] = set()
        self._index = _PrefixIndex(())  # size is used by the layer capacity check
        self._next = 1

    def _suffix(self, number: int) -> str:
        chars = self.index_chars
        base = len(chars)
        # A zero-first ten-character alphabet writes conventional decimal indices.
        positional = base == 10 and chars[0] in "0₀"
        out = ""
        while number:
            if positional:
                number, digit = divmod(number, base)
            else:
                number, digit = divmod(number - 1, base)
            out = chars[digit] + out
        return out

    def new_symbol(self, taken: set[str] | None = None, max_attempts: int = 10_000) -> str:
        occupied = self._taken if taken is None else taken
        while True:
            index = self._next
            self._next += 1
            shape = self.rng.choice(self.alphabet)
            symbol = shape + self._suffix(index)
            if symbol not in occupied:
                return symbol

    def reserve(self, symbols) -> None:
        for symbol in symbols if not isinstance(symbols, str) else (symbols,):
            if symbol in self.alphabet:  # an atom written with a shape glyph keeps that glyph
                self.alphabet = tuple(c for c in self.alphabet if c != symbol)
                if not self.alphabet:
                    raise ValueError(f"shape glyph {symbol!r} is taken by an existing operator, "
                                     "and no other shape is left")
            self._taken.add(symbol)
            self._index.add(symbol)
            if symbol and symbol[0] in self.alphabet and len(symbol) > 1 and all(
                    char in self.index_chars for char in symbol[1:]):
                positional = len(self.index_chars) == 10 and self.index_chars[0] in "0₀"
                number = 0
                for char in symbol[1:]:
                    number = number * len(self.index_chars) + self.index_chars.index(char) + (not positional)
                self._next = max(self._next, number + 1)

    def capacity(self) -> int:
        return 2**63  # serial indices can grow; this is only an early capacity bound

    def new_shape(self) -> tuple[int, str | None]:
        return draw_shape(self.settings.arity_weights, self.rng)


def alphabet_for(settings: OperatorSettings) -> tuple[str, ...]:
    unknown = [name for name in settings.symbol_sets if name not in NAMED_SETS]
    if unknown:
        raise ValueError(f"unknown operators.symbol_sets {unknown}; choose from {sorted(NAMED_SETS)}")
    named = "".join(NAMED_SETS[name] for name in settings.symbol_sets) + settings.symbol_chars
    return build_alphabet(settings.symbol_blocks, settings.symbol_ascii, settings.exclude_confusable, named)


@cache
def build_alphabet(blocks: tuple[str, ...], ascii_chars: str, exclude_confusable: bool,
                   named: str = "") -> tuple[str, ...]:
    chars: list[str] = []
    for char in named:
        if char.isspace() or char.isascii():
            raise ValueError(f"operator symbol character {char!r} must be a non-ASCII symbol or letter")
        if exclude_confusable and any(part in unicodedata.name(char, "") for part in CONFUSABLE_NAME_PARTS):
            continue
        chars.append(char)
    for block in blocks:
        start, end = (int(part, 16) for part in block.split("-"))
        for codepoint in range(start, end + 1):
            char = chr(codepoint)
            name = unicodedata.name(char, "")
            category = unicodedata.category(char)
            # Symbols, or non-ASCII letters (ASCII letters are keywords and variables).
            if not name or not (category in ("Sm", "So") or (category[0] == "L" and not char.isascii())):
                continue
            if exclude_confusable and any(part in name for part in CONFUSABLE_NAME_PARTS):
                continue
            chars.append(char)
    return tuple(dict.fromkeys(chars + list(ascii_chars)))


class SymbolFactory:
    def __init__(self, settings: OperatorSettings, rng: random.Random | None = None) -> None:
        self.settings = settings
        self.rng = rng or random.Random()
        self.alphabet = alphabet_for(settings)
        if not self.alphabet:
            raise ValueError("symbol alphabet is empty; check operators.symbol_sets / symbol_chars / symbol_blocks")
        self._index = _PrefixIndex(())

    def new_symbol(self, taken: set[str] | None = None, max_attempts: int = 10_000) -> str:
        """A symbol that keeps ``taken`` (default: the symbols :meth:`reserve` recorded) prefix-free.

        The length is drawn in proportion to the number of strings of that length, so a set
        can grow close to the capacity ``k ** max_len``; short symbols, which block every
        longer symbol they start, stay rare. Checking a candidate costs O(max_len).
        """
        index = self._index if taken is None else _PrefixIndex(taken)
        lengths = list(range(self.settings.symbol_min_len, self.settings.symbol_max_len + 1))
        weights = [len(self.alphabet) ** n for n in lengths]
        for _ in range(max_attempts):
            length = self.rng.choices(lengths, weights)[0]
            symbol = "".join(self.rng.choice(self.alphabet) for _ in range(length))
            if index.fits(symbol):
                return symbol
        raise RuntimeError(f"no prefix-free symbol found after {max_attempts} attempts; the set holds "
                           f"{index.size} symbols and the capacity is {self.capacity()}: add characters "
                           "(operators.symbol_sets / symbol_chars) or raise operators.symbol_max_len")

    def reserve(self, symbols) -> None:
        """Record symbols in use (the registry's, then each accepted operator's)."""
        for symbol in symbols if not isinstance(symbols, str) else (symbols,):
            self._index.add(symbol)

    def capacity(self) -> int:
        """Upper bound on the size of a prefix-free set over this alphabet: k ** max_len."""
        return len(self.alphabet) ** self.settings.symbol_max_len

    def new_shape(self) -> tuple[int, str | None]:
        """(n_ary, unary_position) drawn by ``operators.arity_weights``; a unary operator is
        prefix or postfix with equal chance. The default weights draw exactly as earlier
        releases: binary with probability 1/2, else prefix or postfix."""
        return draw_shape(self.settings.arity_weights, self.rng)


def draw_shape(weights: dict[int, float], rng) -> tuple[int, str | None]:
    """Draw (n_ary, unary_position) by ``operators.arity_weights``. The default weights draw
    binary with probability 1/2, else prefix or postfix, as earlier releases did."""
    if weights == DEFAULT_ARITY_WEIGHTS:
        if rng.random() < 0.5:
            return BINARY, None
        return UNARY, rng.choice((PREFIX, POSTFIX))
    arities = sorted(weights)
    n_ary = rng.choices(arities, [weights[k] for k in arities])[0]
    if n_ary == UNARY:
        return UNARY, rng.choice((PREFIX, POSTFIX))
    return n_ary, None


class _PrefixIndex:
    """Symbols in use plus all their proper prefixes, for O(len) prefix-freeness checks."""

    def __init__(self, symbols) -> None:
        self.symbols: set[str] = set()
        self.prefixes: set[str] = set()
        for symbol in symbols:
            self.add(symbol)

    @property
    def size(self) -> int:
        return len(self.symbols)

    def add(self, symbol: str) -> None:
        self.symbols.add(symbol)
        self.prefixes.update(symbol[:i] for i in range(1, len(symbol)))

    def fits(self, symbol: str) -> bool:
        """Neither a prefix of a symbol in use, nor started by one (equality included)."""
        if symbol in self.symbols or symbol in self.prefixes:
            return False
        return not any(symbol[:i] in self.symbols for i in range(1, len(symbol)))


def uniquely_decodable(symbols: set[str]) -> bool:
    """Sardinas-Patterson test: every concatenation of ``symbols`` splits in one way."""
    code = set(symbols)
    if "" in code:
        return False

    def dangling(a: set[str], b: set[str]) -> set[str]:
        return {y[len(x):] for x in a for y in b if y.startswith(x) and y != x}

    current = dangling(code, code)
    seen: set[frozenset] = set()
    while current:
        if current & code:
            return False
        key = frozenset(current)
        if key in seen:
            return True
        seen.add(key)
        current = dangling(code, current) | dangling(current, code)
    return True
