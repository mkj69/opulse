"""Seeded payloads stay byte-identical after removing release canary metadata.

``LEGACY`` hashes were computed with commit 97a69ad (before call-form operators, the primitive
recursion style and shape and index names). With ``operators.naming: legacy`` every file must
still match them: operator sets, expression records (including provenance and narrated
solutions in both languages) and benchmark tasks. ``SHAPE_INDEX`` pins the same run under the
default shape and index names.
"""

import hashlib
import json
from pathlib import Path

import pytest
import yaml
from conftest import ROOT

from opulse.canary import CANARY
from opulse.cli.main import main

LEGACY = {
    "ops": "ee6e2e9ebcc9eb11",
    "atomic": "cd588e73ddf2d2d6",
    "direct": "1b5612d267affb30",
    "expr_en": "456d45c4f19d1c8a",
    "expr_zh": "bd9cff9fdd3da8b9",
    "bench": "d934f89dd77b1ac1",
}


def _sha(path: Path) -> str:
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        assert row.pop("meta") == {"canary": CANARY}
        lines.append(json.dumps(row, ensure_ascii=False) + "\n")
    return hashlib.sha256("".join(lines).encode()).hexdigest()[:16]


SHAPE_INDEX = {
    "ops": "b6644fd1ae2d7eea",
    "atomic": "7a389fd4e16f5fd7",
    "direct": "fa9ffb7ce9ed29a3",
    "expr_en": "fe73060837842cef",
    "expr_zh": "10f4a77e72915584",
    "bench": "fb42a1c69dc51814",
}


def _config(tmp_path: Path, name: str, source: Path | None, naming: str) -> Path:
    raw = yaml.safe_load(source.read_text()) if source else {}
    raw = raw or {}
    raw.setdefault("operators", {})["naming"] = naming
    path = tmp_path / name
    path.write_text(yaml.safe_dump(raw, allow_unicode=True))
    return path


@pytest.mark.parametrize("naming", ["legacy", "shape_index"])
def test_default_generation_is_byte_identical(tmp_path, naming):
    default = _config(tmp_path, "default.yaml", ROOT / "configs/default.yaml", naming)
    atomic = _config(tmp_path, "atomic.yaml", ROOT / "configs/atomic.yaml", naming)
    direct = _config(tmp_path, "direct.yaml", None, naming)
    raw = yaml.safe_load(direct.read_text())
    raw["recursion"] = {"style": "direct", "direct_bound": 6}
    direct.write_text(yaml.safe_dump(raw, allow_unicode=True))
    got = {}
    assert main(["operators", "--config", str(default), "--out", str(tmp_path / "ops.jsonl"),
                 "--layers", "8", "6", "4", "--seed", "5"]) == 0
    got["ops"] = _sha(tmp_path / "ops.jsonl")
    assert main(["operators", "--config", str(atomic), "--set", "atomic",
                 "--out", str(tmp_path / "atomic.jsonl"),
                 "--layers", "6", "4", "3", "--seed", "2"]) == 0
    got["atomic"] = _sha(tmp_path / "atomic.jsonl")
    assert main(["operators", "--config", str(direct), "--out", str(tmp_path / "direct.jsonl"),
                 "--layers", "6", "4", "--seed", "11"]) == 0
    got["direct"] = _sha(tmp_path / "direct.jsonl")
    assert main(["expressions", "--operators", str(tmp_path / "ops.jsonl"), "--config", str(default),
                 "--out", str(tmp_path / "ex.jsonl"),
                 "--count", "25", "--seed", "1", "--cot", "en"]) == 0
    got["expr_en"] = _sha(tmp_path / "ex.jsonl")
    assert main(["expressions", "--operators", str(tmp_path / "atomic.jsonl"), "--config",
                 str(atomic), "--out", str(tmp_path / "exz.jsonl"), "--count", "15",
                 "--seed", "2", "--cot", "zh"]) == 0
    got["expr_zh"] = _sha(tmp_path / "exz.jsonl")
    assert main(["bench", "build", "--operators", str(tmp_path / "ops.jsonl"), "--config", str(default),
                 "--out", str(tmp_path / "b.jsonl"),
                 "--count", "8", "--seed", "3", "--format", "steps", "--naming", "pseudo"]) == 0
    got["bench"] = _sha(tmp_path / "b.jsonl")
    assert got == (LEGACY if naming == "legacy" else SHAPE_INDEX)
