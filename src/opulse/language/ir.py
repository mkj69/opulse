"""One intermediate representation of a definition, shared by every view.

A :class:`Concept` is the parsed definition seen as an ordered list of cases. Every view
(symbolic text, LaTeX formula, Python code, controlled English and Chinese, example tables,
summary facts) is computed from it, and every parser of a view returns the same
:class:`opulse.definition.ast.Definition` it was built from.

Operators are identified by :class:`OperatorRef`: symbol, arity and position. Nothing here
assumes one or two arguments; an application with ``n`` arguments is ``n`` children of one
node, so operators of higher arity and call notation ``f(a, b, c)`` fit without changes.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, replace

from opulse.config import Symbols
from opulse.core.operator import Operator
from opulse.core.semantics import base_operation_name
from opulse.definition import ast

IF, ELSE, ALWAYS = "if", "else", "always"


@dataclass(frozen=True)
class OperatorRef:
    """An operator as it is written: symbol, arity and position (``prefix``/``postfix`` for
    unary operators, ``None`` for infix binary ones; other positions pass through untouched)."""

    symbol: str
    arity: int
    position: str | None = None

    @property
    def key(self) -> tuple[str, int, str | None]:
        return (self.symbol, self.arity, self.position)

    @property
    def atom(self) -> str | None:
        """The atom's name when this shape denotes a built-in or registered atom."""
        return base_operation_name(self.symbol, self.arity, self.position)

    @classmethod
    def of(cls, node: ast.Apply | Operator) -> OperatorRef:
        if isinstance(node, Operator):
            return cls(node.symbol, node.n_ary, node.unary_position if node.n_ary == 1 else None)
        return cls(node.symbol, len(node.args), node.unary_position)

    def apply(self, args: tuple[ast.Expr, ...]) -> ast.Apply:
        return ast.Apply(self.symbol, tuple(args), self.position)


@dataclass(frozen=True)
class Case:
    """One branch: ``kind`` is ``if`` (guarded), ``else`` or ``always`` (a bare expression)."""

    index: int  # 1-based, as readers count cases
    kind: str
    guard: ast.Condition | None
    body: ast.Expr

    @property
    def branch(self) -> ast.Branch:
        return ast.Branch(self.body, self.guard, self.kind == ELSE)


@dataclass(frozen=True)
class Concept:
    operator: OperatorRef
    parameters: tuple[str, ...]
    cases: tuple[Case, ...]
    lhs: ast.Apply

    @classmethod
    def of(cls, definition: ast.Definition) -> Concept:
        cases = []
        for index, branch in enumerate(definition.branches, start=1):
            kind = IF if branch.condition is not None else (ELSE if branch.is_else else ALWAYS)
            cases.append(Case(index, kind, branch.condition, branch.expr))
        return cls(OperatorRef.of(definition.lhs), definition.parameters, tuple(cases), definition.lhs)

    def definition(self) -> ast.Definition:
        return ast.Definition(self.lhs, tuple(case.branch for case in self.cases))

    @property
    def partial(self) -> bool:
        """True when no case may apply (the last case has a guard): the value is then NaN."""
        return bool(self.cases) and self.cases[-1].kind == IF

    @property
    def single(self) -> bool:
        """One unconditional expression: ``lhs = { e }``."""
        return len(self.cases) == 1 and self.cases[0].kind == ALWAYS

    def self_calls(self) -> list[tuple[Case, ast.Apply]]:
        """Every application of the operator to itself, with the case it occurs in."""
        found = []
        for case in self.cases:
            for node in nodes_of(case):
                for apply in ast.iter_applications(node):
                    if OperatorRef.of(apply) == self.operator:
                        found.append((case, apply))
        return found

    @property
    def recursive(self) -> bool:
        return bool(self.self_calls())

    def calls(self) -> list[OperatorRef]:
        """Operators applied in the definition (not the operator itself), in order of first use."""
        seen: dict[OperatorRef, None] = {}
        for case in self.cases:
            for node in nodes_of(case):
                for apply in ast.iter_applications(node):
                    ref = OperatorRef.of(apply)
                    if ref != self.operator:
                        seen.setdefault(ref, None)
        return list(seen)


def nodes_of(case: Case) -> Iterator[ast.Expr | ast.Condition]:
    if case.guard is not None:
        yield case.guard
    yield case.body


# ------------------------------------------------------------------ AST helpers


def normalize(node):
    """The same tree with every literal in base 10 (views write literals in decimal)."""
    if isinstance(node, ast.Num):
        return ast.Num(node.value)
    if isinstance(node, ast.Apply):
        return replace(node, args=tuple(normalize(arg) for arg in node.args))
    if isinstance(node, ast.Search):
        return ast.Search(node.index, node.bound, normalize(node.condition))
    if isinstance(node, ast.Compare):
        return ast.Compare(normalize(node.left), node.op, normalize(node.right))
    if isinstance(node, (ast.And, ast.Or)):
        return type(node)(normalize(node.left), normalize(node.right))
    if isinstance(node, ast.Not):
        return ast.Not(normalize(node.operand))
    if isinstance(node, ast.Branch):
        return ast.Branch(normalize(node.expr), normalize(node.condition) if node.condition else None,
                          node.is_else)
    if isinstance(node, ast.Definition):
        return ast.Definition(node.lhs, tuple(normalize(branch) for branch in node.branches))
    return node


def depth(node: ast.Expr) -> int:
    if isinstance(node, ast.Apply):
        return 1 + max(depth(arg) for arg in node.args)
    return 0


def has_search(node) -> bool:
    """Whether a definition, expression or condition contains bounded search."""
    if isinstance(node, ast.Search):
        return True
    if isinstance(node, ast.Definition):
        return any(has_search(branch) for branch in node.branches)
    if isinstance(node, ast.Branch):
        return has_search(node.expr) or (node.condition is not None and has_search(node.condition))
    if isinstance(node, ast.Apply):
        return any(has_search(arg) for arg in node.args)
    if isinstance(node, (ast.Compare, ast.And, ast.Or)):
        return has_search(node.left) or has_search(node.right)
    if isinstance(node, ast.Not):
        return has_search(node.operand)
    if isinstance(node, ast.Truth):
        return has_search(node.expr)
    return False


def has_call_form(node) -> bool:
    """Whether a definition, expression or condition contains an n-ary call."""
    if isinstance(node, ast.Definition):
        return has_call_form(node.lhs) or any(has_call_form(branch) for branch in node.branches)
    if isinstance(node, ast.Branch):
        return has_call_form(node.expr) or (node.condition is not None and has_call_form(node.condition))
    if isinstance(node, ast.Apply):
        return node.n_ary >= 3 or any(has_call_form(arg) for arg in node.args)
    if isinstance(node, ast.Search):
        return has_call_form(node.condition)
    if isinstance(node, (ast.Compare, ast.And, ast.Or)):
        return has_call_form(node.left) or has_call_form(node.right)
    if isinstance(node, ast.Not):
        return has_call_form(node.operand)
    if isinstance(node, ast.Truth):
        return has_call_form(node.expr)
    return False


def substitute(node, mapping: dict):
    """Replace subtrees found in ``mapping`` (expressions and conditions)."""
    if node in mapping:
        return mapping[node]
    if isinstance(node, ast.Apply):
        return replace(node, args=tuple(substitute(arg, mapping) for arg in node.args))
    if isinstance(node, ast.Search):
        return ast.Search(node.index, node.bound, substitute(node.condition,
                          {key: value for key, value in mapping.items() if key != ast.Var(node.index)}))
    if isinstance(node, ast.Compare):
        return ast.Compare(substitute(node.left, mapping), node.op, substitute(node.right, mapping))
    if isinstance(node, (ast.And, ast.Or)):
        return type(node)(substitute(node.left, mapping), substitute(node.right, mapping))
    if isinstance(node, ast.Not):
        return ast.Not(substitute(node.operand, mapping))
    return node


def subterms(node: ast.Expr) -> Iterator[ast.Expr]:
    """Every subexpression, parents before children."""
    yield node
    if isinstance(node, ast.Apply):
        for arg in node.args:
            yield from subterms(arg)


def parse_lhs(text: str, params: tuple[str, ...], symbols: Symbols) -> ast.Apply:
    """The left-hand side written as ``a S b``, ``S a``, ``a S`` or ``S(a, b, c)``."""
    text = text.strip()
    words = text.split()
    names = set(params)
    if len(words) == 3 and words[0] in names and words[2] in names and words[1] not in names:
        return ast.Apply(words[1], (ast.Var(words[0]), ast.Var(words[2])))
    if len(words) == 2 and (words[0] in names) != (words[1] in names):
        if words[1] in names:
            return ast.Apply(words[0], (ast.Var(words[1]),), "prefix")
        return ast.Apply(words[1], (ast.Var(words[0]),), "postfix")
    left, right = symbols.left_paren, symbols.right_paren
    if text.endswith(right) and left in text:
        head, inner = text[: -len(right)].split(left, 1)
        args = tuple(ast.Var(part.strip()) for part in inner.split(","))
        if head.strip() and all(arg.name in names for arg in args):
            return ast.Apply(head.strip(), args)
    raise ValueError(f"cannot read the left-hand side {text!r}")


def parameter_names(symbols: Symbols, arity: int) -> tuple[str, ...]:
    """Operand names for an operator of ``arity`` arguments (``a, b`` and then ``c, d, ...``)."""
    if arity <= 2:
        return symbols.operands(arity)
    extra = [chr(c) for c in range(ord("c"), ord("z") + 1) if chr(c) not in symbols.operands(2)]
    return symbols.operands(2) + tuple(extra[: arity - 2])


def signatures(operators) -> dict[tuple[str, int], set[str | None]]:
    """``(symbol, arity) -> positions`` of the given operators (Operator records or refs)."""
    table: dict[tuple[str, int], set[str | None]] = {}
    for op in operators:
        ref = op if isinstance(op, OperatorRef) else OperatorRef.of(op)
        table.setdefault((ref.symbol, ref.arity), set()).add(ref.position)
    return table
