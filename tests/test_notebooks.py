"""Replay tutorial notebook cells and compare their stored text output."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS = sorted((ROOT / "examples" / "notebooks").glob("*.ipynb"))


@pytest.mark.slow
@pytest.mark.parametrize("notebook", NOTEBOOKS, ids=lambda path: path.stem)
def test_notebook_code_and_stored_output(notebook):
    pytest.importorskip("nbformat")
    script = """
import contextlib
import io
import sys
import nbformat

book = nbformat.read(sys.argv[1], as_version=4)
nbformat.validate(book)
scope = {"__name__": "__main__"}
for count, cell in enumerate((cell for cell in book.cells if cell.cell_type == "code"), start=1):
    output = io.StringIO()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
        exec(compile(cell.source, f"cell {count}", "exec"), scope)
    assert cell.execution_count == count
    assert not any(item.output_type == "error" for item in cell.outputs)
    stored = "".join(item.text for item in cell.outputs if item.output_type == "stream")
    assert output.getvalue() == stored, f"stored output differs in cell {count}"
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    result = subprocess.run([sys.executable, "-c", script, str(notebook)], cwd=ROOT,
                            env=env, capture_output=True, text=True, timeout=60, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
