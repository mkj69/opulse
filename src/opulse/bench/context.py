"""What a model must be told to solve a problem: definitions and base-operation rules.

A problem's *closure* is every defined operator its expression applies, directly or through
other definitions, listed callees first. The rules text states the semantics of exactly the
base operations that occur, plus the general rules (integers and NaN, branch order,
truncating division, the bound).
"""

from __future__ import annotations

from opulse.config import Symbols
from opulse.core.operator import Operator

# One line per atom (exact mode), built-in and user-registered (opulse.core.primitives).
from opulse.core.primitives import atom_names, rule_for
from opulse.core.registry import OperatorRegistry
from opulse.core.semantics import Semantics, base_operation_name
from opulse.definition import ast
from opulse.expression.nodes import Call, Node

SEARCH_RULE = ("search(i, T, condition) returns the first i from 0 through T whose condition "
               "is true, or {nan} if none is true or a comparison is undefined.")
CHINESE_SEARCH_RULE = ("search(i, T, 条件) 返回 0 到 T 之间第一个使条件成立的 i；"
                       "没有这样的 i，或者某个比较无定义时，结果为 {nan}。")


def search_rule(nan: str, language: str = "en") -> str:
    return (CHINESE_SEARCH_RULE if language == "zh" else SEARCH_RULE).format(nan=nan)


def call_form_rule(symbols, language: str = "en") -> str:
    example = symbols.call("S", symbols.operands(3))
    if language == "zh":
        return f"三个及以上参数的运算符写成调用形式 `{example}`，参数之间用 `{symbols.argument_separator}` 分隔。"
    return (f"An operator with three or more arguments is written in call form, `{example}`; "
            f"the arguments are separated by `{symbols.argument_separator}`.")
CHINESE_ATOM_RULES = {
    "add": "a + b 是整数加法。",
    "sub": "a - b 是整数减法。",
    "mul": "a * b 是整数乘法。",
    "div": "a / b 是向零取整的除法（-7 / 2 = -3）；b = 0 时结果为 NaN。",
    "mod": "a % b 是余数 a - b * (a / b)，其符号与 a 相同（-7 % 2 = -1）；b = 0 时结果为 NaN。",
    "neg": "- a 是 a 的相反数。",
    "reverse": "a @ 将 |a| 的十进制数字倒序，并保留 a 的符号（120 @ = 21，-123 @ = -321）。",
    "triangle": "# a 是精确计算的 sign(a) * |a| * (|a| + 1) / 2；仅检查结果是否超过界限（# 4 = 10，# -4 = -10）。",
    "popcount": "a $ 是 |a| 的二进制表示中数字 1 的个数（7 $ = 3）。",
    "digitsum": "& a 是 a 的符号乘以 |a| 的十进制各位数字之和（& -123 = -6）。",
    "succ": "a ⁺ 是 a + 1。",
    "pred": "a ⁻ 是 a - 1。",
    "double": "a « 是 2 * a。",
    "half": "a » 是向零取整的 a / 2。",
    "parity": "a ° 是 |a| % 2（结果为 0 或 1）。",
}


def atom_rule(name: str, language: str = "en") -> str:
    if language == "zh" and name in CHINESE_ATOM_RULES:
        return CHINESE_ATOM_RULES[name]
    return rule_for(name)  # Custom atoms retain the rule supplied by their author.



def callees(registry: OperatorRegistry, op: Operator, symbols: Symbols | None = None) -> list[Operator]:
    """Operators applied in ``op``'s definition, read from the definition itself (not the stored
    dependency list, which could be incomplete)."""
    from opulse.verify import Oracle

    if not hasattr(registry, "_bench_callees"):  # per-registry cache
        registry._bench_callees = {}
    symbols = symbols or Symbols()
    if symbols not in registry._bench_callees:
        registry._bench_callees[symbols] = ({}, Oracle(registry, symbols))
    cache, oracle = registry._bench_callees[symbols]
    if op.func_id not in cache:
        found: dict[str, Operator] = {}
        if op.definition is not None:
            definition = oracle._definition_of(op)
            for branch in definition.branches:
                nodes = [branch.expr] + ([branch.condition] if branch.condition is not None else [])
                for node in nodes:
                    for apply in ast.iter_applications(node):
                        callee = oracle._resolve(apply)
                        found.setdefault(callee.func_id, callee)
        cache[op.func_id] = list(found.values())
    return cache[op.func_id]


def closure(registry: OperatorRegistry, tree: Node, symbols: Symbols | None = None) -> list[Operator]:
    """Defined operators needed to evaluate ``tree``, callees before callers."""
    needed: set[str] = set()

    def visit(op: Operator) -> None:
        if op.definition is None or op.func_id in needed:
            return
        needed.add(op.func_id)
        for dep in callees(registry, op, symbols):
            if dep.func_id != op.func_id:
                visit(dep)

    def walk(node: Node) -> None:
        if isinstance(node, Call):
            visit(node.operator)
            for arg in node.args:
                walk(arg)

    walk(tree)
    return [op for op in registry.topological_order() if op.func_id in needed]


def base_operations_used(registry: OperatorRegistry, tree: Node, operators: list[Operator],
                         symbols: Symbols | None = None) -> list[str]:
    """Names of the base operations that occur in ``tree`` or in the given definitions."""
    used: list[str] = []

    def note(op: Operator) -> None:
        name = base_operation_name(op.symbol, op.n_ary, op.unary_position)
        if op.definition is None and name and name not in used:
            used.append(name)

    def walk(node: Node) -> None:
        if isinstance(node, Call):
            note(node.operator)
            for arg in node.args:
                walk(arg)

    walk(tree)
    for op in operators:
        for dep in callees(registry, op, symbols):
            note(dep)
    order = atom_names()
    return sorted(used, key=order.index)


def rules_text(base_operations: list[str], semantics: Semantics, nan: str = "NaN",
               language: str = "en") -> str:
    if language == "zh":
        bound = semantics.bound
        lines = [
            f"数值是整数或 {nan}（未定义）。",
            "基本运算：",
            *(f"  - {atom_rule(name, language)}" for name in base_operations),
        ]
        if semantics.mode == "modular":
            lines.append(f"每个整数基本运算的结果按 {semantics.modulus} 取模，值在 0 到 {semantics.modulus - 1}。")
        elif bound is not None:
            lines.append(f"基本运算的结果绝对值大于 {bound} 时，结果为 {nan}。")
        lines += [
            f"基本运算的参数含有 {nan} 时，结果为 {nan}。",
            ("定义 `lhs = { e1, if c1; e2, if c2; ...; e, else }` 按顺序检查各分支，"
             "返回第一个条件成立的分支结果；`else` 始终成立。"),
            f"没有条件成立时，结果为 {nan}。比较值为 {nan} 时，结果为 {nan}。",
            "一元运算符的优先级高于二元运算符；后缀运算符的优先级高于前缀运算符。",
            "嵌套在另一个二元运算中的二元运算始终加括号。",
        ]
        return "\n".join(lines)
    bound = semantics.bound
    from opulse.core.primitives import CUSTOM

    typed = any(name in CUSTOM and (CUSTOM[name].result_type != "int" or
                                   any(t != "int" for t in CUSTOM[name].parameter_types))
                for name in base_operations)
    grid_world = any(name.startswith("grid_") for name in base_operations)
    value_kinds = "integers, booleans, strings, lists of integers"
    if grid_world:
        value_kinds += ", grids"
    lines = [
        (f"Values are {value_kinds}, or {nan} (undefined)."
         if typed else f"Values are integers or {nan} (undefined)."),
        "Base operations:",
        *(f"  - {rule_for(name)}" for name in base_operations),
    ]
    if semantics.mode == "modular":
        lines.append(f"Each integer base operation result is reduced modulo {semantics.modulus} into "
                     f"0 through {semantics.modulus - 1}.")
    elif bound is not None:
        lines.append(f"Any base operation whose result is larger than {bound} in absolute value gives {nan}.")
    if typed:
        lines.append(f"A string longer than {semantics.max_string_length} characters gives {nan}.")
        lines.append(f"A list longer than {semantics.max_list_length} elements gives {nan}.")
    if grid_world:
        lines.append("A grid is a rectangular list of digit rows, with 1 to 10 rows and columns; colours are 0 to 9, and 0 is background.")
    lines += [
        f"A base operation other than defined with a {nan} argument gives {nan}."
        if "defined" in base_operations else f"A base operation with a {nan} argument gives {nan}.",
        ("A definition `lhs = { e1, if c1; e2, if c2; ...; e, else }` tries its branches in order and "
         "returns the first branch whose condition holds; `else` always holds."),
        f"If no branch holds, the result is {nan}. If a compared value is {nan}, the result is {nan}.",
        "Unary operators bind tighter than binary ones; a postfix operator binds tighter than a prefix one.",
        "A binary operation used inside another binary operation is always written in parentheses.",
    ]
    return "\n".join(lines)
