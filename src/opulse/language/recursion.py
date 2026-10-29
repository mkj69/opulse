"""What the structure of a recursive definition says about its recursion.

Nothing here depends on a template. From the parsed definition the analysis reads:

* the **self-calls**: every application of the operator to itself, and the case it occurs in;
* the **arguments** each self-call passes for each parameter that changes;
* the **control expressions**: the expressions compared with constants in the guards;
* a **measure**: a candidate ``|e|`` (a control expression or a changing parameter) that is a
  nonnegative integer and strictly smaller at every self-call than in the calling frame,
  whenever that self-call is reached with defined arguments. z3 proves this over the value
  domain; when z3 cannot decide, the claim is checked on a range of inputs and stated as such;
* a **bound** on the nesting depth: with the measure ``μ``, at most ``max μ - min μ + 1``
  nested self-calls happen, where max and min run over inputs that take a recursive case.

The result says plainly what was established. :meth:`RecursionFacts.sentences` never returns
an empty text for a recursive definition: when no measure is found it says so.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

import z3

from opulse.config import Symbols
from opulse.core.semantics import NAN
from opulse.definition import ast
from opulse.language.ir import Concept, OperatorRef
from opulse.solver.z3_encode import NotExpressible, ZVal

PROVED, CHECKED, REFUTED = "proved", "checked", "refuted"


@dataclass
class Measure:
    expression: ast.Expr  # the measure is |expression|
    status: str  # proved | checked
    range: tuple[int, int] | None = None  # for "checked": the inputs tried
    depth: int | None = None  # bound on nested self-calls
    depth_status: str | None = None  # proved | checked


@dataclass
class RecursionFacts:
    operator: OperatorRef
    recursive_cases: list[int]
    base_cases: list[int]
    steps: list[tuple[int, str, ast.Expr]]  # (case, parameter, argument) for changed parameters
    controls: list[ast.Expr]
    measure: Measure | None
    candidates: list[ast.Expr] = field(default_factory=list)
    nan_stops: bool = False  # a NaN argument makes the first comparison NaN

    def sentences(self, lhs: str, symbols: Symbols, lang: str = "en") -> str:
        render = lambda e: f"`{ast.render_expr(e, symbols)}`"
        cases = lambda xs: _cases(xs, lang)
        lines = []
        steps = ("; " if lang == "en" else "；").join(
            f"{render(arg)} for {name} (case {case})" if lang == "en" else f"情形 {case} 中 {name} 换成 {render(arg)}"
            for case, name, arg in self.steps)
        if lang == "en":
            base = self.base_cases
            lines.append(f"Recursion: {lhs} calls itself in {cases(self.recursive_cases)}"
                         + (f"; {cases(base)} {'makes' if len(base) == 1 else 'make'} no self-call." if base else "."))
            if steps:
                lines.append(f"Each self-call passes {steps}.")
            if self.controls:
                lines.append(f"The guards compare {', '.join(render(c) for c in self.controls)} with constants.")
        else:
            lines.append(f"递归：{lhs} 在{cases(self.recursive_cases)}中调用自身"
                         + (f"；{cases(self.base_cases)}不调用自身。" if self.base_cases else "。"))
            if steps:
                lines.append(f"自调用的参数：{steps}。")
            if self.controls:
                lines.append(f"条件把 {'、'.join(render(c) for c in self.controls)} 与常数比较。")
        measure = self.measure
        if measure is None:
            tried = ", ".join(f"|{ast.render_expr(c, symbols)}|" for c in self.candidates) or "none"
            lines.append(f"No decreasing measure was found among the candidates {tried}; this analysis does not "
                         "establish that the recursion stops." if lang == "en" else
                         f"在候选量 {tried} 中没有找到递减的度量；本分析不能确定递归会停止。")
            return " ".join(lines)
        size = f"|{ast.render_expr(measure.expression, symbols)}|"
        how = ("proved by z3 over the value domain" if measure.status == PROVED else
               f"checked on every input in [{measure.range[0]}, {measure.range[1]}]")
        how_zh = ("由 z3 在整个取值范围上证明" if measure.status == PROVED else
                  f"在 [{measure.range[0]}, {measure.range[1]}] 的全部输入上检验")
        if lang == "en":
            lines.append(f"The measure `{size}` is a nonnegative integer that is strictly smaller at every self-call "
                         f"with defined arguments ({how}), so the recursion stops.")
        else:
            lines.append(f"度量 `{size}` 是非负整数，在每次参数有定义的自调用中严格减小（{how_zh}），因此递归会停止。")
        if measure.depth is not None:
            proof = "proved" if measure.depth_status == PROVED else "observed on the checked inputs"
            proof_zh = "已证明" if measure.depth_status == PROVED else "在检验的输入上观察到"
            lines.append(f"At most {measure.depth} nested self-calls happen ({proof})." if lang == "en" else
                         f"自调用最多嵌套 {measure.depth} 层（{proof_zh}）。")
        if self.nan_stops:
            lines.append("A NaN argument makes the first comparison NaN, so such a call is NaN at once."
                         if lang == "en" else "参数为 NaN 时第一个比较即为 NaN，该调用立即为 NaN。")
        return " ".join(lines)


def _cases(numbers: list[int], lang: str) -> str:
    """``case 1``, ``cases 2 and 3``, ``cases 1, 2 and 4`` (Chinese: ``情形 2 和 3``)."""
    items = [str(n) for n in numbers]
    joined = items[0] if len(items) == 1 else ", ".join(items[:-1]) + (" and " if lang == "en" else " 和 ") + items[-1]
    if lang == "en":
        return f"case {joined}" if len(items) == 1 else f"cases {joined}"
    return f"情形 {joined} "


def analyse(operator, definition: ast.Definition, oracle, timeout_ms: int = 3000,
            check_range: int = 60) -> RecursionFacts | None:
    """Recursion facts of ``operator`` (None when it never calls itself)."""
    concept = Concept.of(definition)
    calls = concept.self_calls()
    if not calls:
        return None
    params = concept.parameters
    recursive = sorted({case.index for case, _ in calls})
    base = [case.index for case in concept.cases if case.index not in recursive]
    steps = []
    for case, apply in calls:
        for name, arg in zip(params, apply.args):
            if arg != ast.Var(name) and (case.index, name, arg) not in steps:
                steps.append((case.index, name, arg))
    controls = []
    for case in concept.cases:
        if case.guard is None:
            continue
        for compare in _compares(case.guard):
            for side, other in ((compare.left, compare.right), (compare.right, compare.left)):
                if _constant(other) and not _constant(side) and side not in controls:
                    controls.append(side)
    changed = [ast.Var(name) for _, name, _ in steps]
    candidates = list(dict.fromkeys(controls + changed))
    first_reads = _first_compare_reads(concept)
    nan_stops = bool(steps) and all(name in first_reads for _, name, _ in steps)
    measures = []
    for candidate in candidates:
        measure = _measure(operator, concept, candidate, calls, oracle, timeout_ms, check_range)
        if measure is not None:
            measures.append(measure)
            if measure.status == PROVED and measure.depth_status == PROVED:
                break
    rank = {PROVED: 0, CHECKED: 1, None: 2}
    measures.sort(key=lambda m: (rank[m.status], rank[m.depth_status],
                                 m.depth if m.depth is not None else float("inf")))
    return RecursionFacts(OperatorRef.of(definition.lhs), recursive, base, steps, controls,
                          measures[0] if measures else None, candidates, nan_stops)


def _compares(node: ast.Condition):
    if isinstance(node, ast.Compare):
        yield node
    elif isinstance(node, ast.Not):
        yield from _compares(node.operand)
    else:
        yield from _compares(node.left)
        yield from _compares(node.right)


def _constant(node: ast.Expr) -> bool:
    if isinstance(node, (ast.Num, ast.NaN)):
        return True
    if isinstance(node, ast.Var):
        return False
    return all(_constant(arg) for arg in node.args)


def _first_compare_reads(concept: Concept) -> set[str]:
    for case in concept.cases:
        if case.guard is None:
            return set()
        compare = next(_compares(case.guard))
        return ast.free_variables(compare.left) | ast.free_variables(compare.right)
    return set()


# ------------------------------------------------------------------ the measure


def _measure(operator, concept: Concept, candidate: ast.Expr, calls, oracle, timeout_ms: int,
             check_range: int) -> Measure | None:
    proved = _prove_decrease(operator, concept, candidate, calls, oracle, timeout_ms)
    if proved is False:
        return None
    if proved is True:
        depth = _prove_depth(operator, concept, candidate, oracle, timeout_ms)
        if depth is not None:
            return Measure(candidate, PROVED, depth=depth, depth_status=PROVED)
        observed = _check(operator, concept, candidate, calls, oracle, check_range)
        return Measure(candidate, PROVED, depth=observed[1] if observed else None,
                       depth_status=CHECKED if observed else None)
    observed = _check(operator, concept, candidate, calls, oracle, check_range)
    if observed is None or not observed[0]:
        return None
    return Measure(candidate, CHECKED, (-check_range, check_range), observed[1], CHECKED)


def _check(operator, concept: Concept, candidate, calls, oracle, radius: int):
    """(decreases on every input in [-radius, radius], largest nesting observed)."""
    from opulse.language.views.examples import select_case

    definition = concept.definition()
    params = concept.parameters
    by_case: dict[int, list] = {}
    for case, apply in calls:
        by_case.setdefault(case.index, []).append(apply)
    values = []
    for point in itertools.product(range(-radius, radius + 1), repeat=len(params)):
        env = dict(zip(params, point))
        case = select_case(definition, env, oracle)
        if case not in by_case:
            continue
        old = oracle.evaluate_expr(candidate, env).value
        if old is NAN:
            return None
        values.append(abs(old))
        for apply in by_case[case]:
            args = [oracle.evaluate_expr(arg, env).value for arg in apply.args]
            if any(arg is NAN for arg in args):
                continue
            new = oracle.evaluate_expr(candidate, dict(zip(params, args))).value
            if new is NAN or abs(new) >= abs(old):
                return (False, None)
    depth = (max(values) - min(values) + 1) if values else 0
    return (True, depth)


def _frame(oracle, operator, concept: Concept):
    from opulse.solver.z3_encode import Z3Encoder

    encoder = Z3Encoder(oracle)
    if not encoder.expressible(operator):
        raise NotExpressible("the operator uses atoms without a z3 encoding")
    xs = [z3.Int(f"{name}_0") for name in concept.parameters]
    env = {name: ZVal(z3.BoolVal(True), x) for name, x in zip(concept.parameters, xs)}
    return encoder, xs, env


def _paths(encoder, operator, concept: Concept, env: dict):
    """For each case: the z3 condition under which the case is taken (no earlier case applies,
    no comparison reads NaN, its own guard holds)."""
    paths = {}
    earlier = []
    for case in concept.cases:
        if case.guard is None:
            paths[case.index] = z3.And(*earlier) if earlier else z3.BoolVal(True)
            break
        abort, truth = encoder._condition(case.guard, env, operator, 0, {})
        paths[case.index] = z3.And(*earlier, z3.Not(abort), truth)
        earlier += [z3.Not(abort), z3.Not(truth)]
    return paths


def _size(encoder, operator, node: ast.Expr, env: dict) -> ZVal:
    value = encoder._expr(node, env, operator, 0, {})
    return ZVal(value.defined, z3.If(value.value >= 0, value.value, -value.value))


def _prove_decrease(operator, concept: Concept, candidate, calls, oracle, timeout_ms: int):
    """True (proved), False (z3 found a counterexample) or None (undecided / not encodable)."""
    try:
        encoder, xs, env = _frame(oracle, operator, concept)
        encoder.reset()
        paths = _paths(encoder, operator, concept, env)
        old = _size(encoder, operator, candidate, env)
        problems = []
        for case, apply in calls:
            if any(OperatorRef.of(a) == concept.operator for arg in apply.args
                   for a in ast.iter_applications(arg)):
                return None  # nested self-calls in arguments: out of scope
            args = [encoder._expr(arg, env, operator, 0, {}) for arg in apply.args]
            inner = dict(zip(concept.parameters, args))
            new = _size(encoder, operator, candidate, inner)
            defined = z3.And(*[arg.defined for arg in args])
            problems.append(z3.And(paths[case.index], defined,
                                   z3.Or(z3.Not(old.defined), z3.Not(new.defined), new.value >= old.value)))
    except NotExpressible:
        return None
    solver = z3.Solver()
    solver.set("timeout", timeout_ms)
    solver.add(*[encoder.in_bound(x) for x in xs], z3.Or(*problems))
    result = solver.check()
    if result == z3.unsat:
        return True
    if result == z3.sat:
        return False
    return None


def _prove_depth(operator, concept: Concept, candidate, oracle, timeout_ms: int) -> int | None:
    """``max μ - min μ + 1`` over inputs that take a recursive case, both proved by z3."""
    try:
        encoder, xs, env = _frame(oracle, operator, concept)
        encoder.reset()
        paths = _paths(encoder, operator, concept, env)
        recursive = {case.index for case, _ in concept.self_calls()}
        taken = z3.Or(*[paths[i] for i in recursive if i in paths])
        size = _size(encoder, operator, candidate, env)
    except NotExpressible:
        return None
    base = [encoder.in_bound(x) for x in xs] + [taken, size.defined]
    top = encoder.bound or 2**31 - 1
    high = _extreme(base, size.value, top, timeout_ms, largest=True)
    low = _extreme(base, size.value, top, timeout_ms, largest=False)
    if high is None or low is None:
        return None
    return high - low + 1


def _extreme(constraints, value, top: int, timeout_ms: int, largest: bool) -> int | None:
    """The largest (smallest) ``value`` in [0, top] under ``constraints``, by bisection."""
    solver = z3.Solver()
    solver.set("timeout", timeout_ms)
    solver.add(*constraints)
    if solver.check() != z3.sat:
        return None
    lo, hi = 0, top
    for _ in range(64):
        if lo >= hi:
            return lo
        mid = (lo + hi + (1 if largest else 0)) // 2
        solver.push()
        solver.add(value >= mid if largest else value <= mid)
        result = solver.check()
        solver.pop()
        if result == z3.unknown:
            return None
        if largest:
            lo, hi = (mid, hi) if result == z3.sat else (lo, mid - 1)
        else:
            lo, hi = (lo, mid) if result == z3.sat else (mid + 1, hi)
    return None
