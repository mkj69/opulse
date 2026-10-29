"""The files needed by an installed wheel remain in sync with source defaults."""

from importlib.resources import files
from pathlib import Path

from opulse.cli.operators import DEFAULT_CONFIG
from opulse.config import Settings
from opulse.core.starting_sets import starting_registry
from opulse.worlds import preset_config


def test_packaged_runtime_data_matches_source() -> None:
    root = Path(__file__).resolve().parents[1]
    packaged = files("opulse")
    for source in (root / "configs").glob("*.yaml"):
        assert source.read_bytes() == packaged.joinpath("data", source.name).read_bytes()
    for source in (root / "configs" / "presets").glob("*.yaml"):
        assert source.read_bytes() == packaged.joinpath("data", "presets", source.name).read_bytes()
    assert preset_config("logic").is_file()
    assert preset_config("rel").is_file()
    assert packaged.joinpath("py.typed").is_file()
    assert not packaged.joinpath("data/initial_operators.jsonl").is_file()
    assert not packaged.joinpath("data/atomic_operators.jsonl").is_file()
    assert Settings.load(DEFAULT_CONFIG) == Settings.load(packaged.joinpath("data/default.yaml"))
    assert len(starting_registry("integer")) == 25
    assert len(starting_registry("atomic")) == 21
