"""Describe operators: atoms by their rules, defined operators from their parsed definitions.

Every atom is described, built-in or registered (:mod:`opulse.core.primitives`): built-in
atoms have a sentence in each language written with the configured operand names; a
registered atom is described by the rule it was registered with. Defined operators are
described in two styles. ``math`` keeps conditions and bodies in operator notation, so the
wording cannot change the arithmetic; ``natural`` is the controlled-language view
(:mod:`opulse.language.views.controlled`), which parses back to the same definition. Both use
the configured notation (operand names, brackets, NaN spelling, numeral digits). A recursive
definition gets the recursion facts of :mod:`opulse.language.recursion`, read from its
structure.

The dependency chain of an operator is the closure of the operators its definition applies,
computed from the parsed definitions (not from stored dependency lists), callees first, never
cut short unless a limit is given, in which case the text says how many were left out.
"""

from __future__ import annotations

from collections.abc import Iterator

from opulse.config import Settings, Symbols
from opulse.core.operator import Operator
from opulse.core.primitives import CUSTOM, rule_for
from opulse.core.registry import OperatorRegistry
from opulse.core.semantics import base_operation_name
from opulse.definition import ast
from opulse.language.ir import Concept, has_search, parameter_names
from opulse.language.views import Views

# Built-in atoms, written with the operand names {a} and {b} of the configured notation.
ATOMS = {
    "add": ("`{a} + {b}` 是整数加法。", "`{a} + {b}` is integer addition."),
    "sub": ("`{a} - {b}` 是整数减法。", "`{a} - {b}` is integer subtraction."),
    "mul": ("`{a} * {b}` 是整数乘法。", "`{a} * {b}` is integer multiplication."),
    "div": ("`{a} / {b}` 向零截断；`{b} = 0` 时结果为 {nan}。",
            "`{a} / {b}` truncates toward zero; when `{b} = 0`, the result is {nan}."),
    "mod": ("`{a} % {b} = {a} - {b} × trunc({a} / {b})`，商向零截断，余数与 `{a}` 同号或为零；`{b} = 0` 时结果为 {nan}。",
            ("`{a} % {b} = {a} - {b} × trunc({a} / {b})` uses a quotient truncated toward zero; the remainder has "
            "the sign of `{a}` or is zero; when `{b} = 0`, the result is {nan}.")),
    "neg": ("`- {a}` 将整数取负。", "`- {a}` negates the integer."),
    "reverse": ("`{a} @` 反转 `|{a}|` 的十进制数字，去掉反转后的前导零，再恢复 `{a}` 的符号。",
                ("`{a} @` reverses the decimal digits of `|{a}|`, drops leading zeros in the result, then restores "
                "the sign of `{a}`.")),
    "triangle": ("`# {a}` 为 `sgn({a}) × |{a}|(|{a}| + 1) / 2`，零的符号为零。",
                 "`# {a}` is `sgn({a}) × |{a}|(|{a}| + 1) / 2`, with zero sign for zero."),
    "popcount": ("`{a} $` 计算 `|{a}|` 的二进制中 1 的个数，结果非负。",
                 "`{a} $` counts the 1 bits in the binary representation of `|{a}|`; the result is nonnegative."),
    "digitsum": ("`& {a}` 计算 `|{a}|` 的十进制各位数字之和，再乘 `sgn({a})`。",
                 "`& {a}` sums the decimal digits of `|{a}|`, then multiplies by `sgn({a})`."),
    "succ": ("`{a} ⁺` 是后继 `{a} + 1`。", "`{a} ⁺` is the successor `{a} + 1`."),
    "pred": ("`{a} ⁻` 是前驱 `{a} - 1`。", "`{a} ⁻` is the predecessor `{a} - 1`."),
    "double": ("`{a} «` 是加倍 `2{a}`（二进制左移一位）。", "`{a} «` doubles `{a}` (one binary left shift)."),
    "half": ("`{a} »` 是减半 `trunc({a} / 2)`，向零截断。", "`{a} »` halves `{a}` as `trunc({a} / 2)`, truncating toward zero."),
    "parity": ("`{a} °` 是 `|{a}|` 的最低二进制位（0 或 1）。", "`{a} °` is the lowest binary digit of `|{a}|` (0 or 1)."),
}
STYLES = ("math", "natural")


class Describer:
    """Descriptions of the operators of one registry under one settings object (cached)."""

    def __init__(self, registry: OperatorRegistry, settings: Settings | None = None) -> None:
        self.views = Views(registry, settings)
        self.registry = registry
        self.symbols: Symbols = self.views.symbols
        self._recursion: dict[str, object] = {}

    # ---------------------------------------------------------- one operator
    def describe(self, operator: Operator, lang: str = "zh", style: str = "math") -> str:
        if lang not in ("zh", "en") or style not in STYLES:
            raise ValueError("lang must be zh/en and style must be math/natural")
        if operator.definition is None:
            return self.atom(operator, lang)
        definition = self.views.definition(operator)
        concept = Concept.of(definition)
        text = self._math(concept, lang) if style == "math" else self.views.prose(operator, lang)
        notes = []
        called = [ref.symbol for ref in concept.calls()]
        if concept.recursive:
            called.append(concept.operator.symbol)
        if called:
            names = ", ".join(f"`{symbol}`" for symbol in dict.fromkeys(called))
            notes.append(f"表达式调用运算符 {names}。" if lang == "zh" else f"Expressions call operators {names}.")
        if concept.recursive:
            notes.append(self.recursion(operator).sentences(f"`{self._render(concept.lhs)}`", self.symbols, lang))
            if _step_reads_counter(definition):
                notes.append("每一步除了上一步的结果，还读取走过一步后的计数器。" if lang == "zh" else
                             "Each step reads the stepped counter as well as the previous result.")
        if has_search(definition):
            notes.append("search 从零到给定上界依次测试条件，返回首个满足条件的下标；若无结果则返回 "
                         f"{self.symbols.nan}。" if lang == "zh" else
                         "search tests indices from zero through its bound and returns the first satisfying index; "
                         f"if none does, it returns {self.symbols.nan}.")
        nan = self.symbols.nan
        notes.append(f"条件按顺序短路求值；被求值的比较中任一侧为 {nan} 时，整个调用立即为 {nan}。" if lang == "zh" else
                     "Conditions are evaluated in order with short-circuiting; if either side of an evaluated "
                     f"comparison is {nan}, the whole call is immediately {nan}.")
        separator = "\n" if style == "natural" else " "
        return text + separator + " ".join(notes)

    def recursion(self, operator: Operator):
        from opulse.language.recursion import analyse

        if operator.func_id not in self._recursion:
            facts = analyse(operator, self.views.definition(operator), self.views.oracle)
            if facts is None:
                raise ValueError(f"{operator.symbol!r} does not call itself")
            self._recursion[operator.func_id] = facts
        return self._recursion[operator.func_id]

    def atom(self, operator: Operator, lang: str) -> str:
        nan = self.symbols.nan
        if operator.is_base is not None:
            return (f"`{operator.symbol}` 是 {operator.is_base} 进制数字前缀。" if lang == "zh" else
                    f"`{operator.symbol}` is a base-{operator.is_base} numeral prefix.")
        name = base_operation_name(operator.symbol, operator.n_ary, operator.unary_position)
        if name is None:
            raise ValueError(f"{operator.symbol!r} has no definition and is not a registered atom")
        names = parameter_names(self.symbols, operator.n_ary)
        if name in ATOMS:
            body = ATOMS[name][0 if lang == "zh" else 1].format(a=names[0], b=names[-1], nan=nan)
        else:
            head = self._render(ast.Apply(operator.symbol, tuple(ast.Var(n) for n in names),
                                          operator.unary_position if operator.n_ary == 1 else None))
            rule = rule_for(name)
            body = (f"`{head}` 是原子运算 {name}，规则：{rule}" if lang == "zh" else
                    f"`{head}` is the atom {name}: {rule}")
            if name in CUSTOM and CUSTOM[name].z3 is None:
                body += ("（没有 z3 编码，基于求解器的分析会跳过它。）" if lang == "zh" else
                         " (It has no z3 encoding; solver-based analyses skip it.)")
        tail = (f"输入为 {nan} 时结果为 {nan}；精确模式下结果超出 `[-B, B]` 时为 {nan}。" if lang == "zh" else
                f"{nan} inputs propagate; in exact mode a result outside `[-B, B]` is {nan}.")
        return (f"运算符 `{operator.symbol}`：{body}{tail}" if lang == "zh" else
                f"Operator `{operator.symbol}`: {body} {tail}")

    def _render(self, node: ast.Expr) -> str:
        return ast.render_expr(node, self.symbols, numerals=self.views.numerals.write)

    def _condition(self, node: ast.Condition) -> str:
        return ast.render_condition(node, self.symbols, self.views.numerals.write)

    def _math(self, concept: Concept, lang: str) -> str:
        head = f"`{self._render(concept.lhs)}`"
        parts = []
        for case in concept.cases:
            body = f"`{self._render(case.body)}`"
            first = case.index == 1
            if case.guard is not None:
                condition = f"`{self._condition(case.guard)}`"
                parts.append(f"{'如果' if first else '否则如果'} {condition}，结果为 {body}" if lang == "zh" else
                             f"{'if' if first else 'otherwise if'} {condition}, the result is {body}")
            elif case.kind == "else":
                parts.append(f"否则结果为 {body}" if lang == "zh" else f"otherwise, the result is {body}")
            else:
                parts.append(f"{'无条件' if first else '然后无条件'}结果为 {body}" if lang == "zh" else
                             f"{'unconditionally' if first else 'then unconditionally'}, the result is {body}")
        nan = self.symbols.nan
        if concept.partial and not _exhaustive(concept):
            parts.append(f"否则未定义（{nan}）" if lang == "zh" else f"otherwise undefined ({nan})")
        intro = f"运算符 {head}：" if lang == "zh" else f"Operator {head}: "
        return intro + ("；" if lang == "zh" else "; ").join(parts) + ("。" if lang == "zh" else ".")

    # ---------------------------------------------------------- dependencies
    def closure(self, operator: Operator) -> list[Operator]:
        """Every operator ``operator``'s definition reaches (atoms included), callees first."""
        order: list[Operator] = []
        seen: set[str] = set()

        def visit(op: Operator) -> None:
            if op.func_id in seen:
                return
            seen.add(op.func_id)
            if op.definition is not None:
                for ref in Concept.of(self.views.definition(op)).calls():
                    visit(self.views.oracle._resolve(ref.apply(tuple(ast.Var("a") for _ in range(ref.arity)))))
            if op.func_id != operator.func_id:
                order.append(op)

        visit(operator)
        return order

    def chain(self, operator: Operator, lang: str, limit: int | None = None) -> str:
        needed = self.closure(operator)
        shown = needed if limit is None else needed[:limit]
        lines = [self.describe(op, lang) for op in shown]
        if len(shown) < len(needed):
            left = len(needed) - len(shown)
            lines.append(f"（另有 {left} 个依赖未列出。）" if lang == "zh" else
                         f"({left} more dependencies are not listed.)")
        return "\n".join(lines)


def _exhaustive(concept: Concept) -> bool:
    """True when the guards are ``c == 0``, ``c > 0``, ``c < 0`` on one control expression."""
    guards = [case.guard for case in concept.cases]
    if len(guards) != 3 or not all(isinstance(g, ast.Compare) for g in guards):
        return False
    same = guards[0].left == guards[1].left == guards[2].left
    zero = all(g.right == ast.Num(0) for g in guards)
    return same and zero and sorted(g.op for g in guards) == ["<", "==", ">"]


def _step_reads_counter(definition: ast.Definition) -> bool:
    """Whether a step body reads its changed counter outside the recursive call."""
    if len(definition.branches) < 2:
        return False
    body, ref = definition.branches[1].expr, definition.lhs
    calls = [app for app in ast.iter_applications(body)
             if (app.symbol, app.n_ary, app.unary_position) == (ref.symbol, ref.n_ary, ref.unary_position)]
    if not calls:
        return False
    stepped = {arg for arg, param in zip(calls[0].args, ref.args) if arg != param}

    def outside(node) -> bool:
        if node in stepped:
            return True
        if isinstance(node, ast.Apply) and (node.symbol, node.n_ary, node.unary_position) != \
                (ref.symbol, ref.n_ary, ref.unary_position):
            return any(outside(arg) for arg in node.args)
        return False

    return outside(body)


def describe(operator: Operator, definition: ast.Definition | None, registry: OperatorRegistry,
             lang: str = "zh", style: str = "math", settings: Settings | None = None) -> str:
    """One description of ``operator`` (``definition`` is accepted for compatibility; the
    registry's own definition text is what is described)."""
    describer = Describer(registry, settings)
    if definition is not None and operator.definition is not None:
        parsed = describer.views.definition(operator)
        if parsed != definition:
            raise ValueError("the given definition differs from the operator's definition text")
    return describer.describe(operator, lang, style)


def annotate(registry: OperatorRegistry, settings: Settings | None = None,
             chain_limit: int | None = None) -> Iterator[dict]:
    """Yield operator JSON fields with bilingual descriptions and dependency chains."""
    describer = Describer(registry, settings)
    for operator in registry:
        row = operator.to_dict()
        for lang in ("zh", "en"):
            math = describer.describe(operator, lang, "math")
            row[f"nl_description_math_{lang}"] = math
            row[f"nl_description_natural_{lang}"] = describer.describe(operator, lang, "natural")
            row[f"nl_description_{lang}"] = math
            row[f"nl_description_chain_{lang}"] = describer.chain(operator, lang, chain_limit)
        yield row
