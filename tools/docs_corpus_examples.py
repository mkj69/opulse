"""Regenerate the examples of docs/guide/corpora.md by running ``opulse corpus``.

    python tools/docs_corpus_examples.py

Writes Markdown fragments docs/snippets/corpus_*.md. Every text shown on the page comes
from these runs.
"""

from __future__ import annotations

import io
import json
import re
import shutil
import sys
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from opulse.cli.main import main as cli

SNIPPETS = ROOT / "docs" / "snippets"
WORK = ROOT / "outputs" / "docs_corpus"


def write(name: str, text: str) -> None:
    (SNIPPETS / name).write_text(text.rstrip() + "\n", encoding="utf-8")
    print("wrote", name)


def block(text: str, lang: str = "text") -> str:
    return f"```{lang}\n{text.rstrip()}\n```"


def run(argv: list[str]) -> str:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        assert cli(argv) == 0
    return buffer.getvalue()


def documents(directory: Path) -> list[str]:
    return [json.loads(line)["text"] for path in sorted(directory.glob("*.jsonl"))
            for line in path.read_text(encoding="utf-8").splitlines()]


def numbered_symbols(source: Path, target: Path) -> None:
    """Give the generated operators shape and subscript names for these examples."""
    rows = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines()]
    names = [row["symbol"] for row in rows if row["definition"] is not None]
    subscripts = "₀₁₂₃₄₅₆₇₈₉"
    aliases = {name: "◆" + subscripts[index // 10] + subscripts[index % 10]
               for index, name in enumerate(names, start=1)}
    pattern = re.compile("|".join(re.escape(name) for name in sorted(aliases, key=len, reverse=True)))
    for row in rows:
        row["symbol"] = aliases.get(row["symbol"], row["symbol"])
        if row["definition"] is not None:
            row["definition"] = pattern.sub(lambda match: aliases[match.group()], row["definition"])
    target.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def main() -> None:
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)
    raw_ops = WORK / "raw_operators.jsonl"
    ops = WORK / "operators.jsonl"
    run(["operators", "--out", str(raw_ops), "--layers", "20", "10", "6", "--seed", "3"])
    numbered_symbols(raw_ops, ops)

    corpus = WORK / "corpus"
    argv = ["corpus", "--operators", str(ops), "--out", str(corpus), "--documents", "train=200,test=50",
            "--split", "operator", "--split-ratios", "train=0.8,test=0.2",
            "--mix", "definitions=1,values=2,derivations=2", "--probe", "--seed", "1", "--workers", "2"]
    summary = run(argv)
    shown = ["opulse corpus --operators operators.jsonl --out corpus --documents train=200,test=50 \\",
             "  --split operator --split-ratios train=0.8,test=0.2 \\",
             "  --mix definitions=1,values=2,derivations=2 --probe --seed 1 --workers 2"]
    write("corpus_command.md", block("\n".join(shown)) + "\n\nprints\n\n" +
          block(summary.replace(str(corpus), "corpus"), "json"))

    tree = sorted(p.relative_to(corpus).as_posix() for p in corpus.rglob("*") if p.is_file())
    write("corpus_layout.md", block("\n".join(tree)))

    texts = documents(corpus / "train")
    definitions = [t for t in texts if " = {" in t.split("\n")[0]]
    values = [t for t in texts if t.split("\n")[0].count(" = ") == 1 and " = {" not in t and "\n= " not in t]
    write("corpus_definitions.md", block(definitions[0]))
    write("corpus_values.md", block(values[0]))

    manifest = json.loads((corpus / "manifest.json").read_text(encoding="utf-8"))
    test = manifest["splits"]["test"]
    excerpt = {"format": manifest["format"], "seed": manifest["seed"], "config_hash": manifest["config_hash"],
               "operator_sets": {"operators.jsonl": next(iter(manifest["operator_sets"].values()))},
               "splits": {"test": {key: test[key] for key in ("operators", "operators_mentioned", "documents",
                                                               "chars", "bytes", "tokens_estimate", "kinds")}
                          | {"shards": test["shards"], "mentions_of_other_splits": test["mentions_of_other_splits"]}},
               "totals": manifest["totals"]}
    write("corpus_manifest.md", block(json.dumps(excerpt, ensure_ascii=False, indent=2), "json"))

    probes = [json.loads(line) for line in (corpus / "probe" / "train-00000.jsonl").read_text(
        encoding="utf-8").splitlines()]
    probe = min((p for p in probes if 3 <= len(p["steps"]) <= 5 and any(s["kind"] == "expand" for s in p["steps"])),
                key=lambda p: (len(p["text"]), p["id"]))
    lines = [json.dumps({k: v for k, v in probe.items() if k != "steps"}, ensure_ascii=False)[:-1] + ', "steps": [']
    lines += ["  " + json.dumps(step, ensure_ascii=False) + "," for step in probe["steps"]]
    lines[-1] = lines[-1].rstrip(",")
    lines.append("]}")
    write("corpus_chain.md", block(probe["text"]))
    write("corpus_probe.md", block("\n".join(lines), "json"))
    rows = ["| step | span | text in the span | value |", "| --- | --- | --- | --- |"]
    for step in probe["steps"]:
        span = probe["text"][step["start"]:step["end"]]
        value = "NaN" if step["undefined"] else step["value"]
        rows.append(f"| {step['step']} | {step['start']}..{step['end']} | `{span}` | {value} |")
    write("corpus_probe_table.md", "\n".join(rows))

    narrated = WORK / "narrated"
    run(["corpus", "--operators", str(ops), "--out", str(narrated), "--documents", "40",
         "--mix", "derivations=1", "--derivation-style", "en", "--definitions", "prefix", "--seed", "2"])
    texts = documents(narrated / "train")
    write("corpus_narrated.md", block(min(texts, key=lambda t: (abs(t.count("\n\n") - 4), len(t)))))

    examples = WORK / "examples"
    run(["corpus", "--operators", str(ops), "--out", str(examples), "--documents", "40",
         "--mix", "values=1", "--definitions", "none", "--expressions-per-document", "4", "--seed", "3"])
    write("corpus_values_only.md", block(documents(examples / "train")[0]))


if __name__ == "__main__":
    main()
