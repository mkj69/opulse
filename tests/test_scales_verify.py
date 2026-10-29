"""Focused smoke tests for the independent published scale-data checker."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from opulse.expression.nodes import Call, Number
from tools.check_scales import Mismatch, check_text, registry_for

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools/check_scales.py"


def run_checker(*args: str) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    result = subprocess.run([sys.executable, str(CHECKER), *args], cwd=ROOT,
                            env=env, text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "FAIL" not in result.stdout, result.stdout


def test_small_published_scales() -> None:
    run_checker("--only", "s10", "s100")


def test_rewrite_text_uses_published_precedence_and_associativity() -> None:
    path = ROOT / "docs/assets/data/scales/s10/int10-simple.json"
    main = json.loads(path.read_text(encoding="utf-8"))
    operators, parser, _, renderer = registry_for(main, path.parents[1])
    plus = next(op for op in operators if op.symbol == "+" and op.n_ary == 2)
    modulo = next(op for op in operators if op.symbol == "%" and op.n_ary == 2)
    precedence_tree = Call(plus, (Number(1), Call(modulo, (Number(2), Number(3)))))
    check_text("1 + 2 % 3", precedence_tree, parser, renderer, "precedence", "rewrite")
    with pytest.raises(Mismatch, match="precedence"):
        check_text("(1 + 2) % 3", precedence_tree, parser, renderer, "precedence", "rewrite")

    right_tree = Call(plus, (Number(1), Call(plus, (Number(2), Number(3)))))
    check_text("1 + 2 + 3", right_tree, parser, renderer, "associativity", "rewrite")
    with pytest.raises(Mismatch, match="associativity"):
        check_text("(1 + 2) + 3", right_tree, parser, renderer, "associativity", "rewrite")


@pytest.mark.slow
@pytest.mark.skipif(os.getenv("OPULSE_CHECK_SCALES_ALL") != "1",
                    reason="set OPULSE_CHECK_SCALES_ALL=1 to check every published scale")
def test_all_published_scales() -> None:
    run_checker()
