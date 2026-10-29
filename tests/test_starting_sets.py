"""The generated built-in sets preserve the historical JSONL bytes."""

import hashlib

import pytest

from opulse.cli.main import main
from opulse.core.registry import OperatorRegistry
from opulse.core.starting_sets import starting_jsonl, starting_registry


@pytest.mark.parametrize("name,digest,count", [
    ("integer", "fc07f6fae6cfc0434f3ba18f5789655ebf225a003ab83e7af068351fd760676a", 25),
    ("atomic", "a9b9b1a7563b8627750e785e93265ec297d93d5a1d04e2d882830c28cbcf35c8", 21),
])
def test_starting_set_bytes_and_export(tmp_path, name, digest, count):
    data = starting_jsonl(name).encode("utf-8")
    assert hashlib.sha256(data).hexdigest() == digest
    assert len(starting_registry(name)) == count
    output = tmp_path / "atoms.jsonl"
    assert main(["atoms", "export", "--set", name, "--out", str(output)]) == 0
    assert output.read_bytes() == data
    loaded = OperatorRegistry.from_jsonl(output)
    assert [op.to_dict() for op in loaded] == [op.to_dict() for op in starting_registry(name)]


def test_initial_path_still_overrides_built_in_set(tmp_path):
    initial = tmp_path / "atoms.jsonl"
    assert main(["atoms", "export", "--set", "atomic", "--out", str(initial)]) == 0
    output = tmp_path / "operators.jsonl"
    assert main(["operators", "--config", "configs/atomic.yaml", "--initial", str(initial),
                 "--out", str(output),
                 "--layers", "0"]) == 0
    assert [op.func_id for op in OperatorRegistry.from_jsonl(output)] == [
        op.func_id for op in starting_registry("atomic")]


def test_atomic_set_selects_its_recursion_config(tmp_path):
    output = tmp_path / "atomic.jsonl"
    assert main(["operators", "--set", "atomic", "--out", str(output), "--layers", "0"]) == 0
    assert [op.func_id for op in OperatorRegistry.from_jsonl(output)] == [
        op.func_id for op in starting_registry("atomic")]
