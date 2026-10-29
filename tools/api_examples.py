"""Run the examples of docs/guide/python-api.md and write their code and output as snippets.

    PYTHONPATH=src python tools/api_examples.py

Every ``docs/snippets/api_*.md`` file holds one example: the code, then the output it printed.
``docs/snippets/api_view_*.html`` hold the notebook views (``_repr_html_``) of the same objects.
"""

from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
SNIPPETS = ROOT / "docs" / "snippets"

import opulse


def run(name: str, code: str, namespace: dict) -> None:
    code = textwrap.dedent(code).strip()
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        exec(compile(code, name, "exec"), namespace)  # noqa: S102 - running the documented examples
    text = f"```python\n{code}\n```\n"
    if out.getvalue().strip():
        text += f"\n```text\n{out.getvalue().rstrip()}\n```\n"
    (SNIPPETS / f"api_{name}.md").write_text(text, encoding="utf-8")


def view(name: str, html: str) -> None:
    (SNIPPETS / f"api_view_{name}.html").write_text(f'<div class="op-notebook">{html}</div>\n', encoding="utf-8")


def main() -> int:
    ns: dict = {"opulse": opulse}
    run("grow", """
        import opulse

        world = opulse.World.grow(layers=[20, 10, 5], seed=1)
        print(world)
        print(world.summary()["layers"])
    """, ns)
    world = ns["world"]
    rec = next(op for op in world.operators if op.kind == "recursive" and op.arity == 2)
    simple = next(op for op in world.layer(1) if op.kind == "simple" and op.arity == 2)
    run("operator", f"""
        op = world["{rec.symbol}"]
        print(op.definition)
        print(op.kind, op.layer, op.position)
        print([callee.symbol for callee in op.callees])
        print(op.evaluate(3, 4), op(10, 2))
        print(op.result(3, 4))
    """, ns)
    run("table", "print(op.table([0, 1, 2, 3, 10]))", ns)
    run("trace", """
        trace = op.trace(2, 2)
        print(len(trace), "steps, value", trace.value)
        print("\\n= ".join(trace.lines()[:6]))
    """, ns)
    run("expression", f"""
        expr = world.expression("2 * 3 {simple.symbol} 4 + 1")
        print(expr.text, "=", expr.value)
        print(expr.full_text)
        print(expr.trace().value == expr.value)
        free = world.expression("a {simple.symbol} b")
        print(free.variables, free.evaluate(a=6, b=4))
    """, ns)
    run("sample", """
        for expr in world.sample_expressions(4, depth=2, frequency="zipf:1.5", seed=0):
            print(expr.text, "=", expr.value, " expansion", expr.record["expansion"])
    """, ns)
    run("tasks", """
        tasks = world.tasks("compute", n=20, seed=0, max_depth=2)
        task = min(tasks, key=lambda t: len(t.definitions))
        print(task.expression, "=", task.answer_text)
        print("\\n".join(task.definitions))
        print(tasks.check())
    """, ns)
    run("holes", """
        for hole in world.holes(2, depth=2, unique_only=True, seed=0, timeout_ms=500, domain=50):
            print(hole.text, " x =", hole.solutions)
    """, ns)
    run("equivalence", """
        print(world.equivalent("a + b", "b + a").status)
        verdict = world.equivalent("(a + b) - b", "a")
        print(verdict.status, verdict.counterexample)
    """, ns)
    with tempfile.TemporaryDirectory() as tmp:
        ns["tmp"] = tmp
        run("save", """
            path = world.save(f"{tmp}/my_world")
            print(sorted(p.name for p in path.iterdir()))
            again = opulse.World.load(path)
            print(again.fingerprint == world.fingerprint)
        """, ns)
    (SNIPPETS / "api_save.md").write_text((SNIPPETS / "api_save.md").read_text(encoding="utf-8")
                                          .replace('f"{tmp}/my_world"', '"my_world"'), encoding="utf-8")
    run("dependencies", """
        print([dep.symbol for dep in world.dependencies(op, transitive=True)])
        print([caller.symbol for caller in op.callers])
        graph = world.graph(focus=op)
        print(graph)
    """, ns)
    run("lexer", f"""
        from pygments import highlight
        from pygments.formatters import HtmlFormatter

        html = highlight(op.definition, world.lexer(), HtmlFormatter())
        for token, text in world.lexer().get_tokens("a {simple.symbol} (2 + NaN)"):
            if text.strip():
                print(f"{{text:6}} {{token}}")
    """, ns)
    view("world", world._repr_html_())
    view("operator", ns["op"]._repr_html_())
    view("trace", ns["op"].trace(1, 1)._repr_html_())
    view("task", ns["task"]._repr_html_())
    view("graph", ns["graph"]._repr_html_())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
