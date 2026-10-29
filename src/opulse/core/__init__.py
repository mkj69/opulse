"""Core data types and the value semantics (docs/reference/semantics.md)."""

from opulse.core.operator import (
    BINARY,
    BRANCH,
    DEFINITION_TYPES,
    POSTFIX,
    PREFIX,
    RECURSIVE,
    SIMPLE,
    UNARY,
    Operator,
    is_call_form,
)
from opulse.core.registry import OperatorRegistry
from opulse.core.semantics import (
    DEFAULT_BOUND,
    EXACT,
    LEGACY,
    NAN,
    Semantics,
    is_nan,
    trunc_div,
)

__all__ = [
    "BINARY", "BRANCH", "DEFAULT_BOUND", "DEFINITION_TYPES", "EXACT", "LEGACY", "NAN", "POSTFIX",
    "PREFIX", "RECURSIVE", "SIMPLE", "UNARY", "Operator", "OperatorRegistry", "Semantics", "is_call_form",
    "is_nan", "trunc_div",
]
