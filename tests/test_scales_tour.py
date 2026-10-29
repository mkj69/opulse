"""The scale tour wiring and the published step checker verdicts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from conftest import requires_zh_site

from opulse.expression.nodes import from_ast
from opulse.verify.steps import check_steps
from tools.check_scales import registry_for

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import docs_scales_grade as grade


def test_tour_snippets_use_shared_api():
    _check_tour_snippets("docs", "en")
    script = (ROOT / "docs/assets/js/scales-tour.js").read_text()
    for use in ("OpulseScales", "renderStepList", "renderOperatorChips", "renderTree", "cutFromSet"):
        assert use in script


@requires_zh_site
def test_chinese_tour_snippets_use_shared_api():
    _check_tour_snippets("docs_zh", "zh")
    script = (ROOT / "docs/assets/js/scales-tour.js").read_text()
    assert script == (ROOT / "docs_zh/snippets/localized_assets/js/scales-tour.js").read_text()


def _check_tour_snippets(base, lang):
    for filename in ("granularity_scales", "vis_steps_scales"):
        snippet = (ROOT / base / "snippets" / f"{filename}.html").read_text()
        assert 'class="scales-tour"' in snippet
        assert f'data-lang="{lang}"' in snippet
        assert "scales-core.js" in snippet
        assert "scales-tour.js" in snippet
    guide = (ROOT / base / "guide/visual-tour.md").read_text()
    for filename in ("granularity_scales", "vis_steps_scales"):
        assert f"{filename}.html" in guide


def test_grade_data_for_finished_integer_scales():
    index = json.loads((ROOT / "docs/assets/data/scales/index.json").read_text())
    for scale in index["scales"]:
        if not any(row["world"] == "integer" for row in scale["sets"]):
            continue
        path = ROOT / "docs/assets/data/scales_grade" / f"{scale['key']}.json"
        assert path.exists()
        assert path.stat().st_size <= grade.MAX_FILE
        data = json.loads(path.read_text())
        assert data["schema"] == "opulse.scales-grade/1"
        good, bad = data["runs"]
        assert good["report"]["derivation_correct"]
        assert bad["report"]["first_error"] == data["slip"]
        assert len(good["lines"]) == len(bad["lines"])
        assert sum(a != b for a, b in zip(good["lines"], bad["lines"])) == 1
        assert all(len(run["lines"]) == len(run["statuses"]) for run in data["runs"])


def test_checker_verdict():
    # This grade target has a complete operator closure in its published example.
    scale = "s100"
    path = ROOT / "docs/assets/data/scales_grade" / f"{scale}.json"
    data = json.loads(path.read_text())
    entry = {"id": data["example"], "set": data["set"], "scale": scale,
             "expression": data["question"]}
    example_path = ROOT / "docs/assets/data/scales" / scale / f"{entry['id']}.json"
    example = json.loads(example_path.read_text())
    _, parser, oracle, _ = registry_for(example, example_path.parents[1])
    registry = oracle.registry
    source = from_ast(parser.parse_expr(entry["expression"], expression_mode=True), oracle.registry)
    answer = int(data["answer"])
    for run in data["runs"]:
        result = check_steps(source, run["lines"], parser, registry, oracle, answer)
        assert result.to_dict() == run["report"]
