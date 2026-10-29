"""Check documentation against the installed Opulse source.

Usage: python tools/check_docs.py [--run] [--root PATH] [--timeout SECONDS].

Snippet generators are listed in GENERATORS. They run in a temporary copy of
the required repository inputs, and their outputs are compared byte for byte.
Shell examples run in a temporary directory. For fast,
repeatable checks, --layers values become 2 1, --count and --samples become 3,
--documents becomes 3 (or each named split becomes 3), and --workers becomes 1.
The sweep example gains --quick, which runs its eleven focused cases.
Benchmark build examples gain --max-answer-share 1, since a three-task sample
cannot meet the normal five-percent answer-share limit.
Installation examples run the documentation scan and packaging tests in place
of the full pytest suite; run the full suite separately for release verification.
These substitutions affect execution only; they never change the docs.
Place ``# requires: opulse[interp]`` first in a shell block that needs the
interp extra. The checker skips it only if nnsight, torch, or transformers is
missing, and skips later blocks on the same page that need its output. A
``# run`` first line opts a setup block into execution. Skips are listed
separately from issues. Commands requiring a live model endpoint can fail and
are reported as such when their optional imports are installed.
Use --run --timeout 1800 before a release to give long shell blocks more time.
"""

from __future__ import annotations

import argparse
import ast
import importlib
import importlib.util
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
PYTHON = Path(sys.executable)
GENERATORS = {
    "tools/docs_examples.py": "docs/snippets",
    "tools/docs_visuals.py": "docs/snippets",
    "tools/docs_corpus_examples.py": "docs/snippets",
    "tools/docs_reference.py": "docs/reference",
}
# This SVG is drawn and maintained directly; it has no data generator.
HAND_AUTHORED_INCLUDES = frozenset({"docs/snippets/pipeline.svg.html"})
# These HTML widgets are maintained directly. Their data comes from the named
# exporters, which read finished operator sets outside the repository.
DATA_BACKED_INCLUDES = {
    "docs/snippets/vis_growth.html": "tools/docs_scales_growth.py",
    "docs/snippets/vis_solve.html": "tools/docs_scales_solve.py",
}
DATA_GENERATORS = {}
SECTIONS = {"semantics", "symbols", "numerals", "operators", "recursion", "expressions", "solver", "interest"}
CODE = re.compile(r"^```([^\n]*)\n(.*?)^```", re.MULTILINE | re.DOTALL)
INCLUDE = re.compile(r'--8<--\s+["\']([^"\']+)["\']')
LINK = re.compile(r"(?<!!)\[[^]]+\]\(([^)]+)\)")
PATH = re.compile(r"(?<![\w/])(?:docs(?:_zh)?|configs|data|tools|src|tests|examples)/[\w./-]+")
API = re.compile(r"\bopulse(?:\.[A-Za-z_]\w*)+\b")
CONFIG = re.compile(r"\b(?:" + "|".join(sorted(SECTIONS)) + r")\.[a-z_]\w*\b")
OPTION = re.compile(r"(?<![\w-])--[a-z][a-z0-9-]*")
# Flags of commands shown alongside Opulse but owned by other programs.
EXTERNAL_OPTIONS = {"--include", "--apply", "--no-hf", "--architecture", "--smoke",
                    "--quick", "--reward", "--processes"}
OPTIONAL_IMPORTS = {"interp": ("nnsight", "torch", "transformers")}
REQUIRES = re.compile(r"^# requires: opulse\[([a-z][a-z0-9_]*)\]$")


@dataclass(frozen=True)
class Issue:
    file: str
    line: int
    kind: str
    detail: str

    def __str__(self) -> str:
        return f"{self.file}:{self.line}: {self.kind}: {self.detail}"


@dataclass(frozen=True)
class Skipped:
    file: str
    line: int
    missing: tuple[str, ...]

    def __str__(self) -> str:
        return f"{self.file}:{self.line}: skipped (missing {', '.join(self.missing)})"


def cli_inventory() -> dict[tuple[str, ...], set[str]]:
    """Import registrations and walk every argparse parser, including nested ones."""
    from opulse.cli import main as cli

    parser = argparse.ArgumentParser(prog="opulse")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--plugin", action="append")
    commands = parser.add_subparsers(dest="command", required=True)
    for module in vars(cli).values():
        if isinstance(module, ModuleType) and module.__name__.startswith("opulse.cli.") and hasattr(module, "register"):
            module.register(commands)
    found: dict[tuple[str, ...], set[str]] = {}

    def walk(node: argparse.ArgumentParser, path: tuple[str, ...]) -> None:
        found[path] = {option for action in node._actions for option in action.option_strings}
        for action in node._actions:
            if isinstance(action, argparse._SubParsersAction):
                for name, child in action.choices.items():
                    walk(child, (*path, name))

    walk(parser, ())
    return found


def config_inventory() -> dict[str, object]:
    from dataclasses import asdict

    from opulse.config import Settings

    values = asdict(Settings())
    return {"preset": values["preset"], **{f"{section}.{key}": value for section, members in values.items()
                                        if isinstance(members, dict) for key, value in members.items()}}


def docs_files(root: Path) -> list[Path]:
    return [root / "README.md", *sorted((root / "docs").rglob("*.md")),
            *sorted((root / "docs_zh").rglob("*.md"))]


def heading_ids(markdown: str) -> set[str]:
    """The common Markdown heading IDs, including explicit HTML anchors."""
    ids = set(re.findall(r'<(?:a|[a-z]+)\s+(?:id|name)=["\']([^"\']+)', markdown))
    seen: dict[str, int] = {}
    for line in markdown.splitlines():
        match = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", line)
        if not match:
            continue
        label = re.sub(r"<[^>]+>|`", "", match.group(1))
        explicit = re.search(r"\{\s*#([\w-]+)\s*\}", label)
        if explicit:
            ids.add(explicit.group(1))
            label = label[:explicit.start()]
        slug = re.sub(r"[^\w -]", "", label.lower()).strip().replace(" ", "-")
        count = seen.get(slug, 0)
        ids.add(f"{slug}-{count}" if count else slug)
        seen[slug] = count + 1
    return ids


def markdown_target(candidate: Path) -> Path | None:
    for path in (candidate, candidate.with_suffix(".md"), candidate / "index.md"):
        if path.is_file():
            return path
    return None


def line_at(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def resolve_api(name: str) -> bool:
    parts = name.split(".")
    for end in range(len(parts), 0, -1):
        try:
            obj = importlib.import_module(".".join(parts[:end]))
        except (ImportError, AttributeError):
            continue
        for part in parts[end:]:
            if not hasattr(obj, part):
                break
            obj = getattr(obj, part)
        else:
            return True
    # Optional integration modules can exist even when their third-party import
    # is unavailable in the checker environment. Inspect their public syntax.
    for end in range(len(parts), 1, -1):
        base = ROOT / "src" / Path(*parts[:end])
        path = base.with_suffix(".py") if base.with_suffix(".py").is_file() else base / "__init__.py"
        if not path.is_file():
            continue
        if end == len(parts):
            return True
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            return False
        public = {node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
        public |= {alias.asname or alias.name for node in tree.body
                   if isinstance(node, (ast.Import, ast.ImportFrom)) for alias in node.names}
        return len(parts) == end + 1 and parts[end] in public
    return False


def command_words(line: str) -> list[str]:
    try:
        return shlex.split(line, comments=True)
    except ValueError:
        return []


def check_command(line: str, inventory: dict[tuple[str, ...], set[str]]) -> list[tuple[str, str]]:
    words = command_words(line)
    if not words or words[0] != "opulse":
        return []
    words = words[:next((i for i, word in enumerate(words) if word in {"|", "||", "&&", ";", ">", ">>"}),
                        len(words))]
    path: tuple[str, ...] = ()
    errors = []
    index = 1
    while index < len(words) and words[index].startswith("-"):
        option = words[index].split("=", 1)[0]
        if option not in inventory[()]:
            errors.append(("option", option))
        index += 2 if option == "--plugin" and "=" not in words[index] else 1
    if index < len(words):
        first = (words[index],)
        if first not in inventory:
            if words[index].startswith("<") or words[index] == "...":
                return errors
            return [*errors, ("command", words[index])]
        path = first
        index += 1
        children = {candidate[len(path)] for candidate in inventory
                    if len(candidate) == len(path) + 1 and candidate[:len(path)] == path}
        if children and index < len(words) and not words[index].startswith("-"):
            child = words[index]
            if child not in children:
                errors.append(("subcommand", " ".join((*path, child))))
            else:
                path = (*path, child)
            index += 1
    while index < len(words):
        word = words[index]
        if word.startswith("-"):
            option = word.split("=", 1)[0]
            allowed = set(inventory[path]) | set(inventory[()])
            if option not in allowed:
                errors.append(("option", option))
            # Options consume a value unless the next word is a command choice.
            index += 1
            continue
        child = (*path, word)
        if child in inventory:
            path = child
        index += 1
    return errors


def _check_yaml(text: str, source: str, start: int, defaults: dict[str, object]) -> list[Issue]:
    import yaml

    try:
        obj = yaml.safe_load(text)
    except yaml.YAMLError:
        return []  # some fenced YAML is a record, not a settings file
    if not isinstance(obj, dict) or not set(obj) & (SECTIONS | {"preset"}):
        return []
    issues = []
    for section, members in obj.items():
        if section == "preset":
            continue
        if section not in SECTIONS:
            if isinstance(members, dict) and section not in {"metadata", "provenance"}:
                issues.append(Issue(source, start, "config key", section))
            continue
        if isinstance(members, dict):
            for key in members:
                dotted = f"{section}.{key}"
                if dotted not in defaults:
                    issues.append(Issue(source, start, "config key", dotted))
    return issues


def _default_claims(text: str, source: str, defaults: dict[str, object]) -> list[Issue]:
    issues = []
    section = None
    for number, line in enumerate(text.splitlines(), 1):
        heading = re.match(r"## `?([a-z]+)`?\s*$", line)
        if heading and heading.group(1) in SECTIONS:
            section = heading.group(1)
        if section and line.startswith("| `"):
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) >= 3:
                dotted = f"{section}.{cells[0].strip('`')}"
                if dotted in defaults and cells[2].startswith("`"):
                    shown = cells[2].strip("`")
                    value = defaults[dotted]
                    expected = repr(value)
                    try:
                        actual = ast.literal_eval(shown)
                    except (SyntaxError, ValueError):
                        actual = {"true": True, "false": False, "null": None}.get(shown.lower(), shown)
                    if isinstance(value, tuple) and isinstance(actual, list):
                        actual = tuple(actual)
                    if actual != value:
                        issues.append(Issue(source, number, "default", f"{dotted}: {shown} != {expected}"))
        for match in re.finditer(r"`((?:" + "|".join(SECTIONS) +
                                 r")\.[a-z_]\w*)`\s*(?:\(\s*)?(?:with\s+)?(?:default\b|默认(?:值)?(?:为|是)?)"
                                 r"\s*[:：]?\s*(-?\d+(?:\.\d+)?)", line, re.IGNORECASE):
            key, claim = match.groups()
            if re.match(r"\s*(?:and|和|与|、)\s*-?\d", line[match.end():]):
                continue  # a shared statement assigns two defaults in order
            if key in defaults and isinstance(defaults[key], (int, float)) and float(claim) != float(defaults[key]):
                issues.append(Issue(source, number, "default", f"{key}: {claim} != {defaults[key]}"))
    return issues


def scan(root: Path, inventory: dict[tuple[str, ...], set[str]], defaults: dict[str, object]) -> list[Issue]:
    issues: list[Issue] = []
    all_options = set().union(*inventory.values())
    for file in docs_files(root):
        if not file.is_file():
            continue
        text = file.read_text(encoding="utf-8")
        source = file.relative_to(root).as_posix()
        issues.extend(_default_claims(text, source, defaults))
        for match in CODE.finditer(text):
            language, body = match.groups()
            if language.split()[0:1] in (["yaml"], ["yml"]):
                issues.extend(_check_yaml(body, source, line_at(text, match.start()), defaults))
            if language.split()[0:1] in (["bash"], ["sh"], ["shell"]):
                for line in body.replace("\\\n", " ").splitlines():
                    for kind, value in check_command(line, inventory):
                        issues.append(Issue(source, line_at(text, match.start()), kind, value))
        prose = CODE.sub(lambda match: " " * len(match.group()), text)
        for match in CONFIG.finditer(prose):
            key = match.group()
            suffix = text[match.end():match.end() + 1]
            prefix = text[match.start() - 1:match.start()] if match.start() else ""
            if suffix == "." or prefix in ("/", ".") or key.split(".")[1] in {
                    "md", "json", "jsonl", "png", "html", "yaml", "py", "svg", "wav", "analyzed", "described"}:
                continue
            if resolve_api("opulse." + key):
                continue
            if key not in defaults:
                issues.append(Issue(source, line_at(text, match.start()), "config key", key))
        for match in API.finditer(text):
            name = match.group()
            if (match.start() and text[match.start() - 1] == "/") or re.match(r"/\d+\b", text[match.end():]):
                continue  # repository URLs and versioned schema names are not Python imports
            if not resolve_api(name):
                issues.append(Issue(source, line_at(text, match.start()), "Python API", name))
        for match in re.finditer(r"`(opulse\s+[^`\n]+)`", text):
            for kind, value in check_command(match.group(1), inventory):
                issues.append(Issue(source, line_at(text, match.start()), kind, value))
        for match in OPTION.finditer(prose):
            option = match.group()
            if (option not in all_options and option not in EXTERNAL_OPTIONS and
                    option != "--8" and not option.startswith("--md-")):
                issues.append(Issue(source, line_at(text, match.start()), "option", option))
        if source == "docs/reference/cli.md":
            for number, line in enumerate(text.splitlines(), 1):
                if re.match(r"^\s+--[a-z]", line):
                    match = OPTION.search(line)
                    if match and match.group() not in all_options:
                        issues.append(Issue(source, number, "option", match.group()))
        for match in re.finditer(r"^from\s+(opulse(?:\.[\w]+)+)\s+import\s+([^\n]+)", text, re.MULTILINE):
            module = match.group(1)
            for name in match.group(2).split(","):
                name = name.strip().split(" as ")[0]
                if re.fullmatch(r"[A-Za-z_]\w*", name) and not resolve_api(f"{module}.{name}"):
                    issues.append(Issue(source, line_at(text, match.start()), "Python API", f"{module}.{name}"))
        for match in INCLUDE.finditer(text):
            target = root / match.group(1)
            if not target.is_file():
                issues.append(Issue(source, line_at(text, match.start()), "missing file", match.group(1)))
        for match in LINK.finditer(text):
            href = match.group(1).split()[0].strip("<>")
            if href.startswith(("http:", "https:", "mailto:")):
                continue
            route, _, fragment = href.partition("#")
            if not route and fragment:
                if fragment not in heading_ids(text):
                    issues.append(Issue(source, line_at(text, match.start()), "internal link", href))
                continue
            route_path = route.lstrip("/")
            route_path = route_path.removeprefix("opulse/")
            candidates = ([root / site / route_path for site in ("docs", "docs_zh")]
                          if route.startswith("/") else [file.parent / route])
            targets = [target for candidate in candidates if (target := markdown_target(candidate))]
            if ((route and not targets) or
                    (fragment and targets and not any(target.suffix != ".md" or
                                                        fragment in heading_ids(target.read_text(encoding="utf-8"))
                                                        for target in targets))):
                issues.append(Issue(source, line_at(text, match.start()), "internal link", href))
        for match in PATH.finditer(text):
            name = match.group().rstrip(".,:;")
            if "<" in name or "*" in name or name.endswith("/"):
                continue
            # Only paths presented as a literal file, never generated output paths.
            if (name.startswith(("docs/", "docs_zh/", "configs/", "data/", "tools/", "src/", "tests/", "examples/"))
                    and Path(name).suffix and not re.search(r"(?:mine|your|example|NAME|PATH|<|\*)", name)
                    and not (root / name).exists()):
                issues.append(Issue(source, line_at(text, match.start()), "missing file", name))
    return sorted(set(issues), key=lambda x: (x.file, x.line, x.kind, x.detail))


def _sandbox(root: Path, temp: Path, include_project: bool = False) -> None:
    for name in ("tools", "configs", "data", "examples", "tests"):
        source = root / name
        if source.exists():
            shutil.copytree(source, temp / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (temp / "docs" / "snippets").mkdir(parents=True)
    (temp / "docs" / "assets").mkdir(parents=True)
    (temp / "outputs").mkdir()
    if include_project:
        for name in ("src", "docs", "docs_zh", "LICENSES"):
            source = root / name
            if source.exists():
                shutil.copytree(source, temp / name, dirs_exist_ok=True,
                                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        for name in ("README.md", "CHANGELOG.md", "CONTRIBUTING.md", "CITATION.cff", "pyproject.toml",
                     "mkdocs.yml", "LICENSE", "LICENSE-docs"):
            source = root / name
            if source.is_file():
                shutil.copy2(source, temp / name)


def _check_generator(root: Path, generator: str, output: str, timeout: int) -> tuple[list[Issue], set[str]]:
    issues: list[Issue] = []
    generated_files: set[str] = set()
    with tempfile.TemporaryDirectory(prefix="opulse-docs-") as directory:
        temp = Path(directory)
        _sandbox(root, temp)
        env = {**os.environ, "PYTHONPATH": str(root / "src"), "CUDA_VISIBLE_DEVICES": ""}
        output_dir = temp / output
        try:
            run = subprocess.run([str(PYTHON), generator], cwd=temp, env=env,
                                 capture_output=True, text=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            return [Issue(generator, 1, "generator", "timed out")], generated_files
        if run.returncode:
            message = (run.stderr or run.stdout).strip().splitlines()
            return [Issue(generator, 1, "generator", message[-1] if message else f"exit {run.returncode}")], generated_files
        for generated in output_dir.rglob("*"):
            if not generated.is_file():
                continue
            relative = generated.relative_to(temp)
            generated_files.add(relative.as_posix())
            expected = root / relative
            if not expected.is_file() or generated.read_bytes() != expected.read_bytes():
                issues.append(Issue(relative.as_posix(), 1, "stale snippet", generator))
    return issues, generated_files


def check_snippets(root: Path, timeout: int = 600) -> list[Issue]:
    issues = []
    generated_files: set[str] = set()
    with ThreadPoolExecutor(max_workers=max(1, len(GENERATORS))) as pool:
        runs = pool.map(lambda item: _check_generator(root, *item, timeout), GENERATORS.items())
        for found, files in runs:
            issues.extend(found)
            generated_files.update(files)
    with tempfile.TemporaryDirectory(prefix="opulse-docs-data-") as directory:
        temp = Path(directory)
        _sandbox(root, temp)
        env = {**os.environ, "PYTHONPATH": str(root / "src"), "CUDA_VISIBLE_DEVICES": ""}
        for snippet, (command, inputs) in DATA_GENERATORS.items():
            if not (root / snippet).is_file():
                continue
            missing = [name for name in inputs if not (root / name).exists()]
            if missing:
                issues.append(Issue(snippet, 1, "generator input missing", ", ".join(missing)))
                continue
            for name in inputs:
                source, target = root / name, temp / name
                if target.exists():
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                if source.is_dir():
                    shutil.copytree(source, target)
                else:
                    shutil.copy2(source, target)
            generated = temp / snippet
            generated.parent.mkdir(parents=True, exist_ok=True)
            try:
                run = subprocess.run([str(PYTHON), *command], cwd=temp, env=env,
                                     capture_output=True, text=True, timeout=timeout, check=False)
            except subprocess.TimeoutExpired:
                issues.append(Issue(snippet, 1, "generator", "timed out"))
                continue
            if run.returncode:
                message = (run.stderr or run.stdout).strip().splitlines()
                issues.append(Issue(snippet, 1, "generator", message[-1] if message else f"exit {run.returncode}"))
            elif not generated.is_file() or generated.read_bytes() != (root / snippet).read_bytes():
                issues.append(Issue(snippet, 1, "stale snippet", command[0]))
        for asset in (root / "docs/snippets").glob("*.svg.html"):
            relative = asset.relative_to(root).as_posix()
            if relative not in generated_files and relative not in HAND_AUTHORED_INCLUDES:
                issues.append(Issue(relative, 1, "generator missing", "no generator is registered for this file"))
        for snippet, exporter in DATA_BACKED_INCLUDES.items():
            if (root / snippet).is_file() and not (root / exporter).is_file():
                issues.append(Issue(snippet, 1, "generator missing", exporter))
    return issues


def shell_blocks(text: str) -> list[tuple[int, str]]:
    blocks = []
    for match in CODE.finditer(text):
        if match.group(1).split()[0:1] not in (["bash"], ["sh"], ["shell"]):
            continue
        body = match.group(2)
        first = next((line.strip() for line in body.splitlines() if line.strip()), "")
        if first.startswith(("opulse ", "python tools/")) or first == "# run" or REQUIRES.fullmatch(first):
            blocks.append((line_at(text, match.start()), body))
    return blocks


def required_extra(script: str) -> str | None:
    """Return the extra named by the first line, if present."""
    first = next((line.strip() for line in script.splitlines() if line.strip()), "")
    match = REQUIRES.fullmatch(first)
    return match.group(1) if match else None


def missing_optional_imports(extra: str) -> tuple[str, ...]:
    """Find missing imports for a supported optional extra."""
    names = OPTIONAL_IMPORTS[extra]
    missing = []
    for name in names:
        try:
            available = importlib.util.find_spec(name) is not None
        except (ImportError, ValueError):
            available = False
        if not available:
            missing.append(name)
    return tuple(missing)


def shown_output(text: str, number: int) -> str | None:
    """Read a fenced output introduced by 'prints' after a shell block."""
    for match in CODE.finditer(text):
        if line_at(text, match.start()) != number:
            continue
        tail = text[match.end():match.end() + 1000]
        output = re.match(r"\s*prints\s*\n+```(?:text|json|console)?\n(.*?)\n```", tail, re.DOTALL)
        return output.group(1).strip() if output else None
    return None


def small_script(script: str) -> str:
    """Apply the documented execution size substitutions to shell source."""
    script = re.sub(r"(--layers\s+)(?:\d+\s+)*\d+(?![\d,])", r"\g<1>2 1", script)
    script = re.sub(r"(--(?:count|samples)\s+)\d+", r"\g<1>3", script)
    script = re.sub(r"(--workers\s+)\d+", r"\g<1>1", script)
    script = re.sub(r"python tools/sweep\.py(?!\s+--quick)", "python tools/sweep.py --quick", script)
    script = re.sub(r"(?m)^python -m pytest -q[^\n]*$",
                    "python -m pytest -q tests/test_check_docs.py::test_real_documentation_scan "
                    "tests/test_packaging.py::test_packaged_runtime_data_matches_source", script)
    script = re.sub(r"\bopulse\s+bench\s+build\b", "opulse bench build --max-answer-share 1", script)

    def documents(match: re.Match[str]) -> str:
        value = match.group(2)
        if "=" in value:
            value = re.sub(r"=\d+", "=3", value)
        else:
            value = "3"
        return match.group(1) + value

    return re.sub(r"(--documents\s+)([\w=,]+)", documents, script)


def run_shell(root: Path, timeout: int = 180, only: list[str] | None = None,
              skipped: list[Skipped] | None = None) -> list[Issue]:
    issues = []
    if skipped is None:
        skipped = []
    with tempfile.TemporaryDirectory(prefix="opulse-docs-run-") as directory:
        temp = Path(directory)
        _sandbox(root, temp, include_project=True)
        bin_dir = temp / "bin"
        bin_dir.mkdir()
        (bin_dir / "opulse").write_text(f'#!/bin/sh\nexec "{PYTHON}" -m opulse.cli.main "$@"\n')
        (bin_dir / "python").write_text(f'#!/bin/sh\nexec "{PYTHON}" "$@"\n')
        for shim in bin_dir.iterdir():
            shim.chmod(0o755)
        env = {**os.environ, "PYTHONPATH": str(temp / "src"), "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"],
               "CUDA_VISIBLE_DEVICES": ""}
        for file in docs_files(root):
            if not file.is_file():
                continue
            if only and file.relative_to(root).as_posix() not in only:
                continue
            text = file.read_text(encoding="utf-8")
            skipped_missing: tuple[str, ...] = ()
            for number, body in shell_blocks(text):
                source = file.relative_to(root).as_posix()
                extra = required_extra(body)
                if extra is not None and extra not in OPTIONAL_IMPORTS:
                    issues.append(Issue(source, number, "shell", f"unknown optional extra opulse[{extra}]"))
                    continue
                missing = skipped_missing or (missing_optional_imports(extra) if extra else ())
                if missing:
                    skipped_missing = missing
                    skipped.append(Skipped(source, number, missing))
                    continue
                executed = small_script(body)
                print(f"running {file.relative_to(root)}:{number}", file=sys.stderr, flush=True)
                started = time.monotonic()
                try:
                    run = subprocess.run(["bash", "-e", "-o", "pipefail", "-c", executed], cwd=temp,
                                         env=env, capture_output=True, text=True, timeout=timeout, check=False)
                except subprocess.TimeoutExpired:
                    issues.append(Issue(file.relative_to(root).as_posix(), number, "shell", "timed out"))
                    print(f"finished {source}:{number} in {time.monotonic() - started:.1f} s", file=sys.stderr, flush=True)
                    continue
                print(f"finished {source}:{number} in {time.monotonic() - started:.1f} s", file=sys.stderr, flush=True)
                if run.returncode:
                    message = (run.stderr or run.stdout).strip().splitlines()
                    issues.append(Issue(file.relative_to(root).as_posix(), number, "shell",
                                        f"exit {run.returncode}: {message[-1] if message else ''}"))
                else:
                    expected = shown_output(text, number)
                    if expected is not None and run.stdout.strip() != expected:
                        issues.append(Issue(file.relative_to(root).as_posix(), number, "shell output",
                                            "printed output differs from the included snippet"))
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--run", action="store_true", help="also execute eligible shell code blocks")
    parser.add_argument("--timeout", type=int, default=180, metavar="SECONDS",
                        help="per shell block timeout with --run (default: 180)")
    parser.add_argument("--no-snippets", action="store_true", help="skip generator checks during development")
    parser.add_argument("--only", action="append", metavar="FILE",
                        help="with --run, execute only the shell blocks of this docs file (repeatable)")
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    root = args.root.resolve()
    issues = scan(root, cli_inventory(), config_inventory())
    if not args.no_snippets:
        issues.extend(check_snippets(root))
    if args.run:
        skipped: list[Skipped] = []
        issues.extend(run_shell(root, timeout=args.timeout, only=args.only, skipped=skipped))
        for block in skipped:
            print(block)
    for issue in sorted(issues, key=lambda x: (x.file, x.line, x.kind, x.detail)):
        print(issue)
    print(f"{len(issues)} documentation issue(s)")
    if args.run:
        print(f"{len(skipped)} shell block(s) skipped")
    return bool(issues)


if __name__ == "__main__":
    sys.exit(main())
