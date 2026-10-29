"""Direct export writers keep the release marker in their files."""

import json

from opulse.canary import CANARY
from opulse.cli.main import main
from opulse.core.primitives import write_initial_set


def test_initial_operator_exports_carry_canary(tmp_path):
    atoms = write_initial_set(tmp_path / "atoms.jsonl", ["add", "succ"], seed=3)
    assert all(json.loads(line)["meta"]["canary"] == CANARY for line in atoms.read_text().splitlines())
    for name in ("integer", "atomic"):
        output = tmp_path / f"{name}.jsonl"
        assert main(["atoms", "export", "--set", name, "--out", str(output)]) == 0
        assert all(json.loads(line)["meta"]["canary"] == CANARY for line in output.read_text().splitlines())


def test_compile_json_export(tmp_path, monkeypatch):
    from opulse.compile import __main__ as command

    verified = {"verify": {"ok": True}}
    results = {"operators": {"x": verified}, "stitching": {
        "x": {"whole": verified, "stitched": verified, "stitched_compact": verified,
              "whole_equals_stitched": True}}}
    monkeypatch.setattr(command, "run", lambda _n: results)
    monkeypatch.setattr(command, "format_results", lambda _rows: "checked")
    target = tmp_path / "compiled.json"
    assert command.main(["--n", "2", "--json", str(target)]) == 0
    assert json.loads(target.read_text())["meta"]["canary"] == CANARY
