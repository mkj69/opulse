#!/usr/bin/env bash
# Build distributions, then exercise the installed wheel outside the source tree.
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
shared_python=${OPULSE_SHARED_PYTHON:-$(command -v python3 || command -v python)}
wheelhouse_python=${OPULSE_WHEELHOUSE_PYTHON:-$shared_python}
if ! "$wheelhouse_python" -c 'import importlib.util; assert importlib.util.find_spec("tomllib") or importlib.util.find_spec("tomli")' >/dev/null 2>&1; then
    common_git_dir=$(git -C "$root" rev-parse --path-format=absolute --git-common-dir)
    candidate="${common_git_dir%/.git}/.venv/bin/python"
    if [[ -x $candidate ]]; then
        wheelhouse_python=$candidate
    fi
fi
uv=${OPULSE_UV:-${UV:-$(command -v uv || true)}}
if [[ -n $uv ]]; then
    uv=$(command -v "$uv" || true)
fi
export OPULSE_WHEEL_CACHE=${OPULSE_WHEEL_CACHE:-${UV_CACHE_DIR:-${XDG_CACHE_HOME:-$HOME/.cache}/uv}}
scratch=$(mktemp -d "${TMPDIR:-/tmp}/opulse-fresh-install.XXXXXX")
export PIP_CACHE_DIR="$scratch/pip-cache"
if [[ ${OPULSE_KEEP_TMP:-0} != 1 ]]; then
    trap 'rm -rf "$scratch"' EXIT
fi
mkdir -p "$scratch"/{source,dist,wheelhouse,run}

say() { printf '\n== %s ==\n' "$*"; }
venv() {
    if [[ -n $uv && -x $uv ]]; then
        UV_CACHE_DIR="$scratch/uv-cache" "$uv" venv --python "$shared_python" "$1"
    else
        "$shared_python" -m venv --without-pip "$1"
    fi
}

# Source is copied so setuptools does not leave egg-info or build files in the worktree.
git -C "$root" ls-files -z | tar -C "$root" --null -T - -cf - | tar -C "$scratch/source" -xf -
cat > "$scratch/wheelhouse.py" <<'PY'
import base64
import ast
import csv
import hashlib
import importlib.metadata as metadata
import io
import os
from pathlib import Path
import shutil
import sys
import re
try:
    import tomllib as tomli
except ModuleNotFoundError:
    try:
        import tomli
    except ModuleNotFoundError:
        tomli = None
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from zipfile import ZIP_DEFLATED, ZipFile

source, out = map(Path, sys.argv[1:3])
pyproject = (source / "pyproject.toml").read_text()
if tomli is not None:
    project = tomli.loads(pyproject)["project"]
else:
    # The helper only needs these three arrays. They are Python-compatible TOML
    # string lists, so Python 3.10 can read them without an installed TOML parser.
    def dependency_list(section, key):
        body = re.search(rf"(?ms)^\[{re.escape(section)}\]\s*$(.*?)(?=^\[|\Z)", pyproject)
        if body is None:
            raise SystemExit(f"missing [{section}] in pyproject.toml")
        match = re.search(rf"(?m)^{re.escape(key)}\s*=\s*(\[[^\n]*\])\s*$", body.group(1))
        if match is None:
            raise SystemExit(f"missing single-line {key} dependencies in [{section}]")
        values = ast.literal_eval(match.group(1))
        if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
            raise SystemExit(f"invalid {key} dependencies in [{section}]")
        return values

    project = {"dependencies": dependency_list("project", "dependencies"),
               "optional-dependencies": {
                   extra: dependency_list("project.optional-dependencies", extra)
                   for extra in ("docs", "dev")}}
installed = {canonicalize_name(d.metadata["Name"]): d for d in metadata.distributions()}
seen = set()
missing = set()
queue = [(Requirement(s), "") for s in project["dependencies"]]
for extra in ("docs", "dev"):
    queue += [(Requirement(s), extra) for s in project["optional-dependencies"][extra]]
queue += [(Requirement(s), "") for s in ("setuptools>=77", "wheel")]

def cached(name):
    root = Path(os.environ["OPULSE_WHEEL_CACHE"])
    for info in (root / "archive-v0").glob(f"*/{name.replace('-', '_')}-*.dist-info"):
        if info.is_dir():
            return metadata.PathDistribution(info)
    return None

while queue:
    req, parent_extra = queue.pop(0)
    if req.marker and not req.marker.evaluate({"extra": parent_extra}):
        continue
    name = canonicalize_name(req.name)
    dist = installed.get(name) or cached(name)
    if dist is None:
        missing.add(name)
        continue
    if dist.version not in req.specifier:
        raise SystemExit(f"shared environment has {name} {dist.version}, which does not meet {req.specifier}")
    key = (name, tuple(sorted(req.extras)))
    if key in seen:
        continue
    seen.add(key)
    for text in dist.requires or []:
        dependency = Requirement(text)
        for extra in ("", *req.extras):
            if not dependency.marker or dependency.marker.evaluate({"extra": extra}):
                queue.append((dependency, extra))
                break

if missing:
    raise SystemExit("offline wheelhouse cannot supply: " + ", ".join(sorted(missing)))

def pack(dist):
    name = canonicalize_name(dist.metadata["Name"])
    version = dist.version.replace("-", "_")
    wheel = dist.read_text("WHEEL")
    if wheel is None:
        raise SystemExit(f"{name} has no WHEEL metadata")
    tags = [line[5:] for line in wheel.splitlines() if line.startswith("Tag: ")]
    tag = next((value for value in tags if value.startswith("py3-")), tags[0])
    filename = f"{name.replace('-', '_')}-{version}-{tag}.whl"
    target = out / filename
    info = next(str(path) for path in dist.files or [] if str(path).endswith(".dist-info/WHEEL"))
    record = info.rsplit("/", 1)[0] + "/RECORD"
    entries = []
    with ZipFile(target, "w", ZIP_DEFLATED) as archive:
        for item in dist.files or []:
            member = str(item)
            if member == record or member.startswith("..") or os.path.isabs(member):
                continue
            path = Path(dist.locate_file(item))
            if not path.is_file():
                continue
            content = path.read_bytes()
            archive.writestr(member, content)
            digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=").decode()
            entries.append((member, "sha256=" + digest, str(len(content))))
        stream = io.StringIO()
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerows([*entries, (record, "", "")])
        archive.writestr(record, stream.getvalue())
    print(filename)

for name in sorted({name for name, _ in seen}):
    pack(installed.get(name) or cached(name))

seeds = sorted(Path(os.environ["OPULSE_WHEEL_CACHE"]).glob(
    "archive-v0/*/virtualenv/seed/wheels/embed/pip-*.whl"))
if not seeds:
    for location in ("/opt/saltstack/salt/lib", "/usr/lib", "/usr/local/lib"):
        seeds.extend(Path(location).glob(
            "python*/site-packages/virtualenv/seed/wheels/embed/pip-*.whl"))
if seeds:
    shutil.copy2(seeds[-1], out / seeds[-1].name)
else:
    raise SystemExit("no pip seed wheel is available for the isolated virtualenvs")
PY

say "Construct offline wheelhouse from the shared environment"
PYTHONPATH= "$wheelhouse_python" "$scratch/wheelhouse.py" "$scratch/source" "$scratch/wheelhouse" \
    > "$scratch/wheelhouse.log"
printf 'assembled %s dependency wheels\n' "$(wc -l < "$scratch/wheelhouse.log")"
pip_seed=$(find "$scratch/wheelhouse" -maxdepth 1 -name 'pip-*.whl' | sort | tail -1)

install_pip() {
    PYTHONPATH="$pip_seed" "$1/bin/python" -m pip install --no-index \
        --find-links "$scratch/wheelhouse" pip
}

say "Build source distribution and wheel"
venv "$scratch/build-env"
install_pip "$scratch/build-env"
"$scratch/build-env/bin/python" -m pip install --no-index --find-links "$scratch/wheelhouse" setuptools wheel
if ! (
    cd "$scratch/source"
    if "$shared_python" -c 'import build' >/dev/null 2>&1; then
        PYTHONPATH= "$shared_python" -m build --no-isolation --outdir "$scratch/dist"
    else
        "$scratch/build-env/bin/python" -c \
            'import setuptools.build_meta as b, sys; b.build_sdist(sys.argv[1])' "$scratch/dist"
        "$scratch/build-env/bin/python" -m pip wheel . --no-deps --no-build-isolation \
            --no-index --find-links "$scratch/wheelhouse" --wheel-dir "$scratch/dist"
    fi
) > "$scratch/build.log" 2>&1; then
    tail -80 "$scratch/build.log" >&2
    exit 1
fi
wheel=$(find "$scratch/dist" -maxdepth 1 -name 'opulse-*.whl' -print -quit)
sdist=$(find "$scratch/dist" -maxdepth 1 -name 'opulse-*.tar.gz' -print -quit)
[[ -n $wheel && -n $sdist ]] || { echo 'sdist or wheel was not built' >&2; exit 1; }
printf 'built %s and %s\n' "${sdist##*/}" "${wheel##*/}"
cp "$wheel" "$scratch/wheelhouse/"

say "Check package data in the wheel"
PYTHONPATH= "$shared_python" - "$scratch/source" "$wheel" <<'PY'
from pathlib import Path
import sys
from zipfile import ZipFile

source, wheel = Path(sys.argv[1]), Path(sys.argv[2])
suffixes = {".yaml", ".yml", ".json", ".jsonl", ".j2", ".jinja", ".jinja2",
            ".template", ".tmpl", ".txt"}
expected = {"opulse/" + str(path.relative_to(source / "src/opulse"))
            for path in (source / "src/opulse").rglob("*")
            if path.suffix in suffixes or path.name == "py.typed"
            or "templates" in path.relative_to(source / "src/opulse").parts}
with ZipFile(wheel) as archive:
    names = set(archive.namelist())
missing = expected - names
if missing:
    raise SystemExit("wheel omits package data: " + ", ".join(sorted(missing)))
if not expected:
    raise SystemExit("no source package data found")
print(f"checked {len(expected)} package data files")
PY

say "Install wheel and its runtime dependencies in a fresh virtualenv"
venv "$scratch/fresh-env"
install_pip "$scratch/fresh-env"
python="$scratch/fresh-env/bin/python"
"$python" -m pip install --no-index --find-links "$scratch/wheelhouse" "$wheel"
"$python" -m pip check

say "Install documentation and test extras separately"
"$python" -m pip install --no-index --find-links "$scratch/wheelhouse" 'opulse[docs]'
"$python" -m pip install --no-index --find-links "$scratch/wheelhouse" 'opulse[dev]'
"$python" -m pip check

say "Run installed package smoke checks outside the repository"
(
    cd "$scratch/run"
    unset PYTHONPATH VIRTUAL_ENV
    export PYTHONNOUSERSITE=1
    cli="$scratch/fresh-env/bin/opulse"
    "$cli" --help >/dev/null
    "$cli" operators --out operators.jsonl --layers 3 --proportions 1 0 0 --seed 7
    "$cli" expressions --operators operators.jsonl --out expressions.jsonl --count 3 --seed 3
    "$cli" holes --operators operators.jsonl --out holes.jsonl --count 1 --seed 3
    "$cli" verify --operators operators.jsonl --expressions expressions.jsonl --samples 3
    "$cli" bench build --operators operators.jsonl --out tasks.jsonl --count 2 \
        --max-definitions 2 --max-answer-share 1 --seed 3
    "$cli" bench check --operators operators.jsonl --tasks tasks.jsonl
    "$cli" bench run --tasks tasks.jsonl --out replies.jsonl --reference
    "$cli" bench score --tasks tasks.jsonl --responses replies.jsonl --out score.json > score.output
    printf '5 + 1\n7 + 1\n' > problems.txt
    printf '%s\n' '{"definition": "a ☆ = { a + 1 }"}' > proposals.jsonl
    "$cli" discover --operators operators.jsonl --problems problems.txt --script proposals.jsonl \
        --rounds 1 --record discovery.jsonl > discovery.json
    "$cli" interest --operators operators.jsonl --top 2 --json > interest.json
    "$python" - "$scratch/fresh-env" <<'PY'
import importlib
import importlib.resources
import importlib.util
import json
from pathlib import Path
import pkgutil
import sys

env = Path(sys.argv[1]).resolve()
import opulse
assert Path(opulse.__file__).resolve().is_relative_to(env), opulse.__file__
assert importlib.util.find_spec("torch") is None
assert importlib.util.find_spec("nnsight") is None
for module in pkgutil.iter_modules(opulse.__path__, "opulse."):
    if module.ispkg:
        importlib.import_module(module.name)
import opulse.playground
data = importlib.resources.files("opulse").joinpath("data/default.yaml")
assert data.is_file()
for filename, count in (("expressions.jsonl", 3), ("holes.jsonl", 1),
                        ("tasks.jsonl", 2), ("replies.jsonl", 2)):
    assert len(Path(filename).read_text().splitlines()) == count, filename
assert json.loads(Path("score.json").read_text())["accuracy"] == 1.0
assert json.loads(Path("discovery.json").read_text())["rounds"] == 1
assert json.loads(Path("interest.json").read_text())["summary"]["operators"] > 0
print("installed imports, data, score, discovery and interest passed")
PY
)
say "Fresh install check passed"
