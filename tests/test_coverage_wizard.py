"""Wizard inputs must produce a loadable config or a clear validation failure."""

import json

import pytest

from opulse.cli import wizard
from opulse.cli.main import main


@pytest.mark.parametrize(("answers", "message"), [
    ([1, 2], "JSON object"),
    ({"dry_run": "yes"}, "dry_run must be true or false"),
    ({"layers": [0, 2]}, "layer 0 needs operators"),
    ({"numerals": {"max_base": 37}}, "numerals.digits"),
    ({"operators": {"symbol_blocks": ["not hex"]}}, "invalid Unicode block"),
])
def test_wizard_rejects_invalid_answers_without_writing(tmp_path, capsys, answers, message):
    answer_path = tmp_path / "answers.json"
    out = tmp_path / "config.yaml"
    answer_path.write_text(json.dumps(answers))

    assert main(["wizard", "--answers", str(answer_path), "--out", str(out)]) == 2
    assert message in capsys.readouterr().out
    assert not out.exists()


def test_wizard_failed_preview_does_not_write_config(tmp_path, monkeypatch, capsys):
    answer_path = tmp_path / "answers.json"
    answer_path.write_text("{}")
    out = tmp_path / "config.yaml"

    def fail_preview(settings):
        raise RuntimeError("preview failed")

    monkeypatch.setattr(wizard, "_preview", fail_preview)
    assert main(["wizard", "--answers", str(answer_path), "--out", str(out), "--dry-run"]) == 2
    assert "Dry run failed: preview failed" in capsys.readouterr().out
    assert not out.exists()
    assert main(["wizard", "--answers", str(answer_path), "--out", str(out)]) == 0
    assert out.exists()


def test_wizard_prompt_accepts_default_json_and_plain_text(monkeypatch):
    replies = iter(["", "[2, 3]", "custom"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(replies))
    assert wizard._prompt("layers", [8, 5]) == [8, 5]
    assert wizard._prompt("layers", [8, 5]) == [2, 3]
    assert wizard._prompt("symbol", "⊕") == "custom"
