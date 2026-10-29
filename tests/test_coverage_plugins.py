"""Plugin loading and atom registration use the same rules as built-in atoms."""

import pytest

from opulse.cli.main import main
from opulse.core.primitives import (
    CUSTOM,
    atom_records,
    register_primitive,
    rule_for,
    unregister_primitive,
)
from opulse.core.semantics import BASE_OPERATIONS, Semantics


@pytest.mark.parametrize("source", ["flag", "equals", "environment"])
def test_cli_loads_atom_plugin_before_running_command(tmp_path, monkeypatch, source):
    plugin = tmp_path / "w13_plugin.py"
    plugin.write_text('from opulse.core.primitives import register_primitive\n'
                      'register_primitive("w13atom", "⊛", lambda a: a + 7, rule="a ⊛ adds seven.")\n')
    answers = tmp_path / "answers.json"
    answers.write_text("{}")
    out = tmp_path / "config.yaml"
    argv = ["wizard", "--answers", str(answers), "--out", str(out)]
    monkeypatch.delenv("OPULSE_PLUGINS", raising=False)
    if source == "flag":
        argv = ["--plugin", str(plugin), *argv]
    elif source == "equals":
        argv = [f"--plugin={plugin}", *argv]
    else:
        monkeypatch.setenv("OPULSE_PLUGINS", str(plugin))
    try:
        assert main(argv) == 0
        assert out.exists()
        assert CUSTOM["w13atom"].compute(3) == 10
        assert atom_records(["w13atom"])[0]["symbol"] == "⊛"
    finally:
        unregister_primitive("w13atom")


@pytest.mark.parametrize(("name", "position", "arity", "message"), [
    ("w13bad", "postfix", 0, "one or more arguments"),
    ("w13bad", "middle", 1, "prefix' or 'postfix"),
    ("bad-name", "postfix", 1, "identifier"),
])
def test_atom_registration_rejects_invalid_shape(name, position, arity, message):
    with pytest.raises(ValueError, match=message):
        register_primitive(name, "⊛", lambda a: a, rule="Return a.", n_ary=arity, position=position)


def test_rebinding_atom_moves_its_symbol_and_rule():
    try:
        register_primitive("w13shift", "⊛", lambda a: a + 1, rule="Add one.")
        register_primitive("w13shift", "⊚", lambda a: a + 2, rule="Add two.")
        assert ("⊛", 1, "postfix") not in BASE_OPERATIONS
        assert BASE_OPERATIONS[("⊚", 1, "postfix")] == "w13shift"
        assert atom_records(["w13shift"])[0]["symbol"] == "⊚"
        assert rule_for("w13shift") == "Add two."
        assert Semantics("exact", 100).operations()["w13shift"](3) == 5
    finally:
        unregister_primitive("w13shift")
    with pytest.raises(KeyError, match="unknown atom"):
        rule_for("w13shift")
