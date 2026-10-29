"""Build the executed tutorial notebooks for local authoring."""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from textwrap import dedent

import nbformat

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "examples" / "notebooks"


def notebook(name, title, examples):
    cells = [nbformat.v4.new_markdown_cell(f"# {title}")]
    for explanation, code in examples:
        cells.append(nbformat.v4.new_markdown_cell(explanation))
        cells.append(nbformat.v4.new_code_cell(dedent(code).strip()))
    for index, cell in enumerate(cells):
        cell.id = f"{name[:2]}-{index:02d}"  # stable ids keep rebuilt notebooks free of id churn
    book = nbformat.v4.new_notebook(
        cells=cells,
        metadata={"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
    )
    scope = {"__name__": "__main__"}
    for count, cell in enumerate((cell for cell in book.cells if cell.cell_type == "code"), start=1):
        output = StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            exec(compile(cell.source, f"{name} cell {count}", "exec"), scope)  # noqa: S102
        cell.execution_count = count
        if output.getvalue():
            cell.outputs = [nbformat.v4.new_output("stream", name="stdout", text=output.getvalue())]
    nbformat.validate(book)
    nbformat.write(book, OUT / f"{name}.ipynb")
    print(f"Wrote {name}.ipynb")


notebook("01_grow_your_first_world", "Grow your first world", [
    ("Register one integer atom and put it beside the built in arithmetic atoms.", """
        import random
        from opulse.config import Settings
        from opulse.core import OperatorRegistry
        from opulse.core.operator import Operator
        from opulse.core.primitives import atom_records, register_primitive
        from opulse.generation.pipeline import OperatorFactory, build_layers
        from opulse.language.describe import describe
        from opulse.verify import Oracle

        register_primitive("square_example", "⊞", lambda a: a * a,
                           rule="a ⊞ is a multiplied by itself.")
        rows = atom_records(["add", "sub", "mul", "mod", "neg", "square_example"], seed=7)
        registry = OperatorRegistry(Operator.from_dict(row) for row in rows)
        print([(op.symbol, op.n_ary) for op in registry])
    """),
    ("Grow two small layers and inspect the definitions that were accepted.", """
        settings = Settings()
        factory = OperatorFactory(settings, registry, random.Random(7))
        build_layers(factory, [3, 2])
        grown = [op for op in registry if op.definition]
        for op in grown:
            print(op.definition)
    """),
    ("Describe one generated operator from its parsed definition.", """
        oracle = Oracle(registry)
        selected = grown[0]
        print(describe(selected, oracle._definition_of(selected), registry, lang="en"))
    """),
])

notebook("02_derivations_at_any_granularity", "Derivations at any granularity", [
    ("Grow a small world and choose a call to an operator in its second layer.", """
        import random
        from pathlib import Path
        import opulse
        from opulse.config import Settings
        from opulse.core import OperatorRegistry
        from opulse.definition.parser import DefinitionParser
        from opulse.expression.nodes import Call, Number
        from opulse.expression.render import ExpressionRenderer
        from opulse.generation.pipeline import OperatorFactory, build_layers
        from opulse.trace import Reducer
        from opulse.verify import Oracle, verify_trace

        root = Path(opulse.__file__).resolve().parents[2]
        registry = OperatorRegistry.from_jsonl(root / "data" / "initial_operators.jsonl")
        settings = Settings()
        factory = OperatorFactory(settings, registry, random.Random(13))
        build_layers(factory, [4, 2])
        chosen = next(op for op in registry if op.definition and op.recursive_layer == 1)
        expression = Call(chosen, tuple(Number(3) for _ in range(chosen.n_ary)))
        parser = DefinitionParser(settings.symbols, registry)
        renderer = ExpressionRenderer(settings.symbols)
        print(renderer.full(expression))
    """),
    ("Compare full unfolding with two sets of known operators and check every trace.", """
        oracle = Oracle(registry)
        known_sets = {
            "none": set(),
            "first layer": {op.symbol for op in registry if op.definition and op.recursive_layer == 0},
            "chosen operator": {chosen.symbol},
        }
        traces = {}
        for label, known in known_sets.items():
            reducer = Reducer(registry, factory.runtime, parser,
                              expand=lambda op: op.definition is not None and op.symbol not in known)
            trace = reducer.reduce(expression)
            assert not trace.truncated
            verify_trace(trace, oracle)
            traces[label] = trace
            print(label, "steps:", len(trace.steps),
                  "expansions:", sum(step.kind == "expand" for step in trace.steps),
                  "value:", trace.value)
        assert len({trace.value for trace in traces.values()}) == 1
    """),
    ("Show the first few checked rewrites in the full trace.", """
        for step in traces["none"].steps[:5]:
            print(step.kind, renderer.full(step.expression_after))
    """),
])

notebook("03_benchmark_a_model", "Benchmark a model", [
    ("Grow a small operator set and build three compute tasks with their definitions.", """
        import random
        from pathlib import Path
        import opulse
        from opulse.bench.tasks import BenchBuilder
        from opulse.config import Settings
        from opulse.core import OperatorRegistry
        from opulse.generation.pipeline import OperatorFactory, build_layers

        root = Path(opulse.__file__).resolve().parents[2]
        registry = OperatorRegistry.from_jsonl(root / "data" / "initial_operators.jsonl")
        settings = Settings()
        build_layers(OperatorFactory(settings, registry, random.Random(19)), [4, 2])
        tasks = [task.to_dict() for task in BenchBuilder(
            settings, registry, random.Random(2), max_depth=2, max_answer_share=1.0
        ).tasks("compute", 3)]
        print("tasks:", len(tasks))
        print("first expression:", tasks[0]["expression"])
        print("definitions supplied:", len(tasks[0]["definitions"]))
    """),
    ("Recompute each answer using only the rules and definitions in its prompt.", """
        from opulse.bench.check import base_registry, check_tasks

        problems = check_tasks(tasks, base_registry(registry), settings.symbols, settings.semantics.build())
        assert not problems, problems
        print("prompt checks passed:", len(tasks))
    """),
    ("Grade a fixed stub reply to exercise the scoring path without a model request.", """
        from opulse.cli.bench import summarize

        def stub_reply(prompt):
            return "Answer: 0"

        responses = [{"id": task["id"], "response": stub_reply(task["prompt"])} for task in tasks]
        summary = summarize(tasks, responses)
        print("stub accuracy:", summary["accuracy"], "across", summary["tasks"], "tasks")
    """),
    ("Use this command with your own endpoint and model name when a server is available.", """
        print("opulse bench run --tasks tasks.jsonl --out responses.jsonl "
              "--base-url http://localhost:8000/v1 --model YOUR_MODEL")
    """),
])

notebook("04_one_factor_at_a_time", "One factor at a time", [
    ("Build two expression corpora with the same seed and change only the result base.", """
        import random
        from collections import Counter
        from dataclasses import replace
        from pathlib import Path
        import opulse
        from opulse.config import Settings
        from opulse.core import OperatorRegistry
        from opulse.expression.dataset import ExpressionDataset
        from opulse.runtime import PythonRuntime

        root = Path(opulse.__file__).resolve().parents[2]
        registry = OperatorRegistry.from_jsonl(root / "data" / "initial_operators.jsonl")
        settings10 = Settings()
        settings2 = replace(settings10, expressions=replace(settings10.expressions, result_base=2))
        runtime = PythonRuntime(registry)

        def corpus(settings):
            return list(ExpressionDataset(settings, registry, runtime, random.Random(11), seed=11).records(12))

        decimal = corpus(settings10)
        binary = corpus(settings2)
        assert [row["expression_plain"] for row in decimal] == [row["expression_plain"] for row in binary]
        assert [row["result"] for row in decimal] == [row["result"] for row in binary]
        print("paired records:", len(decimal))
    """),
    ("Count the stored result bases and compare the lengths of the result strings.", """
        for label, rows in (("decimal", decimal), ("binary", binary)):
            bases = dict(Counter(row["result_base"] for row in rows))
            mean_length = round(sum(len(row["result_text"]) for row in rows) / len(rows), 2)
            print(label, "result bases:", bases, "mean result text length:", mean_length)
        print("first pair:", decimal[0]["result_text"], binary[0]["result_text"])
    """),
])

notebook("05_rl_rewards", "Rewards for sample completions", [
    ("Create a step task whose reference answer follows from two arithmetic rewrites.", """
        from pathlib import Path
        import opulse
        from opulse.bench.reward import compute_score, rl_record
        from opulse.cli.bench import step_checker_for
        from opulse.cli.operators import DEFAULT_CONFIG

        root = Path(opulse.__file__).resolve().parents[2]
        operators = root / "data" / "initial_operators.jsonl"
        task = {
            "id": "arithmetic_example", "family": "compute", "format": "steps",
            "prompt": "What is the value of `(1 + 2) * 3`?",
            "expression": "(1 + 2) * 3", "definitions": [],
            "answer": 9, "answer_text": "9", "nan": "NaN", "axes": {"naming": "symbols"},
        }
        row = rl_record(task, operators=str(operators))
        truth = row["reward_model"]["ground_truth"]
        info = row["extra_info"]
        print("reference answer:", task["answer_text"])
    """),
    ("Compare outcome reward and combined step reward for three sample completions.", """
        completions = {
            "full": "= 3 * 3\\n= 9\\nAnswer: 9",
            "partial": "= 3 * 3\\nAnswer: 9",
            "wrong": "= 4 * 3\\nAnswer: 12",
        }
        for label, completion in completions.items():
            outcome = compute_score("opulse", completion, truth)
            combined = compute_score("opulse", completion, truth, info)
            print(label, "outcome:", outcome, "combined:", combined)
    """),
    ("Read checked step progress for the same completions.", """
        check = step_checker_for(operators, DEFAULT_CONFIG)
        for label, completion in completions.items():
            report = check(task, completion)
            print(label, "credit:", report["credit"], "progress:", report["progress"])
    """),
])
