"""The examples view: an input/output table computed by the reference interpreter.

Inputs are chosen so that every case of the definition that can be reached appears at least
once (smallest inputs first), followed by inputs on which the definition is undefined, if
there are any. Values come from :class:`opulse.verify.Oracle`; the table never states a value
the interpreter did not compute.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field

from opulse.config import Symbols
from opulse.core.operator import Operator
from opulse.core.semantics import NAN
from opulse.definition import ast
from opulse.definition.interpreter import COMPARISONS
from opulse.language.views.code import sample_inputs
from opulse.verify.differential import literals

NO_BRANCH, NAN_CONDITION = "no case applies", "a comparison reads NaN"


@dataclass
class Row:
    args: tuple[int, ...]
    value: object
    case: int | str  # 1-based case number, or why the value is NaN


@dataclass
class ExampleTable:
    lhs: str
    parameters: tuple[str, ...]
    rows: list[Row]
    unreached: list[int] = field(default_factory=list)  # cases no tried input selects
    tried: int = 0

    def text(self, symbols: Symbols, cases: bool = True) -> str:
        nan = symbols.nan
        show = lambda value: nan if value is NAN else str(value)
        header = [*self.parameters, self.lhs] + (["case"] if cases else [])
        lines = [f"Examples of `{self.lhs}` (computed by the reference interpreter):",
                 "| " + " | ".join(header) + " |", "|" + " --- |" * len(header)]
        for row in self.rows:
            cells = [show(a) for a in row.args] + [show(row.value)]
            if cases:
                cells.append(str(row.case))
            lines.append("| " + " | ".join(cells) + " |")
        if cases and self.unreached:
            listed = ", ".join(str(case) for case in self.unreached)
            lines.append(f"No input among the {self.tried} tried selects case {listed}.")
        return "\n".join(lines)


def select_case(definition: ast.Definition, env: dict, oracle) -> int | str:
    """The 1-based case the definition takes on ``env``, or why no case is taken."""
    try:
        for index, branch in enumerate(definition.branches, start=1):
            if branch.condition is None or _truth(branch.condition, env, oracle):
                return index
    except _NaNRead:
        return NAN_CONDITION
    return NO_BRANCH


class _NaNRead(Exception):
    pass


def _truth(node: ast.Condition, env: dict, oracle) -> bool:
    if isinstance(node, ast.Compare):
        left = oracle.evaluate_expr(node.left, env).value
        right = oracle.evaluate_expr(node.right, env).value
        if left is NAN or right is NAN:
            raise _NaNRead
        return COMPARISONS[node.op](left, right)
    if isinstance(node, ast.Not):
        return not _truth(node.operand, env, oracle)
    if isinstance(node, ast.And):
        return _truth(node.left, env, oracle) and _truth(node.right, env, oracle)
    return _truth(node.left, env, oracle) or _truth(node.right, env, oracle)


def examples(operator: Operator, definition: ast.Definition, oracle, symbols: Symbols, extra: int = 3,
             seed: int = 0) -> ExampleTable:
    rng = random.Random(seed)
    params = definition.parameters
    points = sample_inputs(len(params), oracle.semantics.bound, literals(definition), rng)
    points.sort(key=lambda p: (max(abs(v) for v in p), p))
    first: dict = {}
    for point in points:
        case = select_case(definition, dict(zip(params, point)), oracle)
        first.setdefault(case, point)
    rows = []
    cases = [index for index in range(1, len(definition.branches) + 1)]
    for case in cases:
        if case in first:
            rows.append(Row(first[case], oracle.evaluate(operator, first[case]).value, case))
    shown = {row.args for row in rows}
    small = [p for p in points if p not in shown]
    for point in small[: max(0, extra)]:
        rows.append(Row(point, oracle.evaluate(operator, point).value,
                        select_case(definition, dict(zip(params, point)), oracle)))
    for reason in (NO_BRANCH, NAN_CONDITION):
        if reason in first and first[reason] not in {row.args for row in rows}:
            rows.append(Row(first[reason], oracle.evaluate(operator, first[reason]).value, reason))
    lhs = ast.render_expr(definition.lhs, symbols)
    unreached = [case for case in cases if case not in first]
    return ExampleTable(lhs, params, rows, unreached, len(points))


ROW = re.compile(r"^\|(.*)\|\s*$")


def parse_table(text: str, symbols: Symbols) -> tuple[str, list[tuple[tuple, object]]]:
    """``(left-hand side, [(args, value), ...])`` from an examples text."""
    match = re.search(r"Examples of `([^`]+)`", text)
    if match is None:
        raise ValueError("an examples text starts with 'Examples of `<left-hand side>`'")
    rows = []
    lines = [line for line in text.splitlines() if ROW.match(line.strip())]
    header = [cell.strip() for cell in ROW.match(lines[0].strip()).group(1).split("|")]
    has_case = header[-1] == "case"
    width = len(header) - (2 if has_case else 1)
    read = lambda cell: NAN if cell == symbols.nan else int(cell)
    for line in lines[2:]:
        cells = [cell.strip() for cell in ROW.match(line.strip()).group(1).split("|")]
        rows.append((tuple(read(c) for c in cells[:width]), read(cells[width])))
    return match.group(1), rows
