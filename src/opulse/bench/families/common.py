"""Shared machinery of the solver graded task families.

* prompt assembly with the same header, rules and definitions layout as the value families;
* operator tables rebuilt from definition texts (as a prompt shows them), with each definition's
  kind read from its text so the z3 encoding treats recursion correctly;
* the verdict on whether two expressions agree on the whole value domain: ``proved`` (z3, or every
  point of a small bounded domain), ``refuted`` (a counterexample checked again by the reference
  interpreter) or ``undecided``. Only ``proved`` and ``refuted`` verdicts are ever used as answers;
* edits of definition syntax trees (inlining, commuting, mutations) used to make task pairs.
"""

from __future__ import annotations

import itertools
import random
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace

from opulse.bench.check import PromptOperators, prompt_registry
from opulse.bench.context import rules_text
from opulse.config import Symbols
from opulse.core.operator import (
    BINARY,
    BRANCH,
    POSTFIX,
    PREFIX,
    RECURSIVE,
    SIMPLE,
    Operator,
)
from opulse.core.primitives import atom_names, rule_for
from opulse.core.registry import OperatorRegistry
from opulse.core.semantics import (
    BASE_OPERATIONS,
    EXACT,
    NAN,
    Semantics,
    base_operation_name,
)
from opulse.definition import ast
from opulse.definition.parser import DefinitionParser
from opulse.expression.nodes import Call, Node, Variable, from_ast

INTRO = ("You are given operators defined from a few base operations. Use the rules and the "
         "definitions exactly as written; do not assume any familiar meaning of the symbols.")
VARIABLES = Symbols().parameter_names
# A bounded domain this small is checked point by point instead of by z3.
EXHAUSTIVE_LIMIT = 200_000
BOUND_LINE = re.compile(r"^Any base operation whose result is larger than (\d+) in absolute value gives ")
MODULUS_LINE = re.compile(r"^Each integer base operation result is reduced modulo (\d+) into 0 through \d+\.$")
STRING_LIMIT_LINE = re.compile(r"^A string longer than (\d+) characters gives NaN\.$")
LIST_LIMIT_LINE = re.compile(r"^A list longer than (\d+) elements gives NaN\.$")
MARKER_LINE = re.compile(r"^  - (\S+)<digits> is a numeral written in base (\d+)\.$")


def same(x, y) -> bool:
    return (x is NAN and y is NAN) or (x is not NAN and y is not NAN and x == y)


def json_value(value):
    return None if value is NAN else value


def show_value(value, nan: str = "NaN") -> str:
    return nan if value is NAN or value is None else str(value)


# ------------------------------------------------------------------ operator tables
def definition_kind(definition: ast.Definition) -> str:
    key = (definition.lhs.symbol, definition.lhs.n_ary, definition.lhs.unary_position)
    for branch in definition.branches:
        nodes = [branch.expr] + ([branch.condition] if branch.condition is not None else [])
        for node in nodes:
            if any((a.symbol, a.n_ary, a.unary_position) == key for a in ast.iter_applications(node)):
                return RECURSIVE
    if len(definition.branches) > 1 or definition.branches[0].condition is not None:
        return BRANCH
    return SIMPLE


def text_registry(definitions: list[str], base: OperatorRegistry, symbols: Symbols,
                  semantics: Semantics, signatures=None) -> PromptOperators:
    """Base operations plus the given definition texts (see ``opulse.bench.check.prompt_registry``),
    each operator typed as simple, branch or recursive by its own text."""
    ops = prompt_registry(definitions, base, symbols, semantics, signatures=signatures)
    for op in ops.registry:
        if op.definition is not None:
            op.definition_type = definition_kind(ops.parser.parse(op.definition))
    return ops


def expression(ops: PromptOperators, text: str) -> Node:
    """An expression over the variables a, b, c, resolved against ``ops``."""
    parser = DefinitionParser(ops.parser.symbols, ops.registry, variables=ops.parser.symbols.parameter_names)
    return from_ast(parser.parse_expr(text, expression_mode=True), ops.registry)


def base_from_prompt(prompt: str) -> tuple[OperatorRegistry, Semantics]:
    """The base operations, numeral markers and bound a prompt states in its rules.

    Grading needs nothing but the prompt: every base operation the model may use is listed
    there in the library's own wording, and the bound is stated in one line.
    """
    lines = prompt.splitlines()
    shown = set(lines)
    by_name = {name: key for key, name in BASE_OPERATIONS.items()}
    ops = []
    for name in atom_names():
        if f"  - {rule_for(name)}" in shown and name in by_name:
            symbol, n_ary, position = by_name[name]
            from opulse.core.primitives import CUSTOM

            primitive = CUSTOM.get(name)
            ops.append(Operator(func_id=f"base-{name}", symbol=symbol, n_ary=n_ary, unary_position=position,
                                priority=1 if n_ary == BINARY else 4,
                                associativity_direction="left" if n_ary == BINARY else "right",
                                parameter_types=primitive.parameter_types if primitive else ("int",) * n_ary,
                                result_type=primitive.result_type if primitive else "int"))
    for line in lines:
        match = MARKER_LINE.match(line)
        if match:
            ops.append(Operator(func_id=f"marker-{match.group(1)}", symbol=match.group(1), n_ary=1,
                                unary_position=PREFIX, is_base=int(match.group(2))))
    bound = next((int(m.group(1)) for m in map(BOUND_LINE.match, lines) if m), None)
    modulus = next((int(m.group(1)) for m in map(MODULUS_LINE.match, lines) if m), None)
    max_string = next((int(m.group(1)) for m in map(STRING_LIMIT_LINE.match, lines) if m), 256)
    max_list = next((int(m.group(1)) for m in map(LIST_LIMIT_LINE.match, lines) if m), 256)
    return OperatorRegistry(ops), (Semantics("modular", None, max_string, max_list, modulus)
                                   if modulus is not None else Semantics(EXACT, bound, max_string, max_list))


def base_operations_in(ops: PromptOperators, texts: list[str], nodes: list[Node] = ()) -> list[str]:
    """Names of the base operations applied in the given definition texts and expressions."""
    used: set[str] = set()

    def note(op: Operator) -> None:
        if op.definition is None:
            name = base_operation_name(op.symbol, op.n_ary, op.unary_position)
            if name:
                used.add(name)

    for text in texts:
        definition = ops.parser.parse(text)
        for branch in definition.branches:
            for node in [branch.expr] + ([branch.condition] if branch.condition is not None else []):
                for apply in ast.iter_applications(node):
                    note(ops.oracle._resolve(apply))
    for node in nodes:
        stack = [node]
        while stack:
            current = stack.pop()
            if isinstance(current, Call):
                note(current.operator)
                stack.extend(current.args)
    order = atom_names()
    return sorted(used, key=order.index)


def marker_lines(base: OperatorRegistry, texts: list[str]) -> list[str]:
    joined = " ".join(texts)
    return [f"  - {op.symbol}<digits> is a numeral written in base {op.is_base}."
            for op in base if op.is_base is not None and op.symbol in joined]


def assemble(definitions: list[str], question: str, bases: list[str], semantics: Semantics, nan: str,
             markers: list[str] = (), extra: list[str] = ()) -> str:
    parts = [INTRO, "", "Rules:", rules_text(bases, semantics, nan)]
    if definitions:
        parts += ["", "Definitions:", *definitions]
    if markers:
        parts += ["", "Numerals:", *markers]
    if extra:
        parts += ["", *extra]
    parts += ["", question]
    return "\n".join(parts)


def domain_text(names: tuple[str, ...], semantics: Semantics) -> str:
    """'all integers a and b from -B to B' (or without the range when there is no bound)."""
    listed = names[0] if len(names) == 1 else ", ".join(names[:-1]) + f" and {names[-1]}"
    if semantics.bound is None:
        return f"all integers {listed}"
    return f"all integers {listed} from -{semantics.bound} to {semantics.bound}"


def variables_in(*nodes: Node) -> tuple[str, ...]:
    found: list[str] = []

    def walk(node: Node) -> None:
        if isinstance(node, Variable):
            if node.name not in found:
                found.append(node.name)
        elif isinstance(node, Call):
            for arg in node.args:
                walk(arg)

    for node in nodes:
        walk(node)
    return tuple(sorted(found, key=lambda name: VARIABLES.index(name) if name in VARIABLES
                        else len(VARIABLES) + found.index(name)))


# ------------------------------------------------------------------ verdicts
@dataclass
class Verdict:
    status: str  # "proved" | "refuted" | "undecided"
    method: str  # "z3" | "exhaustive" | "counterexample" | "none"
    counterexample: dict | None = None
    left: object = None
    right: object = None


def evaluate(ops: PromptOperators, node: Node, env: dict):
    from opulse.expression.nodes import to_ast

    return ops.oracle.evaluate_expr(to_ast(node), env).value


def decide(ops: PromptOperators, left: Node, right: Node, timeout_ms: int = 30_000,
           rlimit: int = 5_000_000, max_nodes: int = 20_000) -> Verdict:
    """Whether ``left`` and ``right`` agree for every assignment of their variables in the domain."""
    from opulse.solver.equivalence import EquivalenceChecker
    from opulse.solver.z3_encode import NotExpressible, Z3Encoder

    names = variables_in(left, right)
    bound = ops.oracle.semantics.bound
    if bound is not None and (2 * bound + 1) ** len(names) <= EXHAUSTIVE_LIMIT:
        for point in itertools.product(range(-bound, bound + 1), repeat=len(names)):
            env = dict(zip(names, point))
            lv, rv = evaluate(ops, left, env), evaluate(ops, right, env)
            if not same(lv, rv):
                return Verdict("refuted", "exhaustive", env, lv, rv)
        return Verdict("proved", "exhaustive")
    encoder = getattr(ops, "_encoder", None)
    if encoder is None:
        try:
            encoder = Z3Encoder(ops.oracle)
        except NotExpressible:
            return Verdict("undecided", "none")
        ops._encoder = encoder
    result = EquivalenceChecker(encoder, timeout_ms=timeout_ms, rlimit=rlimit,
                                max_nodes=max_nodes).check(left, right)
    if result.status == "proved":
        return Verdict("proved", "z3")
    if result.status == "refuted":
        env = dict(result.counterexample)
        lv, rv = evaluate(ops, left, env), evaluate(ops, right, env)
        if same(lv, rv):  # never trust an unconfirmed counterexample
            return Verdict("undecided", "none")
        return Verdict("refuted", "counterexample", env, lv, rv)
    return Verdict("undecided", "none")


def in_domain(point: dict, semantics: Semantics) -> bool:
    return semantics.bound is None or all(abs(v) <= semantics.bound for v in point.values())


def require_known(ops: PromptOperators, definition: ast.Definition) -> None:
    """Raise ``LookupError`` when the definition applies an operator the table does not hold."""
    own = key_of(definition.lhs)
    for branch in definition.branches:
        for node in [branch.expr] + ([branch.condition] if branch.condition is not None else []):
            for apply in ast.iter_applications(node):
                if key_of(apply) != own and ops.registry.find(*key_of(apply)) is None:
                    raise LookupError(f"no operator {apply.symbol!r} ({apply.unary_position or 'binary'})")


def violates(ops: PromptOperators, left: Node, right: Node, env: dict) -> tuple[bool, object, object]:
    lv, rv = evaluate(ops, left, env), evaluate(ops, right, env)
    return not same(lv, rv), lv, rv


# ------------------------------------------------------------------ syntax trees
def count_operations(definition: ast.Definition) -> int:
    """Operator applications in every branch body and condition (a negative literal counts once)."""
    total = 0
    for branch in definition.branches:
        total += sum(1 for _ in ast.iter_applications(branch.expr))
        if branch.condition is not None:
            total += sum(1 for _ in ast.iter_applications(branch.condition))
    return total


def applies(definition: ast.Definition, key: tuple) -> bool:
    for branch in definition.branches:
        for node in [branch.expr] + ([branch.condition] if branch.condition is not None else []):
            if any((a.symbol, a.n_ary, a.unary_position) == key for a in ast.iter_applications(node)):
                return True
    return False


def key_of(apply: ast.Apply) -> tuple:
    return (apply.symbol, apply.n_ary, apply.unary_position)


def _children(node) -> tuple:
    if isinstance(node, ast.Apply):
        return node.args
    if isinstance(node, (ast.Compare, ast.And, ast.Or)):
        return (node.left, node.right)
    if isinstance(node, ast.Not):
        return (node.operand,)
    return ()


def _rebuild(node, children: tuple):
    if isinstance(node, ast.Apply):
        return replace(node, args=tuple(children))
    if isinstance(node, (ast.Compare, ast.And, ast.Or)):
        return replace(node, left=children[0], right=children[1])
    if isinstance(node, ast.Not):
        return replace(node, operand=children[0])
    return node


def nodes_of(definition: ast.Definition) -> Iterator[tuple[tuple, object]]:
    """(path, node) for every node of every branch body and condition."""
    def walk(node, path):
        yield path, node
        for i, child in enumerate(_children(node)):
            yield from walk(child, path + (i,))

    for index, branch in enumerate(definition.branches):
        yield from walk(branch.expr, (index, "expr"))
        if branch.condition is not None:
            yield from walk(branch.condition, (index, "cond"))


def replace_at(definition: ast.Definition, path: tuple, new) -> ast.Definition:
    index, part, *rest = path

    def put(node, steps):
        if not steps:
            return new
        children = list(_children(node))
        children[steps[0]] = put(children[steps[0]], steps[1:])
        return _rebuild(node, tuple(children))

    branch = definition.branches[index]
    if part == "expr":
        branch = replace(branch, expr=put(branch.expr, rest))
    else:
        branch = replace(branch, condition=put(branch.condition, rest))
    branches = list(definition.branches)
    branches[index] = branch
    return replace(definition, branches=tuple(branches))


def substitute(node, env: dict):
    if isinstance(node, ast.Var):
        return env.get(node.name, node)
    children = _children(node)
    if not children:
        return node
    return _rebuild(node, tuple(substitute(child, env) for child in children))


def rename(definition: ast.Definition, symbol: str) -> ast.Definition:
    """The same definition under another symbol (self-applications follow)."""
    old = key_of(definition.lhs)

    def walk(node):
        children = _children(node)
        node = _rebuild(node, tuple(walk(c) for c in children)) if children else node
        if isinstance(node, ast.Apply) and key_of(node) == old:
            node = replace(node, symbol=symbol)
        return node

    branches = tuple(replace(b, expr=walk(b.expr), condition=walk(b.condition) if b.condition is not None else None)
                     for b in definition.branches)
    return ast.Definition(replace(definition.lhs, symbol=symbol), branches)


def inline(definition: ast.Definition, simple: dict[tuple, ast.Definition], path: tuple | None = None):
    """Replace applications of simple (one-branch, non-recursive) definitions by their bodies.

    With ``path`` only the application at that path is replaced; otherwise every application of
    an operator in ``simple`` is (one level: inlined bodies are not expanded again). Arguments are
    substituted as expressions, which matches the semantics: an argument is a value, NaN included,
    and a simple definition has no condition that could reject it.
    """
    def expand(node):
        callee = simple[key_of(node)]
        return substitute(callee.branches[0].expr, dict(zip(callee.parameters, node.args)))

    if path is not None:
        node = dict(nodes_of(definition))[path]
        return replace_at(definition, path, expand(node))

    def walk(node):
        children = _children(node)
        if children:
            node = _rebuild(node, tuple(walk(c) for c in children))
        if isinstance(node, ast.Apply) and key_of(node) in simple:
            return expand(node)
        return node

    branches = tuple(replace(b, expr=walk(b.expr), condition=walk(b.condition) if b.condition is not None else None)
                     for b in definition.branches)
    return replace(definition, branches=branches)


COMMUTATIVE_BASE = {("+", 2, None), ("*", 2, None)}
ARITHMETIC_BINARY = ("+", "-", "*")
FLIPPED = {"<": "<=", "<=": "<", ">": ">=", ">=": ">", "==": "!=", "!=": "=="}


def _is_base_key(key: tuple) -> bool:
    return key in BASE_OPERATIONS


def rewrites(definition: ast.Definition, simple: dict, rng: random.Random) -> list[tuple[str, Callable]]:
    """Edits meant to keep the meaning (the solver decides whether they do)."""
    found: list[tuple[str, Callable]] = []
    negate = rng.random() < 1 / 3
    for path, node in nodes_of(definition):
        if not isinstance(node, ast.Apply):
            continue
        key = key_of(node)
        if key in COMMUTATIVE_BASE and node.args[0] != node.args[1]:
            found.append(("commute", lambda p=path, n=node: replace_at(definition, p, replace(n, args=n.args[::-1]))))
        if key in simple and key != key_of(definition.lhs):
            found.append(("inline", lambda p=path: inline(definition, simple, p)))
        # double negation is the easiest rewrite to spot; it is offered in a third of the draws
        if negate and path[1] == "expr" and not (key == ("-", 1, PREFIX) and isinstance(node.args[0], ast.Num)):
            found.append(("double_negation", lambda p=path, n=node: replace_at(
                definition, p, ast.Apply("-", (ast.Apply("-", (n,), PREFIX),), PREFIX))))
    branches = definition.branches
    for i in range(len(branches) - 1):
        if branches[i].condition is not None and branches[i + 1].condition is not None:
            def swap(i=i):
                items = list(branches)
                items[i], items[i + 1] = items[i + 1], items[i]
                return replace(definition, branches=tuple(items))
            found.append(("reorder_branches", swap))
    return found


def mutations(definition: ast.Definition, rng: random.Random) -> list[tuple[str, Callable]]:
    """Small edits meant to change the meaning (the solver decides whether they do)."""
    found: list[tuple[str, Callable]] = []
    for path, node in nodes_of(definition):
        if isinstance(node, ast.Num):
            delta = rng.choice((1, 2, 3, -1, -2, -3))
            value = node.value + delta if node.value + delta >= 0 else node.value + abs(delta)
            found.append(("literal", lambda p=path, n=node, v=value: replace_at(definition, p, replace(n, value=v))))
        elif isinstance(node, ast.Apply):
            key = key_of(node)
            if node.n_ary == 2 and node.args[0] != node.args[1] and key not in COMMUTATIVE_BASE:
                found.append(("swap_operands", lambda p=path, n=node: replace_at(
                    definition, p, replace(n, args=n.args[::-1]))))
            if node.n_ary == 2 and _is_base_key(key) and node.symbol in ARITHMETIC_BINARY:
                other = rng.choice([s for s in ARITHMETIC_BINARY if s != node.symbol])
                found.append(("base_operation", lambda p=path, n=node, s=other: replace_at(
                    definition, p, replace(n, symbol=s))))
        elif isinstance(node, ast.Compare):
            found.append(("comparison", lambda p=path, n=node: replace_at(
                definition, p, replace(n, op=FLIPPED[n.op]))))
    branches = definition.branches
    if len(branches) > 1:
        for i, j in itertools.combinations(range(len(branches)), 2):
            if branches[i].expr != branches[j].expr:
                def swap(i=i, j=j):
                    items = list(branches)
                    items[i] = replace(items[i], expr=branches[j].expr)
                    items[j] = replace(items[j], expr=branches[i].expr)
                    return replace(definition, branches=tuple(items))
                found.append(("swap_branch_bodies", swap))
    return found


def pick(options: list[tuple[str, Callable]], rng: random.Random) -> tuple[str, Callable]:
    """An edit: first a kind (each kind equally likely), then a place for it."""
    kind = rng.choice(sorted({name for name, _ in options}))
    return rng.choice([option for option in options if option[0] == kind])


def render(definition: ast.Definition, symbols: Symbols) -> str:
    return ast.render_definition(definition, symbols)


def lhs_text(symbol: str, n_ary: int, position: str | None, symbols: Symbols) -> str:
    if n_ary == 2:
        return f"{symbols.left_operand} {symbol} {symbols.right_operand}"
    if n_ary > 2:
        return symbols.call(symbol, symbols.operands(n_ary))
    return f"{symbol} {symbols.left_operand}" if position == PREFIX else f"{symbols.left_operand} {symbol}"


def similarity(a: str, b: str) -> float:
    from difflib import SequenceMatcher

    return round(SequenceMatcher(None, a, b).ratio(), 2)


def body_of(text: str) -> str:
    return text.split(" = ", 1)[1] if " = " in text else text


def fresh_symbols(builder, rng: random.Random, count: int) -> list[str]:
    """Symbols that no operator of the set uses and that keep the set prefix-free."""
    from opulse.generation.symbols import ShapeIndexFactory, SymbolFactory

    settings = builder.settings.operators
    factory = (ShapeIndexFactory if settings.naming == "shape_index" else SymbolFactory)(settings, rng)
    factory.reserve(op.symbol for op in builder.registry)
    chosen = []
    for _ in range(count):
        symbol = factory.new_symbol()
        factory.reserve(symbol)
        chosen.append(symbol)
    return chosen


def ordered_closure(builder, operators: list[Operator]) -> list[Operator]:
    """Definitions the given operators need, callees first (the operators included)."""
    from opulse.bench.context import closure

    calls = [Call(op, tuple(Variable("a") for _ in range(op.n_ary))) for op in operators]
    needed = {op.func_id for call in calls for op in closure(builder.registry, call)}
    return [op for op in builder.registry.topological_order() if op.func_id in needed]


def unary_or_binary(op: Operator) -> str:
    return "binary" if op.n_ary == 2 else (op.unary_position or POSTFIX)


def check_requirements(builder, family: str) -> None:
    if builder.naming != "symbols" or builder.context != "full" or builder.distractors:
        raise ValueError(f"{family} tasks use symbol names, the full context and no distractors")
