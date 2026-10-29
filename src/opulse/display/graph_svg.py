"""Draw a dependency graph as inline SVG, with no layout library.

Columns are dependency depth: atoms and operators that call nothing drawn sit
in column 0, and every operator sits one column right of its deepest callee.
Inside a column, operators are ordered by the mean row of their callees, which
keeps most edges short. Edges run from a caller (right) to a callee (left);
a recursive operator also gets a loop. Node colours follow the docs theme.
"""

from __future__ import annotations

import itertools
from html import escape

from opulse.display.theme import KIND_COLOURS, MONO, SANS, kind_colour

COLUMN_GAP, ROW_GAP, NODE_HEIGHT, MARGIN, LEGEND = 70, 10, 24, 16, 26
_ids = itertools.count()


def _width(symbol: str) -> int:
    return max(40, 10 * len(symbol) + 18)


def layout(ops, edges) -> tuple[dict[str, int], list[list]]:
    """(depth of each func_id, ops per column in drawing order)."""
    ids = {op.func_id for op in ops}
    callees = {op.func_id: [c.func_id for c in op.callees if c.func_id in ids] for op in ops}
    depth: dict[str, int] = {}

    def visit(fid: str, stack: frozenset = frozenset()) -> int:
        if fid in depth:
            return depth[fid]
        if fid in stack:  # not expected: dependencies are acyclic apart from self calls
            return 0
        depth[fid] = 1 + max((visit(c, stack | {fid}) for c in callees[fid]), default=-1)
        return depth[fid]

    for op in ops:
        visit(op.func_id)
    columns: list[list] = [[] for _ in range(1 + max(depth.values(), default=0))]
    for op in ops:
        columns[depth[op.func_id]].append(op)
    rows: dict[str, float] = {}
    for column in columns:
        order = {op.func_id: i for i, op in enumerate(column)}

        def key(op, order=order):
            placed = [rows[c] for c in callees[op.func_id] if c in rows]
            return (sum(placed) / len(placed) if placed else order[op.func_id], order[op.func_id])

        column.sort(key=key)
        for row, op in enumerate(column):
            rows[op.func_id] = row
    return depth, columns


def graph_svg(graph) -> str:
    ops, edges = graph.ops, graph.edges
    uid = f"opg{next(_ids)}"
    _, columns = layout(ops, edges)
    widths = [max((_width(op.symbol) for op in column), default=40) for column in columns]
    xs = [MARGIN + sum(widths[:i]) + COLUMN_GAP * i for i in range(len(columns))]
    pos: dict[str, tuple[float, float, float]] = {}  # func_id -> (x, y, width)
    for i, column in enumerate(columns):
        for row, op in enumerate(column):
            w = _width(op.symbol)
            pos[op.func_id] = (xs[i] + (widths[i] - w) / 2, MARGIN + LEGEND + row * (NODE_HEIGHT + ROW_GAP), w)
    width = (xs[-1] + widths[-1] + MARGIN) if columns else 2 * MARGIN
    height = MARGIN * 2 + LEGEND + max((len(c) for c in columns), default=0) * (NODE_HEIGHT + ROW_GAP) + 10
    width = max(width, 400)

    parts = [(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" '
             f'viewBox="0 0 {width:.0f} {height:.0f}" style="{SANS};font-size:12px;color:inherit" role="img">'),
             f'<title>Operator dependency graph: {len(ops)} operators</title>',
             (f'<defs><marker id="{uid}-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" '
             f'markerHeight="7" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#94a3b8"/></marker></defs>')]
    x = MARGIN
    for kind in ("simple", "branch", "recursive", "atom"):
        colour = KIND_COLOURS[kind]
        parts.append(f'<rect x="{x}" y="{MARGIN - 9}" width="12" height="12" rx="3" fill="{colour}" '
                     f'fill-opacity="0.25" stroke="{colour}"/>'
                     f'<text x="{x + 17}" y="{MARGIN + 1}" fill="currentColor">{kind}</text>')
        x += 30 + 7 * len(kind) + 12
    for caller, callee in edges:
        if caller.func_id == callee.func_id:
            cx, cy, w = pos[caller.func_id]
            colour = KIND_COLOURS["recursive"]
            parts.append(f'<path d="M{cx + w * 0.3:.1f},{cy:.1f} C{cx + w * 0.3:.1f},{cy - 14:.1f} '
                         f'{cx + w * 0.7:.1f},{cy - 14:.1f} {cx + w * 0.7:.1f},{cy:.1f}" fill="none" '
                         f'stroke="{colour}" stroke-width="1.3" marker-end="url(#{uid}-arrow)"/>')
            continue
        sx, sy, _ = pos[caller.func_id]
        tx, ty, tw = pos[callee.func_id]
        sy, ty = sy + NODE_HEIGHT / 2, ty + NODE_HEIGHT / 2
        tx += tw
        mid = (sx + tx) / 2
        parts.append(f'<path d="M{sx:.1f},{sy:.1f} C{mid:.1f},{sy:.1f} {mid:.1f},{ty:.1f} {tx + 1:.1f},{ty:.1f}" '
                     f'fill="none" stroke="#94a3b8" stroke-opacity="0.55" stroke-width="1" '
                     f'marker-end="url(#{uid}-arrow)"/>')
    for op in ops:
        x, y, w = pos[op.func_id]
        colour = kind_colour(op.kind)
        tip = escape(op.definition or f"{op.signature} ({op.kind})")
        if op.definition:
            tip += escape(f"\n{op.kind}, layer {op.layer}")
        parts.append(f'<g><title>{tip}</title><rect x="{x:.1f}" y="{y:.1f}" width="{w}" height="{NODE_HEIGHT}" '
                     f'rx="6" fill="{colour}" fill-opacity="0.18" stroke="{colour}" stroke-width="1.4"/>'
                     f'<text x="{x + w / 2:.1f}" y="{y + NODE_HEIGHT / 2 + 4.5:.1f}" text-anchor="middle" '
                     f'fill="currentColor" style="{MONO};font-size:13px">{escape(op.symbol)}</text></g>')
    parts.append("</svg>")
    return "".join(parts)
