"""Regenerate the data of the visual tour (docs/guide/visual-tour.md) by running Opulse.

    python tools/docs_visuals.py

The remaining components of docs/assets/js/opulse-vis.js read JSON blocks written here. Each
generated ``docs/snippets/vis_<name>.html`` is a complete, embeddable widget: the container, the data and
a static fallback, so any page can show it with

    --8<-- "docs/snippets/vis_<name>.html"

The main operator set is grown with a recorded generation run. The equivalence widget adds four
small definitions to that set. Every shown value, verdict, step grade, solution and count comes
from the library.
The script is deterministic (fixed seeds).
"""

from __future__ import annotations

import html
import io
import json
import random
import sys
from collections import Counter, deque
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from opulse.cli.main import main as cli
from opulse.cli.operators import DEFAULT_CONFIG
from opulse.config import Settings
from opulse.core import OperatorRegistry
from opulse.core.semantics import NAN, base_operation_name
from opulse.core.starting_sets import starting_registry
from opulse.definition.parser import DefinitionParser
from opulse.expression.nodes import Call, Number, Variable, from_dict, to_ast
from opulse.expression.render import ExpressionRenderer
from opulse.generation.pipeline import OperatorFactory, build_layers
from opulse.runtime import PythonRuntime
from opulse.solver.static import RLIMIT_PER_NODE
from opulse.trace import Reducer
from opulse.verify import Oracle, verify_trace

SNIPPETS = ROOT / "docs" / "snippets"
ZH_SNIPPETS = ROOT / "docs_zh" / "snippets"
WORK = ROOT / "outputs" / "docs_visuals"


# The tour grows three to five small layers. At most three branches per definition keeps
# every definition short enough to read in a widget; everything else is the default config.
LAYERS = [8, 6, 4]
GROWTH_SEED = 15
MAX_IF_BRANCHES = 3
SOLVER_SAFETY_TIMEOUT_MS = 30_000
VISUAL_SOLVER_BUDGET = 50


def solver_rlimit(settings: Settings) -> int:
    return min(settings.solver.rlimit, VISUAL_SOLVER_BUDGET * RLIMIT_PER_NODE)
PROFILES = (("Easy 1", [8, 6, 4], 15), ("Easy 2", [8, 6, 4, 1], 15),
            ("Hard", [8, 6, 4, 3], 15), ("Long", [8, 6, 4, 3, 2], 15))
EXAMPLES: dict[str, list[dict]] = {}
PROFILE = 0
ENGINE: Engine | None = None


# ------------------------------------------------------------------ helpers
def num(value):
    """JSON form of a value in Z ∪ {NaN}: an int, or None for NaN."""
    return None if value is NAN or not isinstance(value, int) else value


def kind_of(op) -> str:
    if op.definition is None:
        return "atom"
    return op.definition_type.split("_")[0]  # simple | branch | recursive


def is_atom(op) -> bool:
    """A base operation (numeral markers are base operators too, but not operations)."""
    return op.definition is None and base_operation_name(op.symbol, op.n_ary, op.unary_position) is not None


def write_widget(name: str, kind: str, data: dict, static: str) -> None:
    """docs/snippets/vis_<name>.html: container, data and static fallback, with no blank line
    (a blank line would end the raw HTML block in Markdown)."""
    if ENGINE is not None:
        EXAMPLES.setdefault(name, []).append({"label": PROFILES[PROFILE][0],
                                                "operators": operator_count(name, data, ENGINE),
                                                "steps": step_count(name, data), "data": data,
                                                "description": example_description(name, data),
                                                "static": static, "kind": kind})
        return
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    static = "\n".join(line for line in static.splitlines() if line.strip())
    text = (f'<div class="opv" data-kind="{kind}">\n'
            f'<script type="application/json">{payload}</script>\n'
            f'<div class="opv-static">\n{static}\n</div>\n</div>\n')
    (SNIPPETS / f"vis_{name}.html").write_text(text, encoding="utf-8")
    print(f"wrote vis_{name}.html ({len(text) // 1024} KiB)")


def _calls(tree) -> int:
    return int(tree[1] not in ("num", "var")) + sum(_calls(c) for c in tree[2])


def operator_count(name: str, data: dict, engine: Engine) -> int:
    if name == "growth":
        return sum(n["definition"] is not None for n in data["nodes"])
    if name == "unfold":
        return _calls(data["frames"][0]["tree"])
    if name == "steps":
        return expression_calls(engine, data["question"])
    if name in ("contrast", "solve"):
        return expression_calls(engine, data["expression"])
    if name == "equivalence":
        return max(expression_calls(engine, p["left"]) + expression_calls(engine, p["right"]) for p in data["pairs"])
    if name == "ripple":
        return len(data["nodes"])
    return len(data["operators"])


def expression_calls(engine: Engine, text: str) -> int:
    from opulse.definition import ast

    parser = DefinitionParser(engine.settings.symbols, engine.registry, variables=("x", "a", "b"))
    return sum(1 for _ in ast.iter_applications(parser.parse_expr(text, expression_mode=True)))


def step_count(name: str, data: dict) -> int:
    if name == "growth":
        return len(data["events"]) + 1
    if name == "unfold":
        return len(data["frames"])
    if name == "steps":
        return sum(len(r["rows"]) + 1 for r in data["runs"])
    if name == "solve":
        return 2 + (len(data["scan"]) + 9) // 10 + len(data["reverse"])
    if name == "equivalence":
        return 11 * len(data["pairs"])
    if name == "ripple":
        return max(n["distance"] for n in data["nodes"]) + 3
    return sum(len(series["snapshots"]) for series in data["series"]) if name == "frequency" else 6


def example_description(name: str, data: dict) -> dict[str, str]:
    if name == "growth":
        n = len(data["layers"])
        return {"en": f"This run grows operators across {n} layers.",
                "zh": f"这次运行生成了 {n} 层运算符。"}
    if name == "unfold":
        n = len(data["frames"]) - 1
        return {"en": f"The interpreter reduces this expression in {n} checked steps.",
                "zh": f"解释器通过 {n} 个经过核对的步骤化简这个算式。"}
    if name == "contrast":
        return {"en": "Changing one shown definition changes the reference answer.",
                "zh": "更改题面中的一条定义会改变参考答案。"}
    if name == "steps":
        return {"en": "The checker finds the first wrong line in a continued derivation.",
                "zh": "检查器在继续写出的推导中找出第一处错误。"}
    if name == "solve":
        lo, hi = data["domain"]
        return {"en": f"The solver checks uniqueness across {hi - lo + 1} possible values of x.",
                "zh": f"求解器在 {hi - lo + 1} 个 x 的候选值中核对解的唯一性。"}
    if name == "equivalence":
        return {"en": "Six pairs cover inlining, rewriting, branches, recursion and two counterexamples.",
                "zh": "六对算式涵盖内联、代数改写、分支、递归和两种反例。"}
    if name == "ripple":
        distance = max(n["distance"] for n in data["nodes"])
        return {"en": f"This edit reaches operators {distance} dependency layers away.",
                "zh": f"这次修改影响到相隔 {distance} 层依赖关系的运算符。"}
    count = data["series"][0]["expressions"]
    return {"en": f"Each frequency setting counts calls in {count} sampled expressions.",
            "zh": f"每种频率设置都统计 {count} 个采样算式中的调用。"}


def write_collected() -> None:
    for name, examples in EXAMPLES.items():
        entries = [{k: v for k, v in example.items() if k not in ("static", "kind")}
                   for example in examples]
        data = {"examples": entries}
        payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
        # A large derivation is loaded only when its option is selected.
        if len(payload.encode("utf-8")) > 300_000:
            for i in range(len(entries) - 1, -1, -1):
                path = f"data/visuals/{name}_{i}.json"
                target = ROOT / "docs" / "assets" / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(json.dumps(entries[i].pop("data"), ensure_ascii=False,
                                             separators=(",", ":")), encoding="utf-8")
                entries[i]["url"] = path
                payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
                if len(payload.encode("utf-8")) <= 300_000:
                    break
        static = "\n".join(line for line in examples[0]["static"].splitlines() if line.strip())
        text = (f'<div class="opv" data-kind="{examples[0]["kind"]}">\n'
                f'<script type="application/json">{payload}</script>\n'
                f'<div class="opv-static">\n{static}\n</div>\n</div>\n')
        if ZH_SNIPPETS.parent.is_dir():
            ZH_SNIPPETS.mkdir(parents=True, exist_ok=True)
            (ZH_SNIPPETS / f"vis_{name}.html").write_text(text, encoding="utf-8")
        english_entries = [{**entry, "description": {"en": entry["description"]["en"]}}
                           for entry in entries]
        english_payload = json.dumps({"examples": english_entries}, ensure_ascii=False,
                                     separators=(",", ":")).replace("</", "<\\/")
        english_text = text.replace(payload, english_payload, 1)
        (SNIPPETS / f"vis_{name}.html").write_text(english_text, encoding="utf-8")
        print(f"wrote vis_{name}.html ({len(text) // 1024} KiB; {len(entries)} examples)")


def pre(text: str) -> str:
    return f'<pre class="opv-pre">{html.escape(text)}</pre>'


def quiet(args: list[str]) -> None:
    with redirect_stdout(io.StringIO()):
        cli(args)


class Engine:
    """One operator set with its interpreter, renderer and reducer."""

    def __init__(self, settings: Settings, registry: OperatorRegistry) -> None:
        self.settings = settings
        self.registry = registry
        self.semantics = settings.semantics.build()
        self.oracle = Oracle(registry, settings.symbols, self.semantics)
        self.runtime = PythonRuntime(registry, self.semantics)
        self.parser = DefinitionParser(settings.symbols, registry)
        self.renderer = ExpressionRenderer(settings.symbols)

    def reducer(self) -> Reducer:
        return Reducer(self.registry, self.runtime, self.parser)

    def value(self, node, env=None):
        return self.oracle.evaluate_expr(to_ast(node), env or {}).value

    def text(self, node) -> str:
        return self.renderer.full(node)


def sample_inputs(op) -> list[tuple[int, ...]]:
    points = [(7, 3), (23, 5), (64, 12), (-9, 4)]
    return [p[: op.n_ary] for p in points]


def call_text(op, args) -> str:
    shown = [f"({a})" if a < 0 else str(a) for a in args]
    if op.n_ary == 2:
        return f"{shown[0]} {op.symbol} {shown[1]}"
    return f"{op.symbol} {shown[0]}" if op.unary_position == "prefix" else f"{shown[0]} {op.symbol}"


# ------------------------------------------------------------------ 1. growth
def growth(settings: Settings, layers: list[int] = LAYERS, seed: int = GROWTH_SEED) -> tuple[OperatorRegistry, dict]:
    """Grow the tour's operator set and record every candidate the generator judged."""
    registry = starting_registry()
    factory = OperatorFactory(settings, registry, random.Random(seed))
    events: list[dict] = []

    def rejected(op, reason, kind, layer):
        events.append({"t": "reject", "layer": layer, "kind": kind.split("_")[0], "reason": reason,
                       "symbol": op.symbol if op else None, "definition": op.definition if op else None})

    factory.on_reject = rejected
    build_layers(factory, layers, on_accept=lambda op: events.append({"t": "accept", "id": op.func_id}))

    engine = Engine(settings, registry)
    atoms = [op for op in registry if is_atom(op)]
    nodes = []
    for op in atoms:
        nodes.append({"id": op.func_id, "symbol": op.symbol, "layer": -1, "kind": "atom", "n": op.n_ary,
                      "pos": op.unary_position, "definition": None,
                      "rule": _rule(op), "deps": [], "samples": _samples(engine, op)})
    known = {op.func_id for op in atoms}
    for op in registry:
        if op.definition is None:
            continue
        nodes.append({"id": op.func_id, "symbol": op.symbol, "layer": op.recursive_layer, "kind": kind_of(op),
                      "n": op.n_ary, "pos": op.unary_position, "definition": op.definition,
                      "deps": [d for d in op.dependencies if d in known or d in registry],
                      "samples": _samples(engine, op)})
    reasons = Counter(e["reason"] for e in events if e["t"] == "reject")
    data = {"layers": layers, "seed": seed, "max_if_branches": MAX_IF_BRANCHES,
            "nodes": nodes, "events": events, "rejected": dict(reasons.most_common()),
            "accepted": dict(factory.stats.accepted)}
    return registry, data


def _rule(op) -> str:
    from opulse.core.primitives import rule_for

    return rule_for(base_operation_name(op.symbol, op.n_ary, op.unary_position))


def _samples(engine: Engine, op) -> list[dict]:
    return [{"call": call_text(op, args), "value": num(engine.oracle.evaluate(op, args).value)}
            for args in sample_inputs(op)]


# ------------------------------------------------------------------ 2. unfold
def tree_json(node, engine: Engine):
    """[label, kind, children]; kind is num / atom / simple / branch / recursive."""
    if isinstance(node, Number):
        return ["NaN" if node.value is NAN else str(node.value), "num", []]
    if isinstance(node, Variable):
        return [node.name, "var", []]
    op = node.operator
    return [op.symbol, "atom" if op.definition is None else kind_of(op),
            [tree_json(arg, engine) for arg in node.args], op.n_ary, op.unary_position]


def trace_payload(engine: Engine, tree, title: str) -> dict:
    trace = engine.reducer().reduce(tree)
    verify_trace(trace, engine.oracle)  # every step is re-checked by the reference interpreter
    frames = [{"tree": tree_json(trace.source, engine), "focus": None, "note": None}]
    for step in trace.steps:
        note = {"kind": step.kind, "symbol": step.operator.symbol, "inputs": [num(v) for v in step.inputs],
                "op": kind_of(step.operator), "branch": None if step.branch_index is None else step.branch_index + 1,
                "condition": step.condition, "reason": step.reason, "output": num(step.output)}
        frames.append({"tree": tree_json(step.expression_after, engine), "focus": list(step.path), "note": note,
                       "text": engine.text(step.expression_after)})
    frames[0]["text"] = engine.text(trace.source)
    used = {}
    for step in trace.steps:
        if step.operator.definition and step.operator.symbol not in used:
            used[step.operator.symbol] = step.operator.definition
    return {"title": title, "value": num(trace.value), "frames": frames, "definitions": used,
            "expands": sum(s.kind == "expand" for s in trace.steps),
            "evals": sum(s.kind == "eval" for s in trace.steps)}


def _size(tree) -> tuple[int, int]:
    """(leaves, depth) of a tree_json."""
    if not tree[2]:
        return 1, 1
    parts = [_size(c) for c in tree[2]]
    return sum(p[0] for p in parts), 1 + max(p[1] for p in parts)


def hard_tree(engine: Engine, long: bool = False):
    """Choose a finite nested question containing a branch and a recursive call."""
    recursive = [op for op in engine.registry if op.definition and kind_of(op) == "recursive" and op.n_ary == 1]
    branches = [op for op in engine.registry if op.definition and kind_of(op) == "branch" and op.n_ary == 1]
    simple = [op for op in engine.registry if op.definition and kind_of(op) == "simple" and op.n_ary == 1]
    plus = engine.registry.find("+", 2)
    for rec in recursive:
        for branch in branches:
            for value in (3, 5, 7, 9, 12):
                inside = Call(rec, (Number(value),))
                inside = Call(plus, (inside, Number(2)))
                inside = Call(branch, (inside,))
                inside = Call(rec, (inside,))
                inside = Call(plus, (inside, Number(1)))
                inside = Call(simple[0], (inside,))
                for _ in range(2 if long else 1):
                    inside = Call(branch, (inside,))
                    inside = Call(rec, (inside,))
                if engine.value(inside) is NAN:
                    continue
                trace = engine.reducer().reduce(inside)
                if not trace.truncated and (35 if long else 25) <= len(trace.steps) <= (100 if long else 70):
                    return inside
    raise RuntimeError("no finite hard expression with a checked long trace")


def unfold(engine: Engine, level: int = 0) -> dict:
    """A real verified reduction: an expression opens into its definitions down to atoms and
    folds back into its value."""
    from opulse.expression.generator import ExpressionGenerator, OperatorPool

    generator = ExpressionGenerator(engine.settings.expressions, random.Random(4 + level))
    pool = OperatorPool.from_registry(engine.registry)
    best = None
    for _ in range(4000 if level < 2 else 0):
        tree = generator.tree(pool, max_depth=2, atoms="number")
        if not isinstance(tree, Call) or tree.operator.definition is None:
            continue
        value = engine.value(tree)
        if value is NAN or value == 0:  # a zero result folds away too quietly to show
            continue
        trace = engine.reducer().reduce(tree)
        kinds = {kind_of(s.operator) for s in trace.steps if s.kind == "expand"}
        n = len(trace.steps)
        if not (14 <= n <= 30) or trace.truncated:
            continue
        sizes = [_size(tree_json(s.expression_after, engine)) for s in trace.steps]
        leaves, height = max(s[0] for s in sizes), max(s[1] for s in sizes)
        if leaves > 12 or height > 7:
            continue
        score = len(kinds) * 10 + (n if n <= 24 else 24 - n)
        if best is None or score > best[0]:
            best = (score, tree)
    tree = hard_tree(engine, level == 3) if level >= 2 else best[1]
    data = trace_payload(engine, tree, engine.text(tree))
    write_widget("unfold", "unfold", data,
                 pre("\n= ".join(f["text"] for f in data["frames"])))
    return data


# ------------------------------------------------------------------ 3a. contrast
def contrast(engine: Engine, level: int = 0) -> dict:
    """A real benchmark contrast pair: one definition swapped, a different reference answer, both
    re-derived from the prompt text alone."""
    from opulse.bench.check import answer_from_prompt, base_registry
    from opulse.bench.tasks import BenchBuilder

    builder = BenchBuilder(engine.settings, engine.registry, random.Random(2 + level),
                           max_depth=2 if level < 2 else 4, max_definitions=4 if level < 2 else 8)
    best = None
    for task in builder.tasks("contrast", 24 if level < 2 else 100):
        if task.axes["variant"] == "a":
            first = task
            continue
        pair = (first, task)
        size = sum(len(d) for d in first.definitions) + 3 * len(first.expression) + \
            (500 if len(first.definitions) < 2 else 0)
        calls = expression_calls(engine, first.expression)
        if level >= 2:
            kinds = {kind_of(op) for op in engine.registry if op.definition and op.symbol in first.expression}
            if not (5 <= calls <= 10 and {"branch", "recursive"} <= kinds):
                continue
        score = (-size,) if level < 2 else ((-abs(calls - 6), size) if level == 2 else (calls, size))
        if best is None or score > best[0]:
            best = (score, pair)
    a, b = best[1]
    base = base_registry(engine.registry)
    checked = [answer_from_prompt(t.to_dict(), base, engine.settings.symbols, engine.semantics) for t in (a, b)]
    swapped_a = next(d for d in a.definitions if d not in b.definitions)
    swapped_b = next(d for d in b.definitions if d not in a.definitions)
    rules = a.prompt.split("\nRules:\n", 1)[1].split("\n\n", 1)[0].splitlines()
    variants = []
    for task, value in ((a, checked[0]), (b, checked[1])):
        variants.append({"definitions": task.definitions, "answer": task.answer_text,
                         "rederived": "NaN" if value is NAN else str(value), "prompt": task.prompt})
    data = {"expression": a.expression, "rules": rules, "swapped": [swapped_a, swapped_b],
            "question": a.prompt.rsplit("\n\n", 1)[1], "variants": variants}
    write_widget("contrast", "contrast", data,
                 pre(a.prompt + f"\n\nreference answer: {a.answer_text}\n\nwith\n  {swapped_b}\n"
                     f"instead of\n  {swapped_a}\nthe reference answer is {b.answer_text}"))
    return data


# ------------------------------------------------------------------ 3b. step grading
def steps(engine: Engine, level: int = 0) -> dict:
    """The step checker on a correct derivation and on the same derivation with one slip."""
    from opulse.expression.generator import ExpressionGenerator, OperatorPool
    from opulse.trace.reducer import _replace_at
    from opulse.verify.steps import check_steps

    generator = ExpressionGenerator(engine.settings.expressions, random.Random(8 + level))
    pool = OperatorPool.from_registry(engine.registry, max_layer=0)
    best = None
    for _ in range(3000 if level < 2 else 0):
        tree = generator.tree(pool, max_depth=2, atoms="number")
        if not isinstance(tree, Call) or engine.value(tree) is NAN:
            continue
        trace = engine.reducer().reduce(tree)
        lines = [engine.text(s.expression_after) for s in trace.steps]
        evals = [i for i, s in enumerate(trace.steps) if s.kind == "eval" and 2 <= i < len(lines) - 2]
        if not (6 <= len(lines) <= 9) or not evals or not any(s.kind == "expand" for s in trace.steps):
            continue
        width = max(len(t) for t in lines)
        if best is None or width < best[0]:
            best = (width, tree, trace)
    if level >= 2:
        tree = hard_tree(engine, level == 3)
        trace = engine.reducer().reduce(tree)
        verify_trace(trace, engine.oracle)
    else:
        _, tree, trace = best

    def grade(lines: list[str], answer) -> list[dict]:
        rows, single = [], 0
        for k in range(1, len(lines) + 1):
            report = check_steps(tree, lines[:k], engine.parser, engine.registry, engine.oracle, answer)
            if report.first_error is not None:
                rows.append({"line": lines[k - 1], "status": "error", "message": report.errors[0]})
                rows += [{"line": t, "status": "skipped"} for t in lines[k:]]
                break
            rows.append({"line": lines[k - 1], "status": "single" if report.single_steps > single else "jump"})
            single = report.single_steps
        final = check_steps(tree, lines, engine.parser, engine.registry, engine.oracle, answer).to_dict()
        return rows, {k: final[k] for k in ("steps", "valid_steps", "first_error", "final_correct",
                                            "final_value_correct", "derivation_correct",
                                            "single_steps", "credit")}

    answer = trace.value
    good = [engine.text(s.expression_after) for s in trace.steps]
    # One slip: a computed value is written one too high, and the rest is derived from the slip.
    j = next(i for i, s in enumerate(trace.steps) if s.kind == "eval" and 2 <= i < len(good) - 2)
    step = trace.steps[j]
    slipped = _replace_at(step.expression_before, step.path, Number(step.output + 1))
    rest = engine.reducer().reduce(slipped)
    bad = good[:j] + [engine.text(slipped)] + [engine.text(s.expression_after) for s in rest.steps]
    good_rows, good_report = grade(good, answer)
    bad_rows, bad_report = grade(bad, answer)
    data = {"question": engine.text(tree), "answer": num(answer),
            "runs": [{"label": "correct derivation", "rows": good_rows, "report": good_report},
                     {"label": f"one slip on line {j + 1}", "rows": bad_rows, "report": bad_report,
                      "slip": j, "wrong_answer": num(rest.value)}]}
    write_widget("steps", "steps", data, pre(
        f"{data['question']}\n" + "\n".join(f"= {r['line']}   [{r['status']}]" for r in good_rows)
        + "\n\none slip:\n" + "\n".join(f"= {r['line']}   [{r['status']}{': ' + r['message'] if 'message' in r else ''}]"
                                        for r in bad_rows)))
    return data


# ------------------------------------------------------------------ 3c. solving for x
def solve(engine: Engine, ops_path: Path, level: int = 0) -> dict:
    """A real `opulse holes` record, with every x of the search domain evaluated forward."""
    from opulse.cli.holes import record as hole_record
    from opulse.solver.holes import HoleSolver

    rng = random.Random(3 + level)
    domain = (100, 300, 1000, 5000)[level]
    add = engine.registry.find("+", 2)
    tree = Number(7)
    for _ in range((2, 3, 5, 7)[level]):
        tree = Call(add, (tree, Number(rng.randint(1, 5))))
    path = (0,) * ((2, 3, 5, 7)[level])
    if level >= 2:
        recursive = next(op for op in engine.registry if op.definition and kind_of(op) == "recursive"
                         and op.n_ary == 1)
        branch = next(op for op in engine.registry if op.definition and kind_of(op) == "branch"
                      and op.n_ary == 1)
        constant = Call(recursive, (Call(branch, (Number(7),)),))
        assert engine.value(constant) is not NAN
        tree = Call(add, (tree, constant))
        path = (0,) + path
    problem = HoleSolver(None, engine.oracle, fallback_domain=(-domain, domain),
                         not_expressible_domain=None).problem(tree, path)
    assert problem is not None and problem.solutions.unique and problem.solutions.complete
    record = hole_record(problem, level, engine.renderer)
    tree = from_dict(record["tree"], engine.registry)
    lo, hi = record["domain"]
    lo, hi = max(lo, -60), min(hi, 60)  # the strip shows a window; the solver covered the whole domain
    scan = [{"x": x, "value": num(engine.value(tree, {"x": x}))} for x in range(lo, hi + 1)]
    hits = [c["x"] for c in scan if c["value"] == record["target"]]
    answer = record["answer"]
    check = trace_payload(engine, _substitute(tree, answer), "")
    data = {"expression": engine.text(tree), "target": record["target"], "answer": answer,
            "solutions": record["solutions"], "unique": record["unique"], "domain": record["domain"],
            "method": record["method"], "window": [lo, hi], "scan": scan, "hits": hits,
            "reverse": record["reverse"], "check_value": check["value"], "check_steps": len(check["frames"]) - 1}
    return data


def _substitute(node, value):
    if isinstance(node, Variable):
        return Number(value)
    if isinstance(node, Call):
        return Call(node.operator, tuple(_substitute(a, value) for a in node.args))
    return node


# ------------------------------------------------------------------ 3d. equivalence
def equivalence(engine: Engine, ops_path: Path, level: int = 0) -> dict:

    """Check six different equivalence shapes against one real operator set."""
    from opulse.core import BRANCH, RECURSIVE, Operator
    from opulse.solver.equivalence import EquivalenceChecker
    from opulse.solver.z3_encode import Z3Encoder

    # These four constructed operators join the operators grown for this profile.
    # Dummy code makes them resolvable; all values below come from their parsed definitions.
    registry = OperatorRegistry(list(engine.registry))
    definitions = (
        ("tourbranch1", "⊕", 2, None, BRANCH,
         "a ⊕ b = { a + b, if a < 0 and b > 0; a - b, if a >= 0 and b < 0; a * b, else }"),
        ("tourbranch2", "⊗", 2, None, BRANCH,
         "a ⊗ b = { a - b, if a >= 0 and b < 0; a + b, if a < 0 and b > 0; a * b, else }"),
        ("tourrec", "◈", 1, "prefix", RECURSIVE,
         "◈ a = { 0, if a == 0; (◈ (a - 1)) + 1, if a > 0 and a <= 8 }"),
        ("tourrare", "⊛", 2, None, BRANCH,
         "a ⊛ b = { (a + b) + 1, if a == 2 and b == -3; a + b, else }"),
    )
    for func_id, symbol, arity, position, kind, definition in definitions:
        args = "a" if arity == 1 else "a, b"
        registry.add(Operator(func_id, symbol, arity, position, definition=definition,
                              definition_type=kind,
                              op_compute_func=f"def op_{func_id}({args}):\n    return 0\n",
                              op_count_func=f"def op_count_{func_id}({args}):\n    return 0\n"))
    local = Engine(engine.settings, registry)
    add, sub = registry.find("+", 2), registry.find("-", 2)
    mul = registry.find("*", 2)
    square = next(op for op in registry if op.definition and "a * a" in op.definition)
    a, b = Variable("a"), Variable("b")

    pairs_to_check = (
        ("Inlining", "The square operator is replaced by its multiplication body.",
         Call(square, (a,)), Call(mul, (a, a)), "proved", None),
        ("Constant folding", "Adding zero and folding two constants leaves the same product.",
         Call(mul, (Call(add, (a, Number(0))),
                                   Call(add, (Number(2), Number(3))))),
         Call(mul, (a, Number(5))), "proved", None),
        ("Disjoint branches", "The two conditional cases can change order because they cannot both hold.",
         Call(registry.get("tourbranch1"), (a, b)),
         Call(registry.get("tourbranch2"), (a, b)), "proved", None),
        ("Bounded recursion", "The recursive operator counts from zero to its input on its full defined domain.",
         Call(registry.get("tourrec"), (a,)), a, "checked", [0, 8]),
        ("Rare interior input", "A single interior input activates an extra increment.",
         Call(registry.get("tourrare"), (a, b)),
         Call(add, (a, b)), "refuted", None),
        ("Value bound", "The intermediate sum becomes undefined at the value bound.",
         Call(sub, (Call(add, (a, b)), b)), a, "refuted", None),
    )
    labels_zh = {
        "Inlining": ("内联", "平方运算符展开后就是一次乘法。"),
        "Constant folding": ("常数折叠", "先加零，再合并两个常数，乘积保持不变。"),
        "Disjoint branches": ("互斥分支", "两个条件不可能同时成立，因此可以交换分支顺序。"),
        "Bounded recursion": ("有界递归", "递归运算符在完整的有定义区间内从零数到输入值。"),
        "Rare interior input": ("区间内部的特例", "只有一组内部输入会额外加一。"),
        "Value bound": ("数值上界", "中间的加法在数值上界变为未定义。"),
    }
    rules = {
        "Inlining": [square.definition],
        "Disjoint branches": [definitions[0][-1], definitions[1][-1]],
        "Bounded recursion": [definitions[2][-1]],
        "Rare interior input": [definitions[3][-1]],
    }
    checker = EquivalenceChecker(Z3Encoder(local.oracle), timeout_ms=10_000)
    pairs = []
    for kind, explanation, left, right, expected, checked_range in pairs_to_check:
        if checked_range is None:
            verdict = checker.check(left, right)
            assert verdict.status == expected, (kind, verdict)
            status, counterexample = verdict.status, verdict.counterexample
            left_value, right_value = num(verdict.left_value), num(verdict.right_value)
        else:
            assert all(local.value(left, {"a": x}) == local.value(right, {"a": x})
                       for x in range(checked_range[0], checked_range[1] + 1))
            status, counterexample, left_value, right_value = "checked", None, None, None
        grid = []
        axes = [0, 8] if checked_range else [-4, 4]
        for x in range(axes[0], axes[1] + 1):
            for y in range(-4, 5):
                env = {"a": x, "b": y}
                grid.append([x, y, num(local.value(left, env)), num(local.value(right, env))])
        pairs.append({"kind": kind, "kind_zh": labels_zh[kind][0],
                      "explanation": explanation, "explanation_zh": labels_zh[kind][1],
                      "status": status,
                      "method": "exhaustive" if checked_range else
                      "z3 proof" if status == "proved" else "interpreter checked counterexample",
                      "range": checked_range, "axes": axes, "rules": rules.get(kind, []),
                      "left": local.text(left),
                      "right": local.text(right), "counterexample": counterexample,
                      "left_value": left_value, "right_value": right_value, "grid": grid})
    data = {"bound": engine.semantics.bound, "pairs": pairs,
            "definitions": [item[-1] for item in definitions]}

    write_widget("equivalence", "equiv", data, pre("\n".join(
        f"{p['kind']} ({p['method']}{' on ' + str(p['range']) if p['range'] else ''}): "
        f"{p['left']}  ==  {p['right']}  ->  {p['status']}"
        + (f"  counterexample {p['counterexample']}: {p['left_value']} vs {p['right_value']}"
           if p["counterexample"] else "") for p in pairs)))
    return data


# ------------------------------------------------------------------ 3e. edit propagation
def ripple(engine: Engine, level: int = 0) -> dict:
    """Edit one low-level definition and recompute every operator from the edited text."""
    from opulse.bench.check import base_registry, prompt_registry

    registry = engine.registry
    defined = [op for op in registry if op.definition]
    texts = [op.definition for op in defined]
    base = base_registry(registry)
    users: dict[str, set[str]] = {op.func_id: set() for op in registry}
    for op in defined:
        for dep in op.dependencies:
            if dep != op.func_id and dep in users:
                users[dep].add(op.func_id)

    def dependents(fid):
        dist, queue = {fid: 0}, deque([fid])
        while queue:
            cur = queue.popleft()
            for user in users[cur]:
                if user not in dist:
                    dist[user] = dist[cur] + 1
                    queue.append(user)
        return dist

    swaps = [(" + ", " - "), (" - ", " + "), (" * ", " + "), (" + ", " * "), (" % ", " / "), (" / ", " % ")]
    original = prompt_registry(texts, base, engine.settings.symbols, engine.semantics)
    best = None
    for op in defined:
        if op.recursive_layer != 0:
            continue
        dist = dependents(op.func_id)
        lhs, body = op.definition.split(" = ", 1)
        for old, new in swaps:
            if old not in body:
                continue
            edited_def = f"{lhs} = {body.replace(old, new, 1)}"
            edited = prompt_registry([edited_def if t == op.definition else t for t in texts], base,
                                     engine.settings.symbols, engine.semantics)
            for point in ((6, 4), (5, 3), (9, 2), (12, 7)):
                rows = _ripple_values(defined, original, edited, dist, point)
                changed = sum(r["changed"] for r in rows)
                defined_share = sum(r["new"] is not None for r in rows)
                score = ((max(dist.values()), changed, defined_share) if level >= 2 else
                         (changed, defined_share, len(dist)))
                if best is None or score > best[0]:
                    best = (score, op, edited_def, dist, point, rows)
    _, op, edited_def, dist, point, rows = best
    nodes = []
    by_id = {o.func_id: o for o in defined}
    for row in rows:
        o = by_id[row["id"]]
        row.update(symbol=o.symbol, layer=o.recursive_layer, kind=kind_of(o), definition=o.definition,
                   deps=[d for d in o.dependencies if d in dist and d != o.func_id],
                   self_loop=o.func_id in o.dependencies)
        nodes.append(row)
    data = {"edited": op.func_id, "before": op.definition, "after": edited_def, "point": list(point),
            "nodes": sorted(nodes, key=lambda n: (n["distance"], n["layer"]))}
    write_widget("ripple", "ripple", data, pre(
        f"edit:  {op.definition}\n   ->  {edited_def}\n\n" + "\n".join(
            f"{n['call']:<16} {n['old']!s:>12} -> {n['new']!s:<12} {'changed' if n['changed'] else 'same'}"
            for n in data["nodes"])))
    return data


def _ripple_values(defined, original, edited, dist, point):
    rows = []
    for op in defined:
        if op.func_id not in dist:
            continue
        args = point[: op.n_ary]
        before = original.oracle.evaluate(original.registry.find(op.symbol, op.n_ary, op.unary_position), args).value
        after = edited.oracle.evaluate(edited.registry.find(op.symbol, op.n_ary, op.unary_position), args).value
        rows.append({"id": op.func_id, "distance": dist[op.func_id], "call": call_text(op, args),
                     "old": num(before), "new": num(after),
                     "changed": not ((before is NAN and after is NAN) or before == after)})
    return rows


# ------------------------------------------------------------------ 3f. operator frequency
FREQUENCIES = ("uniform", "zipf:1", "zipf:2")


def frequency(engine: Engine, ops_path: Path, level: int = 0) -> dict:
    """Operator usage in expressions sampled with each --operator-frequency."""
    from opulse.expression.generator import OperatorPool

    count = (100, 200, 400, 600)[level]
    ranking = OperatorPool.from_registry(engine.registry).frequency_ranking(0)
    order = [fid for kind in ("binary", "prefix", "postfix") for fid in ranking[kind]]
    groups = {fid: kind for kind in ranking for fid in ranking[kind]}
    series = []
    for spec in FREQUENCIES:
        out = WORK / f"expressions_{spec.replace(':', '_')}.jsonl"
        quiet(["expressions", "--operators", str(ops_path), "--out", str(out), "--count", str(count),
               "--seed", "11", "--operator-frequency", spec, "--keep-undefined"])
        records = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
        # cumulative usage of each defined operator after every 20 expressions
        totals, snapshots, base_calls, all_calls = Counter(), [], 0, 0
        for i, record in enumerate(records, 1):
            for step in record["steps"]:
                all_calls += 1
                if step["func_id"] in groups:
                    totals[step["func_id"]] += 1
                else:
                    base_calls += 1
            if i % 20 == 0:
                snapshots.append([totals[f] for f in order])
        series.append({"spec": spec, "snapshots": snapshots, "expressions": len(records),
                       "base_share": round(base_calls / all_calls, 3),
                       "sample": [{"expression": r["expression"], "value": r["result"]}
                                  for r in (records[0], records[len(records) // 2], records[-1])]})
    by_id = {op.func_id: op for op in engine.registry}
    data = {"operators": [{"symbol": by_id[f].symbol, "group": groups[f]} for f in order],
            "every": 20, "series": series}
    head = "operator  " + "  ".join(f"{s['spec']:>8}" for s in series)
    rows = [f"{by_id[f].symbol:<9} " + "  ".join(f"{s['snapshots'][-1][i]:>8}" for s in series)
            for i, f in enumerate(order)]
    write_widget("frequency", "freq", data, pre("\n".join([head] + rows)))
    return data


# ------------------------------------------------------------------ main
def main() -> int:
    global PROFILE, ENGINE
    EXAMPLES.clear()
    SNIPPETS.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    base = Settings.load(DEFAULT_CONFIG)
    settings = replace(base, operators=replace(base.operators, max_if_branches=MAX_IF_BRANCHES))
    import time
    for PROFILE, (_, layers, seed) in enumerate(PROFILES):
        registry, _ = growth(settings, layers, seed)
        ops_path = WORK / f"operators_{PROFILE}.jsonl"
        registry.to_jsonl(ops_path)
        engine = Engine(base, OperatorRegistry.from_jsonl(ops_path))
        ENGINE = engine
        for build in (unfold, contrast, steps, ripple):
            start = time.time()
            build(engine, PROFILE)
            print(f"  {PROFILE} {build.__name__}: {time.time() - start:.1f}s", flush=True)
        for build in (frequency, equivalence):
            if build is equivalence and PROFILE != 0:
                continue
            start = time.time()
            build(engine, ops_path, PROFILE)
            print(f"  {PROFILE} {build.__name__}: {time.time() - start:.1f}s", flush=True)
    ENGINE = None
    write_collected()
    return 0


if __name__ == "__main__":
    sys.exit(main())
