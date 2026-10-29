"""Elapsed time may stop a build, but cannot select its output."""

import time

import pytest

from opulse.cli.main import main
from opulse.solver import isolated


def test_operator_build_matches_when_solver_reply_is_delayed(tmp_path, monkeypatch):
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    args = ["operators", "--layers", "5", "3", "--seed", "5"]
    assert main([*args, "--out", str(first)]) == 0

    original = isolated._readline
    calls = 0

    def slow_reply(process, seconds):
        nonlocal calls
        calls += 1
        time.sleep(0.01)
        return original(process, seconds)

    monkeypatch.setattr(isolated, "_readline", slow_reply)
    assert main([*args, "--out", str(second)]) == 0
    assert calls > 0
    assert first.read_bytes() == second.read_bytes()


def test_solver_watchdog_raises_instead_of_returning_unknown(monkeypatch):
    import z3

    monkeypatch.setattr(isolated, "_readline", lambda process, seconds: None)
    with pytest.raises(TimeoutError, match="z3 safety timeout"):
        isolated.check([z3.BoolVal(True)], 1_000, rlimit=100)
