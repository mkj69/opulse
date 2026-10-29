"""Static contract for the shared scale-example browser assets."""

from pathlib import Path

from conftest import requires_zh_site

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "docs/assets/js/scales-core.js"
STYLE = ROOT / "docs/assets/css/scales.css"


def test_shared_api_and_iterative_walks():
    source = SCRIPT.read_text(encoding="utf-8")
    for signature in (
        "function dataRoot()", "function loadIndex()", "function loadExample(scale, id)",
        "cutBelowLayer(L)", "cutFromSet(indices)", "async ensureLayers(layers)",
        "async count(cut)", "async page(cut, offset, size)", "async node(i)",
        "async children(i)", "function fmt(n)", "function layerLabel(layer)",
        "function renderStepList(container, example, cut, opts)",
        "function renderOperatorChips(container, operators, opts)",
        "function renderTree(container, example, cut)", "window.OpulseScales =",
    ):
        assert signature in source
    assert "Iterative postorder" in source
    assert "Iterative depth-first walk" in source
    assert "this.count(cut)" not in source[source.index("async count(cut)"):source.index("async page(cut, offset, size)")]
    assert "this.page(cut" not in source[source.index("async page(cut, offset, size)"):source.index("function stepRow")]
    assert "Array.isArray(data.strings) ? data.strings : this.strings" in source
    assert "document.documentElement.lang" in source


def test_shared_style_is_registered_for_english_build():
    assert STYLE.is_file()
    assert ".os-step" in STYLE.read_text(encoding="utf-8")
    assert "- assets/css/scales.css" in (ROOT / "mkdocs.yml").read_text(encoding="utf-8")


@requires_zh_site
def test_shared_style_is_registered_for_chinese_build():
    assert "INHERIT: mkdocs.yml" in (ROOT / "mkdocs.zh.yml").read_text(encoding="utf-8")
