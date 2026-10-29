"""Regression tests for the documentation inventory and checks."""

import re
from pathlib import Path

import pytest
from conftest import requires_zh_site

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

from tools import check_docs


def test_required_extras_match_project_dependencies() -> None:
    with (check_docs.ROOT / "pyproject.toml").open("rb") as source:
        extras = tomllib.load(source)["project"]["optional-dependencies"]
    used = {
        match.group(1)
        for path in check_docs.docs_files(check_docs.ROOT)
        if path.is_file()
        for line in path.read_text(encoding="utf-8").splitlines()
        if (match := check_docs.REQUIRES.fullmatch(line))
    }
    assert "interp" in used
    for extra in used:
        assert extra in extras
        assert extra in check_docs.OPTIONAL_IMPORTS
        distributions = {re.match(r"[A-Za-z0-9_.-]+", requirement).group()
                         for requirement in extras[extra]}
        assert distributions == set(check_docs.OPTIONAL_IMPORTS[extra])
    assert set(check_docs.OPTIONAL_IMPORTS["interp"]) == {"nnsight", "torch", "transformers"}


def test_cli_passes_shell_timeout(monkeypatch) -> None:
    received = []
    monkeypatch.setattr(check_docs, "scan", lambda *_: [])

    def fake_run_shell(root, timeout=180, only=None, skipped=None):
        received.append((timeout, only))
        return []

    monkeypatch.setattr(check_docs, "run_shell", fake_run_shell)
    assert check_docs.main(["--run", "--no-snippets", "--timeout", "1800", "--only", "docs/about/correctness.md"]) == 0
    assert received == [(1800, ["docs/about/correctness.md"])]


def test_shell_sandbox_has_full_suite_inputs(tmp_path: Path) -> None:
    check_docs._sandbox(check_docs.ROOT, tmp_path, include_project=True)
    for name in ("pyproject.toml", "README.md", "LICENSE", "LICENSE-docs", "src/opulse",
                 "docs/about/correctness.md"):
        assert (tmp_path / name).exists()


@requires_zh_site
def test_shell_sandbox_has_chinese_site_input(tmp_path: Path) -> None:
    check_docs._sandbox(check_docs.ROOT, tmp_path, include_project=True)
    assert (tmp_path / "docs_zh/about/correctness.md").exists()


def test_real_documentation_scan() -> None:
    issues = check_docs.scan(check_docs.ROOT, check_docs.cli_inventory(), check_docs.config_inventory())
    assert issues == [], "\n".join(map(str, issues))


@pytest.mark.slow
def test_real_snippet_generators() -> None:
    issues = check_docs.check_snippets(check_docs.ROOT)
    assert issues == [], "\n".join(map(str, issues))


def test_experiment_reports_are_not_site_inputs() -> None:
    assert check_docs.DATA_GENERATORS == {}
    assert not (check_docs.ROOT / "docs/assets/eval").exists()


def test_scale_widgets_have_separate_data_exporters() -> None:
    assert check_docs.DATA_BACKED_INCLUDES == {
        "docs/snippets/vis_growth.html": "tools/docs_scales_growth.py",
        "docs/snippets/vis_solve.html": "tools/docs_scales_solve.py",
    }
    for snippet, exporter in check_docs.DATA_BACKED_INCLUDES.items():
        assert (check_docs.ROOT / snippet).is_file()
        assert (check_docs.ROOT / exporter).is_file()


def test_cli_and_config_inventory() -> None:
    commands = check_docs.cli_inventory()
    assert ("operators",) in commands
    assert ("bench", "build") in commands
    assert "--layers" in commands[("operators",)]
    assert "--count" in commands[("bench", "build")]
    assert check_docs.config_inventory()["recursion.direct_bound"] == 8
    assert check_docs.config_inventory()["preset"] is None
    assert ("command", "bogus") in check_docs.check_command("opulse bogus", commands)
    assert ("subcommand", "bench bogus") in check_docs.check_command("opulse bench bogus", commands)
    assert check_docs.check_command("opulse audit-data tasks.jsonl | grep -E answer", commands) == []


def test_scan_finds_code_and_link_errors(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Readme\n")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs_zh").mkdir()
    (tmp_path / "docs" / "page.md").write_text(
        "# Page\n"
        "`opulse operators --made-up 1`\n"
        "Use --another-made-up to test an unknown flag.\n"
        "`operators.unknown_key`\n"
        "`opulse.verify.NoSuchName`\n"
        "[missing](absent.md)\n"
        "--8<-- \"docs/snippets/lost.md\"\n"
        "```yaml\nrecursion:\n  nonexisting: 2\n```\n"
    )
    issues = check_docs.scan(tmp_path, check_docs.cli_inventory(), check_docs.config_inventory())
    kinds = {issue.kind for issue in issues}
    assert {"option", "config key", "Python API", "internal link", "missing file"} <= kinds
    assert any(issue.detail == "--another-made-up" for issue in issues)
    assert any(issue.detail == "recursion.nonexisting" for issue in issues)


def test_scan_accepts_repository_urls_and_schema_names(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("https://github.com/example/opulse.git\n`opulse.derivation/1`\n")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs_zh").mkdir()
    issues = check_docs.scan(tmp_path, check_docs.cli_inventory(), check_docs.config_inventory())
    assert not [issue for issue in issues if issue.kind == "Python API"]


def test_documented_default_and_shell_size_rules(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Readme\n")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs_zh").mkdir()
    (tmp_path / "docs" / "page.md").write_text(
        "## `recursion`\n\n| `direct_bound` | `int` | `9` | Example. |\n"
        "```bash\nopulse operators --layers 40 30 20 --out ops.jsonl\n```\n"
    )
    issues = check_docs.scan(tmp_path, check_docs.cli_inventory(), check_docs.config_inventory())
    assert any(issue.kind == "default" and "direct_bound" in issue.detail for issue in issues)
    blocks = check_docs.shell_blocks((tmp_path / "docs" / "page.md").read_text())
    assert len(blocks) == 1
    assert "--layers 2 1" in check_docs.small_script(blocks[0][1])
    assert "--max-answer-share 1" in check_docs.small_script("opulse bench build --count 300")


def test_heading_ids_and_shown_output() -> None:
    assert "current-scope" in check_docs.heading_ids("## Scope { #current-scope }\n")
    assert check_docs.shown_output("```bash\nopulse --help\n```\nprints\n\n```text\nhello\n```\n", 1) == "hello"
    assert check_docs.resolve_api("opulse.integrations.inspect_eval.bench")


def test_default_prose_ignores_grouped_values() -> None:
    defaults = check_docs.config_inventory()
    assert check_docs._default_claims("`recursion.direct_bound` with default 9", "x.md", defaults)
    assert not check_docs._default_claims(
        "`recursion.modulus_min` and `recursion.modulus_max` 默认 3 和 9", "x.md", defaults
    )


def test_snippet_generator_diff(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "generate.py").write_text(
        "from pathlib import Path\n"
        "p = Path('docs/snippets/example.md')\n"
        "p.write_text('fresh\\n')\n"
    )
    (tmp_path / "docs" / "snippets").mkdir(parents=True)
    (tmp_path / "docs" / "snippets" / "example.md").write_text("stale\n")
    monkeypatch.setattr(check_docs, "GENERATORS", {"tools/generate.py": "docs/snippets"})
    issues = check_docs.check_snippets(tmp_path)
    assert any(issue.kind == "stale snippet" and issue.file == "docs/snippets/example.md" for issue in issues)


def test_missing_generator_inputs_are_reported(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "docs" / "snippets").mkdir(parents=True)
    (tmp_path / "docs" / "snippets" / "report.md").write_text("old\n")
    monkeypatch.setattr(check_docs, "GENERATORS", {})
    monkeypatch.setattr(check_docs, "DATA_GENERATORS", {
        "docs/snippets/report.md": (["tools/report.py"], ["outputs/report"]),
    })
    issues = check_docs.check_snippets(tmp_path)
    assert any(issue.kind == "generator input missing" and issue.detail == "outputs/report" for issue in issues)


def test_hand_authored_svg_include_allowlist(tmp_path: Path, monkeypatch) -> None:
    snippets = tmp_path / "docs" / "snippets"
    snippets.mkdir(parents=True)
    (snippets / "pipeline.svg.html").write_text("<svg></svg>\n")
    (snippets / "unknown.svg.html").write_text("<svg></svg>\n")
    monkeypatch.setattr(check_docs, "GENERATORS", {})
    monkeypatch.setattr(check_docs, "DATA_GENERATORS", {})
    issues = check_docs.check_snippets(tmp_path)
    assert [issue.file for issue in issues if issue.kind == "generator missing"] == [
        "docs/snippets/unknown.svg.html"
    ]


def test_shell_exit_code(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Readme\n")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs_zh").mkdir()
    (tmp_path / "docs" / "page.md").write_text("```bash\nopulse bogus\n```\n")
    issues = check_docs.run_shell(tmp_path)
    assert len(issues) == 1
    assert issues[0].kind == "shell"


def test_shell_compares_shown_output(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Readme\n")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs_zh").mkdir()
    (tmp_path / "docs" / "page.md").write_text(
        "```bash\nopulse --help\n```\nprints\n\n```text\nwrong output\n```\n"
    )
    issues = check_docs.run_shell(tmp_path)
    assert any(issue.kind == "shell output" for issue in issues)


def test_optional_shell_blocks_skip_only_for_missing_imports(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "README.md").write_text("# Readme\n")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs_zh").mkdir()
    (tmp_path / "docs" / "page.md").write_text(
        "```bash\n# requires: opulse[interp]\nfalse\n```\n"
        "```bash\nopulse --help\n```\n"
    )
    monkeypatch.setattr(check_docs, "missing_optional_imports", lambda extra: ("nnsight",))
    skipped = []
    assert check_docs.run_shell(tmp_path, skipped=skipped) == []
    assert [block.line for block in skipped] == [1, 5]
    assert all(block.missing == ("nnsight",) for block in skipped)

    monkeypatch.setattr(check_docs, "missing_optional_imports", lambda extra: ())
    skipped = []
    issues = check_docs.run_shell(tmp_path, skipped=skipped)
    assert skipped == []
    assert len(issues) == 1 and "exit 1" in issues[0].detail


def test_unknown_optional_extra_is_an_issue(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Readme\n")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs_zh").mkdir()
    (tmp_path / "docs" / "page.md").write_text("```bash\n# requires: opulse[unknown]\ntrue\n```\n")
    issues = check_docs.run_shell(tmp_path)
    assert len(issues) == 1 and "unknown optional extra" in issues[0].detail


def test_setup_shell_marker_is_executed(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Readme\n")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs_zh").mkdir()
    (tmp_path / "docs" / "page.md").write_text("```bash\n# run\nfalse\n```\n")
    assert len(check_docs.run_shell(tmp_path)) == 1


def test_wizard_prompts_only_dataclass_sections(monkeypatch) -> None:
    from opulse.cli import wizard

    monkeypatch.setattr("builtins.input", lambda prompt: "")
    answers = wizard._answers(None)
    assert "preset" not in answers
    assert answers["operators"]["symbol_sets"]
