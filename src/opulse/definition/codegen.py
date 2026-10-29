"""Compile a :class:`~opulse.definition.ast.Definition` into Python source.

Each operator becomes three functions (docs/reference/semantics.md, sections 4-5):

* ``_e_<id>(a[, b])`` returns ``(value, base_ops, calls)``;
* ``op_<id>(a[, b])`` returns the value;
* ``op_count_<id>(a[, b])`` returns ``base_ops``.

``op_compute_func`` holds the first two, ``op_count_func`` the third, so the
JSON fields keep their legacy meaning. The source is plain Python that Cython
also accepts. It expects ``NAN`` and every base operation's ``op_<id>`` in its
global namespace (see :mod:`opulse.runtime`).

Inside one function, identical calls are evaluated once and their result is
reused, but every occurrence still adds its counts, so the counts equal those
of the reference interpreter, which evaluates every occurrence. Reuse never
crosses out of a conditional block: a value first computed under a
short-circuit is only visible inside that block.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from opulse.core.operator import Operator
from opulse.core.semantics import base_operation_name
from opulse.definition import ast

INDENT = "    "

# Resolves a surface application to the operator it denotes.
Resolver = Callable[[ast.Apply], Operator]


class UnknownOperatorError(LookupError):
    pass


@dataclass(frozen=True)
class GeneratedCode:
    compute: str
    count: str
    dependencies: tuple[str, ...]  # func ids of called operators, excluding itself


def evaluator_name(func_id: str) -> str:
    return f"_e_{func_id}"


def is_base(operator: Operator) -> bool:
    return operator.definition is None and base_operation_name(
        operator.symbol, operator.n_ary, operator.unary_position) is not None


def registry_resolver(registry, self_operator: Operator | None = None) -> Resolver:
    """Resolve against ``registry``; ``self_operator`` (not yet registered) is also visible."""

    def resolve(node: ast.Apply) -> Operator:
        if self_operator is not None and (
            node.symbol == self_operator.symbol
            and node.n_ary == self_operator.n_ary
            and node.unary_position == self_operator.unary_position
        ):
            return self_operator
        operator = registry.find(node.symbol, node.n_ary, node.unary_position)
        if operator is None or not (operator.has_code or is_base(operator)):
            raise UnknownOperatorError(f"no operator for {node.symbol!r} {node.unary_position or 'binary'}")
        return operator

    return resolve


def compile_definition(definition: ast.Definition, func_id: str, resolve: Resolver,
                       parameter_types: tuple[str, ...] | None = None,
                       result_type: str | None = None) -> GeneratedCode:
    params = definition.parameters
    if len(set(params)) != len(params):
        raise ValueError(f"definition parameters repeat a name: {params}")
    _check_variables(definition, set(params))
    writer = _Writer(func_id, resolve)
    if result_type is None and parameter_types is not None:
        try:
            result_type = resolve(definition.lhs).result_type
        except LookupError:
            result_type = "int"
    if parameter_types is not None and (result_type != "int" or
                                        any(kind != "int" for kind in parameter_types)):
        checks = [f"({name} is NAN or ({_type_guard(name, kind)}))"
                  for name, kind in zip(params, parameter_types)]
        writer.line(f"if not ({' and '.join(checks)}):")
        writer.push()
        writer.line("return (NAN, 0, 0)")
        writer.pop()
    writer.emit_definition(definition)
    args = ", ".join(params)
    evaluator = evaluator_name(func_id)
    compute = writer.source(params) + (
        f"\n\ndef op_{func_id}({args}):\n{INDENT}return {evaluator}({args})[0]\n"
    )
    count = f"def op_count_{func_id}({args}):\n{INDENT}return {evaluator}({args})[1]\n"
    called = set(writer.called)
    called.discard(func_id)
    return GeneratedCode(compute, count, tuple(sorted(called)))


def _type_guard(name: str, kind: str) -> str:
    if kind == "int":
        return f"isinstance({name}, int) and not isinstance({name}, bool)"
    if kind == "bool":
        return f"isinstance({name}, bool)"
    if kind == "str":
        return f"isinstance({name}, str)"
    if kind == "grid":
        return (f"isinstance({name}, (tuple, list)) and 1 <= len({name}) <= 10 and "
                f"all(isinstance(_row, (tuple, list)) and 1 <= len(_row) <= 10 "
                f"and len(_row) == len({name}[0]) and "
                f"all(type(_cell) is int and 0 <= _cell <= 9 for _cell in _row) "
                f"for _row in {name})")
    if kind == "list[int]":
        return (f"isinstance({name}, (tuple, list)) and "
                f"all(isinstance(_v, int) and not isinstance(_v, bool) for _v in {name})")
    if kind.startswith("perm["):
        from opulse.core.types import parse_type

        return f"isinstance({name}, Permutation) and len({name}) == {parse_type(kind).size}"
    if kind in ("note", "melody"):
        if kind == "note":
            return f"isinstance({name}, int) and not isinstance({name}, bool) and 0 <= {name} <= 127"
        return (f"isinstance({name}, (tuple, list)) and all(isinstance(_v, (tuple, list)) "
                f"and len(_v) == 2 and isinstance(_v[0], int) and not isinstance(_v[0], bool) "
                f"and 0 <= _v[0] <= 127 and isinstance(_v[1], int) and not isinstance(_v[1], bool) "
                f"and _v[1] > 0 for _v in {name})")
    raise ValueError(f"compiled guard does not support {kind!r}")


# ------------------------------------------------------------------ internals


def _check_variables(definition: ast.Definition, allowed: set[str]) -> None:
    for branch in definition.branches:
        unknown = ast.branch_variables(branch) - allowed
        if unknown:
            raise ValueError(f"definition uses unbound variables {sorted(unknown)}")


@dataclass
class _Scope:
    cached: dict[str, str] = field(default_factory=dict)  # call key -> local holding its triple


class _Writer:
    def __init__(self, func_id: str, resolve: Resolver) -> None:
        self.func_id = func_id
        self.resolve = resolve
        self.lines: list[str] = []
        self.depth = 1
        self.scopes: list[_Scope] = [_Scope()]
        self.counter = 0
        self.called: set[str] = set()
        self.bindings: dict[str, str] = {}

    # -------------------------------------------------------------- utilities
    def line(self, text: str) -> None:
        self.lines.append(INDENT * self.depth + text)

    def fresh(self, prefix: str) -> str:
        self.counter += 1
        return f"{prefix}{self.counter}"

    def lookup(self, key: str) -> str | None:
        for scope in reversed(self.scopes):
            if key in scope.cached:
                return scope.cached[key]
        return None

    def push(self) -> None:
        self.depth += 1
        self.scopes.append(_Scope())

    def pop(self) -> None:
        self.depth -= 1
        self.scopes.pop()

    # ------------------------------------------------------------ definitions
    def emit_definition(self, definition: ast.Definition) -> None:
        self.line("_o = 0")
        self.line("_c = 0")
        for branch in definition.branches:
            if branch.condition is None:  # ``else`` or a bare expression: always taken
                self.line(f"return ({self.value(branch.expr)}, _o, _c)")
                return
            flag = self.condition(branch.condition)
            self.line(f"if {flag}:")
            self.push()
            self.line(f"return ({self.value(branch.expr)}, _o, _c)")
            self.pop()
        self.line("return (NAN, _o, _c)")  # no branch matched

    # ------------------------------------------------------------ expressions
    def value(self, node: ast.Expr) -> str:
        """Emit code computing ``node``; return a Python expression for its value."""
        if isinstance(node, ast.Var):
            return self.bindings.get(node.name, node.name)
        if isinstance(node, ast.Num):
            try:
                return str(node.value)
            except ValueError:
                return hex(node.value)
        if isinstance(node, ast.NaN):
            return "NAN"
        if isinstance(node, ast.Search):
            result = self.fresh("s")
            index = self.fresh("i")
            self.line(f"{result} = NAN")
            self.line(f"for {index} in range({node.bound + 1}):")
            self.push()
            previous = self.bindings.get(node.index)
            self.bindings[node.index] = index
            flag = self.condition(node.condition)
            if previous is None:
                del self.bindings[node.index]
            else:
                self.bindings[node.index] = previous
            self.line(f"if {flag}:")
            self.push()
            self.line(f"{result} = {index}")
            self.line("break")
            self.pop()
            self.pop()
            return result
        if isinstance(node, ast.Literal):
            from opulse.worlds.perm import Permutation

            if isinstance(node.value, Permutation):
                return f"Permutation({tuple(node.value)!r})"
            return repr(node.value)
        args = [self.value(arg) for arg in node.args]
        callee = self.resolve(node)
        self.called.add(callee.func_id)
        joined = ", ".join(args)
        if is_base(callee):
            key = f"{callee.compute_name}({joined})"
            local = self.lookup(key)
            if local is None:
                local = self.fresh("v")
                self.line(f"{local} = {key}")
                self.scopes[-1].cached[key] = local
            self.line("_o += 1")
            self.line("_c += 1")
            return local
        key = f"{evaluator_name(callee.func_id)}({joined})"
        triple = self.lookup(key)
        if triple is None:
            triple = self.fresh("r")
            self.line(f"{triple} = {key}")
            self.scopes[-1].cached[key] = triple
        self.line(f"_o += {triple}[1]")
        self.line(f"_c += 1 + {triple}[2]")
        return f"{triple}[0]"

    # ------------------------------------------------------------- conditions
    def condition(self, node: ast.Condition) -> str:
        """Emit code setting a fresh flag to the truth of ``node``; return the flag.

        A comparison with a NaN side returns NaN from the whole function
        (spec section 4, rule 2). ``and``/``or`` short-circuit.
        """
        flag = self.fresh("t")
        if isinstance(node, ast.Truth):
            value = self.value(node.expr)
            self.line(f"if {value} is NAN:")
            self.push()
            self.line("return (NAN, _o, _c)")
            self.pop()
            self.line(f"{flag} = {value}")
            return flag
        if isinstance(node, ast.Compare):
            left = self.value(node.left)
            right = self.value(node.right)
            checks = [f"{side} is NAN" for side in (left, right) if not side.isdigit()]
            if checks:
                self.line(f"if {' or '.join(checks)}:")
                self.push()
                self.line("return (NAN, _o, _c)")
                self.pop()
            self.line(f"{flag} = {left} {node.op} {right}")
            return flag
        if isinstance(node, ast.Not):
            inner = self.condition(node.operand)
            self.line(f"{flag} = not {inner}")
            return flag
        left = self.condition(node.left)
        self.line(f"{flag} = {left}")
        self.line(f"if {'' if isinstance(node, ast.And) else 'not '}{flag}:")
        self.push()
        right = self.condition(node.right)
        self.line(f"{flag} = {right}")
        self.pop()
        return flag

    def source(self, params: tuple[str, ...]) -> str:
        header = f"def {evaluator_name(self.func_id)}({', '.join(params)}):"
        return "\n".join([header, *self.lines])
