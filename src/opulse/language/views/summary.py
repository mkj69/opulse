"""Summary facts of an operator, each with how it was established.

* **closed forms**: for a case whose body (with simple callees inlined) is arithmetic, SymPy
  proposes an expanded form; it is reported only when z3 proves it equal to the body under
  Opulse semantics (:class:`opulse.solver.equivalence.EquivalenceChecker`);
* **properties**: algebraic laws that :class:`opulse.solver.properties.PropertyChecker` proves;
* **range**: the smallest and largest value seen on the sampled inputs, each proved to be the
  global extreme by z3 when possible, and whether the operator can be NaN;
* **recursion**: :mod:`opulse.language.recursion` for recursive definitions.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

import z3

from opulse.config import Symbols
from opulse.core.operator import Operator
from opulse.core.semantics import NAN
from opulse.definition import ast
from opulse.expression.nodes import from_ast, to_ast
from opulse.language.ir import Concept, OperatorRef, has_search, substitute
from opulse.language.views.code import sample_inputs
from opulse.solver.z3_encode import NotExpressible, ZVal
from opulse.verify.differential import literals

PROVED, OBSERVED = "proved", "observed"


@dataclass
class Bound:
    value: int
    status: str  # proved | observed
    witness: tuple[int, ...]


@dataclass
class Summary:
    lhs: str
    closed_forms: list[tuple[int | None, str]] = field(default_factory=list)  # (case or None, text)
    properties: dict[str, dict] = field(default_factory=dict)
    low: Bound | None = None
    high: Bound | None = None
    nan: str = "unknown"  # never (proved) | observed | unknown
    nan_witness: tuple[int, ...] | None = None
    sampled: int = 0
    recursion: object = None  # RecursionFacts

    def text(self, symbols: Symbols, lang: str = "en") -> str:
        lines = []
        for case, form in self.closed_forms:
            where = f"case {case} of " if case is not None else ""
            lines.append(f"- Closed form: {where}`{self.lhs}` equals `{form}` (proved by z3)." if lang == "en" else
                         f"- 闭式：`{self.lhs}`{'的情形 ' + str(case) if case is not None else ''}等于 `{form}`（z3 已证明）。")
        proved = [name for name, verdict in self.properties.items() if verdict.get("status") == PROVED]
        for name in proved:
            witness = self.properties[name].get("witness")
            extra = f" with element {witness}" if witness is not None else ""
            lines.append(f"- Property: {name.replace('_', ' ')}{extra} (proved by z3)." if lang == "en" else
                         f"- 性质：{name}{'，元素 ' + str(witness) if witness is not None else ''}（z3 已证明）。")
        for label, bound in (("smallest", self.low), ("largest", self.high)):
            if bound is None:
                continue
            how = "proved" if bound.status == PROVED else f"observed on {self.sampled} inputs"
            point = ", ".join(map(str, bound.witness))
            if lang == "en":
                lines.append(f"- The {label} value is {bound.value}, at ({point}) ({how}).")
            else:
                how_zh = "已证明" if bound.status == PROVED else f"在 {self.sampled} 个输入上观察到"
                lines.append(f"- {'最小值' if label == 'smallest' else '最大值'}为 {bound.value}，在 ({point}) 取到（{how_zh}）。")
        nan = symbols.nan
        if self.nan == "never":
            lines.append(f"- The value is never {nan} on the value domain (proved by z3)." if lang == "en" else
                         f"- 在整个取值范围上值都不是 {nan}（z3 已证明）。")
        elif self.nan == OBSERVED:
            point = ", ".join(map(str, self.nan_witness))
            lines.append(f"- The value is {nan} at ({point})." if lang == "en" else f"- 在 ({point}) 处值为 {nan}。")
        if self.recursion is not None:
            lines.append("- " + self.recursion.sentences(f"`{self.lhs}`", symbols, lang))
        if not lines:
            return "No summary facts were established." if lang == "en" else "没有得到可证明的概括事实。"
        return "\n".join(lines)


def summarize(operator: Operator, definition: ast.Definition, oracle, symbols: Symbols, timeout_ms: int = 3000,
              properties: bool = True, seed: int = 0) -> Summary:
    from opulse.language.recursion import analyse

    summary = Summary(ast.render_expr(definition.lhs, symbols))
    concept = Concept.of(definition)
    summary.closed_forms = _closed_forms(operator, concept, oracle, symbols, timeout_ms)
    encoder = _encoder(oracle, operator)
    if properties and encoder is not None:
        from opulse.solver.properties import PropertyChecker

        checker = PropertyChecker(encoder, timeout_ms=timeout_ms)
        summary.properties = checker.check_all(operator)
    _range(summary, operator, definition, oracle, encoder, timeout_ms, seed)
    summary.recursion = analyse(operator, definition, oracle, timeout_ms)
    return summary


def _encoder(oracle, operator):
    from opulse.solver.z3_encode import Z3Encoder

    try:
        encoder = Z3Encoder(oracle)
    except NotExpressible:
        return None
    return encoder if encoder.expressible(operator) else None


def _inline(node: ast.Expr, oracle, self_ref: OperatorRef, depth: int = 0) -> ast.Expr:
    """Replace applications of single-expression definitions by their bodies."""
    if not isinstance(node, ast.Apply):
        return node
    args = tuple(_inline(arg, oracle, self_ref, depth) for arg in node.args)
    ref = OperatorRef.of(node)
    callee = oracle._resolve(node)
    if callee.definition is None or ref == self_ref or depth > 8:
        return ast.Apply(node.symbol, args, node.unary_position)
    callee_concept = Concept.of(oracle._definition_of(callee))
    if not callee_concept.single:
        return ast.Apply(node.symbol, args, node.unary_position)
    body = substitute(callee_concept.cases[0].body,
                      {ast.Var(name): arg for name, arg in zip(callee_concept.parameters, args)})
    return _inline(body, oracle, self_ref, depth + 1)


def _closed_forms(operator, concept: Concept, oracle, symbols: Symbols, timeout_ms: int):
    from opulse.solver.equivalence import EquivalenceChecker, sympy_candidate
    from opulse.solver.z3_encode import Z3Encoder

    forms = []
    if concept.recursive:
        cases = [case for case in concept.cases
                 if not any(OperatorRef.of(a) == concept.operator for a in ast.iter_applications(case.body))]
    else:
        cases = list(concept.cases)
    for case in cases:
        if has_search(case.body):
            continue
        inlined = _inline(case.body, oracle, concept.operator)
        if has_search(inlined):
            continue
        try:
            node = from_ast(inlined, oracle.registry)
            candidate = sympy_candidate(node, oracle.registry)
        except (LookupError, ValueError):
            continue
        if candidate is None:
            continue
        simplified = to_ast(candidate)
        if simplified == case.body or simplified == inlined:
            continue
        try:
            checker = EquivalenceChecker(Z3Encoder(oracle), timeout_ms=timeout_ms)
            verdict = checker.check(from_ast(case.body, oracle.registry), candidate)
        except NotExpressible:
            continue
        if verdict.status == PROVED:
            forms.append((None if concept.single else case.index, ast.render_expr(simplified, symbols)))
    return forms


def _reachable_literals(operator, oracle) -> set[int]:
    found: set[int] = set()
    seen: set[str] = set()
    stack = [operator]
    while stack:
        op = stack.pop()
        if op.func_id in seen or op.definition is None:
            continue
        seen.add(op.func_id)
        definition = oracle._definition_of(op)
        found |= literals(definition)
        for branch in definition.branches:
            for node in (branch.expr, branch.condition):
                if node is not None:
                    stack += [oracle._resolve(apply) for apply in ast.iter_applications(node)]
    return found


def _range(summary: Summary, operator, definition, oracle, encoder, timeout_ms: int, seed: int) -> None:
    rng = random.Random(seed)
    arity = len(definition.parameters)
    points = sample_inputs(arity, oracle.semantics.bound, literals(definition), rng)
    summary.sampled = len(points)
    low = high = None
    for point in points:
        value = oracle.evaluate(operator, point).value
        if value is NAN:
            if summary.nan_witness is None:
                summary.nan, summary.nan_witness = OBSERVED, point
            continue
        if low is None or value < low[0]:
            low = (value, point)
        if high is None or value > high[0]:
            high = (value, point)
    if low is not None:
        # Inputs and base-operation results lie in [-B, B]; when no literal of the definitions
        # involved is larger, so does every value, and an observed -B or B is the extreme.
        bound = oracle.semantics.bound
        if bound is not None and max(map(abs, _reachable_literals(operator, oracle)), default=0) > bound:
            bound = None
        summary.low = Bound(low[0], PROVED if bound is not None and low[0] == -bound else OBSERVED, low[1])
        summary.high = Bound(high[0], PROVED if bound is not None and high[0] == bound else OBSERVED, high[1])
    if encoder is None:
        return
    try:
        encoder.reset()
        xs = [z3.Int(f"x{i}") for i in range(arity)]
        result = encoder._apply(operator, [ZVal(z3.BoolVal(True), x) for x in xs], 0)
    except NotExpressible:
        return
    domain = [encoder.in_bound(x) for x in xs]

    def unsat(*extra) -> bool:
        solver = z3.Solver()
        solver.set("timeout", timeout_ms)
        solver.add(*domain, *extra)
        return solver.check() == z3.unsat

    if summary.low is not None and unsat(result.defined, result.value < summary.low.value):
        summary.low.status = PROVED
    if summary.high is not None and unsat(result.defined, result.value > summary.high.value):
        summary.high.status = PROVED
    if summary.nan_witness is None and unsat(z3.Not(result.defined)):
        summary.nan = "never"


__all__ = ["Bound", "Summary", "summarize"]
