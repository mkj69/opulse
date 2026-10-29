"""Markdown views of :mod:`opulse.api` objects (``_repr_markdown_``), for frontends without HTML."""

from __future__ import annotations


def _fence(text: str) -> str:
    return f"```opulse\n{text}\n```"


def _value(world, value) -> str:
    return world.settings.symbols.nan if value is None else str(value)


def world_markdown(world) -> str:
    summary = world.summary()
    lines = [f"**World**: {summary['operators']} operators over {summary['atoms']} atoms"
             + (f", seed {world.seed}" if world.seed is not None else ""), "",
             "| layer | simple | branch | recursive | total |", "|---|---:|---:|---:|---:|"]
    for layer, counts in summary["layers"].items():
        lines.append(f"| {layer} | {counts.get('simple', 0)} | {counts.get('branch', 0)} | "
                     f"{counts.get('recursive', 0)} | {sum(counts.values())} |")
    return "\n".join(lines)


def operator_markdown(op) -> str:
    head = f"**`{op.symbol}`** {op.kind}" + (f", layer {op.layer}" if op.definition else "") + f", {op.position}"
    body = _fence(op.definition) if op.definition else f"`{op.signature}`: {op.rule or 'an atomic operation'}"
    calls = ", ".join(f"`{c.symbol}`" for c in op.callees)
    return "\n\n".join(part for part in (head, body, f"calls {calls}" if calls else "") if part)


def expression_markdown(expr) -> str:
    if expr.variables:
        return _fence(expr.text)
    return _fence(f"{expr.text} = {_value(expr.world, expr.value)}")


def trace_markdown(trace) -> str:
    return _fence("\n= ".join(trace.lines()))


def task_markdown(task) -> str:
    core = task.core
    return f"**{core.family}** task `{core.id}`, answer `{core.answer_text}`\n\n```text\n{core.prompt}\n```"


def taskset_markdown(tasks) -> str:
    rows = ["| id | family | expression | answer |", "|---|---|---|---|"]
    rows += [f"| {t.core.id} | {t.core.family} | `{t.core.expression}` | {t.core.answer_text} |" for t in tasks]
    return "\n".join(rows)
