"""Controlled English and Chinese: realize a definition as prose and parse the prose back.

The realizer draws one phrase per construct from :mod:`opulse.language.views.lexicon` with a
seeded random generator, so the same definition reads differently under different seeds. The
parser is a memoizing parser over the same phrase table that returns *every* reading of a
line; a text is accepted only when each line has exactly one reading. The realizer parses its
own output and keeps a text only when the parse gives back the definition it started from
(literals compared by value); after a few tries it switches to an explicit form that brackets
every compound operand, and raises if even that fails. A prose definition is therefore an
exact, checkable statement of the rule, not a paraphrase that could drift from it.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field

from opulse.config import Symbols
from opulse.core.semantics import BASE_OPERATIONS
from opulse.definition import ast
from opulse.language.ir import (
    ELSE,
    IF,
    Concept,
    OperatorRef,
    depth,
    has_call_form,
    has_search,
    normalize,
    parameter_names,
    parse_lhs,
    substitute,
    subterms,
)
from opulse.language.views.lexicon import LEXICONS, WHERE_NAMES

LANGS = ("en", "zh")
CJK = re.compile(r"[⺀-⿟　-〿぀-ヿ㐀-䶿一-鿿豈-﫿＀-￯]")
CJK_PUNCT = set("，。；：「」、（）！？")
NO_SPACE_BEFORE = set(",.;:)") | {"，", "。", "；", "：", "」", "、", "）"}
NO_SPACE_AFTER = {"(", "「", "（"}
NUMBERING = re.compile(r"^\s*\d+\.\s+")


class ProseError(ValueError):
    """A text that is not a definition in the controlled language (or has two readings)."""


@dataclass(frozen=True)
class Tok:
    kind: str  # word | num | sym | punct
    text: str

    def same(self, other: Tok) -> bool:
        if self.kind != other.kind:
            return False
        if self.kind == "word":
            return self.text.lower() == other.text.lower()
        return self.text == other.text


@dataclass(frozen=True)
class Slot:
    cat: str
    index: int | None = None  # argument index for ``{E:1}``


# ------------------------------------------------------------------ tokens


def tokenize(text: str, protected: tuple[str, ...] = ()) -> list[Tok]:
    """Words, decimal numbers, backtick symbols and punctuation. Each CJK character is a word,
    so Chinese needs no spaces; ``protected`` words (parameters, the NaN spelling) stay whole."""
    tokens: list[Tok] = []
    protected = tuple(sorted(protected, key=len, reverse=True))
    i, n = 0, len(text)
    while i < n:
        char = text[i]
        if char.isspace():
            i += 1
            continue
        if char == "`":
            j = text.find("`", i + 1)
            if j < 0:
                raise ProseError(f"unclosed backtick at {i}")
            tokens.append(Tok("sym", text[i + 1 : j]))
            i = j + 1
            continue
        word = next((w for w in protected if w and text.startswith(w, i) and _bounded(text, i, len(w))), None)
        if word is not None:
            tokens.append(Tok("word", word))
            i += len(word)
            continue
        if char in "0123456789":
            j = i
            while j < n and text[j] in "0123456789":
                j += 1
            tokens.append(Tok("num", text[i:j]))
            i = j
            continue
        if CJK.match(char):
            tokens.append(Tok("punct" if char in CJK_PUNCT else "word", char))
            i += 1
            continue
        if char.isalnum() or char == "_":
            j = i
            while j < n and (text[j].isalnum() or text[j] == "_") and not CJK.match(text[j]):
                j += 1
            tokens.append(Tok("word", text[i:j]))
            i = j
            continue
        tokens.append(Tok("punct", char))
        i += 1
    return tokens


def _bounded(text: str, start: int, length: int) -> bool:
    """A protected ASCII word must not be part of a longer word."""
    end = start + length
    word = text[start:end]
    if not (word[0].isalnum() or word[0] == "_") or CJK.match(word[0]):
        return True
    before = text[start - 1] if start else " "
    after = text[end] if end < len(text) else " "
    inside = lambda c: (c.isalnum() or c == "_") and not CJK.match(c)
    return not inside(before) and not inside(after)


def detokenize(tokens: list[Tok]) -> str:
    out: list[str] = []
    previous: Tok | None = None
    for tok in tokens:
        text = f"`{tok.text}`" if tok.kind == "sym" else tok.text
        if previous is not None and _space(previous, tok):
            out.append(" ")
        out.append(text)
        previous = tok
    return "".join(out)


def _space(left: Tok, right: Tok) -> bool:
    if right.text in NO_SPACE_BEFORE and right.kind == "punct":
        return False
    if left.text in NO_SPACE_AFTER and left.kind == "punct":
        return False
    cjk = lambda tok: tok.kind in ("word", "punct") and bool(CJK.match(tok.text[:1]))
    if cjk(left) and cjk(right):
        return False
    return not (cjk(left) and left.kind == "punct" or cjk(right) and right.kind == "punct")


# ------------------------------------------------------------------ phrases


@dataclass(frozen=True)
class Rule:
    cat: str
    items: tuple  # Tok | Slot
    kind: tuple

    @property
    def slots(self) -> list[Slot]:
        return [item for item in self.items if isinstance(item, Slot)]


SLOT = re.compile(r"\{([A-Z]+)(?::(\d+))?\}")


def compile_pattern(pattern: str, protected: tuple[str, ...]) -> tuple:
    items: list = []
    position = 0
    for match in SLOT.finditer(pattern):
        items += tokenize(pattern[position : match.start()], protected)
        index = int(match.group(2)) if match.group(2) is not None else None
        items.append(Slot(match.group(1), index))
        position = match.end()
    items += tokenize(pattern[position:], protected)
    return tuple(items)


class Grammar:
    """The phrase table of one language under one notation (the NaN spelling)."""

    def __init__(self, lang: str, symbols: Symbols) -> None:
        if lang not in LANGS:
            raise ValueError(f"lang must be one of {LANGS}")
        self.lang = lang
        self.symbols = symbols
        lexicon = LEXICONS[lang]
        self.includes: dict[str, tuple[str, ...]] = lexicon["includes"]
        self.operand: str = lexicon["operand"]
        self.generic_cat: str = lexicon["generic"]
        self.separator: str = lexicon["separator"]
        self.last: str = lexicon["last"]
        self.qualifiers: dict[str, str] = lexicon["qualifiers"]
        self.protected = (symbols.nan,)
        by_name = {name: key for key, name in BASE_OPERATIONS.items()}
        self.rules: dict[str, list[Rule]] = {}
        for cat, pattern, kind in lexicon["rules"]:
            if kind[0] == "atom" or kind[0] == "neglit":
                name = kind[1] if kind[0] == "atom" else "neg"
                if name not in by_name:
                    continue  # the atom is not registered in this session
                pattern = pattern.replace("{SYMBOL}", by_name[name][0])
            pattern = pattern.replace("{NAN}", symbols.nan)
            self._add(Rule(cat, compile_pattern(pattern, self.protected), kind))
        self.generic: list[tuple[str, tuple]] = []
        for pattern in lexicon["unary"]:
            self.generic.append(("unary", compile_pattern(pattern, self.protected)))
        for pattern in lexicon["qualified"]:
            self.generic.append(("qualified", compile_pattern(pattern, self.protected)))
        for pattern in lexicon["nary"]:
            self.generic.append(("nary", compile_pattern(pattern, self.protected)))

    def _add(self, rule: Rule) -> None:
        self.rules.setdefault(rule.cat, []).append(rule)

    def closure(self, cat: str) -> list[str]:
        """``cat`` and every category it includes, nearest first."""
        found = [cat]
        for item in found:
            for sub in self.includes.get(item, ()):
                if sub not in found:
                    found.append(sub)
        return found

    def args_items(self, arity: int) -> tuple:
        """``{E}, {E} and {E}`` (or the Chinese ``{B}、{B} 与 {B}``) for ``arity`` arguments."""
        items: list = []
        for index in range(arity):
            if index:
                text = self.last if index == arity - 1 else self.separator
                items.append(Tok("punct" if text in (",", "、") else "word", text))
            items.append(Slot(self.operand, index))
        return tuple(items)


# ------------------------------------------------------------------ parser


@dataclass
class _Context:
    params: tuple[str, ...]
    names: tuple[str, ...]  # where-names of the current line
    table: dict[tuple[str, int], set]


class _Parser:
    def __init__(self, grammar: Grammar, tokens: list[Tok], context: _Context) -> None:
        self.g = grammar
        self.tokens = tokens
        self.context = context
        self.memo: dict[tuple[str, int], list] = {}

    def parse(self, cat: str, pos: int) -> list[tuple[object, int]]:
        key = (cat, pos)
        if key in self.memo:
            return self.memo[key]
        self.memo[key] = []  # a category reached again at the same position adds nothing
        results: list[tuple[object, int]] = []
        for sub in self.g.closure(cat):
            results += self._builtin(sub, pos)
            for rule in self.g.rules.get(sub, ()):
                for values, end in self._sequence(rule.items, 0, pos, []):
                    for node in _build(rule.kind, values, rule):
                        results.append((node, end))
            if sub == self.g.generic_cat:
                results += self._generic(pos)
        unique = list(dict.fromkeys(results))[:24]
        self.memo[key] = unique
        return unique

    def _sequence(self, items: tuple, index: int, pos: int, values: list):
        if index == len(items):
            yield list(values), pos
            return
        item = items[index]
        if isinstance(item, Tok):
            if pos < len(self.tokens) and self.tokens[pos].same(item):
                yield from self._sequence(items, index + 1, pos + 1, values)
            return
        for value, end in self.parse(item.cat, pos):
            values.append((item, value))
            yield from self._sequence(items, index + 1, end, values)
            values.pop()

    def _builtin(self, cat: str, pos: int) -> list[tuple[object, int]]:
        if pos >= len(self.tokens):
            return []
        tok = self.tokens[pos]
        if cat == "A":
            if tok.kind == "num":
                return [(ast.Num(int(tok.text)), pos + 1)]
            if tok.kind == "word" and tok.text == self.g.symbols.nan:
                return [(ast.NaN(), pos + 1)]
            if tok.kind == "word" and (tok.text in self.context.params or tok.text in self.context.names):
                return [(ast.Var(tok.text), pos + 1)]
        if cat == "N" and tok.kind == "num":
            return [(ast.Num(int(tok.text)), pos + 1)]
        if cat == "V" and tok.kind == "word" and tok.text in self.context.names:
            return [(tok.text, pos + 1)]
        if cat in ("SYM", "LHS") and tok.kind == "sym":
            return [(tok.text, pos + 1)]
        return []

    def _generic(self, pos: int) -> list[tuple[object, int]]:
        results = []
        for shape, items in self.g.generic:
            if shape == "nary":
                for arity in range(2, 7):
                    expanded = _expand_args(items, self.g.args_items(arity))
                    for values, end in self._sequence(expanded, 0, pos, []):
                        results += [(node, end) for node in self._apply_generic(values, arity, None)]
            elif shape == "unary":
                for values, end in self._sequence(items, 0, pos, []):
                    results += [(node, end) for node in self._apply_generic(values, 1, None)]
            else:
                for position, word in self.g.qualifiers.items():
                    qualified = _expand_qualifier(items, word, self.g.protected, self.g.operand)
                    for values, end in self._sequence(qualified, 0, pos, []):
                        results += [(node, end) for node in self._apply_generic(values, 1, position)]
        return results

    def _apply_generic(self, values: list, arity: int, position: str | None) -> list[ast.Apply]:
        symbol = next(value for slot, value in values if slot.cat == "SYM")
        args = [value for slot, value in values if slot.cat == self.g.operand]
        positions = self.context.table.get((symbol, arity), set())
        if position is not None:
            positions = positions & {position}
        nodes = []
        for candidate in sorted(positions, key=str):
            try:
                nodes.append(ast.Apply(symbol, tuple(args), candidate))
            except ValueError:
                continue
        return nodes


def _expand_args(items: tuple, args: tuple) -> tuple:
    out: list = []
    for item in items:
        if isinstance(item, Slot) and item.cat == "ARGS":
            out += args
        else:
            out.append(item)
    return tuple(out)


def _expand_qualifier(items: tuple, word: str, protected, operand: str) -> tuple:
    out: list = []
    for item in items:
        if isinstance(item, Slot) and item.cat == "QUAL":
            out += tokenize(word, protected)
        elif isinstance(item, Slot) and item.cat == operand:
            out.append(Slot(item.cat, 0))
        else:
            out.append(item)
    return tuple(out)


def _ordered(values: list, cats: tuple[str, ...]) -> list:
    """Slot values of the given categories in argument order (``{E:1}`` puts a value at 1)."""
    picked = [(slot, value) for slot, value in values if slot.cat in cats]
    if any(slot.index is not None for slot, _ in picked):
        picked.sort(key=lambda sv: sv[0].index)
    return [value for _, value in picked]


def _build(kind: tuple, values: list, rule: Rule) -> list:
    head = kind[0]
    if head == "atom":
        key = next(key for key, name in BASE_OPERATIONS.items() if name == kind[1])
        args = _ordered(values, ("E", "B", "A", "N", "T"))
        try:
            return [ast.Apply(key[0], tuple(args), key[2])]
        except ValueError:
            return []
    if head == "neglit":
        return [ast.Apply("-", (values[0][1],), "prefix")]
    if head in ("paren", "group"):
        return [values[0][1]]
    if head == "cmp":
        return [ast.Compare(values[0][1], kind[1], values[1][1])]
    if head == "zero":
        return [ast.Compare(values[0][1], kind[1], ast.Num(0))]
    if head == "pair":
        return [(values[0][1], values[1][1])]
    if head == "cons":
        return [(values[0][1],) + values[1][1]]
    if head in ("andlist", "orlist"):
        parts = (values[0][1],) + values[1][1]
        joined = parts[0]
        for part in parts[1:]:
            joined = ast.And(joined, part) if head == "andlist" else ast.Or(joined, part)
        return [joined]
    if head == "and":
        return [ast.And(values[0][1], values[1][1])]
    if head == "or":
        return [ast.Or(values[0][1], values[1][1])]
    if head == "not":
        return [ast.Not(values[0][1])]
    if head == "wt_none":
        return [()]
    if head == "wt":
        return [values[0][1]]
    if head == "wl_one":
        return [((values[0][1], values[1][1]),)]
    if head == "wl_more":
        return [((values[0][1], values[1][1]),) + values[2][1]]
    # sentences: a tuple of the kind and the slot values by category
    found = {slot.cat: value for slot, value in values}
    return [(kind, found.get("LHS"), found.get("G"), found.get("T"), found.get("WT", ()))]


# ------------------------------------------------------------------ realizer


@dataclass
class _Realizer:
    g: Grammar
    table: dict[tuple[str, int], set]
    rng: random.Random
    explicit: bool = False
    where: float = 0.35  # chance that a long body names a part with "where"
    used: dict = field(default_factory=dict)

    def pick(self, options: list):
        return options[0] if self.explicit else self.rng.choice(options)

    # ---------------------------------------------------------- expressions
    def expr(self, node: ast.Expr, cat: str) -> list[Tok]:
        if isinstance(node, ast.Var):
            return [Tok("word", node.name)]
        if isinstance(node, ast.Num):
            return [Tok("num", str(node.value))]
        if isinstance(node, ast.NaN):
            return [Tok("word", self.g.symbols.nan)]
        options = self._options(node, cat)
        if not options:
            raise ProseError(f"no phrase can state {node!r} in {self.g.lang}")
        items, children = self.pick(options)
        return self._fill(items, children)

    def _options(self, node: ast.Apply, cat: str) -> list[tuple[tuple, dict]]:
        options = []
        for sub in self.g.closure(cat):
            for rule in self.g.rules.get(sub, ()):
                if rule.kind[0] == "paren":
                    if sub == "B":  # Chinese operands: a compound expression always goes in 「」
                        options.append((rule.items, {0: (node, "T")}))
                    continue
                children = _match(rule, node)
                if children is not None:
                    options.append((rule.items, children))
                    if rule.kind[0] == "neglit" and not self.explicit and self.rng.random() < 0.7:
                        return [(rule.items, children)]  # "negative 5" reads best for constants
            if sub == self.g.generic_cat:
                generic = self._generic_options(node)
                natural = [option for option in options if option[0] != ("paren",)]
                # Atoms with their own phrases ("the sum of") are not written in symbol form.
                if not (OperatorRef.of(node).atom and natural and cat != "B"):
                    options += generic
        if self.g.lang == "zh":
            # A compound operand is bracketed; anything else is stated by its own phrase.
            bracketed = [option for option in options if option[0] and option[0][0] == Tok("punct", "「")]
            plain = [option for option in options if option not in bracketed]
            options = bracketed if cat == "B" else plain
        if self.explicit and options:
            # Prefer generic or prefix phrases whose operands are bracketed (no infix forms).
            options.sort(key=lambda option: isinstance(option[0][0], Slot))
        return options

    def _generic_options(self, node: ast.Apply) -> list:
        ref = OperatorRef.of(node)
        positions = self.table.get((ref.symbol, ref.arity), set())
        if ref.position not in positions:
            return []
        options = []
        for shape, items in self.g.generic:
            if shape == "nary" and ref.arity >= 2:
                expanded = _expand_args(items, self.g.args_items(ref.arity))
            elif shape == "unary" and ref.arity == 1 and len(positions) == 1:
                expanded = tuple(Slot(item.cat, 0) if isinstance(item, Slot) and item.cat == self.g.operand
                                 else item for item in items)
            elif shape == "qualified" and ref.arity == 1 and len(positions) > 1:
                expanded = _expand_qualifier(items, self.g.qualifiers[ref.position], self.g.protected,
                                             self.g.operand)
            else:
                continue
            children = {"SYM": ref.symbol}
            for item in expanded:
                if isinstance(item, Slot) and item.cat == self.g.operand:
                    children[item.index] = (node.args[item.index], self.g.operand)
            options.append((expanded, children))
        return options

    def _fill(self, items: tuple, children: dict) -> list[Tok]:
        out: list[Tok] = []
        counter = 0
        for item in items:
            if isinstance(item, Tok):
                out.append(item)
                continue
            if item.cat == "SYM":
                out.append(Tok("sym", children["SYM"]))
                continue
            index = item.index if item.index is not None else counter
            counter += 1
            child, cat = children[index]
            if cat in ("E", "B", "T", "A", "N"):
                if self.explicit and cat == "E" and isinstance(child, ast.Apply):
                    out += [Tok("punct", "(")] + self.expr(child, "T") + [Tok("punct", ")")]
                else:
                    out += self.expr(child, cat)
            else:
                out += self.condition(child, cat)
        return out

    # ---------------------------------------------------------- conditions
    def condition(self, node: ast.Condition, cat: str) -> list[Tok]:
        options = []
        for sub in self.g.closure(cat):
            for rule in self.g.rules.get(sub, ()):
                if rule.kind[0] == "group":
                    continue
                children = _match(rule, node)
                if children is not None:
                    options.append((rule.items, children))
        if cat == "G" and isinstance(node, (ast.And, ast.Or)) and not self.explicit:
            spine = _spine(node)
            if len(spine) >= 3 and self.rng.random() < 0.7:
                return self._list(spine, isinstance(node, ast.And))
        if not options or (self.explicit and isinstance(node, (ast.And, ast.Or)) and cat == "C"):
            group = next(rule for rule in self.g.rules["C"] if rule.kind[0] == "group")
            return self._fill(group.items, {0: (node, "G")})
        items, children = self.pick(options)
        return self._fill(items, children)

    def _list(self, parts: list, conjunction: bool) -> list[Tok]:
        """``A, B, C and D`` for a left-nested chain of one connective."""
        rules = {rule.kind[0]: rule for rule in self.g.rules["AL" if conjunction else "OL"]}
        separator = next(item for item in rules["cons"].items if isinstance(item, Tok))
        word = next(item for item in rules["pair"].items if isinstance(item, Tok))
        out: list[Tok] = []
        for index, part in enumerate(parts):
            if index:
                out.append(word if index == len(parts) - 1 else separator)
            out += self.condition(part, "C")
        return out

    # ---------------------------------------------------------- sentences
    def sentence(self, cat: str, kinds: tuple, slots: dict) -> list[Tok]:
        options = [rule for rule in self.g.rules[cat] if rule.kind in kinds]
        rule = self.pick(options)
        out: list[Tok] = []
        for item in rule.items:
            if isinstance(item, Tok):
                out.append(item)
            elif item.cat == "LHS":
                out.append(Tok("sym", slots["LHS"]))
            elif item.cat == "G":
                out += self.condition(slots["G"], "G")
            elif item.cat == "T":
                out += self.expr(slots["T"], "T")
            elif item.cat == "WT":
                out += self.where_tail(slots.get("WT", ()))
        return out

    def where_tail(self, clauses: tuple) -> list[Tok]:
        tail_rules = {rule.kind[0]: rule for rule in self.g.rules["WT"]}
        if not clauses:
            return []
        out = [item for item in tail_rules["wt"].items if isinstance(item, Tok)]
        list_rules = {rule.kind[0]: rule for rule in self.g.rules["WL"]}
        for position, (name, expr) in enumerate(clauses):
            rule = list_rules["wl_more" if position < len(clauses) - 1 else "wl_one"]
            for item in rule.items:
                if isinstance(item, Tok):
                    out.append(item)
                elif item.cat == "V":
                    out.append(Tok("word", name))
                elif item.cat == "T":
                    out += self.expr(expr, "T")
        return out

    def lift(self, body: ast.Expr, taken: set[str]) -> tuple[ast.Expr, tuple]:
        """Name up to two large parts of a long body ("..., where u is ...")."""
        clauses: list = []
        if self.explicit or depth(body) < 3 or self.rng.random() >= self.where:
            return body, ()
        for _ in range(2):
            parts = [node for node in subterms(body) if node is not body and depth(node) >= 2]
            if not parts:
                break
            part = max(parts, key=depth)
            name = next((n for n in WHERE_NAMES if n not in taken), None)
            if name is None:
                break
            taken.add(name)
            body = substitute(body, {part: ast.Var(name)})
            clauses.append((name, part))
            if depth(body) < 3:
                break
        return body, tuple(clauses)


def _spine(node: ast.Condition) -> list:
    """The parts of a left-nested chain ``((A and B) and C) and D`` of one connective."""
    kind = type(node)
    parts = []
    while isinstance(node, kind):
        parts.append(node.right)
        node = node.left
    parts.append(node)
    return parts[::-1]


def _match(rule: Rule, node) -> dict | None:
    """Children of ``node`` keyed by slot order, when ``rule`` can state ``node``."""
    kind = rule.kind
    slots = rule.slots
    head = kind[0]
    if head == "atom":
        if not isinstance(node, ast.Apply) or OperatorRef.of(node).atom != kind[1]:
            return None
        if len(slots) != len(node.args):
            return None
        children = {}
        for position, slot in enumerate(slots):
            index = slot.index if slot.index is not None else position
            child = node.args[index]
            if slot.cat == "A" and isinstance(child, ast.Apply):
                return None
            children[index] = (child, slot.cat)
        return children
    if head == "neglit":
        if isinstance(node, ast.Apply) and OperatorRef.of(node).atom == "neg" and isinstance(node.args[0], ast.Num):
            return {0: (node.args[0], "N")}
        return None
    if head == "cmp" and isinstance(node, ast.Compare) and node.op == kind[1]:
        return {0: (node.left, "T"), 1: (node.right, "T")}
    if head == "zero" and isinstance(node, ast.Compare) and node.op == kind[1] and node.right == ast.Num(0):
        return {0: (node.left, "T")}
    if head == "and" and isinstance(node, ast.And) or head == "or" and isinstance(node, ast.Or):
        return {0: (node.left, "C"), 1: (node.right, "C")}
    if head == "not" and isinstance(node, ast.Not):
        return {0: (node.operand, "C")}
    return None


# ------------------------------------------------------------------ public API


class ControlledLanguage:
    """Render definitions as controlled prose and parse such prose back into definitions.

    ``table`` maps ``(symbol, arity)`` to the positions of the operators that may occur
    (:func:`opulse.language.ir.signatures`); the definition's own operator is added to it.
    """

    def __init__(self, lang: str, symbols: Symbols, table: dict[tuple[str, int], set]) -> None:
        self.grammar = Grammar(lang, symbols)
        self.symbols = symbols
        self.table = table

    # ---------------------------------------------------------- render
    def render(self, definition: ast.Definition, seed: int = 0, tries: int = 6) -> str:
        if has_search(definition) or has_call_form(definition):
            lhs = ast.render_expr(definition.lhs, self.symbols)
            if has_search(definition):
                head = "搜索定义" if self.grammar.lang == "zh" else "Search definition of"
            else:
                head = "调用形式的定义" if self.grammar.lang == "zh" else "Call-form definition of"
            return f"{head} `{lhs}`:\n{ast.render_definition(definition, self.symbols)}"
        concept = Concept.of(definition)
        table = self._with(concept.operator)
        rng = random.Random(seed)
        problems = []
        for attempt in range(tries + 1):
            explicit = attempt == tries
            realizer = _Realizer(self.grammar, table, rng, explicit)
            try:
                text = self._realize(concept, realizer)
                parsed = self.parse(text)
            except ProseError as exc:
                problems.append(str(exc))
                continue
            if normalize(parsed) == normalize(definition):
                return text
            problems.append("the text reads back as a different definition")
        raise ProseError(f"cannot state {ast.render_definition(definition, self.symbols)!r} "
                         f"unambiguously in {self.grammar.lang}: {problems[-1]}")

    def _realize(self, concept: Concept, realizer: _Realizer) -> str:
        lhs = ast.render_expr(concept.lhs, self.symbols)
        taken = set(concept.parameters) | {self.symbols.nan}
        if concept.single:
            body, clauses = realizer.lift(concept.cases[0].body, set(taken))
            tokens = realizer.sentence("S_SINGLE", (("single",),), {"LHS": lhs, "T": body, "WT": clauses})
            return detokenize(tokens)
        lines = [detokenize(realizer.sentence("S_HEAD", (("head",),), {"LHS": lhs}))]
        for case in concept.cases:
            body, clauses = realizer.lift(case.body, set(taken))
            slots = {"G": case.guard, "T": body, "WT": clauses}
            if case.kind == IF:
                kinds = (("if", "first"),) if case.index == 1 else (("if", "later"),)
            else:
                kinds = (("else",),) if case.kind == ELSE else (("always",),)
            lines.append(f"{case.index}. " + detokenize(realizer.sentence("S_CASE", kinds, slots)))
        if concept.partial:
            lines.append(detokenize(realizer.sentence("S_TRAIL", (("trail",),), {})))
        return "\n".join(lines)

    def _with(self, ref: OperatorRef) -> dict:
        table = {key: set(value) for key, value in self.table.items()}
        table.setdefault((ref.symbol, ref.arity), set()).add(ref.position)
        return table

    # ---------------------------------------------------------- parse
    def parse(self, text: str) -> ast.Definition:
        heads = (("搜索定义 `", "调用形式的定义 `") if self.grammar.lang == "zh" else
                 ("Search definition of `", "Call-form definition of `"))
        head = next((prefix for prefix in heads if text.startswith(prefix)), None)
        if head is not None:
            first, separator, source = text.partition("\n")
            if not separator or not first.endswith("`:"):
                raise ProseError("search prose needs a definition line")
            from opulse.definition.parser import DefinitionParser
            from opulse.definition.syntax import role_of

            parser = DefinitionParser(self.symbols)
            for (symbol, arity), positions in self.table.items():
                for position in positions:
                    parser.notation.roles.setdefault(symbol, set()).add(role_of(arity, position))
            definition = parser.parse(source)
            if ast.render_expr(definition.lhs, self.symbols) != first[len(head):-2]:
                raise ProseError("search prose heading differs from its definition")
            if head == heads[0] and not has_search(definition):
                raise ProseError("search prose has no search expression")
            if head == heads[1] and (has_search(definition) or not has_call_form(definition)):
                raise ProseError("call-form prose needs an n-ary call and no search")
            return definition
        lines = [NUMBERING.sub("", line).strip() for line in text.strip().splitlines() if line.strip()]
        if not lines:
            raise ProseError("empty text")
        params_guess = parameter_names(self.symbols, 6)
        names = _where_names(lines[0], self.grammar, params_guess)
        first = self._line(lines[0], ("S_SINGLE", "S_HEAD"), _Context(params_guess, names, self.table),
                           protected=params_guess + names)
        kind, lhs_text = first[0], first[1]
        lhs = parse_lhs(lhs_text, params_guess, self.symbols)
        params = tuple(arg.name for arg in lhs.args)
        table = self._with(OperatorRef.of(lhs))
        if kind == ("single",):
            if len(lines) != 1:
                raise ProseError("a one-sentence definition has no further lines")
            names = _where_names(lines[0], self.grammar, params)
            context = _Context(params, names, table)
            first = self._line(lines[0], ("S_SINGLE",), context, protected=params + names)
            body = _resolve(first[3], first[4], params)
            return ast.Definition(lhs, (ast.Branch(body),))
        branches = []
        trailer = False
        for number, line in enumerate(lines[1:], start=1):
            if trailer:
                raise ProseError("the closing NaN sentence must be the last line")
            names = _where_names(line, self.grammar, params)
            context = _Context(params, names, table)
            reading = self._line(line, ("S_CASE", "S_TRAIL"), context, protected=params + names)
            case_kind = reading[0][0]
            if case_kind == "trail":
                trailer = True
                continue
            body = _resolve(reading[3], reading[4], params)
            guard = reading[2]
            if guard is not None and reading[4]:
                guard = _resolve_condition(guard, reading[4])
            if case_kind == "if":
                branches.append(ast.Branch(body, guard))
            else:
                branches.append(ast.Branch(body, None, case_kind == "else"))
        if not branches:
            raise ProseError("a definition needs at least one case")
        if trailer != (branches[-1].condition is not None):
            raise ProseError("the closing NaN sentence must appear exactly when the last case has a condition")
        return ast.Definition(lhs, tuple(branches))

    def _line(self, line: str, cats: tuple[str, ...], context: _Context, protected: tuple = ()):
        tokens = tokenize(line, tuple(protected) + self.grammar.protected)
        parser = _Parser(self.grammar, tokens, context)
        readings = []
        for cat in cats:
            readings += [value for value, end in parser.parse(cat, 0) if end == len(tokens)]
        distinct = list(dict.fromkeys(_canonical(reading) for reading in readings))
        if not distinct:
            raise ProseError(f"cannot read the sentence {line!r}")
        if len(distinct) > 1:
            raise ProseError(f"the sentence {line!r} has {len(distinct)} readings")
        return next(reading for reading in readings if _canonical(reading) == distinct[0])


def _canonical(reading):
    """A reading without its phrasing variant, so equal meanings count once."""
    kind, lhs, guard, body, clauses = reading
    return (kind[0], lhs, guard, body, clauses)


def _where_names(line: str, grammar: Grammar, params: tuple[str, ...]) -> tuple[str, ...]:
    """Names a line introduces with its "where" tail (``where u is ...``)."""
    marker = ", where " if grammar.lang == "en" else "，其中"
    if marker not in line:
        return ()
    tail = line.split(marker, 1)[1]
    candidates = [name for name in WHERE_NAMES if name not in params]
    return tuple(name for name in candidates if re.search(rf"(^|\s|，){re.escape(name)}\s", tail))


def _resolve(body: ast.Expr, clauses: tuple, params: tuple[str, ...]) -> ast.Expr:
    if not clauses:
        return body
    names = [name for name, _ in clauses]
    if len(set(names)) != len(names) or set(names) & set(params):
        raise ProseError("each where-name is introduced once and differs from the parameters")
    mapping = {ast.Var(name): expr for name, expr in clauses}
    for _ in range(len(clauses) + 1):
        expanded = substitute(body, mapping)
        if expanded == body:
            break
        body = expanded
    leftover = {name for name in names if any(sub == ast.Var(name) for sub in subterms(body))}
    if leftover:
        raise ProseError(f"where-names {sorted(leftover)} refer to each other in a cycle")
    return body


def _resolve_condition(guard: ast.Condition, clauses: tuple) -> ast.Condition:
    mapping = {ast.Var(name): expr for name, expr in clauses}
    for _ in range(len(clauses) + 1):
        guard = substitute(guard, mapping)
    return guard
