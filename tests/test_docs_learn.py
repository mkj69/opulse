"""The Learn page's links, data and browser wiring stay in sync."""

import json
import re
from html import unescape
from pathlib import Path

import pytest

from tools.docs_learn import CASES, OUT, build, quality_filter
from opulse.core.primitives import BUILT_IN_RULES
from opulse.presets import PRESETS

ROOT = Path(__file__).resolve().parents[1]


def test_learn_nav_order_and_translation():
    en = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    assert en.index("  - Home:") < en.index("  - Why:") < en.index("  - Learn:") < en.index("  - Tour:")
    if (ROOT / "mkdocs.zh.yml").is_file():
        zh = (ROOT / "mkdocs.zh.yml").read_text(encoding="utf-8")
        assert zh.index("  - 首页:") < zh.index("  - 为什么:") < zh.index("  - 入门:") < zh.index("  - 导览:")
        assert "    - learn/" in zh


def test_checked_data_matches_interpreter():
    assert len(CASES) == 12
    assert json.loads(OUT.read_text(encoding="utf-8")) == build()


def test_atoms_are_two_direct_computations():
    atoms = build()[0]
    assert atoms["id"] == "atoms"
    assert atoms["rule"] == ""
    assert atoms["expression"] == "(3 + 4) * 2"
    assert atoms["value"] == "14"
    assert [step["kind"] for step in atoms["steps"]] == ["eval", "eval"]
    assert [step["symbol"] for step in atoms["steps"]] == ["+", "*"]
    assert all(step["operator_kind"] == "atom" for step in atoms["steps"])
    substitution = build()[1]
    assert substitution["value"] == atoms["value"]
    assert substitution["rule"] == "a ◆ b = { (a + b) * 2 }"


def test_atom_tiles_and_editor_labels_on_both_pages():
    js = (ROOT / "docs/assets/js/learn.js").read_text(encoding="utf-8")
    css = (ROOT / "docs/assets/css/learn.css").read_text(encoding="utf-8")
    assert 'row.id !== "atoms"' in js
    assert 'hasRules ? `<label>' in js
    assert 'rule && rule.value.trim()' in js
    assert '[rule, input].filter(Boolean)' in js
    assert 'tr("Expression", "表达式")' in js
    assert 'tr("Rules (definitions)", "规则（定义）")' in js
    assert 'One rule per line: name the inputs, then the body in braces.' in js
    assert 'Optional: write a definition' not in js
    assert '.ol-atoms { display: grid;' in css
    assert set(PRESETS["integer"]["atoms"]) <= set(BUILT_IN_RULES)
    symbols = [re.match(r"(?:a \S+ b|a \S+|\S+ a)", rule).group()
               for rule in BUILT_IN_RULES.values()]
    for file in ("docs/learn.md", "docs_zh/learn.md"):
        if not (ROOT / file).is_file():
            continue
        page = (ROOT / file).read_text(encoding="utf-8")
        assert "  - navigation\n" in page.split("---", 2)[1]
        first = page.split('<section class="ol-card" id="atoms"', 1)[1].split("</section>", 1)[0]
        tiles = re.findall(r'<div class="ol-atom"><code>(.*?)</code><strong>(.*?)</strong><span>(.*?)</span></div>', first)
        assert len(tiles) == len(symbols)
        assert all(name and meaning for _, name, meaning in tiles)
        assert [unescape(symbol) for symbol, _, _ in tiles] == symbols
        assert "<details" not in first
        assert "(3 + 4) * 2" in first


@pytest.mark.parametrize("rule,reason", [
    ("a ◇ b = { (a * 1) + b }", "identity arithmetic"),
    ("a ◇ b = { a + 0 }", "identity arithmetic"),
    ("a ◇ b = { (a - a) + b }", "identity arithmetic"),
    ("a ◇ b = { - (- a) + b }", "double negation"),
    ("a ◇ b = { a + 2 }", "unused parameter b"),
    ("a ◇ b = { a ◆ b }", "pure alias"),
])
def test_quality_filter_rejects_bad_examples(rule, reason):
    with pytest.raises(ValueError, match=reason):
        quality_filter(rule, "3 ◇ 4", "substitution")


def test_page_wiring():
    js = (ROOT / "docs/assets/js/learn.js").read_text(encoding="utf-8")
    checker = (ROOT / "docs/assets/js/challenge-check.js").read_text(encoding="utf-8")
    for file in ("docs/learn.md", "docs_zh/learn.md"):
        if not (ROOT / file).is_file():
            continue
        page = (ROOT / file).read_text(encoding="utf-8")
        assert 'data-opulse-learn' in page
        for id_, *_ in CASES:
            assert f'data-learn-example="{id_}"' in page
    assert "../data/learn.json" in js
    assert "challenge-check.js" in js
    assert "checker.evaluate" in js
    assert "OpulseWorlds.renderValue" in js
    assert "world || \"\"" in checker
    assert "assets/js/learn.js" in (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
