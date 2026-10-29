"""The shared kind explanation is wired into both documentation sites."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITES = ("docs", "docs_zh") if (ROOT / "docs_zh").is_dir() else ("docs",)


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_shared_legend_copy_and_assets():
    js = read("docs/assets/js/kinds-legend.js")
    css = read("docs/assets/css/kinds-legend.css")
    config = read("mkdocs.yml")
    for name in ("Substitution", "Branch", "Recursion"):
        assert name in js
    for example in (
        "a ◆ b = { (a + b) * 2 }",
        "a ◆ b = { a, if a > b; b, else }",
        "a ◆ b = { 0, if b <= 0; (a ◆ (b - 1)) + a, else }",
    ):
        assert example in js
        assert example in read("docs/index.md")
        if "docs_zh" in SITES:
            assert example in read("docs_zh/index.md")
    for form in ("a ◆ b", "a △ / ■ a", "◆(a, b, c)", "{ x, if c; y, else }"):
        assert form in js
    assert "assets/js/kinds-legend.js" in config
    assert "assets/css/kinds-legend.css" in config
    for color in ("substitution", "branch", "recursion"):
        assert f"--op-kind-{color}" in css


def test_static_placements_and_glossaries():
    for site in SITES:
        assert 'id="worlds-kinds" data-kinds-legend' in read(f"{site}/worlds/index.md")
        assert 'id="tour-growth-kinds" data-kinds-legend' in read(f"{site}/guide/visual-tour.md")
        home = read(f"{site}/index.md")
        assert 'id="home-kinds" data-kinds-legend' in home
        for slug in ("substitution", "branch", "recursion"):
            assert f'href="#home-kinds-{slug}"' in home
        glossary = read(f"{site}/glossary.md")
        assert glossary.count("\n## ") == 18


def test_widget_hooks_and_unified_names():
    hooks = {
        "docs/assets/js/worlds/core.js": 'KindsLegend.render(kindLegend',
        "docs/assets/js/scales-growth.js": 'KindsLegend.render(kindLegend',
        "docs/assets/js/scales-tour.js": 'KindsLegend.render(kindLegend',
        "docs/assets/js/granularity.js": 'KindsLegend.render(kindLegend',
        "docs/assets/js/playground.js": 'KindsLegend.render(root.querySelector(".opg-kinds-hook")',
        "docs/assets/js/challenge.js": 'KindsLegend.render(kindLegend',
    }
    for path, call in hooks.items():
        assert call in read(path)
    if "docs_zh" in SITES:
        for widget in ("challenge", "granularity", "playground", "scales-growth", "scales-tour"):
            assert "KindsLegend.render(" in read(f"docs_zh/snippets/localized_assets/js/{widget}.js")
    challenge = read("docs/assets/js/challenge.js")
    assert "seenComplexKind" in challenge
    assert 'kindLegend.querySelector(".kl-shell").open = true' in challenge
    assert 'button.querySelector(".ow-form").title = kindLabel(op.kind)' in read("docs/assets/js/worlds/core.js")
    assert 'simple: "Substitution", branch: "Branch", recursive: "Recursion"' in read("docs/assets/js/scales-growth.js")
    assert 'simple: "Substitution", recursiveKind: "Recursion", branchKind: "Branch"' in read("docs/assets/js/granularity.js")
    for site in SITES:
        assert "--sg-simple:var(--op-kind-substitution)" in read(f"{site}/snippets/vis_growth.html")
