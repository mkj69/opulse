"""Reversible display names for experiments that control for operator glyphs.

Only operator symbols and the spelling of definitions change. Function IDs,
dependencies, evaluation code, precedence, and the registry's base operations
remain the same, so the reference interpreter still supplies the semantics.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field, replace
from importlib.resources import files

from opulse.config import Numerals, Symbols
from opulse.core.registry import OperatorKey, OperatorRegistry
from opulse.definition import ast
from opulse.definition.parser import DefinitionParser
from opulse.definition.syntax import KEYWORDS
from opulse.expression.nodes import Node, map_operators
from opulse.expression.numerals import NumeralWriter

CONSONANTS = "bcdfghjklmnpqrstvwxyz"
VOWELS = "aeiou"
SYLLABLES = tuple(c + v for c in CONSONANTS for v in VOWELS)

# These names would hint at a base operation or a familiar numerical function.
ARITHMETIC_WORDS = frozenset({
    "absolute", "add", "added", "addition", "average", "binary", "bit", "bits",
    "calculate", "count", "counts", "cube", "cubed", "decimal", "decrement", "difference",
    "digit", "digits", "divide", "divided", "division", "double", "equal", "equals",
    "even", "exponent", "factor", "floor", "fraction", "halve", "half", "increment",
    "integer", "linear", "logarithm", "minus", "mod", "modulo", "multiple",
    "multiplication", "multiply", "negative", "number", "numeric", "odd", "operation",
    "operations", "percent", "plus", "power", "product", "quotient", "ratio", "remainder",
    "root", "round", "sign", "square", "squared", "subtract", "subtraction", "sum",
    "times", "total", "triple", "value", "values", "zero",
    "increase", "decrease", "less", "more", "greater", "fewer", "least", "most", "max", "min",
    "maximum", "minimum", "big", "small", "large", "high", "low", "up", "down", "net",
    "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "hundred",
    "thousand", "million", "single", "pair", "twice", "once", "quarter", "dozen", "score",
    "first", "second", "third", "last", "next", "previous", "before", "after", "reverse",
    "flip", "invert", "opposite", "swap", "mirror", "shift", "rotate", "scale", "grow",
    "shrink", "reduce", "raise", "lower", "drop", "gain", "loss", "lose", "cut", "split",
    "join", "merge", "combine", "mix", "remain", "rest", "left", "right",
    "positive", "parity", "prime", "random", "same", "differ", "different", "match",
    "compare", "measure", "length", "size", "amount", "quantity", "degree", "level", "rank",
    "order", "step", "steps", "unit", "units", "whole", "part", "parts", "piece", "share",
    "extra", "additional", "missing", "empty", "full", "none", "nothing", "all", "each",
    "every", "both", "nil", "null", "infinity", "limit", "bound",
})
# Words sharing a stem with a cue word are excluded too (adds, doubled, multiplier, ...).
CUE_STEMS = tuple(sorted({word[:4] for word in ARITHMETIC_WORDS if len(word) >= 4}))


def _hints_arithmetic(word: str) -> bool:
    return word in ARITHMETIC_WORDS or (len(word) >= 4 and word.startswith(CUE_STEMS)) \
        or any(word.startswith(cue) for cue in ARITHMETIC_WORDS if len(cue) == 3)


def _reserved(symbols: Symbols) -> set[str]:
    return set(KEYWORDS) | set(symbols.parameter_names) | {symbols.left_operand, symbols.right_operand, symbols.nan}


def pseudo_words(n: int, rng: random.Random, min_syllables: int = 2,
                 max_syllables: int = 3, *, symbols: Symbols | None = None,
                 exclude: frozenset[str] | set[str] = frozenset()) -> list[str]:
    """Draw distinct lowercase consonant-vowel words with a bounded length."""
    if n < 0 or min_syllables < 1 or max_syllables < min_syllables:
        raise ValueError("n and syllable limits must be non-negative and ordered")
    lengths = range(min_syllables, max_syllables + 1)
    capacity = sum(len(SYLLABLES) ** length for length in lengths)
    forbidden = _reserved(symbols or Symbols()) | set(exclude)
    # Only forbidden strings of the requested shape consume capacity.
    blocked = sum(1 for word in forbidden if _word_index(word, lengths) is not None)
    if n > capacity - blocked:
        raise ValueError(f"requested {n} pseudo-words, but only {capacity - blocked} are available")
    # Sampling integer codes is finite even when nearly all names are requested.
    codes = rng.sample(range(capacity), n + blocked)
    result = [_decode(code, lengths) for code in codes]
    return [word for word in result if word not in forbidden][:n]


def _decode(code: int, lengths: range) -> str:
    base = len(SYLLABLES)
    for length in lengths:
        count = base ** length
        if code < count:
            parts = [""] * length
            for i in range(length - 1, -1, -1):
                code, digit = divmod(code, base)
                parts[i] = SYLLABLES[digit]
            return "".join(parts)
        code -= count
    raise ValueError("pseudo-word code outside the configured range")


def _word_index(word: str, lengths: range) -> int | None:
    if len(word) % 2 or len(word) // 2 not in lengths:
        return None
    if any(word[i:i + 2] not in SYLLABLES for i in range(0, len(word), 2)):
        return None
    return 0  # only shape membership is needed


def _english_words() -> list[str]:
    path = files("opulse.expression").joinpath("data/english_words.txt")
    return [word for word in path.read_text(encoding="utf-8").splitlines() if word]


@dataclass
class AliasMap:
    """Forward and inverse operator names for one display notation."""

    symbol_to_word: dict[OperatorKey, str]
    word_to_symbol: dict[str, OperatorKey]
    symbols: Symbols = field(default_factory=Symbols)
    digits: str = Numerals().digits

    @classmethod
    def build(cls, registry: OperatorRegistry, rng: random.Random, style: str = "pseudo",
              *, symbols: Symbols | None = None, digits: str = Numerals().digits) -> AliasMap:
        symbols = symbols or Symbols()
        defined = [op for op in registry if op.definition is not None]
        excluded = _reserved(symbols) | registry.symbols()
        if style == "pseudo":
            words = pseudo_words(len(defined), rng, symbols=symbols, exclude=excluded)
        elif style == "english":
            pool = [word for word in _english_words()
                    if word not in excluded and not _hints_arithmetic(word)]
            if len(pool) < len(defined):
                raise ValueError(f"only {len(pool)} English aliases available for {len(defined)} operators")
            words = rng.sample(pool, len(defined))
        else:
            raise ValueError(f"unknown alias style {style!r}; expected 'pseudo' or 'english'")
        forward = {(op.symbol, op.n_ary, op.unary_position): word
                   for op, word in zip(defined, words, strict=True)}
        return cls(forward, {word: key for key, word in forward.items()}, symbols, digits)


def _rename_expr(node: ast.Expr, alias: AliasMap) -> ast.Expr:
    if isinstance(node, ast.Search):
        return ast.Search(node.index, node.bound, _rename_condition(node.condition, alias))
    if not isinstance(node, ast.Apply):
        return node
    key = (node.symbol, node.n_ary, node.unary_position)
    return ast.Apply(alias.symbol_to_word.get(key, node.symbol),
                     tuple(_rename_expr(arg, alias) for arg in node.args), node.unary_position)


def _rename_condition(node: ast.Condition, alias: AliasMap) -> ast.Condition:
    if isinstance(node, ast.Truth):
        return ast.Truth(_rename_expr(node.expr, alias))
    if isinstance(node, ast.Compare):
        return ast.Compare(_rename_expr(node.left, alias), node.op, _rename_expr(node.right, alias))
    if isinstance(node, ast.Not):
        return ast.Not(_rename_condition(node.operand, alias))
    kind = ast.And if isinstance(node, ast.And) else ast.Or
    return kind(_rename_condition(node.left, alias), _rename_condition(node.right, alias))


def aliased_registry(registry: OperatorRegistry, alias: AliasMap) -> OperatorRegistry:
    """Copy a registry, re-rendering definitions under its display names."""
    parser = DefinitionParser(alias.symbols, registry, alias.digits)
    writer = NumeralWriter(registry, alias.digits, nan=alias.symbols.nan)
    renamed = []
    for op in registry:
        key = (op.symbol, op.n_ary, op.unary_position)
        definition = op.definition
        if definition is not None:
            original = parser.parse(definition)
            branches = tuple(ast.Branch(
                _rename_expr(branch.expr, alias),
                _rename_condition(branch.condition, alias) if branch.condition is not None else None,
                branch.is_else,
            ) for branch in original.branches)
            changed = ast.Definition(_rename_expr(original.lhs, alias), branches)
            definition = ast.render_definition(changed, alias.symbols, writer.write,
                                               layout="piecewise" if "\n" in definition else "compact",
                                               min_length=0)
        renamed.append(replace(op, symbol=alias.symbol_to_word.get(key, op.symbol),
                               definition=definition))
    return OperatorRegistry(renamed)


def alias_tree(tree: Node, aliased_registry: OperatorRegistry) -> Node:
    """Keep the tree shape and bind every call to the copied registry."""
    return map_operators(tree, lambda op: aliased_registry.get(op.func_id))
