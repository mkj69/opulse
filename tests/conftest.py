import os
import tempfile
from pathlib import Path

import pytest

from opulse.core import OperatorRegistry
from opulse.core.starting_sets import export_starting_set

ROOT = Path(__file__).resolve().parents[1]
requires_zh_site = pytest.mark.skipif(
    not (ROOT / "docs_zh").is_dir(), reason="Chinese site docs_zh/ is absent from the public export"
)
_starting_dir = tempfile.TemporaryDirectory(prefix="opulse-test-atoms-")
INITIAL_OPERATORS = Path(_starting_dir.name) / "initial_operators.jsonl"
export_starting_set("integer", INITIAL_OPERATORS)
export_starting_set("atomic", INITIAL_OPERATORS.parent / "atomic_operators.jsonl")
LEGACY_OPERATORS_1K = Path(os.environ["OPULSE_LEGACY_OPERATORS_1K"]) if "OPULSE_LEGACY_OPERATORS_1K" in os.environ else None


@pytest.fixture
def registry() -> OperatorRegistry:
    return OperatorRegistry.from_jsonl(INITIAL_OPERATORS)


@pytest.fixture(scope="session")
def operators(tmp_path_factory) -> Path:
    """A small generated operator set (three layers), built once per test session."""
    from opulse.cli.main import main

    path = tmp_path_factory.mktemp("operators") / "ops.jsonl"
    assert main(["operators", "--out", str(path), "--layers", "20", "10", "6", "--seed", "3"]) == 0
    return path
