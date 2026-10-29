"""Display helpers: notebook views, the dependency graph SVG and the Pygments lexer.

* :mod:`opulse.display.tokens`: a tokenizer for syntax colouring that never fails;
* :mod:`opulse.display.pygments_lexer`: :class:`OpulseLexer`, registered as ``opulse``;
* :mod:`opulse.display.html` and :mod:`opulse.display.markdown`: the ``_repr_html_`` and
  ``_repr_markdown_`` views of :mod:`opulse.api` objects;
* :mod:`opulse.display.graph_svg`: dependency graphs as inline SVG.

Pygments is needed only for :mod:`opulse.display.pygments_lexer`.
"""

from opulse.display.html import highlight
from opulse.display.tokens import TokenStyle, tokenize

__all__ = ["TokenStyle", "highlight", "tokenize"]
