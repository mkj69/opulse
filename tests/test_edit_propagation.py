"""Candidate selection for the edit propagation example."""

import json
import os
import subprocess
import sys
from pathlib import Path

from examples.edit_propagation import rank_candidates


def test_rank_candidates_skips_definition_without_number() -> None:
    rows = [
        {"func_id": "most_users", "definition": "f = { a + b }", "recursive_layer": 0},
        {"func_id": "editable", "definition": "g = { a + 4 }", "recursive_layer": 0},
        {"func_id": "second", "definition": "i = { a + 2 }", "recursive_layer": 0},
        {"func_id": "recursive", "definition": "h = { a + 8 }", "recursive_layer": 1},
    ]
    dependents = {"most_users": {"a", "b", "c"}, "editable": {"a"},
                  "second": {"a", "b"}, "recursive": {"a", "b", "c", "d"}}

    assert rank_candidates(rows, lambda func_id: dependents[func_id]) == [rows[2], rows[1]]


def test_script_fails_when_no_number_can_be_edited(tmp_path: Path) -> None:
    operators = tmp_path / "operators.jsonl"
    rows = [{"func_id": "plain", "definition": "f = { a + b }", "recursive_layer": 0,
             "dependencies": []}]
    operators.write_text(json.dumps(rows[0]) + "\n", encoding="utf-8")
    root = Path(__file__).resolve().parents[1]

    result = subprocess.run([sys.executable, str(root / "examples/edit_propagation.py"), str(operators)],
                            cwd=root, env={**os.environ, "PYTHONPATH": str(root / "src")},
                            capture_output=True, text=True, check=False)

    assert result.returncode != 0
    assert "no layer 0 definition contains a number to edit" in result.stderr
