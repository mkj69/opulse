"""Three views of one operator: formula, behaviour table and dependency outline.

* **Formula.** Every branch body with the definitions of simple, non-branching callees
  inlined down to base operations (callees that branch or recurse stay as applications).
  Where the operator does not recurse, SymPy proposes an expanded form of the arithmetic
  (``+ - *`` and negation; other operations are kept as opaque applications), and
  :class:`~opulse.solver.equivalence.EquivalenceChecker` decides both rewrites under Opulse
  semantics: ``proved`` (z3), ``refuted`` (a counterexample re-checked by the reference
  interpreter) or ``bounded`` (undecided; no counterexample on a small range). A proposal is
  shown only when it is smaller; a refuted one comes with its counterexample.
* **Behaviour table.** The operator on every input of a range, with the branch path its
  own definition takes (one entry per unfolding of the operator, so recursion shows as a
  sequence) and the value. Consecutive inputs with the same path form one row; for a
  binary operator, rows of ``a`` with the same runs over ``b`` are merged into one block.
* **Outline.** The operators it uses, as a tree (each operator expanded once).

Values come from the reference interpreter (:class:`~opulse.verify.Oracle`) and branch
paths from :class:`~opulse.trace.Reducer` steps, so nothing here is estimated.
"""

from __future__ import annotations

from dataclasses import dataclass

from opulse.core.operator import RECURSIVE, SIMPLE, Operator
from opulse.core.semantics import NAN, base_operation_name
from opulse.definition import ast
from opulse.definition.ast import render_condition
from opulse.expression.nodes import (
    Call,
    Node,
    Number,
    Variable,
    from_ast,
    has_variable,
    literal_form,
    to_ast,
)
from opulse.trace.reducer import Reducer
from opulse.trace.tree import operator_kind

MAX_INLINED_SIZE = 400


@dataclass
class Explainer:
    registry: object
    oracle: object  # opulse.verify.Oracle
    runtime: object
    renderer: object  # opulse.expression.render.ExpressionRenderer
    timeout_ms: int = 3000

    def __post_init__(self) -> None:
        self._inlined: dict[str, Node | None] = {}
        self._reducers: dict[str, Reducer] = {}
        self._checker = None
        try:
            from opulse.solver.equivalence import EquivalenceChecker
            from opulse.solver.z3_encode import Z3Encoder

            self._checker = EquivalenceChecker(Z3Encoder(self.oracle), timeout_ms=self.timeout_ms)
        except Exception:  # noqa: BLE001 - legacy semantics: no z3 encoding, checks are skipped
            self._checker = None

    # ------------------------------------------------------------------ all three
    def explain(self, op: Operator, a_range: tuple[int, int] | None = None,
                b_range: tuple[int, int] | None = None) -> dict:
        definition = self.oracle._definition_of(op)
        return {"operator": op.func_id, "symbol": op.symbol, "kind": operator_kind(op),
                "layer": op.recursive_layer, "definition": op.definition,
                "parameters": list(definition.parameters), "formula": self.formula(op),
                "table": self.table(op, a_range, b_range), "outline": self.outline(op)}

    # ------------------------------------------------------------------ formula
    def formula(self, op: Operator) -> dict:
        definition = self.oracle._definition_of(op)
        recursive = self._recursive(op)
        branches = []
        for index, branch in enumerate(definition.branches):
            if _contains_search(branch.expr):
                branches.append({"index": index, "condition": None if branch.condition is None else
                                 render_condition(branch.condition, self.oracle.parser.symbols),
                                 "else": branch.is_else,
                                 "body": ast.render_expr(branch.expr, self.oracle.parser.symbols),
                                 "inlined": None, "inlined_check": None, "simplified": None,
                                 "simplified_check": None,
                                 "skip_reason": "search expressions cannot be inlined or simplified"})
                continue
            body = from_ast(branch.expr, self.registry)
            inlined = self.inline(body)
            row = {"index": index, "condition": None if branch.condition is None else
                   render_condition(branch.condition, self.oracle.parser.symbols),
                   "else": branch.is_else, "body": self._text(body),
                   "inlined": None if inlined == body else self._text(inlined),
                   "inlined_check": None, "simplified": None, "simplified_check": None}
            if not recursive:
                if inlined != body:
                    row["inlined_check"] = self._check(body, inlined)
                proposal = simplify(self.fold(inlined), self.registry)
                if proposal is not None and _size(proposal) < _size(inlined):
                    verdict = self._check(inlined, proposal)
                    row["simplified_check"] = verdict
                    row["simplified"] = self._text(proposal)
            branches.append(row)
        return {"recursive": recursive, "checked": self._checker is not None and not recursive
                and not any(_contains_search(branch.expr) for branch in definition.branches),
                "branches": branches}

    def inline(self, node: Node) -> Node:
        """``node`` with every application of an inlinable operator replaced by its body."""
        if not isinstance(node, Call):
            return node
        args = tuple(self.inline(arg) for arg in node.args)
        body = self._inlined_body(node.operator)
        if body is None:
            return Call(node.operator, args)
        params = self.oracle._definition_of(node.operator).parameters
        return _substitute(body, dict(zip(params, args)))

    def fold(self, node: Node) -> Node:
        """Every closed application with a defined value replaced by that value."""
        if not isinstance(node, Call):
            return node
        if not has_variable(node):
            value = self.oracle.evaluate_expr(to_ast(node), {}).value
            if value is not NAN:
                return literal_form(Number(value), self.registry)
        return Call(node.operator, tuple(self.fold(arg) for arg in node.args))

    def _inlined_body(self, op: Operator) -> Node | None:
        """The body of a simple operator with callees inlined, or None when it is not inlinable."""
        if op.definition is None or op.definition_type != SIMPLE:
            return None
        if op.func_id not in self._inlined:
            self._inlined[op.func_id] = None  # guards against self-reference
            definition = self.oracle._definition_of(op)
            if not _contains_search(definition.branches[0].expr):
                body = self.inline(from_ast(definition.branches[0].expr, self.registry))
                self._inlined[op.func_id] = body if _size(body) <= MAX_INLINED_SIZE else None
        return self._inlined[op.func_id]

    def _check(self, left: Node, right: Node) -> dict:
        if self._checker is None:
            return {"status": "not checked"}
        return self._checker.check(left, right).to_dict()

    def _recursive(self, op: Operator) -> bool:
        """True when ``op`` or anything it uses recurses."""
        seen, stack = set(), [op]
        while stack:
            current = stack.pop()
            if current.func_id in seen:
                continue
            seen.add(current.func_id)
            if current.definition_type == RECURSIVE:
                return True
            stack.extend(self.registry.get(dep) for dep in current.dependencies if dep in self.registry)
        return False

    # ------------------------------------------------------------------ table
    def table(self, op: Operator, a_range: tuple[int, int] | None = None,
              b_range: tuple[int, int] | None = None) -> dict:
        """Branch paths and values on a range (default: around the constants in the conditions)."""
        if op.n_ary > 2:
            return {"n_ary": op.n_ary, "note": "table covers arity 1 and 2 only"}
        a_range = a_range or default_range(self.oracle._definition_of(op), op.n_ary)
        if op.n_ary == 1:
            rows = []
            for x in range(a_range[0], a_range[1] + 1):
                path, value = self.path(op, (x,))
                if rows and rows[-1]["path"] == path:
                    rows[-1]["to"] = x
                    rows[-1]["values"].append(value)
                else:
                    rows.append({"from": x, "to": x, "path": path, "values": [value]})
            return {"n_ary": 1, "a": list(a_range), "rows": rows}
        b_range = b_range or a_range
        blocks = []
        for x in range(a_range[0], a_range[1] + 1):
            runs = []
            for y in range(b_range[0], b_range[1] + 1):
                path, value = self.path(op, (x, y))
                if runs and runs[-1]["path"] == path:
                    runs[-1]["to"] = y
                    runs[-1]["values"].add(_key(value))
                else:
                    runs.append({"from": y, "to": y, "path": path, "values": {_key(value)}})
            shape = [(r["from"], r["to"], r["path"]) for r in runs]
            if blocks and blocks[-1]["shape"] == shape:
                blocks[-1]["to"] = x
                for old, new in zip(blocks[-1]["runs"], runs):
                    old["values"] |= new["values"]
            else:
                blocks.append({"from": x, "to": x, "shape": shape, "runs": runs})
        out = []
        for block in blocks:
            runs = [{"from": r["from"], "to": r["to"], "path": r["path"], "distinct": len(r["values"]),
                     "value": _unkey(next(iter(r["values"]))) if len(r["values"]) == 1 else None,
                     "min": _bound(r["values"], min), "max": _bound(r["values"], max)}
                    for r in block["runs"]]
            out.append({"from": block["from"], "to": block["to"], "runs": runs})
        return {"n_ary": 2, "a": list(a_range), "b": list(b_range), "blocks": out}

    def path(self, op: Operator, inputs: tuple) -> tuple[list, object]:
        """``([[branch, count], ...], value)``: the branches ``op``'s own unfoldings take,
        1-based and run-length encoded; ``[["undefined", 1]]`` style entries mark NaN rules."""
        reducer = self._reducers.get(op.func_id)
        if reducer is None:
            reducer = self._reducers[op.func_id] = Reducer(self.registry, self.runtime, self.oracle.parser,
                                                           expand=lambda o: o is op)
        trace = reducer.reduce(Call(op, tuple(Number(v) for v in inputs)))
        taken = []
        for step in trace.steps:
            if step.operator is not op:
                continue
            taken.append(step.branch_index + 1 if step.branch_index is not None else step.reason)
        path: list = []
        for item in taken:
            if path and path[-1][0] == item:
                path[-1][1] += 1
            else:
                path.append([item, 1])
        value = self.oracle.evaluate(op, inputs).value
        if not trace.truncated and not _same(value, trace.value):
            raise AssertionError(f"{op.symbol}{inputs}: trace gives {trace.value!r}, reference {value!r}")
        return path, None if value is NAN else value

    # ------------------------------------------------------------------ outline
    def outline(self, op: Operator) -> dict:
        seen: set[str] = set()

        def visit(current: Operator) -> dict:
            node = {"operator": current.func_id, "symbol": current.symbol,
                    "form": operator_form(current, self.renderer.symbols),
                    "kind": operator_kind(current), "layer": current.recursive_layer}
            if current.func_id in seen:
                node["repeat"] = True
                return node
            seen.add(current.func_id)
            if current.definition_type == RECURSIVE:
                node["self"] = True
            uses = []
            for dep in sorted(set(current.dependencies), key=lambda d: (self._layer(d), d)):
                if dep == current.func_id:
                    continue
                if dep in self.registry:
                    used = self.registry.get(dep)
                    if used.definition is None and dep in seen:
                        continue  # a base operation is listed once
                    uses.append(visit(used))
            node["uses"] = uses
            return node

        return visit(op)

    def _layer(self, func_id: str) -> tuple:
        op = self.registry.get(func_id) if func_id in self.registry else None
        return (-(op.recursive_layer or 0) if op is not None and op.definition else 1, op.symbol if op else "")

    def _text(self, node: Node) -> str:
        return self.renderer.full(node)  # definition style: every inner application bracketed


# ------------------------------------------------------------------ text
def render_explanation(data: dict) -> str:
    """Plain text of :meth:`Explainer.explain` output."""
    lines = [f"{data['symbol']}  ({data['kind']}, layer {data['layer']})", data["definition"], "", "formula"]
    formula = data["formula"]
    for row in formula["branches"]:
        where = "else" if row["else"] else (f"if {row['condition']}" if row["condition"] else "always")
        lines.append(f"  branch {row['index'] + 1}, {where}: {row['body']}")
        if row.get("skip_reason"):
            lines.append(f"    ({row['skip_reason']})")
        if row["inlined"]:
            lines.append(f"    inlined:    {row['inlined']}{_verdict(row['inlined_check'])}")
        if row["simplified"]:
            lines.append(f"    SymPy form: {row['simplified']}{_verdict(row['simplified_check'])}")
    if formula["recursive"]:
        lines.append("  (uses recursion: no SymPy form)")
    table = data["table"]
    lines.append("")
    if table["n_ary"] == 1:
        lines.append(f"behaviour, a in [{table['a'][0]}, {table['a'][1]}]")
        for row in table["rows"]:
            span = f"a = {row['from']}" if row["from"] == row["to"] else f"a = {row['from']} .. {row['to']}"
            lines.append(f"  {span:<18} {path_text(row['path']):<24} {_values(row['values'])}")
    elif table["n_ary"] == 2:
        lines.append(f"behaviour, a in [{table['a'][0]}, {table['a'][1]}], b in [{table['b'][0]}, {table['b'][1]}]")
        for block in table["blocks"]:
            span = f"a = {block['from']}" if block["from"] == block["to"] else f"a = {block['from']} .. {block['to']}"
            lines.append(f"  {span}")
            for run in block["runs"]:
                bspan = f"b = {run['from']}" if run["from"] == run["to"] else f"b = {run['from']} .. {run['to']}"
                value = (_show(run["value"]) if run["distinct"] == 1
                         else f"{run['distinct']} values in [{_show(run['min'])}, {_show(run['max'])}]")
                lines.append(f"    {bspan:<16} {path_text(run['path']):<24} {value}")
    else:
        lines.append(f"behaviour: {table['note']} (arity {table['n_ary']})")
    lines += ["", "uses"]
    _outline_lines(data["outline"], lines, "  ")
    return "\n".join(lines)


def operator_form(op: Operator, symbols=None) -> str:
    """The operator applied to placeholder operands: ``a + b``, ``- a``, ``a @``."""
    if op.n_ary <= 2:
        return op.apply_str(*("a", "b")[:op.n_ary])
    if symbols is None:
        from opulse.config import Symbols

        symbols = Symbols()
    return op.apply_str(*symbols.operands(op.n_ary), symbols=symbols)


def _contains_search(node: ast.Expr) -> bool:
    if isinstance(node, ast.Search):
        return True
    return isinstance(node, ast.Apply) and any(_contains_search(arg) for arg in node.args)


def path_text(path: list) -> str:
    parts = []
    for item, count in path:
        name = f"branch {item}" if isinstance(item, int) else f"undefined ({item})"
        parts.append(name if count == 1 else f"{name} x{count}")
    return ", ".join(parts) or "-"


def _outline_lines(node: dict, lines: list[str], pad: str) -> None:
    extra = " (self)" if node.get("self") else ""
    extra += " (above)" if node.get("repeat") else ""
    layer = "" if node["kind"] == "base" else f", layer {node['layer']}"
    lines.append(f"{pad}{node['form']}  ({node['kind']}{layer}){extra}")
    for child in node.get("uses", []):
        _outline_lines(child, lines, pad + "  ")


def _verdict(check: dict | None) -> str:
    if not check:
        return ""
    status = check["status"]
    if status == "refuted":
        point = ", ".join(f"{k} = {v}" for k, v in check["counterexample"].items())
        return f"   [refuted at {point}: {_show(check['left_value'])} vs {_show(check['right_value'])}]"
    if status == "bounded":
        r = check.get("range") or ["?", "?"]
        return f"   [z3 undecided; equal on [{r[0]}, {r[1]}]]"
    if status == "proved":
        return "   [proved equal by z3]"
    return f"   [{status}]"


def _values(values: list) -> str:
    shown = [_show(v) for v in values]
    return ", ".join(shown) if len(shown) <= 8 else ", ".join(shown[:6]) + f", ... , {shown[-1]}"


def _show(value) -> str:
    return "NaN" if value is None or value is NAN else str(value)


# ------------------------------------------------------------------ ranges
def default_range(definition: ast.Definition, n_ary: int) -> tuple[int, int]:
    """Inputs around the constants compared in the conditions, at least ``[-12, 12]``."""
    constants = [0]
    for branch in definition.branches:
        if branch.condition is not None:
            constants += list(_condition_numbers(branch.condition))
    low, high = min(-12, min(constants) - 3), max(12, max(constants) + 3)
    width = 120 if n_ary == 1 else 100
    return max(low, high - width + 1), high


def _condition_numbers(node: ast.Condition):
    for operand in ast.condition_operands(node):
        yield from _numbers(operand)


def _numbers(node: ast.Expr):
    if isinstance(node, ast.Num):
        yield node.value
    elif isinstance(node, ast.Apply):
        if node.symbol == "-" and node.n_ary == 1 and isinstance(node.args[0], ast.Num):
            yield -node.args[0].value
            return
        for arg in node.args:
            yield from _numbers(arg)


# ------------------------------------------------------------------ SymPy
ARITHMETIC = ("add", "sub", "mul", "neg")


def simplify(node: Node, registry) -> Node | None:
    """SymPy's expanded form of ``node``, other operations kept as opaque applications; None
    when ``node`` contains NaN or the arithmetic operators are missing. Only a proposal."""
    import sympy

    from opulse.core.semantics import BASE_OPERATIONS

    ops = {name: registry.find(symbol, n_ary, position)
           for (symbol, n_ary, position), name in BASE_OPERATIONS.items() if name in ARITHMETIC}
    if any(op is None for op in ops.values()):
        return None
    opaque: dict[str, Operator] = {}
    names: dict[str, str] = {}

    def to_sympy(n: Node):
        if isinstance(n, Number):
            if n.value is NAN:
                raise _NoSympy
            return sympy.Integer(n.value)
        if isinstance(n, Variable):
            return sympy.Symbol(n.name, integer=True)
        args = [to_sympy(a) for a in n.args]
        name = None if n.operator.definition is not None else base_operation_name(
            n.operator.symbol, n.operator.n_ary, n.operator.unary_position)
        if name in ARITHMETIC:
            return {"add": lambda x, y: x + y, "sub": lambda x, y: x - y,
                    "mul": lambda x, y: x * y, "neg": lambda x: -x}[name](*args)
        fname = names.setdefault(n.operator.func_id, f"F{len(names)}")
        opaque[fname] = n.operator
        return sympy.Function(fname)(*args)

    try:
        expression = to_sympy(node)
    except _NoSympy:
        return None
    return _from_sympy(sympy.expand(expression), ops, opaque)


class _NoSympy(Exception):
    pass


def _from_sympy(e, ops: dict[str, Operator], opaque: dict[str, Operator]) -> Node:
    import sympy

    def number(n: int) -> Node:
        return Number(n) if n >= 0 else Call(ops["neg"], (Number(-n),))

    back = lambda x: _from_sympy(x, ops, opaque)
    if e.is_Integer:
        return number(int(e))
    if e.is_Symbol:
        return Variable(e.name)
    if isinstance(e, sympy.core.function.AppliedUndef):
        return Call(opaque[e.func.__name__], tuple(back(a) for a in e.args))
    if e.is_Pow and e.exp.is_Integer and int(e.exp) > 0:
        base = back(e.base)
        result = base
        for _ in range(int(e.exp) - 1):
            result = Call(ops["mul"], (result, base))
        return result
    if e.is_Mul:
        coefficient, rest = e.as_coeff_Mul()
        if coefficient == -1:
            return Call(ops["neg"], (back(rest),))
        factors = [sympy.Integer(coefficient)] if coefficient != 1 else []
        factors += list(sympy.Mul.make_args(rest))
        result = back(factors[0])
        for factor in factors[1:]:
            result = Call(ops["mul"], (result, back(factor)))
        return result
    if e.is_Add:
        terms = sorted(sympy.Add.make_args(e), key=lambda t: t.could_extract_minus_sign())
        result = back(terms[0])
        for term in terms[1:]:
            if term.could_extract_minus_sign():
                result = Call(ops["sub"], (result, back(-term)))
            else:
                result = Call(ops["add"], (result, back(term)))
        return result
    raise ValueError(f"unsupported SymPy expression {e!r}")


# ------------------------------------------------------------------ helpers
def _substitute(node: Node, env: dict[str, Node]) -> Node:
    if isinstance(node, Variable):
        return env.get(node.name, node)
    if isinstance(node, Call):
        return Call(node.operator, tuple(_substitute(arg, env) for arg in node.args))
    return node


def _size(node: Node) -> int:
    return 1 + sum(_size(arg) for arg in node.args) if isinstance(node, Call) else 1


def _same(a, b) -> bool:
    return (a is NAN and b is NAN) or (a is not NAN and b is not NAN and a == b)


def _key(value):
    return "NaN" if value is None or value is NAN else value


def _unkey(value):
    return None if value == "NaN" else value


def _bound(values: set, pick):
    numbers = [v for v in values if v != "NaN"]
    return pick(numbers) if numbers else None


__all__ = ["Explainer", "default_range", "path_text", "render_explanation", "simplify"]
