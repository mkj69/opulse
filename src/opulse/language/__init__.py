"""Natural-language views of definitions and narrations of verified calculation traces.

* :mod:`opulse.language.ir`: one intermediate representation of a definition;
* :mod:`opulse.language.views`: symbolic, formula, code, controlled prose (English and
  Chinese), examples and summary views, with parsers back to the definition;
* :mod:`opulse.language.describe`: operator descriptions and dependency chains;
* :mod:`opulse.language.recursion`: what a recursive definition's structure establishes;
* :mod:`opulse.language.narrate`: forward and reverse narrations of solutions.
"""

from opulse.language.describe import Describer, annotate, describe
from opulse.language.narrate import narrate, narrate_reverse
from opulse.language.views import Views

__all__ = ["Describer", "Views", "annotate", "describe", "narrate", "narrate_reverse"]
