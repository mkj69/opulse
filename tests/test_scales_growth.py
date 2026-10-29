"""Checks for the cached growth data used by both visual tours."""

import json
from pathlib import Path
from urllib.parse import urljoin

from conftest import requires_zh_site

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs/assets/data/scales_growth"
SEEDS = {"int10": 101, "int100": 102, "int1000": 103,
         "int10000b": 105, "str10": 206, "str100": 202,
         "str1000": 203, "str10000": 211}


def test_growth_exports_are_consistent():
    paths = sorted(p for p in DATA.glob("*.json") if not p.name.endswith(".definitions.json"))
    assert paths
    for path in paths:
        assert path.stat().st_size < 3_000_000
        if path.name.endswith(".definitions.json"):
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["set"] == path.stem
        assert data["seed"] == SEEDS[path.stem]
        assert data["seconds"] >= 0
        assert sum(row["count"] for row in data["layers"]) == data["size"]
        assert sum(row["accepted"] for row in data["funnel"]) == data["size"]
        assert sum(row["rejected"] for row in data["funnel"]) + data["size"] == data["proposed"]
        assert data["funnel"][-1]["cumulative"]["accepted"] == data["size"]
        assert data["funnel"][-1]["cumulative"]["reasons"] == data["rejected"]
        assert [row["accepted"] for row in data["funnel"]] == [row["count"] for row in data["layers"]]
        assert all(sum(row["reasons"].values()) == row["rejected"] for row in data["funnel"])
        for row in data["layers"]:
            assert sum(row["kinds"].values()) == row["count"]
            assert sum(n for _, n in row["closure"]) == row["count"]
            assert sum(n for _, n in row["chain"]) == row["count"]
            assert sum(n for _, n in row["layer_span"]) == row["count"]
            assert max(value for value, _ in row["layer_span"]) <= row["layer"] + 1
        density = data["density"]
        assert sum(map(sum, density["layer_matrix"])) == data["edge_count"]
        assert sum(map(sum, density["fine"])) == data["edge_count"]
        assert density["bins"] <= 128
        graph = data["graph"]
        nodes, edges = graph["nodes"], graph["edges"]
        definitions_path = DATA / graph["definitions"]
        assert definitions_path.stat().st_size < 3_000_000
        definitions = json.loads(definitions_path.read_text(encoding="utf-8"))
        assert len(nodes) == len(definitions) == data["size"] + density["layer_ranges"][0][1]
        assert all(len(n) == 4 and n[1] in density["layers"] and n[2] in range(4)
                   and isinstance(n[3], int) for n in nodes)
        assert sum(n[2] != 0 for n in nodes) == data["size"]
        assert len(edges) == data["edge_count"] * 2
        assert all(0 <= i < len(nodes) for i in edges)
        for layer in density["layers"]:
            xs = sorted(n[3] for n in nodes if n[1] == layer)
            assert xs == list(range(len(xs)))


def test_both_snippets_load_the_widget():
    _check_growth_snippet("docs")


@requires_zh_site
def test_chinese_snippet_loads_the_widget():
    _check_growth_snippet("docs_zh")


def _check_growth_snippet(name):
    snippet = (ROOT / name / "snippets/vis_growth.html").read_text(encoding="utf-8")
    assert "scales-growth.js" in snippet
    assert "data-base=" not in snippet


def test_data_url_comes_from_script_src_at_any_page_depth():
    script = (ROOT / "docs/assets/js/scales-growth.js").read_text(encoding="utf-8")
    assert "document.currentScript && document.currentScript.src" in script
    assert 'new URL("../data/scales_growth/", SCRIPT)' in script
    assert "location.href" not in script
    for prefix in ("/", "/opulse/", "/opulse/zh/"):
        script_url = f"https://example.test{prefix}assets/js/scales-growth.js"
        expected = f"https://example.test{prefix}assets/data/scales_growth/int10.json"
        for page in ("guide/visual-tour/", "guide/deeper/topic/"):
            page_url = f"https://example.test{prefix}{page}"
            assert urljoin(urljoin(script_url, "../data/scales_growth/"), "int10.json") == expected
            assert urljoin(page_url, "int10.json") != expected


def test_integer_thousand_run_is_exported():
    data = json.loads((DATA / "int1000.json").read_text(encoding="utf-8"))
    assert data["size"] == 1000
    assert data["seed"] == 103
    assert len(data["layers"]) == 10


def test_integer_ten_thousand_run_is_exported():
    data = json.loads((DATA / "int10000b.json").read_text(encoding="utf-8"))
    assert data["size"] == 10000
    assert data["seed"] == 105
    assert len(data["layers"]) == 12
    assert sum(row["accepted"] for row in data["funnel"]) == 10000
    assert len(data["graph"]["nodes"]) >= 10000


def test_all_scales_mount_shared_graph():
    script = (ROOT / "docs/assets/js/scales-growth.js").read_text(encoding="utf-8")
    assert '[["int10"], ["int100"], ["int1000"], ["int10000b"]]' in script
    assert 'data.graph ? graphView(parent,data,t) : null;' in script
    assert 'window.OpGraph.mount(parent, data.graph, data._definitions' in script
    for name in (("docs", "docs_zh") if (ROOT / "docs_zh").is_dir() else ("docs",)):
        snippet = (ROOT / name / "snippets/vis_growth.html").read_text(encoding="utf-8")
        assert 'opgraph.js' in snippet
    if (ROOT / "docs_zh").is_dir():
        assert (ROOT / "docs/assets/js/opgraph.js").read_bytes() == (
            ROOT / "docs_zh/assets/js/opgraph.js").read_bytes()


@requires_zh_site
def test_chinese_script_mirrors_shared_widget():
    english = (ROOT / "docs/assets/js/scales-growth.js").read_bytes()
    chinese = (ROOT / "docs_zh/snippets/localized_assets/js/scales-growth.js").read_bytes()
    assert english == chinese
