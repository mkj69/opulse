"""Small end to end checks of the large cross-check harness."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


def _harness():
    path = Path(__file__).resolve().parents[1] / "tools" / "crosscheck.py"
    spec = importlib.util.spec_from_file_location("crosscheck", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_crosscheck_tiny_numeric_and_typed(tmp_path):
    harness = _harness()
    selected = ["default", "strings"]
    assert set(selected) <= set(harness.worlds())
    output = tmp_path / "findings.jsonl"
    result = harness.run(selected=selected, count=2, seeds=[3], z3_rate=1,
                         bench_rate=1, processes=1, output=output,
                         cython=False, network=False)
    assert result["expressions"] == 4
    assert result["expressions_per_world"] == {"default": 2, "strings": 2}
    assert result["checked"] == {"action": 0, "interpreter": 4, "compiled_python": 4,
                                 "reductions": 8, "verify_trace": 8, "cython": 0}
    assert result["disagreements"] == 0, output.read_text()
    assert result["z3"] > 0
    assert result["bench"] == 4
    assert output.read_text() == ""


def test_crosscheck_writes_reproduction_on_disagreement(tmp_path, monkeypatch):
    harness = _harness()
    monkeypatch.setattr(harness, "_runtime_tree", lambda tree, runtime: object())
    output = tmp_path / "findings.jsonl"
    result = harness.run(selected=["default"], count=1, seeds=[3], z3_rate=0,
                         bench_rate=0, processes=1, output=output,
                         cython=False, network=False)
    assert result["disagreements"] == 1
    finding = json.loads(output.read_text())
    assert finding["world"] == "default" and finding["seed"] == 3
    assert finding["tree"] and finding["operators"] and finding["settings"]
    assert "python" in finding["error"]


def test_crosscheck_skips_z3_for_non_exact_world_in_pool(tmp_path):
    output = tmp_path / "findings.jsonl"
    root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [sys.executable, str(root / "tools/crosscheck.py"), "--worlds", "clock",
         "--count", "4", "--seeds", "3", "4", "--z3-rate", "1",
         "--bench-rate", "0", "--processes", "2", "--no-cython", "--no-network",
         "--out", str(output)], capture_output=True, text=True, check=True,
    )
    result = json.loads(completed.stdout)
    assert result["expressions"] == 4
    assert result["z3"] == 0
    assert result["z3 not applicable"] == 4
    assert result["disagreements"] == 0, output.read_text()


def test_crosscheck_skips_failed_z3_expression(tmp_path, monkeypatch):
    harness = _harness()
    monkeypatch.setattr(harness, "_z3_value", lambda tree, encoder: (_ for _ in ()).throw(ValueError("unsupported")))
    output = tmp_path / "findings.jsonl"
    result = harness.run(selected=["default"], count=1, seeds=[3], z3_rate=1,
                         bench_rate=0, processes=1, output=output,
                         cython=False, network=False)
    assert result["z3 not applicable"] == 1
    assert result["disagreements"] == 0, output.read_text()
