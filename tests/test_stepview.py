"""Shared step viewer wiring and a few trace highlighting edge cases."""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "docs/assets/js"


def test_registered_before_widgets_and_shared_style():
    config = (ROOT / "mkdocs.yml").read_text()
    assert config.index("assets/js/stepview.js") < config.index("assets/js/playground.js")
    assert config.index("assets/css/stepview.css") < config.index("assets/css/playground.css")
    source = (JS / "stepview.js").read_text()
    for marker in ("function render(container, options)", "page_size", "options.initial", "options.labels",
                   "options.renderValue", "source.load(offset, size)", "aria-activedescendant",
                   "prefers-reduced-motion", "goToStep(n)", "ArrowDown", "PageDown"):
        assert marker in source
    style = (ROOT / "docs/assets/css/stepview.css").read_text()
    for marker in (".opg-detail", ".opg-steps", ".opg-focus", ".opg-new", "max-width: 44.9375em"):
        assert marker in style


def test_every_derivation_widget_uses_shared_viewer():
    wiring = {
        "playground.js": ("OpulseStepView.render", "steps, initial:", "explain(step, state.atomRules)"),
        "scales-core.js": ("OpulseStepView.render", "example.page(cut, offset, size)", "example.count(cut)"),
        "scales-tour.js": ("api.renderStepList(stepBox", "OpulseStepView.render", "current.statuses"),
        "home-scales.js": ("api.renderStepList(listBox", "api.renderTree(treeBox"),
        "challenge.js": ("OpulseStepView.render", "example.fullPage(offset, size)", "coarse_steps"),
        "challenge-modes.js": ("OpulseStepView.render", "item.correct_steps", 'mode === "hole"'),
        "worlds/core.js": ("OpulseStepView.render", "renderer.renderStep", "callsTree(data, op)"),
        "worlds/tasks.js": ("OpulseStepView.render", "renderer.renderStep", "renderer.selectExample"),
        "worlds/challenge.js": ("OpulseStepView.render", "renderer.renderStep", "record.answer"),
    }
    for filename, markers in wiring.items():
        source = (JS / filename).read_text()
        assert all(marker in source for marker in markers), filename
    assert "trace.map((step, i)" in (JS / "worlds/challenge.js").read_text()
    assert "i ? lines[i - 1] : data.question" in (JS / "scales-tour.js").read_text()
    assert "rows[0].before !== undefined" in (JS / "challenge-modes.js").read_text()
    assert "vis_unfold_scales.html" not in (ROOT / "docs/guide/visual-tour.md").read_text()
    if (ROOT / "docs_zh").is_dir():
        assert "vis_unfold_scales.html" not in (ROOT / "docs_zh/guide/visual-tour.md").read_text()


def test_chinese_localized_overrides_match():
    if not (ROOT / "docs_zh").is_dir():
        pytest.skip("The public export has no Chinese site")
    for filename in ("playground.js", "scales-tour.js", "challenge.js"):
        assert (JS / filename).read_bytes() == (
            ROOT / "docs_zh/snippets/localized_assets/js" / filename
        ).read_bytes()


@pytest.mark.parametrize("filename", [
    "stepview.js", "playground.js", "scales-core.js", "scales-tour.js", "home-scales.js",
    "challenge.js", "challenge-modes.js", "worlds/core.js", "worlds/tasks.js", "worlds/challenge.js",
])
def test_javascript_syntax(filename):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is unavailable")
    subprocess.run([node, "--check", str(JS / filename)], check=True, capture_output=True)


def test_diff_spans_share_context_without_highlighting_unchanged_text():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is unavailable")
    script = """const vm=require('node:vm'),fs=require('node:fs');
const context={window:{}};vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),context);
const diff=context.window.OpulseStepView.difference;
const cases=[['a + b','a * b',[[2,3],[2,3]]],['(2 + 2) * 3','4 * 3',[[0,7],[0,1]]],['abc','abc',[[3,3],[3,3]]]];
for(const [a,b,expected] of cases){const got=diff(a,b);if(JSON.stringify(got)!==JSON.stringify(expected))throw Error(JSON.stringify({a,b,got,expected}));}
"""
    subprocess.run([node, "-e", script, str(JS / "stepview.js")], check=True, capture_output=True)


def test_lazy_page_navigation_and_highlights():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is unavailable")
    subprocess.run([node, str(ROOT / "tests/js/stepview-smoke.js"), str(JS / "stepview.js")],
                   check=True, capture_output=True)
