"""Colours shared by the notebook views and the dependency graph.

They follow the documentation theme (docs/assets/css/custom.css): cyan for
composition (simple definitions), amber for branching, magenta for recursion.
The shades are mid tones, readable on light and dark notebook backgrounds.
"""

from __future__ import annotations

KIND_COLOURS = {
    "simple": "#06b6d4",  # cyan: composition
    "branch": "#f59e0b",  # amber: branching
    "recursive": "#d946ef",  # magenta: recursion
    "atom": "#94a3b8",  # slate: atomic operations
    "marker": "#94a3b8",
}

TOKEN_STYLES = {
    "keyword": "color:#f59e0b;font-weight:600",
    "constant": "color:#f43f5e",
    "number": "color:#818cf8",
    "comparison": "color:#f59e0b",
    "equals": "opacity:.75",
    "punctuation": "opacity:.6",
    "parameter": "font-style:italic",
    "operator": "color:#06b6d4;font-weight:600",
    "base": "font-weight:600",
    "name": "",
    "whitespace": "",
    "text": "",
}

MONO = "font-family:'JetBrains Mono',ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"
SANS = "font-family:Inter,system-ui,-apple-system,'Segoe UI',sans-serif"


def kind_colour(kind: str) -> str:
    return KIND_COLOURS.get(kind, KIND_COLOURS["atom"])
