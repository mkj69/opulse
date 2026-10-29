"""Homepage scale switcher uses the checked scale-example export."""

import json
from pathlib import Path

from conftest import requires_zh_site

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs/assets/data/scales"


def test_homepage_scale_data_and_widget():
    index = json.loads((DATA / "index.json").read_text(encoding="utf-8"))
    assert index["schema"] == "opulse.scales/1"
    assert [scale["key"] for scale in index["scales"]] == ["s10", "s100", "s1000", "s10000"]
    for scale in index["scales"]:
        assert 0 <= len(scale["examples"]) <= 4
        if len(scale["examples"]) == 1:
            assert scale["key"] == "s10000" and index["unfinished"]
        sets = {entry["name"]: entry for entry in scale["sets"]}
        for row in scale["examples"]:
            assert {"id", "set", "kind", "target", "layer", "closure_size", "coarse_steps",
                    "middle_steps", "full_steps", "expression", "value"} <= row.keys()
            assert row["set"] in sets
            example = json.loads((DATA / scale["key"] / f"{row['id']}.json").read_text(encoding="utf-8"))
            assert example["schema"] == "opulse.scale-example/1"
            header = example["header"]
            assert (header["target"], header["layer"], header["closure_size"]) == (
                row["target"], row["layer"], row["closure_size"]
            )
            assert header["sentence"] and header["sentence_zh"]
            assert header["expression"] == row["expression"]
            assert header["value"] == row["value"]
            assert header["verification"]["full_trace_verified"] is True
            cuts = header["cut_table"]
            assert [cut["L"] for cut in cuts] == list(range(header["layer"] + 2))
            assert (cuts[-1]["steps"], cuts[header["middle_cut"]]["steps"], cuts[0]["steps"]) == (
                row["coarse_steps"], row["middle_steps"], row["full_steps"]
            )
            assert cuts[-1]["steps"] == 1
            assert any(op["symbol"] == row["target"] and op["definition"] for op in example["operators"])
            assert example["chunks"][-1]["file"].endswith("/root.json")


def test_homepage_snippets_and_localization():
    assert not list((ROOT / "docs/assets/data/home_examples").glob("*.json"))
    assert "--home" not in (ROOT / "tools/docs_granularity.py").read_text(encoding="utf-8")
    _check_homepage_snippet("en", "docs")
    script = (ROOT / "docs/assets/js/home-scales.js").read_text(encoding="utf-8")
    for name in ("loadIndex", "loadExample", "cutBelowLayer", "cutFromSet", "renderStepList",
                 "renderOperatorChips", "renderTree"):
        assert name in script


@requires_zh_site
def test_chinese_homepage_snippet_and_mirror():
    _check_homepage_snippet("zh", "docs_zh")
    script = (ROOT / "docs/assets/js/home-scales.js").read_text(encoding="utf-8")
    mirror = (ROOT / "docs_zh/snippets/localized_assets/js/home-scales.js").read_text(encoding="utf-8")
    assert script == mirror


def _check_homepage_snippet(lang, site):
    snippet = (ROOT / "docs/snippets" / f"home_examples_{lang}.html").read_text(encoding="utf-8")
    assert f'data-lang="{lang}"' in snippet
    assert 'src="assets/js/scales-core.js"' in snippet
    assert 'src="assets/js/home-scales.js"' in snippet
    assert "assets/data/home_examples/" not in snippet
    page = (ROOT / site / "index.md").read_text(encoding="utf-8")
    assert f'home_examples_{lang}.html' in page
    assert 'href="about/benchmarks/"' in page
