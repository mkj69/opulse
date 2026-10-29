"""Syntax colouring: the tokenizer and the Pygments lexer on generated definitions."""

from __future__ import annotations

import json
import random

import pytest
from conftest import INITIAL_OPERATORS

from opulse.config import Settings
from opulse.core.registry import OperatorRegistry
from opulse.definition.ast import render_definition
from opulse.display.tokens import TokenStyle, tokenize
from opulse.generation.pipeline import OperatorFactory, build_layers

pygments = pytest.importorskip("pygments")

from pygments.lexers import get_lexer_by_name
from pygments.token import Error

from opulse.display.pygments_lexer import OpulseLexer

ROOT_DATA = INITIAL_OPERATORS


def _kinds(text: str, style: TokenStyle | None = None) -> list[tuple[str, str]]:
    return [(kind, value) for _, kind, value in tokenize(text, style or TokenStyle()) if kind != "whitespace"]


def test_token_kinds():
    assert _kinds("a ⊕∆ b = { a + 12, if a >= 3 and not b == NaN; b @, else }") == [
        ("parameter", "a"), ("operator", "⊕∆"), ("parameter", "b"), ("equals", "="), ("punctuation", "{"),
        ("parameter", "a"), ("base", "+"), ("number", "12"), ("punctuation", ","), ("keyword", "if"),
        ("parameter", "a"), ("comparison", ">="), ("number", "3"), ("keyword", "and"), ("keyword", "not"),
        ("parameter", "b"), ("comparison", "=="), ("constant", "NaN"), ("punctuation", ";"),
        ("parameter", "b"), ("base", "@"), ("punctuation", ","), ("keyword", "else"), ("punctuation", "}")]


def test_base_markers_and_words():
    style = TokenStyle.build(markers=["⊺⇮"], words=["blend"], parameters=["x"])
    assert _kinds("-⊺⇮1A blend x", style) == [("base", "-"), ("number", "⊺⇮1A"), ("operator", "blend"),
                                              ("parameter", "x")]
    assert _kinds("Ξ a")[0] == ("operator", "Ξ")


def test_tokens_cover_the_text():
    text = "f(…v…) = { base, if v % m == 0; g(… R = f(…(v % m) - 1…) …), if v % m > 0 } _ ! '"
    assert "".join(value for _, _, value in tokenize(text)) == text
    assert all(kind in {"keyword", "constant", "number", "comparison", "equals", "punctuation", "parameter",
                        "operator", "base", "name", "whitespace", "text"} for _, kind, _ in tokenize(text))


def test_lexer_registration_and_options():
    from pathlib import Path

    pyproject = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    assert '[project.entry-points."pygments.lexers"]' in pyproject
    assert 'opulse = "opulse.display.pygments_lexer:OpulseLexer"' in pyproject
    from opulse.display.pygments_lexer import register

    register()  # what the entry point does for an installed package
    lexer = get_lexer_by_name("opulse")
    assert isinstance(lexer, OpulseLexer)
    tokens = list(OpulseLexer(parameters="x,y", markers="⊺⇮").get_tokens("x ⊕ ⊺⇮1A"))
    assert ("Token.Name.Variable", "x") in [(str(t), v) for t, v in tokens]
    assert ("Token.Literal.Number.Integer", "⊺⇮1A") in [(str(t), v) for t, v in tokens]


def _definitions(count: int) -> list[str]:
    """``count`` generated definitions: drafts over a grown registry, with several symbol sets."""
    found = []
    sets = (("math", "arrows", "shapes"), ("greek",), ("circled", "squared", "suits"), ("logic", "sets"))
    for index, symbol_sets in enumerate(sets):
        settings = Settings.from_dict({"operators": {"symbol_sets": list(symbol_sets)}})
        registry = OperatorRegistry.from_jsonl(ROOT_DATA)
        factory = OperatorFactory(settings, registry, random.Random(index))
        build_layers(factory, [6, 3])
        kinds = ("simple_definition", "branch_definition", "recursive_definition")
        while len(found) < count * (index + 1) // len(sets):
            kind = factory.rng.choice(kinds)
            try:
                draft = factory._draft(kind, factory.rng.choice((1, 1, 0)) if kind != kinds[2] else 1)
            except Exception:  # noqa: BLE001, S112 - a draft without candidates is skipped
                continue
            found.append(render_definition(draft.definition, settings.symbols))
    return found


def test_lexer_has_no_error_tokens_on_thousands_of_definitions():
    lexer = OpulseLexer()
    definitions = _definitions(3000)
    assert len(definitions) >= 3000
    for text in definitions:
        tokens = list(lexer.get_tokens_unprocessed(text))
        assert all(token is not Error and Error not in token.split() for _, token, _ in tokens), text
        assert "".join(value for _, _, value in tokens) == text
        head = text.split("=", 1)[0].split()
        operator_tokens = [v for _, t, v in tokens if str(t) in ("Token.Name.Function", "Token.Operator")]
        assert any(symbol in operator_tokens for symbol in head if symbol not in ("a", "b")), text


def test_lexer_on_legacy_operator_set():
    from conftest import LEGACY_OPERATORS_1K

    if LEGACY_OPERATORS_1K is None or not LEGACY_OPERATORS_1K.is_file():
        pytest.skip("legacy operator set not available")
    lexer = OpulseLexer()
    for line in LEGACY_OPERATORS_1K.read_text(encoding="utf-8").splitlines():
        text = json.loads(line).get("definition")
        if text:
            assert all(Error not in token.split() for _, token, _ in lexer.get_tokens_unprocessed(text)), text
