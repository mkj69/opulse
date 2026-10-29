"""Opulse: synthetic operators, definitions and expressions.

The high level Python interface lives in :mod:`opulse.api`; its classes are
importable from here (``opulse.World``) without loading the rest eagerly.
"""

__version__ = "0.2.0"

_API = ("World", "Op", "Expression", "Trace", "Task", "TaskSet", "Hole", "Graph", "make_settings")


def __getattr__(name: str):
    if name in _API:
        from opulse import api

        return getattr(api, name)
    raise AttributeError(f"module 'opulse' has no attribute {name!r}")


def __dir__():
    return sorted([*globals(), *_API])
