"""Tokenizer and parser for definitions and expressions (docs/reference/semantics.md section 8).

Hand-written instead of a generated grammar, because three things depend on
the operator set and the configured notation:

* **Operator runs.** Adjacent operator characters (``&-1``, ``-9⊽⋐``) are
  split against the known symbols. Every segmentation is enumerated; one
  segmentation is required, several are a syntax error (never a guess).
* **Roles.** Whether a symbol is binary, prefix, postfix or a call-form operator
  (three or more arguments, ``⊕(a, b, c)``) comes from the operator set, plus the
  left-hand side of the definition being parsed.
* **Notation.** Brackets, variable names, the equals sign and NaN come from
  :class:`~opulse.config.Symbols`; base-marked numerals from the registry.

Precedence: postfix binds tighter than prefix, both tighter than binary
operators (``- a @`` is ``- (a @)``; unary operators chain). A call-form
application delimits itself and is an operand like a number (``- ⊕(1, 2, 3) @``
is ``- (⊕(1, 2, 3) @)``); a symbol written before a bracket with three or more
separated arguments is read as a call, one with fewer as a prefix operator. In definitions
all binary operators share one level and associate to the left (generated
definitions are fully parenthesised). In expression mode binary operators use
the operators' ``priority`` (larger binds tighter) and associativity.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import ChainMap
from collections.abc import Callable
from dataclasses import dataclass, field

from opulse.config import Symbols
from opulse.core.operator import POSTFIX, PREFIX
from opulse.definition import ast

COMPARISONS = ("==", "!=", ">=", "<=", ">", "<")
KEYWORDS = ("if", "else", "and", "or", "not", "search")
PUNCTUATION = ("{", "}", ";", ",")
RESERVED_CHARS = set("{};,=<>!") | set("_")

BINARY_ROLE, PREFIX_ROLE, POSTFIX_ROLE, CALL_ROLE = "binary", PREFIX, POSTFIX, "call"


def role_of(n_ary: int, unary_position: str | None) -> str:
    """The notation role of an operator shape."""
    if n_ary == 2:
        return BINARY_ROLE
    if n_ary > 2:
        return CALL_ROLE
    return unary_position


class SyntaxProblem(ValueError):
    pass


@dataclass(frozen=True)
class Token:
    kind: str  # op | num | var | nan | kw | cmp | punct | sep | lparen | rparen | eq | end
    text: str
    value: object = None  # int for numbers
    base: int = 10
    pos: int = 0


@dataclass
class Notation:
    """Everything the tokenizer needs to know about symbols and numerals."""

    symbols: Symbols
    roles: dict[str, set[str]] = field(default_factory=dict)  # operator symbol -> roles
    markers: dict[str, int] = field(default_factory=dict)  # base-marker symbol -> base
    digits: str = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    variables: tuple[str, ...] = ()
    priority: dict[tuple[str, str], tuple[int, str]] = field(default_factory=dict)  # (symbol, role) -> (prio, assoc)

    @classmethod
    def from_registry(cls, registry, symbols: Symbols, digits: str | None = None,
                      variables: tuple[str, ...] = ()) -> Notation:
        notation = cls(symbols, digits=digits or cls.digits, variables=variables)
        for op in registry:
            notation.check_symbol(op.symbol)
            if op.is_base is not None:
                notation.markers[op.symbol] = op.is_base
                continue
            role = role_of(op.n_ary, op.unary_position)
            notation.roles.setdefault(op.symbol, set()).add(role)
            if op.priority is not None:
                notation.priority[(op.symbol, role)] = (op.priority, op.associativity_direction or "left")
        return notation

    def check_symbol(self, symbol: str) -> None:
        """Words used by the grammar or operands cannot also name operators."""
        reserved = set(KEYWORDS) | set(self.variables) | set(self.symbols.parameter_names) | {
            self.symbols.left_operand, self.symbols.right_operand, self.symbols.nan,
        }
        if symbol in reserved:
            raise ValueError(f"operator symbol {symbol!r} conflicts with a keyword, operand, or NaN spelling")
        separator = self.symbols.argument_separator
        if separator not in PUNCTUATION and separator in symbol:
            raise ValueError(f"operator symbol {symbol!r} contains the argument separator {separator!r}")

    def with_role(self, symbol: str, role: str) -> Notation:
        """This notation plus one role, without copying the (possibly very large) tables."""
        roles = ChainMap({symbol: self.roles.get(symbol, set()) | {role}}, self.roles)
        return Notation(self.symbols, roles, self.markers, self.digits, self.variables, self.priority)

    # --------------------------------------------------------------- lexing
    def is_operator_char(self, char: str) -> bool:
        s = self.symbols
        if char in "₀₁₂₃₄₅₆₇₈₉":
            return True
        if char.isspace() or char.isalnum() or char in RESERVED_CHARS:
            return False
        return char not in s.left_paren and char not in s.right_paren and char not in s.argument_separator

    def known(self) -> set[str]:
        return set(self.roles) | set(self.markers)


def tokenize(text: str, notation: Notation, allow_unknown: bool = True) -> list[Token]:
    s = notation.symbols
    names = set(notation.variables) | {s.left_operand, s.right_operand} | set(s.parameter_names)
    if re.search(r"\bsearch\s*" + re.escape(s.left_paren), text):
        names.add("i")
    tokens: list[Token] = []
    i, n = 0, len(text)
    separator = [] if s.argument_separator in PUNCTUATION else [(s.argument_separator, "sep")]
    fixed = sorted([(s.left_paren, "lparen"), (s.right_paren, "rparen")]
                   + [(c, "cmp") for c in COMPARISONS] + [(p, "punct") for p in PUNCTUATION]
                   + separator + [(s.equals, "eq")], key=lambda item: -len(item[0]))
    while i < n:
        char = text[i]
        if char.isspace():
            i += 1
            continue
        if text.startswith("P[", i):
            from opulse.worlds.perm import Permutation

            try:
                value, used = json.JSONDecoder().raw_decode(text[i + 1:])
                value = Permutation(value)
            except (json.JSONDecodeError, ValueError, TypeError) as exc:
                raise SyntaxProblem(f"invalid permutation at {i}: {exc}") from exc
            tokens.append(Token("literal", text[i:i + used + 1], value, pos=i))
            i += used + 1
            continue
        if char in ('"', '[') and char not in (s.left_paren, s.right_paren):
            try:
                value, used = json.JSONDecoder().raw_decode(text[i:])
            except json.JSONDecodeError as exc:
                raise SyntaxProblem(f"invalid literal at {i}: {exc}") from exc
            if char == '[' and not isinstance(value, list):
                raise SyntaxProblem(f"expected a list at {i}")
            tokens.append(Token("literal", text[i:i + used], tuple(value) if isinstance(value, list) else value,
                                pos=i))
            i += used
            continue
        matched = next(((lit, kind) for lit, kind in fixed if lit and text.startswith(lit, i)), None)
        # ``=`` (equals) vs ``==`` (comparison): the longer literal wins because of the sort.
        if matched is not None and not (matched[1] == "eq" and text.startswith("==", i)):
            tokens.append(Token(matched[1], matched[0], pos=i))
            i += len(matched[0])
            continue
        if s.nan and text.startswith(s.nan, i) and not (
                i + len(s.nan) < n and notation.is_operator_char(text[i + len(s.nan)])):
            tokens.append(Token("nan", s.nan, pos=i))
            i += len(s.nan)
            continue
        # Shape-index names begin with a symbol glyph and continue with letters or
        # subscript digits. Read the complete name before attempting numeral lexing.
        if unicodedata.category(char) in ("So", "Sm") and i + 1 < n and text[i + 1].isalnum():
            j = i + 1
            while j < n and text[j].isalnum():
                j += 1
            compound = text[i:j]
            marker_number = any(text.startswith(marker, i) and i + len(marker) < n and
                                text[i + len(marker)] in notation.digits[:base]
                                for marker, base in notation.markers.items())
            if not marker_number and (compound in notation.roles or char not in notation.roles):
                _split(compound, i, notation, tokens, allow_unknown)
                i = j
                continue
        if char in notation.digits[:10]:
            j = i
            while j < n and text[j] in notation.digits[:10]:
                j += 1
            value = 0
            for digit in text[i:j]:
                value = value * 10 + notation.digits.index(digit)
            tokens.append(Token("num", text[i:j], value, 10, i))
            i = j
            continue
        if char.isalpha():
            j = i
            while j < n and (text[j].isalpha() or text[j].isdigit()):
                j += 1
            word = text[i:j]
            if word in KEYWORDS:
                tokens.append(Token("kw", word, pos=i))
            elif word in ("true", "false"):
                tokens.append(Token("literal", word, word == "true", pos=i))
            elif word == s.nan:
                tokens.append(Token("nan", word, pos=i))
            elif word in names:
                tokens.append(Token("var", word, pos=i))
            elif word.isascii() and (word in notation.roles or word in notation.markers):
                tokens.append(Token("op", word, pos=i))
            elif word.isalpha() and not word.isascii():
                # Operator symbols may be non-ASCII letters (e.g. Greek); they are written
                # separated by spaces or brackets, so the whole word is a run of symbols.
                _split(word, i, notation, tokens, allow_unknown)
            else:
                raise SyntaxProblem(f"unknown word {word!r} at {i}")
            i = j
            continue
        if notation.is_operator_char(char):
            j = i
            while j < n and notation.is_operator_char(text[j]):
                j += 1
            i = _operator_run(text, i, j, notation, tokens, allow_unknown)
            continue
        raise SyntaxProblem(f"unexpected character {char!r} at {i}")
    tokens.append(Token("end", "", pos=n))
    return tokens


def _operator_run(text: str, start: int, end: int, notation: Notation, out: list[Token],
                  allow_unknown: bool) -> int:
    """Split ``text[start:end]`` into symbols; a trailing base marker swallows its digits."""
    run = text[start:end]
    # A base marker directly followed by digits is a numeral: ``⊺⇮1A``.
    for marker, base in sorted(notation.markers.items(), key=lambda kv: -len(kv[0])):
        if run.endswith(marker):
            k = end
            digits = notation.digits[:base]
            while k < len(text) and text[k] in digits:
                k += 1
            if k > end:
                head = run[: len(run) - len(marker)]
                if head:
                    _split(head, start, notation, out, allow_unknown)
                literal = text[end:k]
                value = 0
                for d in literal:
                    value = value * base + digits.index(d)
                out.append(Token("num", marker + literal, value, base, end - len(marker)))
                return k
    _split(run, start, notation, out, allow_unknown)
    return end


def _split(run: str, pos: int, notation: Notation, out: list[Token], allow_unknown: bool) -> None:
    segmentations = _segmentations(run, notation.roles, limit=2)
    if len(segmentations) == 1:
        offset = pos
        for symbol in segmentations[0]:
            out.append(Token("op", symbol, pos=offset))
            offset += len(symbol)
        return
    if len(segmentations) > 1:
        raise SyntaxProblem(f"operator run {run!r} at {pos} splits in more than one way: "
                            f"{segmentations[0]} / {segmentations[1]}")
    if allow_unknown:
        out.append(Token("op", run, pos=pos))  # one unknown symbol (e.g. a definition's own)
        return
    raise SyntaxProblem(f"operator run {run!r} at {pos} is not made of known symbols")


def _segmentations(run: str, known, limit: int) -> list[list[str]]:
    """Up to ``limit`` ways to write ``run`` as a concatenation of known symbols.

    Tries every piece length at every position: O(len(run)^2) lookups, independent of how
    many symbols are known (runs are a few characters; registries can hold 100k symbols).
    """
    found: list[list[str]] = []

    def walk(i: int, acc: list[str]) -> None:
        if len(found) >= limit:
            return
        if i == len(run):
            found.append(list(acc))
            return
        for length in range(len(run) - i, 0, -1):
            piece = run[i : i + length]
            if piece in known:
                acc.append(piece)
                walk(i + length, acc)
                acc.pop()

    walk(0, [])
    return found


# ------------------------------------------------------------------- parsing


class _Parser:
    def __init__(self, tokens: list[Token], notation: Notation, expression_mode: bool,
                 strict: bool = False) -> None:
        self.tokens = tokens
        self.i = 0
        self.notation = notation
        self.expression_mode = expression_mode
        self.strict = strict  # every binary operand that is itself binary must be parenthesised

    # ---------------------------------------------------------- utilities
    @property
    def tok(self) -> Token:
        return self.tokens[self.i]

    def peek(self, k: int = 1) -> Token:
        return self.tokens[min(self.i + k, len(self.tokens) - 1)]

    def take(self, kind: str, text: str | None = None) -> Token:
        tok = self.tok
        if tok.kind != kind or (text is not None and tok.text != text):
            want = text or kind
            raise SyntaxProblem(f"expected {want!r} at {tok.pos}, found {tok.text or tok.kind!r}")
        self.i += 1
        return tok

    def roles(self, symbol: str) -> set[str]:
        return self.notation.roles.get(symbol, set())

    @staticmethod
    def starts_operand(tok: Token) -> bool:
        return tok.kind in ("num", "literal", "var", "nan", "lparen", "op") or \
            (tok.kind == "kw" and tok.text == "search")

    # -------------------------------------------------------- expressions
    def expr(self, min_level: int = 0) -> ast.Expr:
        if self.strict:
            return self._strict_expr()
        left = self.unary()
        while self.tok.kind == "op" and self._is_binary_here():
            symbol = self.tok.text
            level, assoc = self._binary_level(symbol)
            if level < min_level:
                break
            self.i += 1
            right = self.expr(level + 1 if assoc == "left" else level)
            left = ast.Apply(symbol, (left, right))
        return left

    def _strict_expr(self) -> ast.Expr:
        left = self.unary()
        if self.tok.kind == "op" and self._is_binary_here():
            symbol = self.tok.text
            self.i += 1
            left = ast.Apply(symbol, (left, self.unary()))
            if self.tok.kind == "op" and self._is_binary_here():
                raise SyntaxProblem(f"{symbol!r} and {self.tok.text!r} at {self.tok.pos} need parentheses")
        return left

    def _is_binary_here(self) -> bool:
        roles = self.roles(self.tok.text)
        if BINARY_ROLE in roles:
            return True
        return not roles and self.starts_operand(self.peek())  # unknown symbol between operands

    def _binary_level(self, symbol: str) -> tuple[int, str]:
        if not self.expression_mode:
            return 1, "left"
        prio, assoc = self.notation.priority.get((symbol, BINARY_ROLE), (1, "left"))
        return prio, assoc

    def is_separator(self, tok: Token) -> bool:
        return tok.kind in ("sep", "punct") and tok.text == self.notation.symbols.argument_separator

    def _try_call(self) -> ast.Apply | None:
        """``symbol(arg, arg, arg, ...)`` with three or more arguments, else None (nothing consumed)."""
        tok = self.tok
        roles = self.roles(tok.text)
        if self.peek().kind != "lparen" or (roles and CALL_ROLE not in roles):
            return None
        start = self.i
        self.i += 2
        try:
            args = [self.expr()]
            while self.is_separator(self.tok):
                self.i += 1
                args.append(self.expr())
            self.take("rparen")
        except SyntaxProblem:
            if roles == {CALL_ROLE}:
                raise
            self.i = start
            return None
        if len(args) < 3:
            if roles == {CALL_ROLE}:
                raise SyntaxProblem(f"{tok.text!r} at {tok.pos} takes three or more arguments, got {len(args)}")
            self.i = start
            return None
        return ast.Apply(tok.text, tuple(args))

    def unary(self) -> ast.Expr:
        tok = self.tok
        if tok.kind == "op":
            call = self._try_call()
            if call is not None:
                return self.postfix(call)
            roles = self.roles(tok.text)
            if PREFIX_ROLE in roles or not roles:
                self.i += 1
                return ast.Apply(tok.text, (self.unary(),), PREFIX)
            raise SyntaxProblem(f"{tok.text!r} at {tok.pos} cannot start an operand")
        return self.postfix()

    def postfix(self, node: ast.Expr | None = None) -> ast.Expr:
        node = self.atom() if node is None else node
        while self.tok.kind == "op":
            roles = self.roles(self.tok.text)
            binary_reading = (BINARY_ROLE in roles or not roles) and self.starts_operand(self.peek())
            if (POSTFIX_ROLE in roles or not roles) and not binary_reading:
                node = ast.Apply(self.tok.text, (node,), POSTFIX)
                self.i += 1
                continue
            break
        return node

    def atom(self) -> ast.Expr:
        tok = self.tok
        if tok.kind == "kw" and tok.text == "search":
            self.i += 1
            self.take("lparen")
            index = self.take("var").text
            if index != "i":
                raise SyntaxProblem("search index must be i")
            self._take_separator()
            bound = self.take("num")
            self._take_separator()
            condition = self.condition()
            self.take("rparen")
            return ast.Search(index, bound.value, condition)
        if tok.kind == "num":
            self.i += 1
            return ast.Num(tok.value, tok.base)
        if tok.kind == "literal":
            self.i += 1
            return ast.Literal(tok.value)
        if tok.kind == "var":
            self.i += 1
            return ast.Var(tok.text)
        if tok.kind == "nan":
            self.i += 1
            return ast.NaN()
        if tok.kind == "lparen":
            self.i += 1
            node = self.expr()
            self.take("rparen")
            return node
        raise SyntaxProblem(f"expected an operand at {tok.pos}, found {tok.text or tok.kind!r}")

    def _take_separator(self) -> None:
        if not self.is_separator(self.tok):
            raise SyntaxProblem(f"expected argument separator at {self.tok.pos}")
        self.i += 1

    # --------------------------------------------------------- conditions
    def condition(self) -> ast.Condition:
        node = self.conjunction()
        while self.tok.kind == "kw" and self.tok.text == "or":
            self.i += 1
            node = ast.Or(node, self.conjunction())
        return node

    def conjunction(self) -> ast.Condition:
        node = self.negation()
        while self.tok.kind == "kw" and self.tok.text == "and":
            self.i += 1
            node = ast.And(node, self.negation())
        return node

    def negation(self) -> ast.Condition:
        if self.tok.kind == "kw" and self.tok.text == "not":
            self.i += 1
            return ast.Not(self.negation())
        start = self.i
        try:  # a comparison, possibly starting with a parenthesised expression
            left = self.expr()
            op = self.take("cmp").text
            return ast.Compare(left, op, self.expr())
        except SyntaxProblem:
            self.i = start
        try:
            expression = self.expr()
            if self.tok.kind in ("punct", "end", "rparen"):
                return ast.Truth(expression)
        except SyntaxProblem:
            pass
        self.i = start
        if self.tok.kind == "lparen":  # a parenthesised condition
            self.i += 1
            node = self.condition()
            self.take("rparen")
            return node
        raise SyntaxProblem(f"expected a condition at {self.tok.pos}")

    # --------------------------------------------------------- definitions
    def definition(self) -> ast.Definition:
        lhs = self.lhs()
        self.take("eq")
        self.take("punct", "{")
        branches = [self.branch()]
        while self.tok.kind == "punct" and self.tok.text == ";":
            self.i += 1
            branches.append(self.branch())
        self.take("punct", "}")
        self.take("end")
        return ast.Definition(lhs, tuple(branches))

    def lhs(self) -> ast.Apply:
        t0, t1, t2 = self.tok, self.peek(1), self.peek(2)
        if t0.kind == "op" and t1.kind == "lparen":  # call form: ⊕(a, b, c)
            self.i += 2
            names = [self.take("var").text]
            while self.is_separator(self.tok):
                self.i += 1
                names.append(self.take("var").text)
            self.take("rparen")
            if len(names) < 3:
                raise SyntaxProblem("call form is for three or more parameters; write 'a ⊕ b', '⊕ a' or 'a ⊕'")
            if len(set(names)) != len(names):
                raise SyntaxProblem(f"parameters of {t0.text!r} repeat a name: {names}")
            node, role = ast.Apply(t0.text, tuple(ast.Var(name) for name in names)), CALL_ROLE
        elif t0.kind == "var" and t1.kind == "op" and t2.kind == "var":
            if t0.text == t2.text:
                raise SyntaxProblem(f"parameters of {t1.text!r} repeat a name: {t0.text}")
            self.i += 3
            node = ast.Apply(t1.text, (ast.Var(t0.text), ast.Var(t2.text)))
            role = BINARY_ROLE
        elif t0.kind == "op" and t1.kind == "var":
            self.i += 2
            node, role = ast.Apply(t0.text, (ast.Var(t1.text),), PREFIX), PREFIX_ROLE
        elif t0.kind == "var" and t1.kind == "op":
            self.i += 2
            node, role = ast.Apply(t1.text, (ast.Var(t0.text),), POSTFIX), POSTFIX_ROLE
        else:
            raise SyntaxProblem("left-hand side must be one operator applied to variables")
        if self.tok.kind != "eq":
            raise SyntaxProblem("left-hand side must be one operator applied to variables")
        self.notation = self.notation.with_role(node.symbol, role)
        return node

    def branch(self) -> ast.Branch:
        expr = self.expr()
        if self.tok.kind == "punct" and self.tok.text == ",":
            self.i += 1
            if self.tok.kind == "kw" and self.tok.text == "else":
                self.i += 1
                return ast.Branch(expr, is_else=True)
            self.take("kw", "if")
            return ast.Branch(expr, self.condition())
        return ast.Branch(expr)


def parse_definition(text: str, notation: Notation) -> ast.Definition:
    lhs_notation = notation
    tokens = tokenize(text, lhs_notation)
    # Re-tokenize with the new symbol known, so its occurrences in the body split correctly.
    parser = _Parser(tokens, notation, expression_mode=False)
    lhs = parser.lhs()
    role = role_of(lhs.n_ary, lhs.unary_position)
    full = notation.with_role(lhs.symbol, role)
    parser = _Parser(tokenize(text, full), full, expression_mode=False)
    definition = parser.definition()
    # Names beyond a and b (c, d, ...) are parameters only of operators that declare them.
    known = set(definition.parameters) | set(notation.variables) | {
        notation.symbols.left_operand, notation.symbols.right_operand}
    used = set().union(*(ast.branch_variables(branch) for branch in definition.branches))
    if used - known:
        raise SyntaxProblem(f"unknown word {min(used - known)!r}: not a parameter of {lhs.symbol!r}")
    return definition


def parse_expression(text: str, notation: Notation, expression_mode: bool = True,
                     strict: bool = False) -> ast.Expr:
    """``strict`` rejects a binary operation used as an operand of another without parentheses."""
    parser = _Parser(tokenize(text, notation), notation, expression_mode, strict)
    node = parser.expr()
    parser.take("end")
    return node


def parse_condition(text: str, notation: Notation) -> ast.Condition:
    parser = _Parser(tokenize(text, notation), notation, expression_mode=False)
    node = parser.condition()
    parser.take("end")
    return node


Writer = Callable[[int, int], str]  # (value, base) -> numeral text
