"""A forgiving tokenizer for Opulse text, used for syntax colouring only.

Unlike :mod:`opulse.definition.syntax` it needs no operator set: every run of
symbol characters is one operator token, and anything it does not recognise
becomes plain text. It never fails, so it can colour definitions, expressions,
schematic templates and prompts alike. The Pygments lexer
(:mod:`opulse.display.pygments_lexer`) and the notebook views share it.

Token kinds:

``keyword``      ``if``, ``else``, ``and``, ``or``, ``not``
``constant``     the NaN spelling (and ``Inf``)
``number``       decimal digits, or a base marker followed by its digits
``comparison``   ``==`` ``!=`` ``>=`` ``<=`` ``>`` ``<``
``equals``       the definition sign (``=`` by default)
``punctuation``  braces, brackets, parentheses, ``;`` and ``,``
``parameter``    the operand names (``a`` and ``b`` by default)
``operator``     a symbol run with a non ASCII character, a non ASCII word, or a configured word
``base``         a symbol run made of ASCII characters only (``+``, ``-``, ``%``, ...)
``name``         any other ASCII word
``whitespace``   spaces and newlines
``text``         any other character
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field

KEYWORDS = frozenset(("if", "else", "and", "or", "not"))
COMPARISONS = ("==", "!=", ">=", "<=", ">", "<")
PUNCTUATION = frozenset("{}()[];,")
# Characters that end a symbol run (the grammar reserves them, see opulse.definition.syntax).
STOP = frozenset("{}()[];,=<>!_")
DIGITS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

KINDS = ("keyword", "constant", "number", "comparison", "equals", "punctuation", "parameter",
         "operator", "base", "name", "whitespace", "text")


@dataclass(frozen=True)
class TokenStyle:
    """What the tokenizer should know about one notation. Every field has a default."""

    parameters: tuple[str, ...] = ("a", "b", "c", "d", "e", "f")  # Symbols().operands(6)
    nan: str = "NaN"
    constants: tuple[str, ...] = ("Inf",)
    equals: str = "="
    words: tuple[str, ...] = ()  # operator names that are words (e.g. benchmark aliases)
    markers: tuple[str, ...] = ()  # numeral base markers, e.g. "⊺⇮" in "⊺⇮1A"
    digits: str = DIGITS
    _words: frozenset = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_words", frozenset(self.words))

    @classmethod
    def build(cls, parameters: Iterable[str] | None = None, nan: str | None = None,
              words: Iterable[str] = (), markers: Iterable[str] = (), equals: str | None = None,
              digits: str | None = None) -> TokenStyle:
        default = cls()
        return cls(parameters=tuple(parameters) if parameters is not None else default.parameters,
                   nan=nan or default.nan, equals=equals or default.equals, words=tuple(words),
                   markers=tuple(sorted(markers, key=len, reverse=True)), digits=digits or default.digits)


DEFAULT_STYLE = TokenStyle()


def tokenize(text: str, style: TokenStyle = DEFAULT_STYLE) -> Iterator[tuple[int, str, str]]:
    """Yield ``(offset, kind, text)`` covering ``text`` exactly, in order."""
    i, n = 0, len(text)
    comparisons = sorted({*COMPARISONS}, key=len, reverse=True)
    while i < n:
        char = text[i]
        if char.isspace():
            j = i
            while j < n and text[j].isspace():
                j += 1
            yield i, "whitespace", text[i:j]
            i = j
            continue
        end = _marker_numeral(text, i, style)
        if end:
            yield i, "number", text[i:end]
            i = end
            continue
        word = _configured_word(text, i, style)
        if word:
            yield i, "operator", word
            i += len(word)
            continue
        if style.equals and text.startswith(style.equals, i) and not text.startswith("==", i):
            yield i, "equals", style.equals
            i += len(style.equals)
            continue
        cmp = next((c for c in comparisons if text.startswith(c, i)), None)
        if cmp:
            yield i, "comparison", cmp
            i += len(cmp)
            continue
        if char in PUNCTUATION:
            yield i, "punctuation", char
            i += 1
            continue
        if "0" <= char <= "9":
            j = i
            while j < n and "0" <= text[j] <= "9":
                j += 1
            yield i, "number", text[i:j]
            i = j
            continue
        if char.isalnum():
            j = i
            while j < n and text[j].isalnum():
                j += 1
            yield i, _word_kind(text[i:j], style), text[i:j]
            i = j
            continue
        if char not in STOP:
            j = i
            while j < n and _symbol_char(text[j]) and not _marker_numeral(text, j, style) \
                    and not (style.equals and j > i and text.startswith(style.equals, j)):
                j += 1
            if not text[i:j].isascii():  # a shape and index name such as ◆₁₂ is one operator
                while j < n and text[j].isalnum():
                    j += 1
            run = text[i:j]
            yield i, "base" if run.isascii() else "operator", run
            i = j
            continue
        yield i, "text", char
        i += 1


def _symbol_char(char: str) -> bool:
    return not (char.isspace() or char.isalnum() or char in STOP)


def _marker_numeral(text: str, i: int, style: TokenStyle) -> int:
    """End offset of a base marked numeral starting at ``i``, or 0."""
    for marker in style.markers:
        if marker and text.startswith(marker, i):
            j = i + len(marker)
            while j < len(text) and text[j] in style.digits:
                j += 1
            if j > i + len(marker):
                return j
    return 0


def _configured_word(text: str, i: int, style: TokenStyle) -> str:
    if not style.words or (i > 0 and text[i - 1].isalnum()):
        return ""
    for word in sorted(style.words, key=len, reverse=True):
        end = i + len(word)
        if text.startswith(word, i) and not (end < len(text) and text[end].isalnum() and word[-1:].isalnum()):
            return word
    return ""


def _word_kind(word: str, style: TokenStyle) -> str:
    if word in KEYWORDS:
        return "keyword"
    if word == style.nan or word in style.constants:
        return "constant"
    if word in style.parameters:
        return "parameter"
    if word in style._words:
        return "operator"
    if not word.isascii():
        return "operator"  # e.g. Greek letters used as operator symbols
    return "name"
