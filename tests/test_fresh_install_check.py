"""Opt-in integration test for installation from a built wheel."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


@pytest.mark.slow
@pytest.mark.skipif(os.environ.get("OPULSE_RUN_FRESH_INSTALL") != "1",
                    reason="set OPULSE_RUN_FRESH_INSTALL=1 to build and install in /tmp")
def test_fresh_install_check() -> None:
    script = Path(__file__).resolve().parents[1] / "tools/fresh_install_check.sh"
    subprocess.run(["bash", str(script)], cwd=script.parent.parent, check=True)
