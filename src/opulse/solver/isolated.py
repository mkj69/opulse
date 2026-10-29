"""Solve z3 queries in a worker process that can be killed.

z3 does not always honour its own ``timeout`` or ``rlimit``: on some nonlinear
integer problems a single ``check()`` runs for minutes and cannot be
interrupted from Python. :func:`check` sends the assertions (as SMT-LIB) to a
long-lived worker process (``python -m opulse.solver.isolated``) and waits at
most ``timeout_ms`` plus a grace period; if the worker does not answer in
time it is killed and a clear error is raised.

The worker applies ``rlimit`` to decide when to return ``unknown``. The wall
clock only guards against a solver that ignores its resource limit.
"""

from __future__ import annotations

import json
import selectors
import subprocess
import sys
import threading

import z3

GRACE_S = 1.0
STARTUP_S = 120.0  # the worker imports z3 before it can answer; this wait is not part of a query

_lock = threading.Lock()
_worker: subprocess.Popen | None = None


def _start() -> subprocess.Popen:
    """A worker that has finished importing z3, so its start-up time never counts against the
    timeout of a query (which would turn the first answer of a process into "unknown")."""
    process = subprocess.Popen([sys.executable, "-m", "opulse.solver.isolated"], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, text=True, bufsize=1)
    if _readline(process, STARTUP_S) != "ready\n":
        process.kill()
        process.wait()
        raise RuntimeError("the z3 worker process did not start")
    return process


def _readline(process: subprocess.Popen, seconds: float) -> str | None:
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ)
        if not selector.select(seconds):
            return None
    return process.stdout.readline() or None


def restart() -> None:
    """Stop the worker; the next query starts a fresh one.

    z3 answers under ``rlimit`` can depend on the queries a process solved before, so a run
    that must be reproducible (one operator generation) starts from a fresh worker."""
    global _worker
    with _lock:
        if _worker is not None and _worker.poll() is None:
            _worker.stdin.close()
            _worker.kill()
            _worker.wait()
        _worker = None


def check(assertions: list, timeout_ms: int, rlimit: int | None = None,
          variables: list[str] | None = None) -> tuple[str, dict[str, int]]:
    """``("sat" | "unsat" | "unknown", model)``; the model holds the integer ``variables``."""
    if timeout_ms <= 0 or (rlimit is not None and rlimit <= 0):
        raise ValueError("z3 safety timeout and resource limit must be positive")
    global _worker
    # Serialize from a fresh context: the SMT-LIB text (its let names and their order) would
    # otherwise depend on every term the calling process built before, and so would the answer.
    context = z3.Context()
    solver = z3.Solver(ctx=context)
    solver.add(*(assertion.translate(context) for assertion in assertions))
    request = json.dumps({"smt2": solver.to_smt2(), "timeout_ms": timeout_ms, "rlimit": rlimit,
                          "variables": variables or []})
    with _lock:
        if _worker is None or _worker.poll() is not None:
            _worker = _start()
        try:
            _worker.stdin.write(request + "\n")
            _worker.stdin.flush()
            line = _readline(_worker, timeout_ms / 1000 + GRACE_S)
        except (BrokenPipeError, OSError):
            line = None
        if line is not None:
            answer = json.loads(line)
            if answer["status"] == "error":
                raise RuntimeError(f"z3 worker failed: {answer['error']}")
            return answer["status"], answer["model"]
        _worker.kill()
        _worker.wait()
        _worker = None
        raise TimeoutError(f"z3 safety timeout after {timeout_ms} ms; no verdict was recorded")


def _serve() -> None:
    sys.stdout.write("ready\n")
    sys.stdout.flush()
    for line in sys.stdin:
        request = json.loads(line)
        try:
            # A fresh context per query: z3 counts rlimit over the life of a context, so a shared
            # context would make answers depend on the queries the worker saw before.
            context = z3.Context()
            solver = z3.Solver(ctx=context)
            solver.set("timeout", int(request["timeout_ms"]))
            if request["rlimit"]:
                solver.set("rlimit", int(request["rlimit"]))
            solver.add(z3.parse_smt2_string(request["smt2"], ctx=context))
            result = solver.check()
            status = "sat" if result == z3.sat else "unsat" if result == z3.unsat else "unknown"
            model = {}
            if status == "sat":
                m = solver.model()
                model = {name: m.eval(z3.Int(name, context), model_completion=True).as_long()
                         for name in request["variables"]}
            answer = {"status": status, "model": model}
        except Exception as exc:  # noqa: BLE001 - report, never crash the worker
            answer = {"status": "error", "error": repr(exc)}
        sys.stdout.write(json.dumps(answer) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    _serve()
