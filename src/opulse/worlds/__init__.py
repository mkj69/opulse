"""Exportable Opulse worlds and their website showcases."""

from pathlib import Path


def preset_config(name: str) -> Path:
    """Use an editable checkout preset, or its bundled wheel counterpart."""
    package = Path(__file__).resolve().parents[1]
    checkout = package.parents[1] / "configs" / "presets" / f"{name}.yaml"
    return checkout if checkout.is_file() else package / "data" / "presets" / f"{name}.yaml"
