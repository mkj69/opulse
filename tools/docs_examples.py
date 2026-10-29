"""Regenerate every example shown in the documentation by running Opulse.

    python tools/docs_examples.py

Writes Markdown fragments to docs/snippets/ (included by the pages with
``--8<--``) and an example HTML report to docs/assets/report/. Nothing in
those fragments is written by hand: if the engine changes, rerun this script.
"""

from __future__ import annotations

import io
import json
import random
import sys
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from opulse.cli.main import main as cli
from opulse.config import Settings
from opulse.core import BINARY, OperatorRegistry, Semantics
from opulse.core.starting_sets import starting_registry
from opulse.definition.parser import DefinitionParser
from opulse.expression.nodes import Call, Variable
from opulse.expression.render import ExpressionRenderer
from opulse.generation.pipeline import OperatorFactory, build_layers
from opulse.language.describe import describe
from opulse.language.narrate import narrate_reverse
from opulse.runtime import PythonRuntime
from opulse.solver.equivalence import EquivalenceChecker, sympy_candidate
from opulse.solver.holes import HoleSolver, hole_paths
from opulse.solver.properties import PropertyChecker
from opulse.solver.smt import export, prelude
from opulse.solver.static import reachable_branches
from opulse.solver.z3_encode import Z3Encoder
from opulse.verify import Oracle

SNIPPETS = ROOT / "docs" / "snippets"
WORK = ROOT / "outputs" / "docs_examples"



def write(name: str, text: str) -> None:
    (SNIPPETS / name).write_text(text.rstrip() + "\n", encoding="utf-8")
    print("wrote", name)


def block(text: str, lang: str = "text") -> str:
    return f"```{lang}\n{text.rstrip()}\n```"


def compact(value, indent: int = 0) -> str:
    """JSON with scalars, lists of scalars and small objects kept on one line."""
    pad = "  " * indent
    simple = lambda v: not isinstance(v, (dict, list)) or (
        isinstance(v, list) and all(not isinstance(x, (dict, list)) for x in v)) or (
        isinstance(v, dict) and len(v) <= 3 and all(not isinstance(x, (dict, list)) for x in v.values()))
    if simple(value):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        inner = ",\n".join(pad + "  " + compact(v, indent + 1) for v in value)
        return "[\n" + inner + "\n" + pad + "]"
    inner = ",\n".join(f'{pad}  {json.dumps(k, ensure_ascii=False)}: {compact(v, indent + 1)}' for k, v in value.items())
    return "{\n" + inner + "\n" + pad + "}"


def grow(settings: Settings, layers, seed: int, initial: str | Path = "integer") -> tuple[OperatorRegistry, OperatorFactory]:
    registry = (starting_registry(initial) if isinstance(initial, str) and initial in ("integer", "atomic")
                else OperatorRegistry.from_jsonl(initial))
    factory = OperatorFactory(settings, registry, random.Random(seed))
    build_layers(factory, layers)
    return registry, factory


def pick(registry, kind: str, n: int = 1, layer: int | None = None):
    found = [op for op in registry if op.definition_type == kind and (layer is None or op.recursive_layer == layer)]
    found.sort(key=lambda op: len(op.definition))
    return found[:n]


def write_json(name: str, data) -> None:
    (SNIPPETS / name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print("wrote", name)
    (SNIPPETS / name.replace(".json", "_static.html")).write_text(static_view(data), encoding="utf-8")


def static_view(data) -> str:
    """Plain HTML shown inside an animation box until (or unless) the script replaces it."""
    import html

    if "frames" in data:  # a reduction trace
        lines = [f["before"].replace("[[", "").replace("]]", "") for f in data["frames"]]
        if data["frames"]:
            lines.append(data["frames"][-1]["after"].replace("[[", "").replace("]]", ""))
        text = "\n= ".join(lines)
    elif "steps" in data:  # a reverse derivation
        rows = [f"{s['symbol']} must give {s['target']}  ->  unknown in {{{', '.join(map(str, s['candidates']))}}}"
                for s in data["steps"]]
        text = f"{data['expression']} = {data['target']}\n" + "\n".join(rows) + \
            f"\nx in {{{', '.join(map(str, data['solutions']))}}}"
    else:  # operators by layer
        text = "\n".join(f"layer {op['layer']}  {op['definition']}" for op in data["operators"])
    return f'<pre class="oa-static">{html.escape(text)}</pre>'


def marked(node, target, path=()) -> str:
    """Fully bracketed text with the subtree at ``target`` wrapped in [[ ]] (for highlighting)."""
    from opulse.core import NAN
    from opulse.expression.nodes import Number

    if isinstance(node, Number):
        text = "NaN" if node.value is NAN else (f"({node.value})" if node.value < 0 else str(node.value))
    elif isinstance(node, Variable):
        text = node.name
    else:
        args = [marked(arg, target, path + (i,)) for i, arg in enumerate(node.args)]
        args = [f"({a})" if isinstance(arg, Call) else a for a, arg in zip(args, node.args)]
        text = node.operator.apply_str(*args)
    return f"[[{text}]]" if path == target else text


def trace_frames(trace, title: str) -> dict:
    frames = []
    for step in trace.steps:
        frames.append({
            "kind": step.kind, "symbol": step.operator.symbol,
            "inputs": [value if isinstance(value, int) else None for value in step.inputs],
            "before": marked(step.expression_before, step.path),
            "after": marked(step.expression_after, step.path),
            "branch": None if step.branch_index is None else step.branch_index + 1,
            "condition": step.condition, "reason": step.reason,
            "output": step.output if isinstance(step.output, int) else None,
        })
    return {"title": title, "frames": frames}


def main() -> int:
    SNIPPETS.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    settings = Settings()

    # ------------------------------------------------------------ operators
    ops_path = WORK / "operators.jsonl"
    ops_path.unlink(missing_ok=True)  # `opulse operators` resumes an existing file; start fresh
    with redirect_stdout(io.StringIO()):
        cli(["operators", "--out", str(ops_path), "--layers", "10", "6", "4", "--seed", "7"])
    registry = OperatorRegistry.from_jsonl(ops_path)
    oracle = Oracle(registry, settings.symbols, settings.semantics.build())
    encoder = Z3Encoder(oracle)
    simple = pick(registry, "simple_definition", 2)
    branch = pick(registry, "branch_definition", 2)
    recursive = pick(registry, "recursive_definition", 2)
    write("operators.md", block("\n".join(op.definition for op in simple + branch + recursive)))
    rec = recursive[0]
    write("operator_record.md", block(compact(
        {k: rec.to_dict()[k] for k in ("func_id", "symbol", "n_ary", "unary_position", "recursive_layer",
                                       "definition", "definition_type", "max_path_depth", "max_edge_count",
                                       "dependencies")}), "json"))
    if rec.n_ary == 2:
        points = [(a, b) for a in (0, 5, -5, 9, 2147483647) for b in (0, 7, -3)][:9]
    else:  # one input per line, written in the operator's own notation
        points = [(a,) for a in (0, 1, 5, -5, 9, 12, 100, -2147483647, 2147483647)][:9]
    lines = []
    for args in points:
        result = oracle.evaluate(rec, args)
        shown = rec.apply_str(*(f"({v})" if v < 0 else str(v) for v in args))
        lines.append(f"{shown} = {result.value}    base_ops = {result.base_ops}")
    write("evaluate.md", block("\n".join(lines)))

    # ----------------------------------------------------------- expressions
    expr_path = WORK / "expressions.jsonl"
    with redirect_stdout(io.StringIO()):
        cli(["expressions", "--operators", str(ops_path), "--out", str(expr_path), "--count", "40",
             "--seed", "3", "--cot", "en", "--keep-undefined"])
    records = [json.loads(line) for line in expr_path.read_text().splitlines()]
    defined = sorted((r for r in records if not r["undefined"]), key=lambda r: len(r["cot"]))
    short = next(r for r in defined if "unfold" in r["cot"])
    keys = ("expression", "result", "undefined", "result_text", "expansion", "max_path_depth", "max_edge_count")
    write("expression_record.md", block(compact({k: short[k] for k in keys}), "json"))
    write("cot.md", block(short["cot"].replace("\n\n", "\n")))
    undefined = next((r for r in records if r["undefined"]), None)
    if undefined is not None:
        write("expression_undefined.md", block(compact(
            {k: undefined[k] for k in ("expression", "result", "undefined", "result_text")}), "json"))

    # ---------------------------------------------------------- descriptions
    parsed = oracle._definition_of(rec)
    write("describe.md", block(describe(rec, parsed, registry, "en", "math") + "\n\n"
                               + describe(rec, parsed, registry, "en", "natural")))
    div = registry.find("/", BINARY)
    write("describe_base.md", block(describe(div, None, registry, "en")))

    # ----------------------------------------------------------------- holes
    solver = HoleSolver(encoder, oracle)
    renderer = ExpressionRenderer(settings.symbols)
    from opulse.expression.generator import ExpressionGenerator, OperatorPool

    generator = ExpressionGenerator(settings.expressions, random.Random(5))
    pool = OperatorPool.from_registry(registry)
    unique = multi = None
    rng = random.Random(1)
    while unique is None or multi is None:
        tree = generator.tree(pool, max_depth=2, atoms="number")
        if not isinstance(tree, Call):
            continue
        problem = solver.problem(tree, rng.choice(hole_paths(tree)))
        if problem is None:
            continue
        if problem.solutions.unique and problem.solutions.method == "z3" and len(problem.reverse) >= 2 \
                and unique is None:
            unique = problem
        elif problem.solutions.complete and 1 < len(problem.solutions.values) <= 6 and multi is None:
            multi = problem
    from opulse.cli.holes import record as hole_record

    for name, problem in (("holes_unique.md", unique), ("holes_multi.md", multi)):
        data = hole_record(problem, 0, renderer)
        data.pop("tree")
        write(name, block(compact(data), "json"))
    write("holes_reverse.md", block(narrate_reverse(unique, renderer, "en").replace("\n\n", "\n")))

    # -------------------------------------------------------------- analysis
    checker = PropertyChecker(encoder, timeout_ms=3000)
    plus, minus, times = (registry.find(s, BINARY) for s in "+-*")
    rows = []
    for op, prop in ((plus, "commutative"), (minus, "commutative"), (plus, "associative"), (times, "right_identity"),
                     (next(op for op in branch + simple + recursive if op.n_ary == 2), "commutative")):
        verdict = checker.check(op, prop).to_dict()
        rows.append(f"| `{op.symbol}` | {prop} | {verdict['status']} | "
                    f"{verdict.get('counterexample', verdict.get('witness', ''))} |")
    write("properties.md", "| Operator | Property | Verdict | Counterexample / element |\n| --- | --- | --- | --- |\n"
          + "\n".join(rows))
    base = prelude(encoder)
    write("smt.md", block(export(rec, encoder, base), "lisp"))
    reach = [(op.definition, reachable_branches(op, encoder)) for op in branch]
    write("reachability.md", block("\n".join(f"{d}\n  -> {v}" for d, v in reach)))

    # ------------------------------------------------------------ equivalence
    eq_lines = []
    for bound in (2**31 - 1, None):
        eq_oracle = Oracle(registry, settings.symbols, Semantics("exact", bound))
        eq = EquivalenceChecker(Z3Encoder(eq_oracle))
        a, b = Variable("a"), Variable("b")
        left = Call(minus, (Call(plus, (a, b)), b))
        square = Call(times, (Call(plus, (a, b)), Call(plus, (a, b))))
        expanded = sympy_candidate(square, registry)
        for x, y in ((left, a), (square, expanded)):
            v = eq.check(x, y).to_dict()
            extra = f"  counterexample {v['counterexample']}: {v['left_value']} vs {v['right_value']}" \
                if "counterexample" in v else ""
            eq_lines.append(f"bound={bound}:  {renderer.full(x)}  ==  {renderer.full(y)}  ->  {v['status']}{extra}")
    write("equivalence.md", block("\n".join(eq_lines)))

    # ----------------------------------------------------------------- atoms
    atomic_settings = Settings.load(ROOT / "configs" / "atomic.yaml")
    atoms, _ = grow(atomic_settings, [6, 4], 1, "atomic")
    shown = pick(atoms, "simple_definition", 2) + pick(atoms, "recursive_definition", 1)
    write("atoms.md", block("\n".join(op.definition for op in shown), "opulse"))

    # -------------------------------------------------------------- notation
    custom = Settings.from_dict({"symbols": {"left_operand": "x", "right_operand": "y", "left_paren": "[",
                                             "right_paren": "]", "equals": ":=", "nan": "Undef"},
                                 "expressions": {"variables": ["x", "y"]},
                                 "operators": {"partial_probability": 0.4}})
    custom_reg, _ = grow(custom, [6, 3], 2)
    shown = pick(custom_reg, "branch_definition", 1) + pick(custom_reg, "recursive_definition", 1)
    write("notation_custom.md", block("\n".join(op.definition for op in shown), "opulse"))
    greek = replace(settings, operators=replace(settings.operators, naming="legacy",
                                                 symbol_sets=("greek",), symbol_max_len=2))
    greek_reg, _ = grow(greek, [6, 3], 2)
    write("notation_greek.md", block("\n".join(op.definition for op in pick(greek_reg, "simple_definition", 3)), "opulse"))
    parser = DefinitionParser(settings.symbols, registry)
    write("parse.md", block(f"{'&-1':<10} -> {parser.parse_expr('&-1')}\n"
                            f"{'- a @':<10} -> {parser.parse_expr('- a @')}"))

    # ------------------------------------------------------------ complexity
    from opulse.analysis.complexity import analyze_operator

    runtime = PythonRuntime(registry, settings.semantics.build())
    fits = [analyze_operator(op, runtime, oracle, encoder) for op in (simple[0], recursive[0])]
    write("complexity.md", block("\n".join(json.dumps({k: (round(v, 3) if isinstance(v, float) else v)
                                                         for k, v in fit.items() if k != "coefficients"},
                                                        ensure_ascii=False) for fit in fits), "json"))

    # ----------------------------------------------------------- granularity
    from opulse.expression.nodes import from_dict as _from_dict
    from opulse.language.narrate import narrate
    from opulse.trace import Reducer as _Reducer

    gran_parser = DefinitionParser(settings.symbols, registry)
    gran_runtime = PythonRuntime(registry, settings.semantics.build())
    candidates = sorted((r for r in records if not r["undefined"]), key=lambda r: len(r["cot"]))
    chosen = next(r for r in candidates if r["cot"].count("unfold") >= 3)
    tree = _from_dict(chosen["tree"], registry)
    rows, texts = [], {}
    for label, kwargs, flag in (("full (default)", {}, ""), ("unfold one level", {"max_depth": 1}, "--cot-depth 1"),
                                ("layer 0 known", {"expand": lambda op: op.definition is not None and
                                                   (op.recursive_layer or 0) >= 1}, "--cot-known-layers 1"),
                                ("nothing unfolded", {"max_depth": 0}, "--cot-depth 0")):
        trace = _Reducer(registry, gran_runtime, gran_parser, **kwargs).reduce(tree)
        rows.append(f"| {label} | `{flag or '(none)'}` | {len(trace.steps)} | "
                    f"{sum(st.kind == 'expand' for st in trace.steps)} | {trace.value} |")
        texts[label] = narrate(trace, renderer, "en").replace("\n\n", "\n")
    write("granularity.md", f"Expression: `{chosen['expression_plain']}`\n\n"
          "| Granularity | Option | Steps | Unfoldings | Value |\n| --- | --- | --- | --- | --- |\n" + "\n".join(rows))
    write("granularity_depth1.md", block(texts["unfold one level"]))

    # ------------------------------------------------------------ animations
    from opulse.expression.nodes import from_dict
    from opulse.trace import Reducer

    reducer = Reducer(registry, runtime, DefinitionParser(settings.symbols, registry))
    trace = reducer.reduce(from_dict(short["tree"], registry))
    write_json("anim_trace.json", trace_frames(trace, f"{short['expression_plain']} = {short['result']}"))
    call_args = (2, 2) if rec.n_ary == 2 else (2,)
    from opulse.expression.nodes import Number

    call = Call(rec, tuple(Number(v) for v in call_args))
    write_json("anim_recursion.json", trace_frames(reducer.reduce(call), rec.definition))
    write_json("anim_holes.json", {
        "expression": renderer.full(unique.expression), "target": unique.target,
        "steps": [{"symbol": st.operator_symbol, "known": {str(k): v for k, v in st.known.items()},
                   "position": st.unknown_position, "target": st.target, "candidates": st.candidates,
                   "complete": st.complete} for st in unique.reverse],
        "solutions": unique.solutions.values, "unique": unique.solutions.unique,
        "domain": list(unique.solutions.domain)})
    layer_registry, layer_factory = grow(settings, [8, 6, 4], 7)
    generated = [op for op in layer_registry if op.definition]
    ids = {op.func_id for op in generated}
    write_json("anim_layers.json", {
        "operators": [{"id": op.func_id, "symbol": op.symbol, "layer": op.recursive_layer,
                       "kind": op.definition_type.split("_")[0], "definition": op.definition,
                       "deps": [d for d in op.dependencies if d in ids and d != op.func_id]} for op in generated],
        "rejected": layer_factory.stats.summary()["rejected"]})

    # ---------------------------------------------------------------- report
    report = ROOT / "docs" / "assets" / "report"
    with redirect_stdout(io.StringIO()):
        cli(["viz", "--operators", str(ops_path), "--expressions", str(expr_path), "--out", str(report)])
    print("wrote", report / "index.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
