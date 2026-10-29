import pytest
from conftest import ROOT

from opulse.config import Settings

LEGACY_CONFIG = ROOT / "tests" / "fixtures" / "legacy_config.yaml"


def test_default_yaml_matches_dataclass_defaults():
    assert Settings.load(ROOT / "configs" / "default.yaml") == Settings()


def test_legacy_flat_config_is_translated():
    settings = Settings.load(LEGACY_CONFIG)
    assert settings.symbols.left_operand == "a"
    assert settings.operators.max_if_branches == 10
    assert settings.expressions.variables == ("a", "b")
    assert settings.expressions.type_weights["atom"] == 0.1
    assert settings.expressions.cot_base == 10


def test_unknown_keys_are_rejected():
    with pytest.raises(ValueError):
        Settings.from_dict({"operators": {"max_branches": 3}})
    with pytest.raises(ValueError):
        Settings.from_dict({"operatorz": {}})
