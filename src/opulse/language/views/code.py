"""The code view: a definition as a plain Python function, its parser and its check.

    @definition("a ⊕ b")
    def op_circled_plus(a, b):
        if gt(a, b):
            return add(a, b)
        return NO_CASE

Atoms are called by their names (``add``, ``mod``, ``succ`` or a registered atom's name),
defined operators by a name derived from their symbol, comparisons by ``gt``, ``lt``, ``ge``,
``le``, ``eq`` and ``ne``. :data:`PRELUDE` gives these names the reference semantics: atoms
propagate NaN and apply the bound, a comparison that reads NaN makes the whole call NaN, and
``and``/``or``/``not`` short-circuit as in definitions. ``NO_CASE`` is NaN returned because no
branch applies; ``NAN`` is the literal.

The function is checked by running it: :func:`check_code` executes it with the prelude and
compares it with the reference interpreter on boundary and random inputs.
"""

from __future__ import annotations

import ast as pyast
import random
import re
import unicodedata

from opulse.config import Symbols
from opulse.core.semantics import BASE_OPERATIONS, NAN, Semantics
from opulse.definition import ast
from opulse.language.ir import ALWAYS, ELSE, IF, Concept, OperatorRef

COMPARE = {">": "gt", "<": "lt", ">=": "ge", "<=": "le", "==": "eq", "!=": "ne"}
FROM_COMPARE = {name: op for op, name in COMPARE.items()}


class CodeError(ValueError):
    pass


def function_name(ref: OperatorRef, table: dict | None = None) -> str:
    """``op_`` plus the Unicode names of the symbol's characters; unary operators whose symbol
    also has the other position get ``_prefix``/``_postfix``."""
    parts = []
    for char in ref.symbol:
        if char.isascii() and (char.isalnum() or char == "_"):
            parts.append(char)
            continue
        try:
            name = unicodedata.name(char)
        except ValueError:
            name = f"u{ord(char):04x}"
        parts.append(re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_"))
    name = "op_" + "_".join(parts)
    positions = (table or {}).get((ref.symbol, ref.arity), {ref.position})
    if ref.arity == 1 and len(positions) > 1 or ref.arity != 1 and ref.position not in (None,):
        name += f"_{ref.position}"
    return name


# ------------------------------------------------------------------ render


def render(definition: ast.Definition, symbols: Symbols, table: dict | None = None) -> str:
    concept = Concept.of(definition)
    for name in concept.parameters:
        if not name.isidentifier():
            raise CodeError(f"parameter {name!r} is not a Python name")
    lhs = ast.render_expr(definition.lhs, symbols)
    lines = [f"@definition({lhs!r})",
             f"def {function_name(concept.operator, table)}({', '.join(concept.parameters)}):"]
    if concept.single:
        return "\n".join(lines + [f"    return {_expr(concept.cases[0].body, table)}"])
    opened = False
    for case in concept.cases:
        body = _expr(case.body, table)
        last = case.index == len(concept.cases)
        if case.kind == IF:
            test = _condition(case.guard, table)
        elif case.kind == ELSE and last and opened:
            lines += ["    else:", f"        return {body}"]
            break
        elif case.kind == ALWAYS and last:
            lines.append(f"    return {body}")
            break
        else:  # an else or bare branch that is first or followed by more branches
            test = "ELSE" if case.kind == ELSE else "ALWAYS"
        lines += [f"    {'elif' if opened else 'if'} {test}:", f"        return {body}"]
        opened = True
    if concept.partial:
        lines.append("    return NO_CASE")
    return "\n".join(lines)


def _expr(node: ast.Expr, table) -> str:
    if isinstance(node, ast.Var):
        return node.name
    if isinstance(node, ast.Num):
        return str(node.value)
    if isinstance(node, ast.NaN):
        return "NAN"
    if isinstance(node, ast.Search):
        return f"search_index({node.bound}, lambda {node.index}: {_condition(node.condition, table)})"
    ref = OperatorRef.of(node)
    name = ref.atom or function_name(ref, table)
    return f"{name}({', '.join(_expr(arg, table) for arg in node.args)})"


def _condition(node: ast.Condition, table) -> str:
    if isinstance(node, ast.Compare):
        return f"{COMPARE[node.op]}({_expr(node.left, table)}, {_expr(node.right, table)})"
    if isinstance(node, ast.Not):
        return f"not {_wrap(node.operand, table)}"
    op = "and" if isinstance(node, ast.And) else "or"
    return f"{_wrap(node.left, table)} {op} {_wrap(node.right, table)}"


def _wrap(node: ast.Condition, table) -> str:
    text = _condition(node, table)
    return text if isinstance(node, ast.Compare) else f"({text})"


# ------------------------------------------------------------------ parse


def parse(text: str, symbols: Symbols, names: dict[str, OperatorRef] | None = None,
          params: tuple[str, ...] | None = None) -> list[ast.Definition]:
    """Every ``@definition`` function in ``text``. Calls resolve to atoms by name, to functions
    defined in the text, then to ``names`` (function name -> operator)."""
    from opulse.language.ir import parameter_names, parse_lhs

    try:
        module = pyast.parse(text)
    except SyntaxError as exc:
        raise CodeError(f"not Python: {exc}") from exc
    atoms = {name: OperatorRef(*key) for key, name in BASE_OPERATIONS.items()}
    known = dict(names or {})
    functions = []
    for item in module.body:
        if not isinstance(item, pyast.FunctionDef):
            raise CodeError("the code view holds only @definition functions")
        if len(item.decorator_list) != 1 or not _is_definition(item.decorator_list[0]):
            raise CodeError(f"{item.name} needs exactly one @definition(\"<left-hand side>\") decorator")
        lhs_text = item.decorator_list[0].args[0].value
        params_here = tuple(arg.arg for arg in item.args.args)
        lhs = parse_lhs(lhs_text, params or params_here or parameter_names(symbols, 6), symbols)
        if tuple(arg.name for arg in lhs.args) != params_here:
            raise CodeError(f"{item.name}: parameters {params_here} differ from {lhs_text!r}")
        known[item.name] = OperatorRef.of(lhs)
        functions.append((item, lhs))
    return [_function(item, lhs, known, atoms) for item, lhs in functions]


def _is_definition(node) -> bool:
    return (isinstance(node, pyast.Call) and isinstance(node.func, pyast.Name) and node.func.id == "definition"
            and len(node.args) == 1 and isinstance(node.args[0], pyast.Constant)
            and isinstance(node.args[0].value, str) and not node.keywords)


def _function(item: pyast.FunctionDef, lhs: ast.Apply, known: dict, atoms: dict) -> ast.Definition:
    branches: list[ast.Branch] = []
    body = list(item.body)
    if body and isinstance(body[0], pyast.Expr) and isinstance(body[0].value, pyast.Constant):
        body = body[1:]  # a docstring
    reader = _Expressions(known, atoms, {arg.arg for arg in item.args.args})
    if not body:
        raise CodeError(f"{item.name} is empty")
    statement, rest = body[0], body[1:]
    if isinstance(statement, pyast.Return) and not rest:
        return ast.Definition(lhs, (ast.Branch(reader.expr(statement.value)),))
    if not isinstance(statement, pyast.If):
        raise CodeError(f"{item.name}: expected an if/elif chain or a single return")
    node = statement
    while True:
        body_expr = reader.returned(node.body)
        if _is_name(node.test, "ELSE"):
            branches.append(ast.Branch(body_expr, None, True))
        elif _is_name(node.test, "ALWAYS"):
            branches.append(ast.Branch(body_expr))
        else:
            branches.append(ast.Branch(body_expr, reader.condition(node.test)))
        if len(node.orelse) == 1 and isinstance(node.orelse[0], pyast.If):
            node = node.orelse[0]
            continue
        if node.orelse:
            branches.append(ast.Branch(reader.returned(node.orelse), None, True))
            if rest:
                raise CodeError(f"{item.name}: statements after the else branch")
            return ast.Definition(lhs, tuple(branches))
        break
    if branches[-1].condition is None:  # the chain ended with ELSE/ALWAYS: nothing may follow
        if rest:
            raise CodeError(f"{item.name}: statements after an unconditional branch")
        return ast.Definition(lhs, tuple(branches))
    if len(rest) != 1 or not isinstance(rest[0], pyast.Return):
        raise CodeError(f"{item.name}: the case chain must end with one return statement")
    if not _is_name(rest[0].value, "NO_CASE"):
        branches.append(ast.Branch(reader.expr(rest[0].value)))
    return ast.Definition(lhs, tuple(branches))


def _is_true(node) -> bool:
    return isinstance(node, pyast.Constant) and node.value is True


def _is_name(node, name: str) -> bool:
    return isinstance(node, pyast.Name) and node.id == name


class _Expressions:
    def __init__(self, known: dict, atoms: dict, params: set[str]) -> None:
        self.known = known
        self.atoms = atoms
        self.params = params

    def returned(self, body: list) -> ast.Expr:
        if len(body) != 1 or not isinstance(body[0], pyast.Return):
            raise CodeError("each branch is one return statement")
        return self.expr(body[0].value)

    def expr(self, node) -> ast.Expr:
        if isinstance(node, pyast.Name):
            if node.id == "NAN":
                return ast.NaN()
            if node.id in self.params:
                return ast.Var(node.id)
            raise CodeError(f"unknown name {node.id!r}")
        if isinstance(node, pyast.Constant) and type(node.value) is int and node.value >= 0:
            return ast.Num(node.value)
        if isinstance(node, pyast.Call) and isinstance(node.func, pyast.Name) and not node.keywords:
            name = node.func.id
            if name == "search_index":
                if (len(node.args) != 2 or not isinstance(node.args[0], pyast.Constant)
                        or type(node.args[0].value) is not int or node.args[0].value < 0
                        or not isinstance(node.args[1], pyast.Lambda)
                        or len(node.args[1].args.args) != 1):
                    raise CodeError("search_index needs a non-negative bound and a one-argument lambda")
                index = node.args[1].args.args[0].arg
                reader = _Expressions(self.known, self.atoms, self.params | {index})
                return ast.Search(index, node.args[0].value, reader.condition(node.args[1].body))
            ref = self.atoms.get(name) or self.known.get(name)
            if ref is None:
                raise CodeError(f"unknown operator {name!r}")
            if len(node.args) != ref.arity:
                raise CodeError(f"{name} takes {ref.arity} argument(s)")
            return ref.apply(tuple(self.expr(arg) for arg in node.args))
        raise CodeError(f"unsupported expression {pyast.dump(node)[:60]}")

    def condition(self, node) -> ast.Condition:
        if isinstance(node, pyast.Call) and isinstance(node.func, pyast.Name) and node.func.id in FROM_COMPARE:
            if len(node.args) != 2:
                raise CodeError("comparisons take two arguments")
            return ast.Compare(self.expr(node.args[0]), FROM_COMPARE[node.func.id], self.expr(node.args[1]))
        if isinstance(node, pyast.UnaryOp) and isinstance(node.op, pyast.Not):
            return ast.Not(self.condition(node.operand))
        if isinstance(node, pyast.BoolOp):
            parts = [self.condition(value) for value in node.values]
            joined = parts[0]
            for part in parts[1:]:
                joined = ast.And(joined, part) if isinstance(node.op, pyast.And) else ast.Or(joined, part)
            return joined
        raise CodeError(f"unsupported condition {pyast.dump(node)[:60]}")


# ------------------------------------------------------------------ run


class Undefined(Exception):
    """A comparison read NaN: the current call is NaN."""


def prelude(semantics: Semantics) -> dict:
    """Names the code view uses, with the reference semantics."""
    namespace: dict = dict(semantics.operations())

    def comparison(op):
        def compare(x, y):
            if x is NAN or y is NAN:
                raise Undefined
            return op(x, y)
        return compare

    import operator as py

    for name, fn in (("gt", py.gt), ("lt", py.lt), ("ge", py.ge), ("le", py.le), ("eq", py.eq), ("ne", py.ne)):
        namespace[name] = comparison(fn)

    def definition(lhs: str):
        def wrap(fn):
            def call(*args):
                try:
                    return fn(*args)
                except Undefined:
                    return NAN
            call.__name__ = fn.__name__
            call.lhs = lhs
            return call
        return wrap

    namespace.update(NAN=NAN, NO_CASE=NAN, ELSE=True, ALWAYS=True, definition=definition)
    def search_index(bound, condition):
        for index in range(bound + 1):
            if condition(index):
                return index
        return NAN

    namespace["search_index"] = search_index
    return namespace


def run(text: str, semantics: Semantics, helpers: dict | None = None) -> dict:
    """Execute code-view text; returns its namespace (functions by name)."""
    namespace = prelude(semantics)
    namespace.update(helpers or {})
    exec(compile(text, "<code view>", "exec"), namespace)  # noqa: S102 - our own rendered text
    return namespace


def sample_inputs(arity: int, bound: int | None, literals: set[int], rng: random.Random, count: int = 200):
    """Boundary values (0, ±1, ±2, literals and their neighbours, the bound), all their
    combinations for one or two arguments, then random points."""
    edges = {0, 1, -1, 2, -2, 3, -3, 7, -7, 10, -10, 100, -100}
    for value in literals:
        edges |= {value - 1, value, value + 1, -value}
    if bound is not None:
        edges |= {bound, -bound, bound - 1, -(bound - 1)}
        edges = {v for v in edges if abs(v) <= bound}
    edges = sorted(edges, key=lambda v: (abs(v), v))
    points = []
    if arity <= 2:
        import itertools

        points += list(itertools.product(edges, repeat=arity))
    else:
        points += [tuple(rng.choice(edges) for _ in range(arity)) for _ in range(count)]
    span = min(bound or 10**6, 10**6)
    points += [tuple(rng.randint(-span, span) for _ in range(arity)) for _ in range(count)]
    points += [tuple(rng.randint(-20, 20) for _ in range(arity)) for _ in range(count)]
    return list(dict.fromkeys(points))


__all__ = ["ALWAYS", "CodeError", "function_name", "parse", "prelude", "render", "run", "sample_inputs"]
