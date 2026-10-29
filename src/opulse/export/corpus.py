"""Convert Opulse JSONL records into documents with a single text field."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from opulse.canary import marked


def record_text(record: dict, fields: tuple[str, ...] = ()) -> str:
    """Select explicit fields, or the usual text in an expression or task record."""
    if fields:
        values = [record[field] for field in fields]
    elif isinstance(record.get("text"), str):
        values = [record["text"]]
    elif isinstance(record.get("prompt"), str):
        values = [record["prompt"], f"Answer: {record['answer_text']}"]
    elif isinstance(record.get("expression"), str):
        values = [f"{record['expression']} = {record['result_text']}"]
        if isinstance(record.get("cot"), str):
            values.append(record["cot"])
    elif isinstance(record.get("definition"), str):
        values = [record["definition"]]
    else:
        raise ValueError("record has no supported text field; pass --fields")
    if not all(isinstance(value, str) for value in values):
        raise ValueError("selected fields must contain strings")
    return "\n".join(values)


def iter_text(paths: list[Path], fields: tuple[str, ...] = ()) -> Iterator[str]:
    for path in paths:
        with path.open(encoding="utf-8") as source:
            for line_number, line in enumerate(source, 1):
                if not line.strip():
                    continue
                try:
                    yield record_text(json.loads(line), fields)
                except (KeyError, ValueError, TypeError) as exc:
                    raise ValueError(f"{path}:{line_number}: {exc}") from exc


def export_megatron(paths: list[Path], output: Path, fields: tuple[str, ...] = ()) -> int:
    if any(path.resolve() == output.resolve() for path in paths):
        raise ValueError("output must differ from every input file")
    output.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output.open("w", encoding="utf-8") as sink:
        for value in iter_text(paths, fields):
            sink.write(json.dumps(marked({"text": value}), ensure_ascii=False) + "\n")
            count += 1
    return count
