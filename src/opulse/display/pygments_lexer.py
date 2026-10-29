"""Pygments lexer for Opulse definitions and expressions.

Registered under the name ``opulse`` through the ``pygments.lexers`` entry
point, so Markdown code blocks marked ```` ```opulse ```` are coloured by any
Pygments based highlighter once the package is installed::

    from pygments import highlight
    from pygments.formatters import HtmlFormatter
    from opulse.display.pygments_lexer import OpulseLexer

    highlight("a ⊕ b = { a + (b @) }", OpulseLexer(), HtmlFormatter())

Options (all optional): ``parameters`` (operand names, default ``a,b``), ``nan``
(the NaN spelling), ``words`` (operator names that are words), ``markers``
(numeral base markers) and ``equals`` (the definition sign). List options take
a list or a comma separated string. :meth:`opulse.World.lexer` returns a lexer
configured for one world.

Operator symbols with a non ASCII character are ``Name.Function``; ASCII runs
such as ``+`` or ``%`` are ``Operator``. The lexer never emits ``Error``.
"""

from __future__ import annotations

import re

from pygments.lexer import Lexer
from pygments.token import (
    Keyword,
    Name,
    Number,
    Operator,
    Punctuation,
    Text,
    Whitespace,
)

from opulse.display.tokens import TokenStyle, tokenize

TOKEN_TYPES = {
    "keyword": Keyword,
    "constant": Keyword.Constant,
    "number": Number.Integer,
    "comparison": Operator.Word,
    "equals": Punctuation,
    "punctuation": Punctuation,
    "parameter": Name.Variable,
    "operator": Name.Function,
    "base": Operator,
    "name": Name,
    "whitespace": Whitespace,
    "text": Text,
}


class OpulseLexer(Lexer):
    """Lexer for Opulse operator definitions, expressions and solution steps."""

    name = "Opulse"
    aliases = ("opulse",)
    filenames = ("*.opulse",)
    mimetypes = ("text/x-opulse",)
    url = "https://github.com/mkj69/opulse"

    def __init__(self, **options) -> None:
        super().__init__(**options)
        self.style_options = TokenStyle.build(
            parameters=_list_option(options, "parameters") or None,
            nan=options.get("nan"),
            words=_list_option(options, "words"),
            markers=_list_option(options, "markers"),
            equals=options.get("equals"),
        )

    def get_tokens_unprocessed(self, text: str):
        for offset, kind, value in tokenize(text, self.style_options):
            yield offset, TOKEN_TYPES[kind], value


def _list_option(options: dict, name: str) -> list[str]:
    """A list option given as a list or as a comma (or space) separated string."""
    value = options.get(name) or []
    if isinstance(value, str):
        value = [item for item in re.split(r"[,\s]+", value) if item]
    return [str(item) for item in value]


def register() -> None:
    """Make ``opulse`` known to :func:`pygments.lexers.get_lexer_by_name` without installing the package.

    An installed package registers the lexer through its entry point; this is for source
    checkouts (the documentation build calls it from ``tools/mkdocs_hooks.py``).
    """
    from pygments.lexers import LEXERS

    LEXERS.setdefault("OpulseLexer", (__name__, OpulseLexer.name, tuple(OpulseLexer.aliases),
                                      tuple(OpulseLexer.filenames), tuple(OpulseLexer.mimetypes)))


# Only lexer classes: pygments imports every name listed here as a lexer.
__all__ = ["OpulseLexer"]
