"""Step-by-step reduction of an expression by unfolding operator definitions.

Strategy: applicative order, leftmost-innermost. At each step the reducer
picks the leftmost operator application whose arguments are all numbers
(the *focus*) and rewrites it:

* ``eval``   - a primitive operator (no definition), or an operator the caller
  chose not to unfold, is replaced by its computed value;
* ``expand`` - a defined operator is replaced by the body of the branch whose
  condition holds, with the parameters substituted by the argument values;
* ``undefined`` - a branch condition compared NaN, or no branch matched: the
  focus becomes NaN (docs/reference/semantics.md section 4, rules 2-3).

Recursive operators simply expand again on the next steps, so the trace
shows the recursion unfolding. The final number always equals the value the
compiled function returns (tests check this).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from opulse.core.operator import Operator
from opulse.core.registry import OperatorRegistry
from opulse.core.semantics import NAN
from opulse.definition import ast
from opulse.definition.ast import render_condition
from opulse.definition.codegen import registry_resolver
from opulse.definition.interpreter import COMPARISONS
from opulse.definition.parser import DefinitionParser
from opulse.expression.nodes import Call, Node, Number, Variable

Path = tuple[int, ...]  # child indices from the root


@dataclass(frozen=True)
class TraceStep:
    index: int
    kind: str  # "expand" | "eval" | "undefined"
    path: Path
    operator: Operator
    inputs: tuple[int, ...]
    before: Node  # the focus subtree
    after: Node  # what replaced it
    expression_before: Node
    expression_after: Node
    branch_index: int | None = None
    condition: str | None = None  # the chosen condition with values substituted
    reason: str | None = None  # for "undefined": "nan_condition" or "no_branch"
    depth: int = 0  # how many unfoldings produced the focus (0: written in the expression)
    search_attempts: str | None = None  # trials of searches inside an expanded body

    @property
    def output(self):
        return self.after.value if isinstance(self.after, Number) else None


@dataclass
class Trace:
    source: Node
    steps: list[TraceStep] = field(default_factory=list)
    truncated: bool = False

    @property
    def result(self) -> Node:
        return self.steps[-1].expression_after if self.steps else self.source

    @property
    def value(self):
        return self.result.value if isinstance(self.result, Number) else None


class Reducer:
    """Unfolds definitions of operators in ``registry`` using ``runtime`` for primitives.

    Granularity (how detailed a solution is):

    * ``expand`` decides which defined operators are unfolded; the others are *known* and
      computed in one step. The default unfolds every operator that has a definition; pass
      e.g. ``lambda op: op.recursive_layer >= 2`` to treat layers 0 and 1 as known.
    * ``max_depth`` limits how deep unfolding goes: an application produced by ``max_depth``
      unfoldings is computed in one step. ``max_depth=1`` unfolds only the operators written
      in the expression itself.

    A one-step computation of a defined operator is an ``eval`` step like a base operation;
    its value is checked like any other step (``opulse.verify.verify_trace``).
    """

    def __init__(self, registry: OperatorRegistry, runtime, parser: DefinitionParser,
                 expand: Callable[[Operator], bool] | None = None, max_steps: int = 2000,
                 max_depth: int | None = None) -> None:
        self.registry = registry
        self.runtime = runtime
        self.parser = parser
        self.expand = expand or (lambda op: op.definition is not None)
        self.max_steps = max_steps
        self.max_depth = max_depth
        self._resolve = registry_resolver(registry)
        self._definitions: dict[str, ast.Definition] = {}

    def reduce(self, expression: Node) -> Trace:
        trace = Trace(expression)
        current = expression
        depths = _depths(expression, 0)  # unfolding depth of every application, same shape
        while not isinstance(current, Number):
            if len(trace.steps) >= self.max_steps:
                trace.truncated = True
                break
            path, focus = _leftmost_ready(current)
            depth = _depth_at(depths, path)
            step = self._rewrite(len(trace.steps), path, focus, current, depth)
            trace.steps.append(step)
            current = step.expression_after
            depths = _replace_at_depths(depths, path, _depths(step.after, depth + 1))
        return trace

    # ------------------------------------------------------------------
    def _rewrite(self, index: int, path: Path, focus: Call, whole: Node, depth: int = 0) -> TraceStep:
        op = focus.operator
        inputs = tuple(arg.value for arg in focus.args)  # type: ignore[union-attr]
        too_deep = self.max_depth is not None and depth >= self.max_depth
        search_attempts = None
        if not self.expand(op) or op.definition is None or too_deep:
            after: Node = Number(self.runtime.compute(op)(*inputs))
            kind, branch_index, condition, reason = "eval", None, None, None
        else:
            definition = self._definition(op)
            env = dict(zip(definition.parameters, inputs))
            branch_index, branch, reason = self._choose_branch(definition, env)
            condition = None
            if branch is None:  # NaN in a condition, or no branch matched
                after, kind = Number(NAN), "undefined"
            else:
                if isinstance(branch.expr, ast.Search):
                    attempts = []
                    value = NAN
                    for index_value in range(branch.expr.bound + 1):
                        trial = {**env, branch.expr.index: index_value}
                        truth = self._truth(branch.expr.condition, trial)
                        attempts.append(f"{branch.expr.index}={index_value}: " +
                                        ("NaN" if truth is NAN else str(truth)))
                        if truth is NAN or truth:
                            value = index_value if truth is True else NAN
                            break
                    after, kind = Number(value), "eval"
                    condition = "; ".join(attempts)
                else:
                    trials: list[str] = []
                    after = self._instantiate(branch.expr, env, trials)
                    search_attempts = "; ".join(trials) or None
                    kind = "expand"
                if branch.condition is not None and condition is None:
                    condition = render_condition(_substitute_condition(branch.condition, env),
                                                 self.parser.symbols)
        return TraceStep(index, kind, path, op, inputs, focus, after, whole, _replace_at(whole, path, after),
                         branch_index, condition, reason, depth, search_attempts)

    def _definition(self, op: Operator) -> ast.Definition:
        if op.func_id not in self._definitions:
            self._definitions[op.func_id] = self.parser.parse(op.definition)
        return self._definitions[op.func_id]

    def _choose_branch(self, definition: ast.Definition, env: dict):
        """``(index, branch, None)``, or ``(None, None, reason)`` when the result is undefined."""
        for index, branch in enumerate(definition.branches):
            if branch.condition is None:
                return index, branch, None
            truth = self._truth(branch.condition, env)
            if truth is NAN:
                return None, None, "nan_condition"
            if truth:
                return index, branch, None
        return None, None, "no_branch"

    def _truth(self, node: ast.Condition, env: dict):
        if isinstance(node, ast.Truth):
            return self._value(node.expr, env)
        if isinstance(node, ast.Compare):
            left, right = self._value(node.left, env), self._value(node.right, env)
            if left is NAN or right is NAN:
                return NAN
            return COMPARISONS[node.op](left, right)
        if isinstance(node, ast.Not):
            inner = self._truth(node.operand, env)
            return inner if inner is NAN else not inner
        left = self._truth(node.left, env)
        if left is NAN:
            return NAN
        if isinstance(node, ast.And) and not left:
            return False
        if isinstance(node, ast.Or) and left:
            return True
        return self._truth(node.right, env)

    def _value(self, node: ast.Expr, env: dict):
        if isinstance(node, ast.Var):
            return env[node.name]
        if isinstance(node, ast.Num):
            return node.value
        if isinstance(node, ast.NaN):
            return NAN
        if isinstance(node, ast.Search):
            for index in range(node.bound + 1):
                truth = self._truth(node.condition, {**env, node.index: index})
                if truth is NAN:
                    return NAN
                if truth:
                    return index
            return NAN
        if isinstance(node, ast.Literal):
            return node.value
        op = self._resolve(node)
        return self.runtime.compute(op)(*(self._value(arg, env) for arg in node.args))

    def _instantiate(self, node: ast.Expr, env: dict, trials: list[str] | None = None) -> Node:
        if isinstance(node, ast.Var):
            return Number(env[node.name])
        if isinstance(node, ast.Num):
            return Number(node.value)
        if isinstance(node, ast.NaN):
            return Number(NAN)
        if isinstance(node, ast.Search):
            if trials is not None:
                attempts = []
                value = NAN
                for index in range(node.bound + 1):
                    truth = self._truth(node.condition, {**env, node.index: index})
                    attempts.append(f"{node.index}={index}: " + ("NaN" if truth is NAN else str(truth)))
                    if truth is NAN or truth:
                        value = index if truth is not NAN else NAN
                        break
                trials.append("; ".join(attempts))
                return Number(value)
            return Number(self._value(node, env))
        if isinstance(node, ast.Literal):
            return Number(node.value)
        return Call(self._resolve(node), tuple(self._instantiate(arg, env, trials) for arg in node.args))


def _depths(node: Node, depth: int):
    """``(depth, children)`` for every application, ``None`` for numbers and variables."""
    if isinstance(node, Call):
        return depth, tuple(_depths(arg, depth) for arg in node.args)
    return None


def _depth_at(depths, path: Path) -> int:
    for i in path:
        depths = depths[1][i]
    return depths[0]


def _replace_at_depths(depths, path: Path, replacement):
    if not path:
        return replacement
    head, *rest = path
    children = list(depths[1])
    children[head] = _replace_at_depths(children[head], tuple(rest), replacement)
    return depths[0], tuple(children)


def _leftmost_ready(node: Node, path: Path = ()) -> tuple[Path, Call]:
    """Leftmost-innermost call whose arguments are all numbers."""
    assert isinstance(node, Call)
    for index, arg in enumerate(node.args):
        if isinstance(arg, Call):
            return _leftmost_ready(arg, path + (index,))
        if isinstance(arg, Variable):
            raise ValueError(f"cannot reduce an expression with variable {arg.name!r}")  # noqa: TRY004
    return path, node


def _replace_at(node: Node, path: Path, replacement: Node) -> Node:
    if not path:
        return replacement
    assert isinstance(node, Call)
    head, *rest = path
    args = list(node.args)
    args[head] = _replace_at(args[head], tuple(rest), replacement)
    return Call(node.operator, tuple(args))


def _substitute_condition(node: ast.Condition, env: dict[str, int]) -> ast.Condition:
    def sub(expr: ast.Expr) -> ast.Expr:
        if isinstance(expr, ast.Var):
            if expr.name not in env:
                return expr
            value = env[expr.name]
            if value is NAN:
                return ast.NaN()
            return ast.negate(value) if isinstance(value, int) and not isinstance(value, bool) else ast.Literal(value)
        if isinstance(expr, ast.Apply):
            return ast.Apply(expr.symbol, tuple(sub(a) for a in expr.args), expr.unary_position)
        if isinstance(expr, ast.Search):
            local = {name: value for name, value in env.items() if name != expr.index}
            return ast.Search(expr.index, expr.bound, _substitute_condition(expr.condition, local))
        return expr

    if isinstance(node, ast.Compare):
        return ast.Compare(sub(node.left), node.op, sub(node.right))
    if isinstance(node, ast.And):
        return ast.And(_substitute_condition(node.left, env), _substitute_condition(node.right, env))
    if isinstance(node, ast.Or):
        return ast.Or(_substitute_condition(node.left, env), _substitute_condition(node.right, env))
    if isinstance(node, ast.Truth):
        return ast.Truth(sub(node.expr))
    return ast.Not(_substitute_condition(node.operand, env))


def path_label(path: Path) -> str:
    return "root" + "".join(f".{i}" for i in path)
