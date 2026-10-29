"""The generated references cover the live parser and every settings field."""

import argparse
import importlib.util
from dataclasses import fields, is_dataclass
from pathlib import Path

import pytest
from conftest import requires_zh_site

from opulse.cli import main as cli_main
from opulse.config import Settings

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("docs_reference", ROOT / "tools" / "docs_reference.py")
assert SPEC and SPEC.loader
docs_reference = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(docs_reference)


def test_configuration_describes_every_setting_and_rejects_missing_description(monkeypatch):
    defaults = Settings()
    keys = {f"{section.name}.{item.name}" if is_dataclass(getattr(defaults, section.name))
            else section.name
            for section in fields(Settings)
            for item in (fields(getattr(defaults, section.name))
                         if is_dataclass(getattr(defaults, section.name)) else (None,))}
    assert keys == set(docs_reference.DESCRIPTIONS)
    assert docs_reference.config_page() == (ROOT / "docs/reference/configuration.md").read_text()
    monkeypatch.delitem(docs_reference.DESCRIPTIONS, "preset")
    with pytest.raises(ValueError, match="preset"):
        docs_reference.config_page()
    monkeypatch.setitem(docs_reference.DESCRIPTIONS, "preset", "   ")
    before = (ROOT / "docs/reference/cli.md").read_text()
    with pytest.raises(ValueError, match="preset"):
        docs_reference.main()
    assert (ROOT / "docs/reference/cli.md").read_text() == before


def test_cli_reference_covers_registered_commands_and_new_options():
    parser = argparse.ArgumentParser(prog="opulse")
    commands = parser.add_subparsers(dest="command")
    for module in (value for value in vars(cli_main).values()
                   if hasattr(value, "register") and getattr(value, "__name__", "").startswith("opulse.cli.")):
        module.register(commands)
    page = docs_reference.cli_page()
    assert page == (ROOT / "docs/reference/cli.md").read_text()
    for name in commands.choices:
        assert f"## {name}\n" in page
    for option in ("--media", "--world", "--records", "--preset", "--interest-selection",
                   "--solver", "--recursion-styles", "--definition-format"):
        assert option in page


@requires_zh_site
def test_chinese_reference_keys_options_and_defaults_match():
    english = (ROOT / "docs/reference/configuration.md").read_text().splitlines()
    chinese = (ROOT / "docs_zh/reference/configuration.md").read_text().splitlines()
    config_rows = lambda lines: [tuple(line.split(" | ")[:3]) for line in lines if line.startswith("| `")]
    assert config_rows(english) == config_rows(chinese)

    parser = argparse.ArgumentParser(prog="opulse")
    commands = parser.add_subparsers(dest="command")
    for module in (value for value in vars(cli_main).values()
                   if hasattr(value, "register") and getattr(value, "__name__", "").startswith("opulse.cli.")):
        module.register(commands)
    page = (ROOT / "docs_zh/reference/cli.md").read_text().splitlines()
    actual = {}
    heading = None
    for line in page:
        if line.startswith(("## ", "### ")):
            heading = line.split(" ", 1)[1]
        elif heading and line.startswith("| `-"):
            parts = line.split(" | ")
            actual.setdefault(heading, []).append((parts[0].strip("| "), parts[1].strip("`")))

    def check(name, sub):
        expected = []
        for action in sub._actions:
            if not action.option_strings:
                continue
            default = docs_reference.relative_default(action.default)
            if isinstance(default, Path):
                default = str(default)
            expected.append((", ".join(f"`{option}`" for option in action.option_strings), repr(default)))
        assert actual[name] == expected
        for action in sub._actions:
            if isinstance(action, argparse._SubParsersAction):
                for child_name, child in action.choices.items():
                    check(f"{name} {child_name}", child)

    for name, sub in commands.choices.items():
        check(name, sub)
