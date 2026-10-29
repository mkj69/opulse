"""The operator record and its JSONL representation.

An :class:`Operator` is plain data. It knows how to describe itself (arity,
position, how to render its left-hand side) but not how to find other
operators; that is the job of :class:`opulse.core.registry.OperatorRegistry`.

The JSON field names match the legacy ``operator_*.jsonl`` files so that old
datasets load unchanged and downstream tools (CoT expansion, NL description)
can read new output.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from typing import Any

# Arity / position vocabulary. Operators with three or more arguments (``n_ary >= 3``) have
# no position: they are written in call form, ``⊕(a, b, c)``.
UNARY = 1
BINARY = 2
PREFIX = "prefix"
POSTFIX = "postfix"


def is_call_form(n_ary: int) -> bool:
    """Applications with three or more arguments are written ``symbol(arg, arg, arg)``."""
    return n_ary > BINARY

# Definition kinds.
SIMPLE = "simple_definition"
BRANCH = "branch_definition"
RECURSIVE = "recursive_definition"
DEFINITION_TYPES = (SIMPLE, BRANCH, RECURSIVE)


_OMIT_WHEN_NONE = ("z3_status", "interest", "skeleton_id", "world", "correspondence_grade", "primitive_name")


@dataclass
class Operator:
    func_id: str
    symbol: str
    n_ary: int
    unary_position: str | None = None
    id: int | None = None
    recursive_layer: int | None = None
    is_base: int | None = None
    definition: str | None = None
    definition_type: str | None = None
    priority: int | None = None
    associativity_direction: str | None = None
    max_path_depth: int = 0
    max_edge_count: int = 0
    op_compute_func: str | None = None
    op_count_func: str | None = None
    dependencies: list[str] = field(default_factory=list)
    parameter_types: tuple[str, ...] | None = None
    result_type: str = "int"
    primitive_name: str | None = None
    # Natural-language fields written by downstream tools; carried through untouched.
    nl_description: str | None = None
    nl_description_zh: str | None = None
    nl_description_en: str | None = None
    nl_description_chain: str | None = None
    nl_description_chain_zh: str | None = None
    nl_description_chain_en: str | None = None
    # Solver fields written by ``opulse analyze`` (docs/reference/semantics.md section 9).
    z3: str | None = None  # SMT-LIB functions of this operator (opulse.solver.smt)
    z3_status: str | None = None  # reason an SMT export is unavailable
    properties: dict | None = None  # algebraic laws with proved/refuted/bounded verdicts
    branch_reachability: list | None = None  # per conditional branch: reachable/dead/unknown
    # Interestingness scores written by ``opulse interest`` or an opt-in generation run.
    interest: dict | None = None
    skeleton_id: str | None = None
    world: str | None = None
    correspondence_grade: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.n_ary, bool) or not isinstance(self.n_ary, int) or self.n_ary < UNARY:
            raise ValueError(f"n_ary must be a positive integer, got {self.n_ary!r}")
        if self.n_ary == UNARY and self.unary_position not in (PREFIX, POSTFIX):
            raise ValueError(f"unary operator {self.symbol!r} needs prefix/postfix position")
        if self.n_ary >= BINARY:
            self.unary_position = None
        if self.dependencies is None:
            self.dependencies = []
        if self.parameter_types is None:
            self.parameter_types = ("int",) * self.n_ary
        else:
            self.parameter_types = tuple(self.parameter_types)
        if len(self.parameter_types) != self.n_ary:
            raise ValueError("parameter_types must match operator arity")
        from opulse.core.types import parse_type

        for value_type in (*self.parameter_types, self.result_type):
            parse_type(value_type)

    # ------------------------------------------------------------------ naming
    @property
    def compute_name(self) -> str:
        return f"op_{self.func_id}"

    @property
    def count_name(self) -> str:
        return f"op_count_{self.func_id}"

    @property
    def is_unary(self) -> bool:
        return self.n_ary == UNARY

    @property
    def is_primitive(self) -> bool:
        """True for hand-written initial operators that have no definition string."""
        return self.definition is None

    @property
    def has_code(self) -> bool:
        return bool(self.op_compute_func and self.op_count_func)

    def apply_str(self, *operands: str, symbols=None) -> str:
        """Render this operator applied to already-rendered operand strings.

        ``symbols`` (:class:`opulse.config.Symbols`) supplies the brackets and the argument
        separator of the call form; only operators with three or more arguments use them.
        """
        if is_call_form(self.n_ary):
            if symbols is None:
                from opulse.config import Symbols

                symbols = Symbols()
            return symbols.call(self.symbol, operands)
        if self.n_ary == BINARY:
            left, right = operands
            return f"{left} {self.symbol} {right}"
        (operand,) = operands
        if self.unary_position == PREFIX:
            return f"{self.symbol} {operand}"
        return f"{operand} {self.symbol}"

    # --------------------------------------------------------------- JSON I/O
    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in _OMIT_WHEN_NONE:  # later fields stay out of records that do not use them
            if data[key] is None:
                del data[key]
        if self.parameter_types == ("int",) * self.n_ary and self.result_type == "int":
            data.pop("parameter_types")
            data.pop("result_type")
        return data

    def to_json(self) -> str:
        from opulse.canary import marked

        return json.dumps(marked(self.to_dict()), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Operator:
        known = {f.name for f in fields(cls)}
        return cls(**{key: value for key, value in data.items() if key in known})

    @classmethod
    def from_json(cls, line: str) -> Operator:
        return cls.from_dict(json.loads(line))
