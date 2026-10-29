"""The formula view: a definition as a LaTeX piecewise function, and its parser.

Markup states every operator's shape, so the text needs no operator table to be read back:
``x \\mathbin{\\text{S}} y`` is binary, ``\\text{S}\\, x`` prefix, ``x \\,\\text{S}`` postfix and
``\\operatorname{\\text{S}}\\left(x, y, z\\right)`` an application in call form. Addition,
subtraction, multiplication and negation use ``+``, ``-``, ``\\times`` and a leading ``-``.
Every compound operand is bracketed with ``\\left( \\right)``, so the structure is explicit.

Rows of the ``cases`` environment are the branches in order: ``\\text{if } c``, ``\\text{otherwise}``
(an ``else`` branch) and ``\\text{always}`` (a bare expression after other branches). A partial
definition ends with the row ``\\mathrm{NaN} & \\text{if no case above applies}``, which states
the semantics and is not a branch.
"""

from __future__ import annotations

from opulse.config import Symbols
from opulse.definition import ast
from opulse.language.ir import ALWAYS, ELSE, IF, Concept, OperatorRef

INFIX = {"add": "+", "sub": "-", "mul": "\\times"}
COMPARE = {">": ">", "<": "<", ">=": "\\geq", "<=": "\\leq", "==": "=", "!=": "\\neq"}
NO_CASE = "if no case above applies"
ESCAPES = {"\\": "\\textbackslash{}", "{": "\\{", "}": "\\}", "$": "\\$", "&": "\\&", "#": "\\#",
           "%": "\\%", "_": "\\_", "^": "\\^{}", "~": "\\~{}"}


class LatexError(ValueError):
    pass


def escape(text: str) -> str:
    return "".join(ESCAPES.get(char, char) for char in text)


# ------------------------------------------------------------------ render


def render(definition: ast.Definition, symbols: Symbols) -> str:
    concept = Concept.of(definition)
    head = _expr(definition.lhs, symbols, top=True)
    if concept.single:
        return f"{head} = {_expr(concept.cases[0].body, symbols, top=True)}"
    rows = []
    for case in concept.cases:
        body = _expr(case.body, symbols, top=True)
        if case.kind == IF:
            rows.append(f"  {body} & \\text{{if }} {_condition(case.guard, symbols)}")
        else:
            rows.append(f"  {body} & \\text{{{'otherwise' if case.kind == ELSE else 'always'}}}")
    if concept.partial:
        rows.append(f"  \\mathrm{{{escape(symbols.nan)}}} & \\text{{{NO_CASE}}}")
    return f"{head} = \\begin{{cases}}\n" + " \\\\\n".join(rows) + "\n\\end{cases}"


def _expr(node: ast.Expr, symbols: Symbols, top: bool = False) -> str:
    if isinstance(node, ast.Var):
        return node.name if len(node.name) == 1 and node.name.isascii() and node.name.isalpha() \
            else f"\\mathit{{{escape(node.name)}}}"
    if isinstance(node, ast.Num):
        return str(node.value)
    if isinstance(node, ast.NaN):
        return f"\\mathrm{{{escape(symbols.nan)}}}"
    if isinstance(node, ast.Search):
        return (f"\\operatorname{{search}}\\left({_expr(ast.Var(node.index), symbols)}, {node.bound}, "
                f"{_condition(node.condition, symbols)}\\right)")
    ref = OperatorRef.of(node)
    args = [_expr(arg, symbols) for arg in node.args]
    symbol = f"\\text{{{escape(ref.symbol)}}}"
    if ref.atom in INFIX:
        text = f"{args[0]} {INFIX[ref.atom]} {args[1]}"
    elif ref.atom == "neg":
        text = f"-{args[0]}"
    elif ref.arity == 2 and ref.position is None:
        text = f"{args[0]} \\mathbin{{{symbol}}} {args[1]}"
    elif ref.arity == 1 and ref.position == "prefix":
        text = f"{symbol}\\, {args[0]}"
    elif ref.arity == 1 and ref.position == "postfix":
        text = f"{args[0]} \\,{symbol}"
    else:  # call form, any arity
        return f"\\operatorname{{{symbol}}}\\left({', '.join(_expr(a, symbols, True) for a in node.args)}\\right)"
    return text if top else f"\\left({text}\\right)"


def _condition(node: ast.Condition, symbols: Symbols) -> str:
    if isinstance(node, ast.Compare):
        return f"{_expr(node.left, symbols, True)} {COMPARE[node.op]} {_expr(node.right, symbols, True)}"
    if isinstance(node, ast.Not):
        return f"\\lnot {_operand(node.operand, symbols)}"
    op = "\\land" if isinstance(node, ast.And) else "\\lor"
    return f"{_operand(node.left, symbols)} {op} {_operand(node.right, symbols)}"


def _operand(node: ast.Condition, symbols: Symbols) -> str:
    text = _condition(node, symbols)
    return text if isinstance(node, ast.Compare) else f"\\left({text}\\right)"


# ------------------------------------------------------------------ parse


class _Reader:
    def __init__(self, text: str, symbols: Symbols) -> None:
        self.s = text
        self.i = 0
        self.symbols = symbols

    def ws(self) -> None:
        while self.i < len(self.s) and self.s[self.i].isspace():
            self.i += 1

    def at(self, literal: str) -> bool:
        self.ws()
        if not self.s.startswith(literal, self.i):
            return False
        # a command name must end here (``\\left`` is not ``\\leq``)
        end = self.i + len(literal)
        return not (literal[-1:].isalpha() and literal.startswith("\\") and end < len(self.s) and self.s[end].isalpha())

    def eat(self, literal: str) -> bool:
        if self.at(literal):
            self.i += len(literal)
            return True
        return False

    def expect(self, literal: str) -> None:
        if not self.eat(literal):
            raise LatexError(f"expected {literal!r} at {self.i}: {self.s[self.i:self.i + 30]!r}")

    def group(self) -> str:
        """A ``{...}`` group with LaTeX escapes undone."""
        self.expect("{")
        out = []
        while self.i < len(self.s):
            char = self.s[self.i]
            if char == "}":
                self.i += 1
                return "".join(out)
            if char == "\\":
                for plain, escaped in ESCAPES.items():
                    if self.s.startswith(escaped, self.i):
                        out.append(plain)
                        self.i += len(escaped)
                        break
                else:
                    raise LatexError(f"unknown escape at {self.i}")
                continue
            out.append(char)
            self.i += 1
        raise LatexError("unclosed group")

    # ---------------------------------------------------------- expressions
    def node(self) -> ast.Expr:
        if self.at("-") and not self.at("->"):
            self.expect("-")
            return ast.Apply("-", (self.unit(),), "prefix")
        if self.at("\\text"):
            self.expect("\\text")
            symbol = self.group()
            self.expect("\\,")
            return ast.Apply(symbol, (self.unit(),), "prefix")
        left = self.unit()
        for atom, mark in INFIX.items():
            if self.at(mark) and not (mark == "-" and self.at("->")):
                self.expect(mark)
                symbol = {"add": "+", "sub": "-", "mul": "*"}[atom]
                return ast.Apply(symbol, (left, self.unit()))
        if self.eat("\\mathbin"):
            self.expect("{")
            self.expect("\\text")
            symbol = self.group()
            self.expect("}")
            return ast.Apply(symbol, (left, self.unit()))
        if self.at("\\,"):
            self.expect("\\,")
            self.expect("\\text")
            return ast.Apply(self.group(), (left,), "postfix")
        return left

    def unit(self) -> ast.Expr:
        self.ws()
        if self.eat("\\left("):
            inner = self.node()
            self.expect("\\right)")
            return inner
        if self.eat("\\mathrm"):
            name = self.group()
            if name != self.symbols.nan:
                raise LatexError(f"unknown constant {name!r}")
            return ast.NaN()
        if self.eat("\\mathit"):
            return ast.Var(self.group())
        if self.eat("\\operatorname"):
            self.expect("{")
            if self.eat("search"):
                self.expect("}")
                self.expect("\\left(")
                index = self.node()
                if not isinstance(index, ast.Var):
                    raise LatexError("search index must be a variable")
                self.expect(",")
                bound = self.node()
                if not isinstance(bound, ast.Num):
                    raise LatexError("search bound must be a non-negative integer")
                self.expect(",")
                condition = self.condition()
                self.expect("\\right)")
                return ast.Search(index.name, bound.value, condition)
            self.expect("\\text")
            symbol = self.group()
            self.expect("}")
            self.expect("\\left(")
            args = [self.node()]
            while self.eat(","):
                args.append(self.node())
            self.expect("\\right)")
            return ast.Apply(symbol, tuple(args))
        if self.i < len(self.s) and self.s[self.i].isdigit():
            j = self.i
            while j < len(self.s) and self.s[j].isdigit():
                j += 1
            value = int(self.s[self.i : j])
            self.i = j
            return ast.Num(value)
        if self.i < len(self.s) and self.s[self.i].isascii() and self.s[self.i].isalpha():
            self.i += 1
            return ast.Var(self.s[self.i - 1])
        raise LatexError(f"expected an operand at {self.i}: {self.s[self.i:self.i + 30]!r}")

    # ---------------------------------------------------------- conditions
    def condition(self) -> ast.Condition:
        left = self.literal()
        if self.eat("\\land"):
            return ast.And(left, self.literal())
        if self.eat("\\lor"):
            return ast.Or(left, self.literal())
        return left

    def literal(self) -> ast.Condition:
        if self.eat("\\lnot"):
            return ast.Not(self.literal())
        start = self.i
        if self.eat("\\left("):
            try:
                inner = self.condition()
                self.expect("\\right)")
                if not any(self.at(op) for op in COMPARE.values()):
                    return inner
            except LatexError:
                pass
            self.i = start
        left = self.node()
        for op, mark in sorted(COMPARE.items(), key=lambda kv: -len(kv[1])):
            if self.eat(mark):
                return ast.Compare(left, op, self.node())
        raise LatexError(f"expected a comparison at {self.i}")


def parse(text: str, symbols: Symbols) -> ast.Definition:
    reader = _Reader(text.strip(), symbols)
    lhs = reader.node()
    if not isinstance(lhs, ast.Apply) or not all(isinstance(arg, ast.Var) for arg in lhs.args):
        raise LatexError("the left-hand side must be one operator applied to parameters")
    reader.expect("=")
    if not reader.eat("\\begin{cases}"):
        body = reader.node()
        _end(reader)
        return ast.Definition(lhs, (ast.Branch(body),))
    branches: list[ast.Branch] = []
    closed = False
    while True:
        if closed:
            raise LatexError(f"the row {NO_CASE!r} must be the last one")
        body = reader.node()
        reader.expect("&")
        reader.expect("\\text")
        label = reader.group()
        if label == "if ":
            branches.append(ast.Branch(body, reader.condition()))
        elif label == "otherwise":
            branches.append(ast.Branch(body, None, True))
        elif label == "always":
            branches.append(ast.Branch(body))
        elif label == NO_CASE and body == ast.NaN():
            closed = True
        else:
            raise LatexError(f"unknown row label {label!r}")
        if not reader.eat("\\\\"):
            break
    reader.expect("\\end{cases}")
    _end(reader)
    if not branches or closed != (branches[-1].condition is not None):
        raise LatexError(f"the row {NO_CASE!r} must appear exactly when the last case has a condition")
    return ast.Definition(lhs, tuple(branches))


def _end(reader: _Reader) -> None:
    reader.ws()
    if reader.i != len(reader.s):
        raise LatexError(f"unexpected text at {reader.i}: {reader.s[reader.i:reader.i + 30]!r}")


__all__ = ["ALWAYS", "ELSE", "IF", "LatexError", "parse", "render"]
