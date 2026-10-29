"""The isolated z3 worker returns models and serializes solver errors."""

import io
import json
import sys

import z3

from opulse.solver import isolated


def test_worker_protocol_returns_model_and_error(monkeypatch):
    x = z3.Int("x")
    solver = z3.Solver()
    solver.add(x == 7)
    requests = [
        {"smt2": solver.to_smt2(), "timeout_ms": 1000, "rlimit": 10000, "variables": ["x"]},
        {"smt2": "(", "timeout_ms": 1000, "rlimit": None, "variables": []},
    ]
    stdin = io.StringIO("".join(json.dumps(request) + "\n" for request in requests))
    stdout = io.StringIO()
    monkeypatch.setattr(sys, "stdin", stdin)
    monkeypatch.setattr(sys, "stdout", stdout)

    isolated._serve()

    ready, *lines = stdout.getvalue().splitlines()
    assert ready == "ready"  # written once, before the first query
    answers = [json.loads(line) for line in lines]
    assert answers[0] == {"status": "sat", "model": {"x": 7}}
    assert answers[1]["status"] == "error"
    assert "error" in answers[1]
