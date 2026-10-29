"""Read, check and grade a definition written by an agent.

A submitted definition must

1. parse under the operator set's notation;
2. define the requested operator (same symbol, arity and position) with the
   standard parameter names;
3. apply only operators the agent was allowed to use, plus itself;
4. call itself, if at all, in one of the recursion forms of
   docs/reference/semantics.md section 4.1, which guarantee termination.

:class:`EquivalenceGrader` then compares the definition with a reference
operator on every input in ``[-B, B]`` (``B`` the semantics bound): z3 proves
or refutes equivalence, and when z3 cannot decide in time every input of a
stated smaller domain is evaluated by the reference interpreter.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

from opulse.config import Settings
from opulse.core.operator import BRANCH, RECURSIVE, SIMPLE, Operator
from opulse.core.registry import OperatorRegistry
from opulse.core.semantics import NAN, base_operation_name
from opulse.definition import ast
from opulse.definition.parser import DefinitionParser, DefinitionSyntaxError
from opulse.expression.nodes import Call, Variable
from opulse.verify import Oracle

# Symbol of the internal copy of a submitted definition: it never clashes with a real operator
# because operator symbols cannot contain spaces.
CANDIDATE_SYMBOL = "⟨submitted operator⟩"


class SubmissionError(ValueError):
    """The submission is not a usable definition; the message says why."""


@dataclass(frozen=True)
class Shape:
    symbol: str
    n_ary: int
    unary_position: str | None

    @classmethod
    def of(cls, operator: Operator) -> Shape:
        return cls(operator.symbol, operator.n_ary, operator.unary_position)

    def matches(self, node: ast.Apply) -> bool:
        return (node.symbol, node.n_ary, node.unary_position) == (self.symbol, self.n_ary, self.unary_position)

    def describe(self) -> str:
        if self.n_ary == 1:
            return f"unary {self.unary_position}"
        return "binary" if self.n_ary == 2 else f"{self.n_ary} arguments"


def parse_submission(text: str, parser: DefinitionParser, shape: Shape, parameters: tuple[str, ...]) -> ast.Definition:
    """The parsed definition, or :class:`SubmissionError`."""
    text = (text or "").strip()
    if not text:
        raise SubmissionError("the submission is empty")
    try:
        definition = parser.parse(text)
    except (DefinitionSyntaxError, ValueError) as exc:
        raise SubmissionError(f"parse error: {exc}") from None
    if not shape.matches(definition.lhs):
        raise SubmissionError(f"the left-hand side must define {shape.symbol!r} ({shape.describe()})")
    if definition.parameters != parameters:
        raise SubmissionError(f"the parameters must be named {', '.join(parameters)}")
    return definition


def applications(definition: ast.Definition):
    """Every operator application in the bodies and conditions."""
    for branch in definition.branches:
        yield from ast.iter_applications(branch.expr)
        if branch.condition is not None:
            yield from ast.iter_applications(branch.condition)


def check_callees(definition: ast.Definition, shape: Shape, resolve, allowed: set[str]) -> None:
    """Every application is the operator itself or resolves to an operator in ``allowed``."""
    for node in applications(definition):
        if shape.matches(node):
            continue
        try:
            operator = resolve(node)
        except Exception:  # noqa: BLE001 - any lookup failure means the operator is unknown
            operator = None
        if operator is None or operator.func_id not in allowed:
            where = "binary" if node.n_ary == 2 else node.unary_position
            raise SubmissionError(f"operator {node.symbol!r} ({where}) is not available here")


def definition_kind(definition: ast.Definition, shape: Shape) -> str:
    if any(shape.matches(node) for node in applications(definition)):
        return RECURSIVE
    if len(definition.branches) == 1 and definition.branches[0].condition is None:
        return SIMPLE
    return BRANCH


def check_recursion(definition: ast.Definition, shape: Shape, resolve, *, primitive: bool = False) -> None:
    """A self-calling definition must follow template A, B or C (spec section 4.1).

    Template A: ``{ base, if v % m == 0; ..f(..(v % m) - 1..).., if v % m > 0;
    ..f(..(v % m) + 1..).., if v % m < 0 }`` with a literal ``m >= 2``.
    Template B: ``{ base, if v == 0; ..f(..v - 1..).., if v > 0 and v <= T;
    ..f(..v + 1..).., if v < 0 and v >= - T }`` with a literal ``T >= 1``.
    Template C: B (or A) with ``x ⁻`` and ``x ⁺`` in place of ``x - 1`` and ``x + 1``.

    The other argument slots of a recursive call may hold any expression without
    a recursive call. These forms make every recursive call strictly closer to
    the base case, so evaluation always terminates.
    """
    def base_named(node, name: str) -> bool:
        if not isinstance(node, ast.Apply):
            return False
        try:
            operator = resolve(node)
        except Exception:  # noqa: BLE001
            return False
        return operator.definition is None and \
            base_operation_name(operator.symbol, operator.n_ary, operator.unary_position) == name

    def literal(node) -> int | None:
        if isinstance(node, ast.Num):
            return node.value
        if base_named(node, "neg") and isinstance(node.args[0], ast.Num):
            return -node.args[0].value
        return None

    def compare(node, left, op: str, value: int) -> bool:
        return isinstance(node, ast.Compare) and node.left == left and node.op == op and literal(node.right) == value

    def self_calls(node) -> list[ast.Apply]:
        return [n for n in ast.iter_applications(node) if shape.matches(n)]

    fail = SubmissionError(
        "a definition that calls itself must follow one of the recursion forms (A, B or C) exactly")
    branches = definition.branches
    if len(branches) != 3 or any(b.condition is None for b in branches):
        raise fail
    first = branches[0].condition
    if not isinstance(first, ast.Compare) or first.op != "==" or literal(first.right) != 0:
        raise fail
    control = first.left
    if isinstance(control, ast.Var):  # template B or C
        variable = control.name
        down, up = branches[1].condition, branches[2].condition
        if not (isinstance(down, ast.And) and isinstance(up, ast.And)):
            raise fail
        size = literal(down.right.right) if isinstance(down.right, ast.Compare) else None
        if size is None or size < 1 or not (compare(down.left, control, ">", 0)
                                            and compare(down.right, control, "<=", size)
                                            and compare(up.left, control, "<", 0)
                                            and compare(up.right, control, ">=", -size)):
            raise fail
    elif base_named(control, "mod") and isinstance(control.args[0], ast.Var) \
            and isinstance(control.args[1], ast.Num) and control.args[1].value >= 2:  # template A
        variable = control.args[0].name
        if not (compare(branches[1].condition, control, ">", 0) and compare(branches[2].condition, control, "<", 0)):
            raise fail
    else:
        raise fail
    position = definition.parameters.index(variable)
    if any(self_calls(b.condition) for b in branches) or self_calls(branches[0].expr):
        raise fail

    def stepped(node, direction: str) -> bool:
        if isinstance(node, ast.Apply) and node.n_ary == 1 and node.args[0] == control:
            return base_named(node, "pred" if direction == "down" else "succ")
        return (isinstance(node, ast.Apply) and node.n_ary == 2 and node.args[0] == control
                and literal(node.args[1]) == 1 and base_named(node, "sub" if direction == "down" else "add"))

    for branch, direction in ((branches[1], "down"), (branches[2], "up")):
        calls = self_calls(branch.expr)
        if not calls:
            raise fail
        for call in calls:
            for index, arg in enumerate(call.args):
                if index == position and not stepped(arg, direction):
                    raise fail
                if index != position and self_calls(arg):
                    raise fail
    if primitive:
        primitive_fail = SubmissionError(
            "form D needs the last parameter as counter, an independent base, and steps using "
            "both the stepped counter and previous result")
        if position != len(definition.parameters) - 1 or not isinstance(control, ast.Var):
            raise primitive_fail

        def contains(node, sought) -> bool:
            if node == sought:
                return True
            if isinstance(node, ast.Apply):
                return any(contains(arg, sought) for arg in node.args)
            return False

        if contains(branches[0].expr, control):
            raise primitive_fail
        other_args = tuple(ast.Var(name) for name in definition.parameters[:-1])
        for branch, direction in ((branches[1], "down"), (branches[2], "up")):
            calls = self_calls(branch.expr)
            if len(calls) != 1 or calls[0].args[:-1] != other_args:
                raise primitive_fail
            stepped_counter = calls[0].args[-1]
            if not stepped(stepped_counter, direction):
                raise primitive_fail

            def used_outside_call(node, stepped_counter=stepped_counter) -> bool:
                if isinstance(node, ast.Apply) and shape.matches(node):
                    return False
                if node == stepped_counter:
                    return True
                return any(used_outside_call(arg) for arg in node.args) if isinstance(node, ast.Apply) else False

            if not used_outside_call(branch.expr):
                raise primitive_fail


def rename(definition: ast.Definition, shape: Shape, symbol: str) -> ast.Definition:
    """``definition`` with every application of ``shape`` (its own symbol) renamed to ``symbol``."""
    def expr(node):
        if isinstance(node, ast.Apply):
            args = tuple(expr(arg) for arg in node.args)
            name = symbol if shape.matches(node) else node.symbol
            return ast.Apply(name, args, node.unary_position)
        return node

    def condition(node):
        if node is None:
            return None
        if isinstance(node, ast.Compare):
            return ast.Compare(expr(node.left), node.op, expr(node.right))
        if isinstance(node, ast.Not):
            return ast.Not(condition(node.operand))
        return type(node)(condition(node.left), condition(node.right))

    branches = tuple(ast.Branch(expr(b.expr), condition(b.condition), b.is_else) for b in definition.branches)
    return ast.Definition(expr(definition.lhs), branches)


# ------------------------------------------------------------------- grading
@dataclass
class Verdict:
    status: str  # "identical" | "proved" | "exhaustive" | "refuted"
    domain: str  # the domain the verdict covers, in words
    counterexample: dict | None = None
    expected: object = None  # reference value at the counterexample (int or None for NaN)
    got: object = None  # the submission's value there

    @property
    def equivalent(self) -> bool:
        return self.status in ("identical", "proved", "exhaustive")

    def to_dict(self) -> dict:
        data = {"status": self.status, "equivalent": self.equivalent, "domain": self.domain}
        if self.counterexample is not None:
            data.update(counterexample=self.counterexample, expected=self.expected, got=self.got)
        return data


def _json(value):
    return None if value is NAN else value


class EquivalenceGrader:
    """Decides whether a definition agrees with a reference operator on the bounded domain.

    The steps, each deterministic so that a transcript replays exactly:

    1. the same syntax tree as the reference (after renaming) is ``identical``;
    2. a concrete search over small and boundary inputs looks for a counterexample;
    3. z3 decides the question on ``[-B, B]`` under a resource limit ``rlimit`` (a count of
       solver steps, not a time), with ``timeout_ms`` only as a safety net;
    4. if z3 cannot decide, every input in ``[-r, r]`` (``exhaustive_range``) is evaluated.
    """

    def __init__(self, registry: OperatorRegistry, settings: Settings | None = None, rlimit: int = 5_000_000,
                 timeout_ms: int = 10_000, exhaustive_range: dict[int, int] | None = None,
                 max_nodes: int = 20_000) -> None:
        from opulse.solver.equivalence import EquivalenceChecker
        from opulse.solver.z3_encode import NotExpressible, Z3Encoder

        self.settings = settings or Settings()
        self.semantics = self.settings.semantics.build()
        self.oracle = Oracle(registry, self.settings.symbols, self.semantics)
        self.rlimit, self.timeout_ms, self.max_nodes = rlimit, timeout_ms, max_nodes
        try:
            self.encoder = Z3Encoder(self.oracle)
            self.searcher = EquivalenceChecker(self.encoder)
        except NotExpressible:  # legacy mode has no z3 encoding: exhaustive checks only
            self.encoder = self.searcher = None
        self.exhaustive_range = {1: 2000, 2: 50, **(exhaustive_range or {})}
        self._count = 0

    def radius(self, n_ary: int) -> int:
        return self.exhaustive_range.get(n_ary, 2 if n_ary == 3 else 1)

    def domain_text(self, n_ary: int) -> str:
        bound = self.semantics.bound
        full = "all integers" if bound is None else f"every integer in [-{bound}, {bound}]"
        r = self.radius(n_ary)
        return f"{full} (z3); when z3 cannot decide, every integer in [-{r}, {r}] is checked"

    def grade(self, reference: Operator, definition: ast.Definition, kind: str) -> Verdict:
        shape = Shape.of(reference)
        self._count += 1
        candidate = Operator(func_id=f"submitted{self._count}", symbol=CANDIDATE_SYMBOL, n_ary=reference.n_ary,
                             unary_position=reference.unary_position, definition_type=kind)
        renamed = rename(definition, shape, CANDIDATE_SYMBOL)
        candidate.definition = ast.render_definition(renamed, self.settings.symbols)
        self.oracle.include(candidate)
        self.oracle._parsed[candidate.func_id] = renamed  # never re-parsed: the symbol is internal
        try:
            return self._grade(reference, candidate)
        finally:
            self.oracle.forget(candidate)

    def _grade(self, reference: Operator, candidate: Operator) -> Verdict:
        names = self.settings.symbols.operands(reference.n_ary)
        operands = tuple(Variable(name) for name in names)
        left, right = Call(reference, operands), Call(candidate, operands)
        bound = self.semantics.bound
        full = "all integers" if bound is None else f"[-{bound}, {bound}]"
        if rename(self.oracle._definition_of(reference), Shape.of(reference), CANDIDATE_SYMBOL) == \
                self.oracle._definition_of(candidate):
            return Verdict("identical", full)  # the same syntax tree: equal everywhere
        if self.searcher is not None:
            found = self.searcher._search(left, right, names)
            if found is not None:
                return Verdict("refuted", full, found.counterexample, _json(found.left_value), _json(found.right_value))
            verdict = self._z3(left, right, names, full)
            if verdict is not None:
                return verdict
        r = self.radius(reference.n_ary)
        for point in itertools.product(range(-r, r + 1), repeat=reference.n_ary):
            env = dict(zip(names, point))
            diff = self.searcher._differ(left, right, env) if self.searcher else self._differ(left, right, env)
            if diff is not None:
                return Verdict("refuted", f"[-{r}, {r}]", env, _json(diff[0]), _json(diff[1]))
        return Verdict("exhaustive", f"[-{r}, {r}]")

    def _differ(self, left: Call, right: Call, env: dict) -> tuple | None:
        point = tuple(env.values())
        lv = self.oracle.evaluate(left.operator, point).value
        rv = self.oracle.evaluate(right.operator, point).value
        same = lv is rv or (lv is not NAN and rv is not NAN and lv == rv)
        return None if same else (lv, rv)

    def _z3(self, left: Call, right: Call, names: tuple[str, ...], full: str) -> Verdict | None:
        import z3

        from opulse.solver.equivalence import encode_node
        from opulse.solver.isolated import check
        from opulse.solver.z3_encode import NotExpressible, ZVal

        enc = self.encoder
        xs = {name: z3.Int(name) for name in names}
        env = {name: ZVal(z3.BoolVal(True), x) for name, x in xs.items()}
        enc.reset()  # no time budget: the encoding is limited by its node count only
        enc.max_nodes, saved = self.max_nodes, enc.max_nodes
        try:
            lz, rz = encode_node(enc, left, env), encode_node(enc, right, env)
        except NotExpressible:
            return None
        finally:
            enc.max_nodes = saved
        differ = z3.Or(lz.defined != rz.defined, z3.And(lz.defined, rz.defined, lz.value != rz.value))
        status, model = check([*[enc.in_bound(x) for x in xs.values()], differ], self.timeout_ms,
                              rlimit=self.rlimit, variables=list(names))
        if status == "unsat":
            return Verdict("proved", full)
        if status == "sat":
            point = {name: model[name] for name in names}
            diff = self.searcher._differ(left, right, point)
            if diff is not None:
                return Verdict("refuted", full, point, _json(diff[0]), _json(diff[1]))
        return None
