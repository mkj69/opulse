"""Regenerate the examples of docs/guide/views.md and the language parts of step-by-step.md.

    python tools/docs_views.py

Every fragment is written by running Opulse on a generated operator set; nothing is typed by
hand. English fragments go to docs/snippets/ and Chinese fragments go to docs_zh/snippets/.
"""

from __future__ import annotations

import io
import json
import random
import sys
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from opulse.bench.tasks import BenchBuilder
from opulse.cli.main import main as cli
from opulse.config import Settings
from opulse.core import OperatorRegistry
from opulse.definition.parser import DefinitionParser
from opulse.expression.aliases import AliasMap, aliased_registry
from opulse.expression.nodes import Call, Number
from opulse.expression.render import ExpressionRenderer
from opulse.language import Describer, Views, narrate
from opulse.runtime import PythonRuntime
from opulse.trace import Reducer

SNIPPETS = ROOT / "docs" / "snippets"
ZH_SNIPPETS = ROOT / "docs_zh" / "snippets"
WORK = ROOT / "outputs" / "docs_views"


def write(name: str, text: str) -> None:
    if name.endswith("_zh.md") and not ZH_SNIPPETS.parent.is_dir():
        return
    destination = ZH_SNIPPETS if name.endswith("_zh.md") else SNIPPETS
    destination.mkdir(parents=True, exist_ok=True)
    (destination / name).write_text(text.rstrip() + "\n", encoding="utf-8")
    print("wrote", name)


def block(text: str, lang: str = "text") -> str:
    fence = "````" if "```" in text else "```"
    return f"{fence}{lang}\n{text.rstrip()}\n{fence}"


def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    ops_path = WORK / "operators.jsonl"
    ops_path.unlink(missing_ok=True)
    with redirect_stdout(io.StringIO()):
        cli(["operators", "--out", str(ops_path), "--layers", "10", "6", "4", "--seed", "7"])
    settings = Settings()
    original = OperatorRegistry.from_jsonl(ops_path)
    shapes = "◆●◇○▲△■□✦✧"
    subscript = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")
    names = {(op.symbol, op.n_ary, op.unary_position):
             f"{shapes[index % len(shapes)]}{str(index + 1).translate(subscript)}"
             for index, op in enumerate(op for op in original if op.definition is not None)}
    alias = AliasMap(names, {name: key for key, name in names.items()}, settings.symbols)
    registry = aliased_registry(original, alias)
    registry.to_jsonl(ops_path)
    views = Views(registry, settings)
    describer = Describer(registry, settings)
    by_length = lambda kind: sorted((op for op in registry if op.definition_type == kind),
                                    key=lambda op: len(op.definition))
    recursive = by_length("recursive_definition")[0]
    branch = next(op for op in by_length("branch_definition") if op.definition.count(";") >= 2)

    # ------------------------------------------------------------ six views of one operator
    write("views_symbolic.md", block(views.symbolic(recursive)))
    write("views_formula.md", block(views.formula(recursive), "latex"))
    write("views_code.md", block(views.code(recursive), "python"))
    write("views_prose_en.md", block(views.prose(recursive, "en", 0)))
    write("views_prose_zh.md", block(views.prose(recursive, "zh", 0)))
    write("views_examples.md", views.examples(recursive).text(settings.symbols).split("\n", 1)[1])
    write("views_summary.md", views.summary(recursive).text(settings.symbols))
    paraphrases = []
    for seed in range(4):
        text = views.prose(branch, "en", seed)
        if text not in paraphrases:
            paraphrases.append(text)
    write("views_paraphrases.md", block("\n\n".join(f"seed {seed}:\n{text}" for seed, text in enumerate(paraphrases))))
    write("views_branch_symbolic.md", block(branch.definition))
    checks = {view: views.round_trip(recursive, view, "en").ok for view in ("symbolic", "formula", "code", "prose")}
    write("views_round_trip.md", block(json.dumps(checks)))

    # ------------------------------------------------------------ a prose prompt task
    builder = BenchBuilder(settings, registry, random.Random(3), definition_format="prose", max_definitions=2)
    task = next(builder.tasks("compute", 1))
    write("views_prompt.md", block(task.prompt))
    with redirect_stdout(io.StringIO()):
        tasks_path = WORK / "prose_tasks.jsonl"
        cli(["bench", "build", "--operators", str(ops_path), "--out", str(tasks_path), "--count", "20",
             "--definition-format", "prose"])
        out = io.StringIO()
    with redirect_stdout(out):
        cli(["bench", "check", "--operators", str(ops_path), "--tasks", str(tasks_path)])
    write("views_prompt_check.md", block(out.getvalue().strip().splitlines()[-1]))

    # ------------------------------------------------------------ descriptions
    write("describe_chain.md", block(describer.chain(recursive, "en")))
    write("describe.md", block(describer.describe(recursive, "en", "math") + "\n\n" +
                               describer.describe(recursive, "en", "natural")))

    # ------------------------------------------------------------ narration
    renderer = ExpressionRenderer(settings.symbols)
    reducer = Reducer(registry, PythonRuntime(registry, settings.semantics.build()),
                      DefinitionParser(settings.symbols, registry))
    args = (Number(13),) * recursive.n_ary
    tree = Call(registry.find("-", 2), (Call(recursive, args), Number(2)))
    trace = reducer.reduce(tree)
    write("narrate_terse.md", block(narrate(trace, renderer, "en", "terse")))
    write("narrate_explained.md", block(narrate(trace, renderer, "en", "explained", registry=registry)))
    write("narrate_explained_zh.md", block(narrate(trace, renderer, "zh", "explained", registry=registry)))
    write("narrate_collapsed.md", block(narrate(trace, renderer, "en", "terse", collapse="atoms")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
