"""Turn recorded forward and reverse steps into checkable prose.

The narrator reads values and expressions already present in a trace or hole problem. Three
styles of forward narration:

* ``full`` (the default, used by stored chains of thought): every line names the step and
  repeats the whole expression before and after it;
* ``terse``: one short line per step, about the rewritten part only;
* ``explained``: says why each case is taken, with the values of the compared expressions
  ("since `7 % 5 = 2` and `2 > 0`, case 2 applies"), and shows the whole expression after
  each unfolding.

``collapse`` merges a run of consecutive computed steps into one line: ``"atoms"`` merges
base operations, ``"known"`` every step computed in one go (atoms and operators the reducer
did not unfold), or pass a predicate on the operator. Every number in a narration is a value
of the trace or of a comparison the trace records; the values of compared expressions are
recomputed with the reference interpreter from the step's inputs.
"""

from __future__ import annotations

from collections.abc import Callable

from opulse.core.operator import Operator
from opulse.core.semantics import NAN, Semantics
from opulse.definition import ast
from opulse.expression.nodes import Call, Number, Variable
from opulse.expression.render import ExpressionRenderer
from opulse.solver.holes import HOLE, HoleProblem
from opulse.trace.reducer import Trace, TraceStep

STYLES = ("full", "terse", "explained")


def _value(value: object, renderer: ExpressionRenderer) -> str:
    return renderer.full(Number(value))


def _collapse_rule(collapse) -> Callable[[Operator], bool] | None:
    if collapse is None:
        return None
    if collapse == "atoms":
        return lambda op: op.definition is None
    if collapse == "known":
        return lambda op: True
    if callable(collapse):
        return collapse
    raise ValueError("collapse must be None, 'atoms', 'known' or a predicate on operators")


def _groups(steps: list[TraceStep], rule) -> list[list[TraceStep]]:
    groups: list[list[TraceStep]] = []
    for step in steps:
        joinable = rule is not None and step.kind == "eval" and rule(step.operator)
        if joinable and groups and groups[-1][-1].kind == "eval" and rule(groups[-1][-1].operator):
            groups[-1].append(step)
        else:
            groups.append([step])
    return groups


def narrate(trace: Trace, renderer: ExpressionRenderer, lang: str, style: str = "full", registry=None,
            collapse=None, semantics=None) -> str:
    """Describe each verified reduction step in trace order.

    ``registry`` is needed for the ``explained`` style. Pass the trace's ``semantics`` when
    explaining a trace produced with nondefault arithmetic bounds.
    """
    if lang not in ("zh", "en"):
        raise ValueError("lang must be zh or en")
    if style not in STYLES:
        raise ValueError(f"style must be one of {STYLES}")
    if trace.truncated:
        raise ValueError("cannot narrate a truncated trace as a final answer")
    explainer = None
    if style == "explained":
        if registry is None:
            raise ValueError("the explained style needs the registry (to read the definitions)")
        explainer = _Explainer(registry, renderer, semantics)
    rule = _collapse_rule(collapse)
    lines = [_start(trace, renderer, lang, style)]
    rendered: dict = {}  # each step starts from the previous step's result: render it once
    for group in _groups(trace.steps, rule):
        if len(group) > 1:
            lines.append(_collapsed(group, renderer, lang, style))
        elif style == "full":
            lines.append(_full(group[0], renderer, lang, rendered))
        elif style == "terse":
            lines.append(_terse(group[0], renderer, lang))
        else:
            lines.append(explainer.step(group[0], lang))
    answer = _value(trace.value, renderer) if trace.value is not None else renderer.full(trace.result)
    if style == "full":
        lines.append(f"最终答案：`{answer}`。" if lang == "zh" else f"Final answer: `{answer}`.")
    else:
        lines.append(f"答案：`{answer}`。" if lang == "zh" else f"Answer: `{answer}`.")
    return "\n\n".join(lines) if style == "full" else "\n".join(lines)


def _start(trace: Trace, renderer: ExpressionRenderer, lang: str, style: str) -> str:
    source = renderer.full(trace.source)
    if style == "full":
        return f"原式：`{source}`。" if lang == "zh" else f"Starting expression: `{source}`."
    if style == "terse":
        return f"计算 `{source}`。" if lang == "zh" else f"Compute `{source}`."
    return (f"计算 `{source}`，每次改写最左边、参数都已是数的那个运算。" if lang == "zh" else
            f"Compute `{source}`, each time rewriting the leftmost application whose arguments are numbers.")


def _computed(step: TraceStep, renderer: ExpressionRenderer) -> str:
    return f"`{renderer.full(step.before)} = {_value(step.output, renderer)}`"


def _collapsed(group: list[TraceStep], renderer: ExpressionRenderer, lang: str, style: str) -> str:
    listed = ("，" if lang == "zh" else ", ").join(_computed(step, renderer) for step in group)
    text = f"计算：{listed}。" if lang == "zh" else f"Compute {listed}."
    if style in ("full", "explained"):
        after = renderer.full(group[-1].expression_after)
        text += f"新表达式为 `{after}`。" if lang == "zh" else f" The expression is now `{after}`."
    return text


def _terse(step: TraceStep, renderer: ExpressionRenderer, lang: str) -> str:
    focus = f"`{renderer.full(step.before)}`"
    if step.kind == "eval":
        if step.condition is not None and step.branch_index is not None:
            return (f"依次检验搜索条件：{step.condition}；{_computed(step, renderer)}。" if lang == "zh" else
                    f"Test the search condition in order: {step.condition}; {_computed(step, renderer)}.")
        return f"{_computed(step, renderer)}。" if lang == "zh" else f"{_computed(step, renderer)}."
    if step.kind == "expand":
        after = f"`{renderer.full(step.after)}`"
        trials = (f" 搜索依次检验：{step.search_attempts}。" if lang == "zh" else
                  f" Search trials: {step.search_attempts}.") if step.search_attempts else ""
        return ((f"{focus} 化为 {after}（情形 {step.branch_index + 1}）。" if lang == "zh" else
                 f"{focus} becomes {after} (case {step.branch_index + 1}).") + trials)
    nan = renderer.symbols.nan
    if lang == "zh":
        cause = "比较读到 " + nan if step.reason == "nan_condition" else "没有情形成立"
        return f"`{renderer.full(step.before)} = {nan}`（{cause}）。"
    cause = f"a comparison reads {nan}" if step.reason == "nan_condition" else "no case applies"
    return f"`{renderer.full(step.before)} = {nan}` ({cause})."


def _full(step: TraceStep, renderer: ExpressionRenderer, lang: str, rendered: dict | None = None) -> str:
    """The original line format; stored chains of thought are checked against it byte for byte.

    ``rendered`` caches expression texts across the steps of one trace."""
    cache = {} if rendered is None else rendered

    def show(node) -> str:
        hit = cache.get(id(node))
        if hit is None or hit[0] is not node:
            hit = (node, f"`{renderer.full(node)}`")
            cache[id(node)] = hit
        return hit[1]

    before = show(step.expression_before)
    after = show(step.expression_after)
    inputs = ", ".join(_value(value, renderer) for value in step.inputs)
    symbol = f"`{step.operator.symbol}`"
    if step.kind == "expand":
        trials = (f" 搜索依次检验：{step.search_attempts}。" if lang == "zh" else
                  f" Search trials: {step.search_attempts}.") if step.search_attempts else ""
        if lang == "zh":
            reason = (f"条件 `{step.condition}` 成立" if step.condition is not None else
                      "命中无条件分支")
            return (f"在 {before} 中展开运算符 {symbol}，输入为 `{inputs}`；"
                    f"选择第 {step.branch_index + 1} 个分支，因为{reason}；新表达式为 {after}。{trials}")
        reason = (f"condition `{step.condition}` holds" if step.condition is not None else
                  "the unconditional branch applies")
        return (f"In {before}, unfold operator {symbol} on inputs `{inputs}`; "
                f"take branch {step.branch_index + 1} because {reason}, giving {after}.{trials}")
    if step.kind == "eval" and step.operator.definition is not None:
        # A defined operator computed in one step (a known operator, or below the depth limit).
        value = _value(step.output, renderer)
        if step.condition is not None and step.branch_index is not None:
            if lang == "zh":
                return (f"在 {before} 中依次检验搜索条件：{step.condition}；结果为 `{value}`；"
                        f"新表达式为 {after}。")
            return (f"In {before}, test the search condition in order: {step.condition}; "
                    f"the result is `{value}`, giving {after}.")
        if lang == "zh":
            return (f"在 {before} 中，{symbol} 是已知运算，不再展开，直接得到 {symbol}(`{inputs}`) = `{value}`；"
                    f"新表达式为 {after}。")
        return (f"In {before}, {symbol} is a known operator and is not unfolded: {symbol}(`{inputs}`) = "
                f"`{value}`; the new expression is {after}.")
    if step.kind == "eval":
        value = _value(step.output, renderer)
        if lang == "zh":
            return f"在 {before} 中计算运算符 {symbol}，输入为 `{inputs}`，得到 `{value}`；新表达式为 {after}。"
        return (f"In {before}, evaluate operator {symbol} on inputs `{inputs}` to get "
                f"`{value}`; the new expression is {after}.")
    if lang == "zh":
        cause = ("某个条件的比较一侧为 NaN" if step.reason == "nan_condition" else
                 "没有任何分支的条件成立")
        return (f"在 {before} 中展开运算符 {symbol}，输入为 `{inputs}`：{cause}，"
                f"所以结果为 NaN；新表达式为 {after}。")
    cause = ("one side of a condition's comparison is NaN" if step.reason == "nan_condition" else
             "no branch condition holds")
    return (f"In {before}, unfold operator {symbol} on inputs `{inputs}`: {cause}, "
            f"so the result is NaN; the new expression is {after}.")


class _Explainer:
    """Why each case is or is not taken, with the compared values recomputed by the interpreter."""

    def __init__(self, registry, renderer: ExpressionRenderer, semantics=None) -> None:
        from opulse.verify import Oracle

        self.renderer = renderer
        self.symbols = renderer.symbols
        self.oracle = Oracle(registry, renderer.symbols, semantics if semantics is not None else Semantics())

    def _show(self, value) -> str:
        return _value(value, self.renderer)

    def _expr(self, node: ast.Expr, env: dict) -> str:
        """``node`` with the parameters replaced by their values (negative values bracketed)."""
        def sub(expr):
            if isinstance(expr, ast.Var):
                value = env[expr.name]
                return ast.NaN() if value is NAN else ast.negate(value)
            if isinstance(expr, ast.Apply):
                return ast.Apply(expr.symbol, tuple(sub(arg) for arg in expr.args), expr.unary_position)
            return expr

        return ast.render_expr(sub(node), self.symbols)

    def _side(self, node: ast.Expr, env: dict, facts: list[str]):
        value = self.oracle.evaluate_expr(node, env).value
        if isinstance(node, ast.Apply):
            facts.append(f"`{self._expr(node, env)} = {self._show(value)}`")
        return value

    def condition(self, node: ast.Condition, env: dict, facts: list[str]):
        """Truth of ``node`` (or NAN), adding the facts a reader needs, in evaluation order."""
        from opulse.definition.interpreter import COMPARISONS

        if isinstance(node, ast.Compare):
            left = self._side(node.left, env, facts)
            right = self._side(node.right, env, facts)
            if left is NAN or right is NAN:
                return NAN
            truth = COMPARISONS[node.op](left, right)
            text = f"`{self._show(left)} {node.op} {self._show(right)}`"
            facts.append(text if truth else (f"{text} 不成立" if self._zh else f"{text} is false"))
            return truth
        if isinstance(node, ast.Not):
            inner = self.condition(node.operand, env, facts)
            return inner if inner is NAN else not inner
        left = self.condition(node.left, env, facts)
        if left is NAN:
            return NAN
        if isinstance(node, ast.And) and not left or isinstance(node, ast.Or) and left:
            return left
        return self.condition(node.right, env, facts)

    def step(self, step: TraceStep, lang: str) -> str:
        self._zh = lang == "zh"
        focus = f"`{self.renderer.full(step.before)}`"
        if step.kind == "eval":
            if step.operator.definition is not None:
                if step.condition is not None and step.branch_index is not None:
                    return (f"依次检验搜索条件：{step.condition}；计算 {_computed(step, self.renderer)}。" if self._zh
                            else f"Test the search condition in order: {step.condition}; "
                                 f"compute {_computed(step, self.renderer)}.")
                return (f"{step.operator.symbol} 是已知运算，直接计算 {_computed(step, self.renderer)}。" if self._zh else
                        f"`{step.operator.symbol}` is known, so compute {_computed(step, self.renderer)} directly.")
            return f"计算 {_computed(step, self.renderer)}。" if self._zh else f"Compute {_computed(step, self.renderer)}."
        definition = self.oracle._definition_of(step.operator)
        env = dict(zip(definition.parameters, step.inputs))
        binding = ("，".join if self._zh else ", ".join)(
            f"`{name} = {self._show(value)}`" for name, value in env.items())
        lines = [f"展开 {focus}（{binding}）。" if self._zh else f"Unfold {focus} with {binding}."]
        chosen = step.branch_index if step.kind == "expand" else None
        for index, branch in enumerate(definition.branches):
            if chosen is not None and index > chosen:
                break
            if branch.condition is None:
                lines.append(f"情形 {index + 1} 没有条件，因此适用。" if self._zh else
                             f"Case {index + 1} has no condition, so it applies.")
                break
            facts: list[str] = []
            truth = self.condition(branch.condition, env, facts)
            joined = ("，".join(facts) if self._zh else " and ".join(facts))
            if truth is NAN:
                nan = self.symbols.nan
                lines.append(f"情形 {index + 1} 的比较读到 {nan}（{joined}），所以 {focus} 的值为 {nan}。" if self._zh else
                             f"Case {index + 1} compares a {nan} ({joined}), so {focus} is {nan}.")
                break
            if truth:
                lines.append(f"因为 {joined}，情形 {index + 1} 适用。" if self._zh else
                             f"Since {joined}, case {index + 1} applies.")
                break
            lines.append(f"情形 {index + 1} 不适用：{joined}。" if self._zh else
                         f"Case {index + 1} does not apply: {joined}.")
        if step.kind == "undefined" and step.reason == "no_branch":
            nan = self.symbols.nan
            lines.append(f"没有情形适用，所以 {focus} 的值为 {nan}。" if self._zh else
                         f"No case applies, so {focus} is {nan}.")
        if step.kind == "expand":
            after = self.renderer.full(step.after)
            whole = self.renderer.full(step.expression_after)
            lines.append(f"于是 {focus} 化为 `{after}`，表达式变为 `{whole}`。" if self._zh else
                         f"So {focus} becomes `{after}`, and the expression is now `{whole}`.")
            if step.search_attempts:
                lines.append(f"搜索依次检验：{step.search_attempts}。" if self._zh else
                             f"Search trials: {step.search_attempts}.")
        return " ".join(lines) if not self._zh else "".join(lines)


# ------------------------------------------------------------------ reverse


def _hole_path(node, path: tuple = ()) -> tuple | None:
    if isinstance(node, Variable) and node.name == HOLE:
        return path
    if isinstance(node, Call):
        for index, arg in enumerate(node.args):
            found = _hole_path(arg, path + (index,))
            if found is not None:
                return found
    return None


def _set(values, show) -> str:
    """``{1, 2, 3}``; a run of five or more consecutive integers is written ``{-5, -4, ..., 5}``."""
    values = list(values)
    parts, index = [], 0
    while index < len(values):
        end = index
        while end + 1 < len(values) and isinstance(values[end], int) and values[end + 1] == values[end] + 1:
            end += 1
        if end - index >= 4:
            parts += [show(values[index]), show(values[index + 1]), "...", show(values[end])]
        else:
            parts += [show(v) for v in values[index : end + 1]]
        index = end + 1
    return "{" + ", ".join(parts) + "}"


ORDINALS_EN = ("first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth")


def _argument(position: int, arity: int, lang: str) -> str:
    """How a reader names argument ``position`` of an operator with ``arity`` arguments."""
    if lang == "zh":
        if arity == 1:
            return "参数"
        if arity == 2:
            return "左参数" if position == 0 else "右参数"
        return f"第 {position + 1} 个参数"
    if arity == 1:
        return "argument"
    if arity == 2:
        return "left argument" if position == 0 else "right argument"
    return f"{ORDINALS_EN[position]} argument" if position < len(ORDINALS_EN) else f"argument {position + 1}"


def narrate_reverse(problem: HoleProblem, renderer: ExpressionRenderer, lang: str) -> str:
    """Work from the outside in: what each enclosing operation needs from the part that holds x."""
    if lang not in ("zh", "en"):
        raise ValueError("lang must be zh or en")
    zh = lang == "zh"
    show = lambda value: _value(value, renderer)
    path = _hole_path(problem.expression) or ()
    domain = problem.solutions.domain
    lines = []
    node = problem.expression
    for depth, step in enumerate(problem.reverse):
        if not isinstance(node, Call):
            break
        position = path[depth] if depth < len(path) else step.unknown_position
        arity = len(node.args)
        target = _set(step.target, show) if isinstance(step.target, list) else show(step.target)
        whole = f"`{renderer.full(node)}`"
        part = node.args[position]
        part_text = f"`{renderer.full(part)}`"
        known = [(index, value) for index, value in sorted(step.known.items())]
        if zh:
            need = f"{whole} 必须等于 {target}。" if not isinstance(step.target, list) else \
                f"{whole} 必须是 {target} 中的某个值。"
            given = "，".join(f"它的{_argument(i, arity, lang)}是 {show(v)}" for i, v in known)
        else:
            need = f"{whole} must equal {target}." if not isinstance(step.target, list) else \
                f"{whole} must take one of the values {target}."
            given = " and ".join(f"its {_argument(i, arity, lang)} is {show(v)}" for i, v in known)
        unknown = _argument(position, arity, lang)
        if not step.candidates and not step.complete:
            lines.append(f"{need}{given}；{unknown} {part_text} 在这里为 {renderer.symbols.nan}，推导到此为止。" if zh else
                         f"{need} {given.capitalize() + '; ' if given else ''}its {unknown} {part_text} is "
                         f"{renderer.symbols.nan} here, so the derivation stops.")
            break
        candidates = _set(step.candidates, show)
        span = step.domain or domain
        span_text = f"[{span[0]}, {span[1]}]"
        if zh:
            sure = f"在 {span_text} 内这些候选是全部可能" if step.complete else f"在 {span_text} 内不保证列全"
            lines.append(f"{need}{given + '，' if given else ''}所以{unknown} {part_text} 只能取 {candidates}；{sure}。")
        else:
            sure = (f"no other value in {span_text} works" if step.complete else
                    f"other values in {span_text} are not ruled out")
            lead = f"{given[0].upper() + given[1:]}, so its" if given else "Its"
            lines.append(f"{need} {lead} {unknown} {part_text} must be one of {candidates}; {sure}.")
        node = part
    solutions = _set(problem.solutions.values, show)
    span_text = f"[{domain[0]}, {domain[1]}]"
    target = show(problem.target)
    if zh:
        if problem.solutions.unique:
            lines.append(f"所以 x = {show(problem.solutions.values[0])}；在 {span_text} 内没有别的 x 使值为 {target}。")
        elif problem.solutions.complete:
            lines.append(f"所以 x 是 {solutions} 之一；这就是 {span_text} 内的全部解。")
        else:
            lines.append(f"已知的解为 {solutions}；在 {span_text} 内是否还有别的解没有确定。")
    else:
        if problem.solutions.unique:
            lines.append(f"So x = {show(problem.solutions.values[0])}, and no other x in {span_text} gives {target}.")
        elif problem.solutions.complete:
            lines.append(f"So x is one of {solutions}; these are all the solutions in {span_text}.")
        else:
            lines.append(f"The solutions found are {solutions}; whether {span_text} holds others is not determined.")
    return "\n\n".join(lines)
