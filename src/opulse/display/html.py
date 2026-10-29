"""HTML views of :mod:`opulse.api` objects for Jupyter (``_repr_html_``).

Only inline styles are used, so the views survive notebook sanitizers and
static renderers. Colours come from :mod:`opulse.display.theme`.
"""

from __future__ import annotations

from html import escape
from itertools import pairwise

from opulse.display.theme import MONO, SANS, TOKEN_STYLES, kind_colour
from opulse.display.tokens import DEFAULT_STYLE, TokenStyle, tokenize

FOCUS = "\x02", "\x03"  # brackets a highlighted span inside rendered text


# ----------------------------------------------------------------------------- building blocks
def highlight(text: str, style: TokenStyle = DEFAULT_STYLE, marks: list[tuple[int, int, str]] = ()) -> str:
    """Syntax coloured HTML for Opulse ``text``; ``marks`` wraps character ranges in styled spans."""
    out: list[str] = []
    bounds = sorted({b for start, end, _ in marks for b in (start, end)})
    for offset, kind, value in tokenize(text, style):
        css = TOKEN_STYLES.get(kind, "")
        pieces = [offset] + [b for b in bounds if offset < b < offset + len(value)] + [offset + len(value)]
        for start, end in pairwise(pieces):
            chunk = escape(text[start:end])
            if css:
                chunk = f'<span style="{css}">{chunk}</span>'
            out.append((start, chunk))
    html = []
    open_mark = None
    for start, chunk in out:
        mark = next(((s, e, css) for s, e, css in marks if s <= start < e), None)
        if mark != open_mark:
            if open_mark is not None:
                html.append("</span>")
            if mark is not None:
                html.append(f'<span style="{mark[2]}">')
            open_mark = mark
        html.append(chunk)
    if open_mark is not None:
        html.append("</span>")
    return "".join(html)


def highlight_marked(text: str, style: TokenStyle, css: str) -> str:
    """Like :func:`highlight`, for text whose focus is bracketed by the ``FOCUS`` characters."""
    marks = []
    plain = []
    start = None
    for char in text:
        if char == FOCUS[0]:
            start = len(plain)
        elif char == FOCUS[1] and start is not None:
            marks.append((start, len(plain), css))
            start = None
        else:
            plain.append(char)
    return highlight("".join(plain), style, marks)


def code(text: str, style: TokenStyle = DEFAULT_STYLE, block: bool = False) -> str:
    inner = highlight(text, style)
    if block:
        return (f'<pre style="{MONO};font-size:13px;margin:4px 0;padding:6px 8px;white-space:pre-wrap;'
                f'background:rgba(127,127,127,.08);border-radius:6px">{inner}</pre>')
    return f'<code style="{MONO};font-size:13px;background:none">{inner}</code>'


def badge(text: str, colour: str = "#94a3b8") -> str:
    return (f'<span style="display:inline-block;padding:0 7px;margin-right:4px;border-radius:9px;font-size:11px;'
            f'border:1px solid {colour};color:{colour};{SANS}">{escape(str(text))}</span>')


def chip(op) -> str:
    colour = kind_colour(op.kind)
    return (f'<span title="{escape(str(op))}" style="{MONO};display:inline-block;padding:0 6px;margin:1px 3px 1px 0;'
            f'border-radius:4px;border-left:3px solid {colour};background:rgba(127,127,127,.10)">'
            f'{escape(op.symbol)}</span>')


def box(inner: str) -> str:
    return (f'<div style="{SANS};font-size:13px;line-height:1.45;border:1px solid rgba(127,127,127,.3);'
            f'border-radius:8px;padding:10px 12px;margin:2px 0;max-width:100%;overflow-x:auto">{inner}</div>')


TABLE = 'style="border-collapse:collapse;font-size:12.5px;margin:6px 0"'
CELL = "padding:2px 10px;border-bottom:1px solid rgba(127,127,127,.2);text-align:right"
HEAD = "padding:2px 10px;border-bottom:1px solid rgba(127,127,127,.5);text-align:right;font-weight:600"


def _value(world, value) -> str:
    if value is None:
        return f'<span style="color:#f43f5e;opacity:.8">{escape(world.settings.symbols.nan)}</span>'
    return escape(str(value))


# ----------------------------------------------------------------------------- world
def world_html(world) -> str:
    summary = world.summary()
    kinds = ("simple", "branch", "recursive")
    head = "".join(f'<th style="{HEAD};color:{kind_colour(k)}">{k}</th>' for k in kinds)
    rows = [(f'<tr><td style="{CELL};text-align:left">atoms</td>'
            f'<td style="{CELL}" colspan="3"></td><td style="{CELL}">{summary["atoms"]}</td></tr>')]
    totals = dict.fromkeys(kinds, 0)
    for layer, counts in summary["layers"].items():
        cells = "".join(f'<td style="{CELL}">{counts.get(k, 0) or ""}</td>' for k in kinds)
        for k in kinds:
            totals[k] += counts.get(k, 0)
        rows.append(f'<tr><td style="{CELL};text-align:left">layer {layer}</td>{cells}'
                    f'<td style="{CELL}">{sum(counts.values())}</td></tr>')
    cells = "".join(f'<td style="{CELL};font-weight:600">{totals[k]}</td>' for k in kinds)
    rows.append(f'<tr><td style="{CELL};text-align:left;font-weight:600">all layers</td>{cells}'
                f'<td style="{CELL};font-weight:600">{summary["operators"]}</td></tr>')
    table = (f'<table {TABLE}><tr><th style="{HEAD};text-align:left"></th>{head}'
             f'<th style="{HEAD}">total</th></tr>{"".join(rows)}</table>')
    title = (f'<div style="font-size:15px;font-weight:600">World '
             f'<span style="font-weight:400;opacity:.75">{summary["operators"]} operators over '
             f'{summary["atoms"]} atoms')
    if world.seed is not None:
        title += f", seed {world.seed}"
    if world.atoms_label:
        title += f", atoms {escape(str(world.atoms_label))}"
    title += "</span></div>"
    style = world.token_style
    atoms = " ".join(chip(op) for op in world.atoms)
    sections = []
    for layer in range(world.layer_count):
        ops = world.layer(layer)
        shown = ops[:60]
        lines = "".join(f'<div style="border-left:3px solid {kind_colour(op.kind)};padding-left:8px;margin:2px 0">'
                        f'{code(op.definition, style)}</div>' for op in shown)
        more = f'<div style="opacity:.7">and {len(ops) - len(shown)} more</div>' if len(ops) > len(shown) else ""
        sections.append(f'<details style="margin:2px 0"><summary>layer {layer}: {len(ops)} operators</summary>'
                        f'{lines}{more}</details>')
    return box(title + table + f'<div style="margin:4px 0">atoms: {atoms}</div>' + "".join(sections))


# ----------------------------------------------------------------------------- operators
def operator_html(op) -> str:
    world = op.world
    colour = kind_colour(op.kind)
    header = (f'<div style="margin-bottom:4px"><span style="{MONO};font-size:20px;font-weight:700;color:{colour};'
              f'margin-right:10px">{escape(op.symbol)}</span>{badge(op.kind, colour)}'
              f'{badge("layer " + str(op.layer)) if op.kind not in ("atom", "marker") else ""}'
              f'{badge(op.position)}'
              f'{badge("priority " + str(op.priority)) if op.priority is not None else ""}</div>')
    if op.definition:
        body = code(op.definition, world.token_style, block=True)
    elif op.kind == "marker":
        body = f'<div>numeral base marker for base {op.record.is_base}</div>'
    else:
        body = f'<div>{code(op.signature, world.token_style)}: {escape(op.rule or "an atomic operation")}</div>'
    parts = [header, body]
    if op.callees:
        parts.append(f'<div style="margin:4px 0">calls {"".join(chip(c) for c in op.callees)}'
                     + (" and itself" if op.is_recursive else "") + "</div>")
    if op.kind != "marker":
        try:
            parts.append(value_table_html(op.table(), compact=True))
        except Exception as exc:  # noqa: BLE001 - a view must never fail
            parts.append(f'<div style="opacity:.7">no value table: {escape(str(exc))}</div>')
    return box("".join(parts))


def value_table_html(table, compact: bool = False) -> str:
    op, world = table.op, table.op.world
    if op.arity == 1:
        head = "".join(f'<th style="{HEAD}">{a}</th>' for a in table.rows)
        cells = "".join(f'<td style="{CELL}">{_value(world, v)}</td>' for v in table.rows.values())
        label = escape(op.record.apply_str(world.settings.symbols.left_operand))
        html = (f'<table {TABLE}><tr><th style="{HEAD};text-align:left">a</th>{head}</tr>'
                f'<tr><td style="{CELL};text-align:left;{MONO}">{label}</td>{cells}</tr></table>')
    else:
        head = "".join(f'<th style="{HEAD}">{b}</th>' for b in table.values)
        body = "".join(f'<tr><th style="{HEAD}">{a}</th>'
                       + "".join(f'<td style="{CELL}">{_value(world, v)}</td>' for v in row.values()) + "</tr>"
                       for a, row in table.rows.items())
        html = f'<table {TABLE}><tr><th style="{HEAD}">a \\ b</th>{head}</tr>{body}</table>'
    return html if compact else box(html)


# ----------------------------------------------------------------------------- expressions and traces
class _MarkingRenderer:
    """Renders an expression with one subtree (found by identity) bracketed by ``FOCUS``."""

    def __init__(self, renderer, focus) -> None:
        self.renderer = renderer
        self.focus = focus

    def minimal(self, node) -> str:
        base = self.renderer
        focus = self.focus
        original = base._render

        def render(node, *args, **kwargs):
            text = original(node, *args, **kwargs)
            return f"{FOCUS[0]}{text}{FOCUS[1]}" if node is focus else text

        base._render = render
        try:
            return base.minimal(node)
        finally:
            del base._render


def _marked(world, node, focus) -> str:
    try:
        return _MarkingRenderer(world.renderer, focus).minimal(node)
    except Exception:  # noqa: BLE001 - fall back to plain text
        return world.renderer.minimal(node)


def expression_html(expr) -> str:
    world = expr.world
    style = world.token_style
    parts = [code(expr.text, style)]
    if not expr.variables:
        parts.append(f' <span style="opacity:.7">=</span> <b>{_value(world, expr.value)}</b>')
    ops = [op for op in expr.operators if op.kind != "atom"]
    if ops:
        parts.append(f'<div style="margin-top:4px;font-size:12px">uses {"".join(chip(op) for op in ops)}</div>')
    return box("".join(parts))


def _step_rule(world, step) -> str:
    op = step.operator
    nan = world.settings.symbols.nan
    show = lambda v: nan if v is None or v.__class__.__name__ == "_Undefined" else str(v)
    applied = op.apply_str(*(show(v) if (v is None or isinstance(v, int) and v >= 0) else f"({show(v)})"
                             for v in step.inputs))
    style = world.token_style
    colour = kind_colour(world._view(op).kind)
    if step.kind == "expand":
        branch = f"branch {step.branch_index + 1}" if step.branch_index is not None else ""
        why = f", since {code(step.condition, style)}" if step.condition else ""
        return (f'<span style="color:{colour};font-weight:600">unfold</span> {code(applied, style)} '
                f'<span style="opacity:.7">{branch}</span>{why}')
    if step.kind == "eval":
        return (f'<span style="opacity:.8;font-weight:600">compute</span> {code(applied, style)} = '
                f'{_value(world, None if step.output is None else step.output)}')
    return (f'<span style="color:#f43f5e;font-weight:600">undefined</span> {code(applied, style)} '
            f'<span style="opacity:.7">({escape(str(step.reason))})</span>')


def trace_html(trace, head: int = 40, tail: int = 10) -> str:
    world = trace.world
    style = world.token_style
    steps = trace.steps
    rows = []
    indices = list(range(len(steps)))
    if len(steps) > head + tail:
        indices = indices[:head] + [None] + indices[-tail:]
    for index in indices:
        if index is None:
            rows.append(f'<tr><td style="{CELL}"></td><td style="{CELL};text-align:left;opacity:.7" colspan="2">'
                        f'{len(steps) - head - tail} more steps</td></tr>')
            continue
        step = steps[index]
        colour = kind_colour(world._view(step.operator).kind)
        css = f"background:color-mix(in srgb,{colour} 22%,transparent);border-radius:3px;outline:1px solid {colour}"
        before = highlight_marked(_marked(world, step.expression_before, step.before), style, css)
        rows.append(f'<tr><td style="{CELL};opacity:.6">{index + 1}</td>'
                    f'<td style="{CELL};text-align:left;{MONO}">{before}</td>'
                    f'<td style="{CELL};text-align:left">{_step_rule(world, step)}</td></tr>')
    result = "truncated" if trace.truncated else _value(world, trace.value)
    rows.append(f'<tr><td style="{CELL}"></td><td style="{CELL};text-align:left;{MONO}" colspan="2">'
                f'= <b>{result}</b></td></tr>')
    title = (f'<div style="font-weight:600;margin-bottom:2px">Trace '
             f'<span style="font-weight:400;opacity:.75">{len(steps)} steps</span></div>')
    return box(title + f'<table {TABLE}>{"".join(rows)}</table>')


# ----------------------------------------------------------------------------- tasks and holes
def task_html(task) -> str:
    world = task.world
    style = world.token_style
    core = task.core
    header = (f'<div style="margin-bottom:4px">{badge(core.family, "#06b6d4")}{badge("context " + core.context)}'
              f'{badge(core.format)}<span style="opacity:.6;font-size:12px">{escape(str(core.id))}</span></div>')
    defs = "".join(f'<div>{code(d, style)}</div>' for d in core.definitions) or '<div style="opacity:.7">none</div>'
    question = (f'<div style="margin-top:6px"><b>expression</b> {code(core.expression, style)}'
                f' <span style="opacity:.7">answer</span> <b>{escape(core.answer_text)}</b></div>')
    prompt = (f'<details style="margin-top:4px"><summary>prompt</summary><pre style="{MONO};font-size:12px;'
              f'white-space:pre-wrap">{escape(core.prompt)}</pre></details>')
    return box(header + f"<div><b>definitions</b>{defs}</div>" + question + prompt)


def taskset_html(tasks, limit: int = 20) -> str:
    world = tasks.world
    style = world.token_style
    rows = "".join(f'<tr><td style="{CELL};opacity:.6">{escape(str(t.core.id))}</td>'
                   f'<td style="{CELL}">{escape(t.core.family)}</td>'
                   f'<td style="{CELL};text-align:left">{code(t.core.expression, style)}</td>'
                   f'<td style="{CELL}">{len(t.core.definitions)}</td>'
                   f'<td style="{CELL};font-weight:600">{escape(t.core.answer_text)}</td></tr>'
                   for t in list(tasks)[:limit])
    more = f'<div style="opacity:.7">and {len(tasks) - limit} more</div>' if len(tasks) > limit else ""
    head = "".join(f'<th style="{HEAD}">{h}</th>' for h in ("id", "family", "expression", "definitions", "answer"))
    return box(f'<div style="font-weight:600">{len(tasks)} tasks</div><table {TABLE}><tr>{head}</tr>{rows}</table>'
               + more)


def hole_html(hole) -> str:
    world = hole.world
    sols = ", ".join(str(v) for v in hole.solutions[:12]) + (f", … ({len(hole.solutions)} values)" if len(hole.solutions) > 12 else "")
    status = "unique" if hole.unique else ("complete" if hole.complete else "incomplete")
    return box(f'{code(hole.text, world.token_style)}<div style="margin-top:4px">x ∈ {{{escape(sols)}}} '
               f'{badge(status, "#06b6d4" if hole.unique else "#94a3b8")}'
               f'<span style="opacity:.7">removed number {hole.answer}</span></div>')
