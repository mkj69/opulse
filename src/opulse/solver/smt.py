"""SMT-LIB export of operator definitions, including the ``z3`` field.

Each operator ``f`` becomes two SMT-LIB functions whose arguments are
(definedness, value) pairs, one pair per operand::

    (define-fun f_d ((a_d Bool) (a Int) (b_d Bool) (b Int)) Bool ...)  ; f(a, b) is defined
    (define-fun f_v ((a_d Bool) (a Int) (b_d Bool) (b Int)) Int  ...)  ; its value where defined

Operands carry definedness because a definition may ignore an undefined
operand (docs/reference/semantics.md section 4). Bodies call other operators by
name, so each export stays as small as the definition. Operators are
declared with ``define-funs-rec`` (also non-recursive ones: ``define-fun`` is
a macro in z3 and would inline whole dependency chains). The base operations come from a shared prelude in
which truncating division and the bound are spelled out (SMT-LIB ``div`` and
``mod`` are Euclidean and would be wrong for negative operands).

``module`` assembles a self-contained script (prelude, dependencies in
topological order, the operator). ``check_module`` evaluates it with z3 on
boundary inputs, NaN included, and compares every result with the reference
oracle; ``export`` never returns text that failed this check.
"""

from __future__ import annotations

import itertools
import re

import z3

from opulse.core.operator import Operator
from opulse.core.primitives import CUSTOM
from opulse.core.semantics import BASE_OPERATIONS, NAN, base_operation_name
from opulse.definition import ast
from opulse.solver.z3_encode import NotExpressible, Z3Encoder, ZVal

CHECK_VALUES = (0, 1, -1, 2, -2, 3, -7, 9, 10, -10, 99, -100, 12345, -54321)
_COMPARE = {"==": "=", "!=": "distinct", ">": ">", "<": "<", ">=": ">=", "<=": "<="}


def smt_name(operator: Operator) -> str:
    return f"op_{operator.func_id}"


def is_operation(operator: Operator) -> bool:
    """False for numeral-base markers, which are registered but never applied."""
    return operator.definition is not None or base_operation_name(
        operator.symbol, operator.n_ary, operator.unary_position) is not None


# ----------------------------------------------------------------- prelude
def prelude(encoder: Z3Encoder) -> str:
    """Base operations as ``base_<name>_d`` / ``base_<name>_v`` over defined operands."""
    names = ["a", "b", *(f"x{i}" for i in range(2, max((k[1] for k in BASE_OPERATIONS), default=2)))]
    variables = [z3.Int(name) for name in names]
    lines = [f"; Opulse base operations, exact mode, bound B = {encoder.bound}"]
    for (_, n_ary, _), name in BASE_OPERATIONS.items():
        if name == "defined":
            if encoder.oracle.registry.find("defined", 1, "prefix") is None:
                continue
            lines.append("(define-fun base_defined_d ((a_d Bool) (a Int)) Bool true)")
            lines.append("(define-fun base_defined_v ((a_d Bool) (a Int)) Int (ite a_d 1 0))")
            continue
        primitive = CUSTOM.get(name)
        if primitive is not None and (primitive.result_type != "int" or
                                      any(kind != "int" for kind in primitive.parameter_types)):
            continue  # this SMT-LIB exporter represents integer functions only
        args = variables[:n_ary]
        encoder.reset()
        try:
            zv = encoder._base(name, [ZVal(z3.BoolVal(True), x) for x in args])
        except NotExpressible:
            continue  # digit operations without a bound; operators using them are not exported
        params = " ".join(f"({x} Int)" for x in args)
        lines.append(f"(define-fun base_{name}_d ({params}) Bool\n  {z3.simplify(zv.defined).sexpr()})")
        lines.append(f"(define-fun base_{name}_v ({params}) Int\n  {z3.simplify(zv.value).sexpr()})")
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------- operators
class _Translator:
    """AST -> SMT-LIB text producing (definedness, value) pairs."""

    def __init__(self, resolve) -> None:
        self.resolve = resolve
        self.search_indices: dict[str, int] = {}

    def expr(self, node: ast.Expr) -> tuple[str, str]:
        if isinstance(node, ast.Var):
            if node.name in self.search_indices:
                return "true", _int(self.search_indices[node.name])
            return f"{node.name}_d", node.name
        if isinstance(node, ast.Num):
            return "true", _int(node.value)
        if isinstance(node, ast.NaN):
            return "false", "0"
        if isinstance(node, ast.Literal):
            raise NotExpressible("SMT export supports integer expressions only")
        if isinstance(node, ast.Search):
            if node.bound > 32:
                raise NotExpressible("search bound exceeds 32")
            defined, value = "false", "0"
            previous = self.search_indices.get(node.index)
            for index in reversed(range(node.bound + 1)):
                self.search_indices[node.index] = index
                abort, truth = self.condition(node.condition)
                defined = f"(ite {abort} false (ite {truth} true {defined}))"
                value = f"(ite {truth} {_int(index)} {value})"
            if previous is None:
                self.search_indices.pop(node.index, None)
            else:
                self.search_indices[node.index] = previous
            return defined, value
        callee = self.resolve(node)
        if callee.result_type != "int" or any(kind != "int" for kind in callee.parameter_types):
            raise NotExpressible("SMT export supports integer operations only")
        args = [self.expr(arg) for arg in node.args]
        if callee.definition is None:
            name = base_operation_name(callee.symbol, callee.n_ary, callee.unary_position)
            if name == "defined":
                return "true", f"(base_defined_v {args[0][0]} {args[0][1]})"
            values = " ".join(v for _, v in args)
            defined = _and(*[d for d, _ in args], f"(base_{name}_d {values})")
            return defined, f"(base_{name}_v {values})"
        pairs = " ".join(f"{d} {v}" for d, v in args)
        return f"({smt_name(callee)}_d {pairs})", f"({smt_name(callee)}_v {pairs})"

    def condition(self, node: ast.Condition) -> tuple[str, str]:
        """``(abort, truth)`` exactly as in the z3 encoder (spec 4, rule 2; short circuit)."""
        if isinstance(node, ast.Compare):
            (ld, lv), (rd, rv) = self.expr(node.left), self.expr(node.right)
            return f"(not {_and(ld, rd)})", f"({_COMPARE[node.op]} {lv} {rv})"
        if isinstance(node, ast.Truth):
            raise NotExpressible("SMT export supports integer conditions only")
        if isinstance(node, ast.Not):
            abort, truth = self.condition(node.operand)
            return abort, f"(not {truth})"
        (la, lt), (ra, rt) = self.condition(node.left), self.condition(node.right)
        if isinstance(node, ast.And):
            return f"(or {la} (and (not {la}) {lt} {ra}))", f"(and {lt} {rt})"
        return f"(or {la} (and (not {la}) (not {lt}) {ra}))", f"(or {lt} {rt})"

    def definition(self, definition: ast.Definition) -> tuple[str, str]:
        cases = []
        defined, value = "false", "0"  # no branch matched
        for branch in definition.branches:
            if branch.condition is None:
                defined, value = self.expr(branch.expr)
                break
            cases.append((*self.condition(branch.condition), *self.expr(branch.expr)))
        for abort, truth, body_d, body_v in reversed(cases):
            defined = f"(ite {abort} false (ite {truth} {body_d} {defined}))"
            value = f"(ite {truth} {body_v} {value})"
        return defined, value


def own_text(operator: Operator, definition: ast.Definition, resolve) -> str:
    """The operator's own SMT-LIB functions (calls to other operators by name)."""
    if operator.result_type != "int" or any(kind != "int" for kind in operator.parameter_types):
        raise NotExpressible("SMT export supports integer operations only")
    defined, value = _Translator(resolve).definition(definition)
    params = " ".join(f"({p}_d Bool) ({p} Int)" for p in definition.parameters)
    name = smt_name(operator)
    header = "".join(f"; {line}\n" for line in
                     (f"{operator.symbol}: {operator.definition}").splitlines())
    # define-funs-rec for every operator, recursive or not: z3 expands define-fun as a macro,
    # which inlines whole dependency chains and grows exponentially with the layer.
    return (header + f"(define-funs-rec (({name}_d ({params}) Bool) ({name}_v ({params}) Int))\n"
            f"  ({defined}\n   {value}))\n")


def module(operator: Operator, encoder: Z3Encoder, base: str | None = None) -> str:
    """Self-contained script: prelude, every dependency in topological order, the operator."""
    current_base = prelude(encoder)
    if base is not None and base != current_base:
        raise ValueError("stale prelude for current operator definitions")
    oracle = encoder.oracle
    order: list[Operator] = []
    seen: set[str] = set()

    def visit(op: Operator) -> None:
        if op.func_id in seen or op.definition is None:
            return
        seen.add(op.func_id)
        for node in _applications(oracle._definition_of(op)):
            callee = oracle._resolve(node)
            if callee.func_id != op.func_id:
                visit(callee)
        order.append(op)

    visit(operator)
    parts = [current_base]
    parts += [own_text(op, oracle._definition_of(op), oracle._resolve) for op in order]
    return "\n".join(parts)


def _applications(definition: ast.Definition):
    def walk(node):
        if isinstance(node, ast.Apply):
            yield node
            for arg in node.args:
                yield from walk(arg)
        elif isinstance(node, ast.Search):
            yield from walk(node.condition)
        elif isinstance(node, ast.Compare):
            yield from walk(node.left)
            yield from walk(node.right)
        elif isinstance(node, ast.Not):
            yield from walk(node.operand)
        elif isinstance(node, (ast.And, ast.Or)):
            yield from walk(node.left)
            yield from walk(node.right)

    for branch in definition.branches:
        if branch.condition is not None:
            yield from walk(branch.condition)
        yield from walk(branch.expr)


# ------------------------------------------------------------------ checks
def _call(operator: Operator, args: tuple) -> tuple[str, str]:
    """SMT terms for ``operator(*args)`` with NaN operands: (definedness, value)."""
    if operator.definition is None:  # strict base operation
        base = base_operation_name(operator.symbol, operator.n_ary, operator.unary_position)
        if base == "defined":
            return "true", (f"(base_defined_v {'false' if args[0] is NAN else 'true'} "
                            f"{'0' if args[0] is NAN else _int(args[0])})")
        values = " ".join("0" if a is NAN else _int(a) for a in args)
        defined = _and(*["false" if a is NAN else "true" for a in args], f"(base_{base}_d {values})")
        return defined, f"(base_{base}_v {values})"
    pairs = " ".join("false 0" if a is NAN else f"true {_int(a)}" for a in args)
    name = smt_name(operator)
    return f"({name}_d {pairs})", f"({name}_v {pairs})"


def evaluate_module(text: str, operator: Operator, points: list[tuple]) -> list:
    """Evaluate a module on concrete inputs (NAN allowed): one int or NAN per point.

    z3 parses the module (so the text is valid SMT-LIB for it); the values come
    from :class:`SmtEvaluator`, an independent evaluator of the SMT-LIB integer
    theory with lazy ``ite`` (z3's simplifier expands both arms of an ``ite``,
    which does not terminate quickly on recursive definitions).
    """
    z3.parse_smt2_string(text, ctx=z3.Context())  # syntax and sort check
    evaluator = SmtEvaluator(text)
    results = []
    for args in points:
        defined, value = (evaluator.evaluate(term) for term in _call(operator, args))
        results.append(value if defined else NAN)
    return results


class SmtEvaluator:
    """Evaluates ground terms over ``define-fun`` / ``define-funs-rec`` (Ints and Bools only).

    Integer ``div``/``mod`` follow SMT-LIB (Euclidean: ``0 <= mod < |divisor|``);
    a zero divisor is an error because the exported text never divides by zero.
    """

    def __init__(self, text: str) -> None:
        self.functions: dict[str, tuple[list[str], object]] = {}
        self.memo: dict = {}
        for command in _parse_sexprs(text):
            head = command[0]
            if head == "define-fun":
                _, name, params, _sort, body = command
                self.functions[name] = ([p[0] for p in params], body)
            elif head == "define-funs-rec":
                _, decls, bodies = command
                for (name, params, _sort), body in zip(decls, bodies):
                    self.functions[name] = ([p[0] for p in params], body)
            else:
                raise ValueError(f"unexpected SMT command {head!r}")

    def evaluate(self, term: str):
        (expr,) = _parse_sexprs(term)
        return self._eval(expr, {})

    def _eval(self, e, env: dict):
        if isinstance(e, str):
            if e in env:
                return env[e]
            if e == "true":
                return True
            if e == "false":
                return False
            return int(e)
        head, *args = e
        if head == "ite":
            return self._eval(args[1] if self._eval(args[0], env) else args[2], env)
        if head == "and":
            return all(self._eval(a, env) for a in args)
        if head == "or":
            return any(self._eval(a, env) for a in args)
        if head == "let":
            bindings, body = args
            inner = dict(env)
            inner.update({name: self._eval(value, env) for name, value in bindings})
            return self._eval(body, inner)
        values = [self._eval(a, env) for a in args]
        if head in self.functions:
            key = (head, tuple(values))
            if key not in self.memo:
                params, body = self.functions[head]
                self.memo[key] = self._eval(body, dict(zip(params, values)))
            return self.memo[key]
        return _builtin(head, values)


def _builtin(head: str, v: list):
    if head == "not":
        return not v[0]
    if head == "=>":
        return (not v[0]) or v[1]
    if head == "=":
        return all(x == v[0] for x in v[1:])
    if head == "distinct":
        return len(set(v)) == len(v)
    if head in ("<", "<=", ">", ">="):
        compare = {"<": lambda x, y: x < y, "<=": lambda x, y: x <= y,
                   ">": lambda x, y: x > y, ">=": lambda x, y: x >= y}[head]
        return all(compare(x, y) for x, y in itertools.pairwise(v))
    if head == "+":
        return sum(v)
    if head == "-":
        return -v[0] if len(v) == 1 else v[0] - sum(v[1:])
    if head == "*":
        product = 1
        for x in v:
            product *= x
        return product
    if head in ("div", "mod"):
        a, b = v
        if b == 0:
            raise ZeroDivisionError("SMT-LIB division by zero in an exported term")
        r = a % abs(b)  # Python: 0 <= r < |b|
        return r if head == "mod" else (a - r) // b
    if head == "abs":
        return abs(v[0])
    raise ValueError(f"unsupported SMT-LIB function {head!r}")


def _parse_sexprs(text: str) -> list:
    tokens = []
    for line in text.splitlines():
        line = line.split(";", 1)[0]
        tokens += line.replace("(", " ( ").replace(")", " ) ").split()
    stack: list[list] = [[]]
    for token in tokens:
        if token == "(":
            stack.append([])
        elif token == ")":
            done = stack.pop()
            stack[-1].append(done)
        else:
            stack[-1].append(token)
    if len(stack) != 1:
        raise ValueError("unbalanced SMT-LIB text")
    return stack[0]


def check_module(text: str, operator: Operator, encoder: Z3Encoder) -> None:
    bound = encoder.bound
    edges = () if bound is None else (bound, -bound, bound - 1)
    values = [v for v in (*CHECK_VALUES, *edges) if bound is None or abs(v) <= bound] + [NAN]
    if operator.n_ary > 2:  # retain the domain edges when reducing the product grid
        required = list(dict.fromkeys((*edges[:2], NAN)))
        size = max(len(required), round(400 ** (1 / operator.n_ary)))
        values = list(dict.fromkeys(values[: max(0, size - len(required))] + required))
    points = list(itertools.product(values, repeat=operator.n_ary))
    for args, got in zip(points, evaluate_module(text, operator, points)):
        expected = encoder.oracle.evaluate(operator, args).value
        if not (got is expected or (got is not NAN and expected is not NAN and got == expected)):
            raise AssertionError(f"SMT export of {operator.symbol!r} gives {got} at {args}, "
                                 f"the reference gives {expected}")


def export(operator: Operator, encoder: Z3Encoder, base: str | None = None) -> str | None:
    """The operator's own SMT-LIB functions after checking the assembled module; None for markers."""
    if not is_operation(operator):
        return None
    if operator.result_type != "int" or any(kind != "int" for kind in operator.parameter_types):
        return None
    base = base or prelude(encoder)
    text = module(operator, encoder, base)
    used = set(re.findall(r"\(base_(\w+?)_[dv] ", text))
    if any(f"(define-fun base_{name}_d " not in base for name in used):
        return None  # uses a base operation the prelude cannot express (digit operations without a bound)
    check_module(text, operator, encoder)
    if operator.definition is None:
        return None  # base operations live in the prelude
    return own_text(operator, encoder.oracle._definition_of(operator), encoder.oracle._resolve)


def _and(*terms: str) -> str:
    terms = tuple(t for t in terms if t != "true")
    if not terms:
        return "true"
    return terms[0] if len(terms) == 1 else f"(and {' '.join(terms)})"


def _int(n: int) -> str:
    return str(n) if n >= 0 else f"(- {-n})"
