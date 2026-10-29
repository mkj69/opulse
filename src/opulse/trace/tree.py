"""Hierarchical derivations: one derivation that can be read at any granularity.

A :class:`Derivation` is the reduction of one expression in which every defined operator
is computed in one step (an ``eval`` step). Each such step carries a *child*: the derivation
of that application on its own, ``op(inputs)``, which unfolds ``op`` once (an ``expand`` or
``undefined`` step) and computes the applications of the body, each defined one again in one
step with a child of its own. Following children all the way down reaches base operations
only.

The *cut* (which defined operators are known) only decides how much of the tree is shown.
:func:`flatten` replaces every ``eval`` step of an operator that should be unfolded by the
steps of its child, recursively, and gives exactly the :class:`~opulse.trace.Trace` that
:class:`~opulse.trace.Reducer` produces with the same ``expand`` and ``max_depth``
(``tests/test_trace_tree.py`` checks this). The reduction is applicative order,
leftmost-innermost, so the body of an unfolded application is reduced completely before
anything to its right, which is what makes the splice exact.

Every node is a reducer trace of its own and is checked with
:func:`opulse.verify.verify_trace` (:func:`verify_tree`).

JSON (:func:`to_json`, schema ``opulse.derivation/1``)::

    {
      "schema": "opulse.derivation/1",
      "expression": "<text of the expression>",
      "value": <int> | null,            # null: undefined (NaN)
      "root": "<node id>",
      "operators": {"<func_id>": {"symbol", "n_ary", "position", "layer", "kind",
                                  "priority", "associativity", "definition"}},
      "nodes": {"<node id>": {
          "operator": "<func_id>" | null,   # null for the root expression
          "inputs": [<int> | null, ...],     # null: NaN; [] for the root
          "source": <tree>, "text": "<text of source>", "value": <int> | null,
          "steps": [{"kind": "expand" | "eval" | "undefined",
                     "path": [<child index>, ...],   # from the node's source
                     "operator": "<func_id>", "inputs": [...], "depth": <int>,
                     "before": <tree>, "after": <tree>, "expression_after": <tree>,
                     "branch": <int> | null, "condition": "<text>" | null,
                     "reason": "nan_condition" | "no_branch" | null,
                     "child": "<node id>" | null}]}}
    }

``kind`` of an operator is ``base`` (no definition), ``simple``, ``branch`` or ``recursive``.
A ``<tree>`` is ``{"num": <int>}``, ``{"num": null}`` (NaN), ``{"var": "<name>"}`` or
``{"op": "<func_id>", "args": [<tree>, ...]}``. Node ids are ``n0`` (the root), ``n1``, ...
in the order the nodes were built; equal applications share one node. ``depth`` is local to
the node: ``0`` for steps on the node's own source, ``1`` for the body of its unfolding.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from opulse.core.operator import BRANCH, RECURSIVE, SIMPLE, Operator
from opulse.core.semantics import NAN
from opulse.expression.nodes import Call, Node, Number, Variable
from opulse.trace.reducer import Path, Reducer, Trace, TraceStep, _replace_at

SCHEMA = "opulse.derivation/1"


@dataclass
class TreeStep:
    """A step of one node; ``child`` opens an ``eval`` step of a defined operator."""

    step: TraceStep
    child: Derivation | None = None


@dataclass(eq=False)
class Derivation:
    """The coarse reduction of ``source``; ``operator``/``inputs`` are set for a sub-derivation."""

    source: Node
    trace: Trace
    steps: list[TreeStep] = field(default_factory=list)
    operator: Operator | None = None
    inputs: tuple = ()

    @property
    def value(self):
        return self.trace.value

    def nodes(self) -> list[Derivation]:
        """This node and every node below it, each once, in build order of discovery."""
        seen: dict[int, Derivation] = {}
        stack = [self]
        while stack:
            node = stack.pop()
            if id(node) in seen:
                continue
            seen[id(node)] = node
            stack.extend(s.child for s in reversed(node.steps) if s.child is not None)
        return list(seen.values())


@dataclass(frozen=True)
class ViewStep:
    """A step of a flattened derivation and, for an ``eval`` of a defined operator, its node."""

    step: TraceStep
    child: Derivation | None


# ------------------------------------------------------------------ building
class TreeBuilder:
    """Builds derivation trees over ``registry``; equal applications share one node."""

    def __init__(self, registry, runtime, parser, max_nodes: int = 50_000) -> None:
        self.registry = registry
        self.runtime = runtime
        self.parser = parser
        self.max_nodes = max_nodes
        self._top = Reducer(registry, runtime, parser, max_depth=0)
        self._one = Reducer(registry, runtime, parser, max_depth=1)
        self._memo: dict[tuple, Derivation] = {}

    def build(self, expression: Node) -> Derivation:
        """The tree of ``expression`` (a closed expression), opened down to base operations."""
        root = self._node(expression, self._top.reduce(expression), None, ())
        self._open(root)
        return root

    def application(self, operator: Operator, inputs: Iterable) -> Derivation:
        """The tree of one application ``operator(inputs)``, unfolded once at the top."""
        node = self._application(operator, tuple(inputs))
        self._open(node)
        return node

    # ------------------------------------------------------------------
    def _application(self, operator: Operator, inputs: tuple) -> Derivation:
        key = (operator.func_id, tuple(_key(v) for v in inputs))
        node = self._memo.get(key)
        if node is None:
            if len(self._memo) >= self.max_nodes:
                raise RecursionError(f"derivation tree larger than {self.max_nodes} nodes")
            source = Call(operator, tuple(Number(v) for v in inputs))
            node = self._memo[key] = self._node(source, self._one.reduce(source), operator, inputs)
        return node

    def _node(self, source: Node, trace: Trace, operator, inputs) -> Derivation:
        if trace.truncated:
            raise ValueError("a single unfolding exceeded the reducer's step limit")
        return Derivation(source, trace, [TreeStep(s) for s in trace.steps], operator, inputs)

    def _open(self, root: Derivation) -> None:
        # Iterative, so deep recursion in the operators does not hit Python's stack limit.
        stack, done = [root], set()
        while stack:
            node = stack.pop()
            if id(node) in done:
                continue
            done.add(id(node))
            for item in node.steps:
                step = item.step
                if (step.kind == "eval" and step.operator.definition is not None
                        and step.branch_index is None and item.child is None):
                    item.child = self._application(step.operator, step.inputs)
                    stack.append(item.child)


def build_tree(expression: Node, registry, runtime, parser, max_nodes: int = 50_000) -> Derivation:
    """Shortcut for ``TreeBuilder(registry, runtime, parser).build(expression)``."""
    return TreeBuilder(registry, runtime, parser, max_nodes).build(expression)


# ------------------------------------------------------------------ cuts
def cut(known: Iterable[str] = (), known_layers: int = 0) -> Callable[[Operator], bool]:
    """The ``expand`` predicate of a cut, as in ``opulse expressions --cot-known(-layers)``.

    A defined operator is unfolded unless its layer is below ``known_layers`` or its symbol
    or func_id is in ``known``.
    """
    names = set(known)

    def expand(op: Operator) -> bool:
        return (op.definition is not None and (op.recursive_layer or 0) >= known_layers
                and op.symbol not in names and op.func_id not in names)

    return expand


def _unfold_all(op: Operator) -> bool:
    return op.definition is not None


# ------------------------------------------------------------------ flattening
def flatten_view(root: Derivation, expand: Callable[[Operator], bool] | None = None,
                 max_depth: int | None = None) -> list[ViewStep]:
    """The steps of ``root`` at a cut, with the node behind every remaining defined ``eval``."""
    expand = expand or _unfold_all
    local: list[tuple[Path, int, TreeStep]] = []

    def collect(node: Derivation, prefix: Path, base: int) -> None:
        for item in node.steps:
            step = item.step
            path, depth = prefix + step.path, base + step.depth
            opened = (step.kind == "eval" and step.operator.definition is not None
                      and step.branch_index is None and expand(step.operator)
                      and (max_depth is None or depth < max_depth))
            if opened:
                if item.child is None:
                    raise ValueError(f"the node of {step.operator.symbol} was not built")
                collect(item.child, path, depth)
            else:
                local.append((path, depth, item))

    collect(root, (), 0)
    view, current = [], root.source
    for index, (path, depth, item) in enumerate(local):
        s = item.step
        after = _replace_at(current, path, s.after)
        view.append(ViewStep(TraceStep(index, s.kind, path, s.operator, s.inputs, s.before, s.after, current,
                                       after, s.branch_index, s.condition, s.reason, depth,
                                       s.search_attempts), item.child))
        current = after
    return view


def align(root: Derivation, expands: list[Callable[[Operator], bool]]) -> tuple[list[list[ViewStep]],
                                                                                list[tuple[int, ...]]]:
    """The derivation at several cuts, ordered from coarse to fine, and how their steps line up.

    Returns ``(views, owners)``: ``views[k]`` is :func:`flatten_view` at ``expands[k]``, and
    ``owners[j][k]`` is the index of the step at cut ``k`` that the ``j``-th step at the finest
    cut belongs to (so ``owners[j][-1] == j``). One step at a coarser cut stands for a
    contiguous block of finer steps. Every cut must unfold at least what the cut before it
    unfolds; otherwise a ``ValueError`` is raised.
    """
    expands = list(expands)
    if not expands:
        raise ValueError("align needs at least one cut")
    levels = len(expands)
    views = [flatten_view(root, expand) for expand in expands]
    counters = [0] * levels
    owners: list[tuple[int, ...]] = []
    stack: list[tuple[Derivation, int, tuple]] = [(root, 0, (None,) * levels)]
    # Depth-first in step order, like flatten_view, with an explicit stack.
    while stack:
        node, start, owner = stack.pop()
        for position in range(start, len(node.steps)):
            item = node.steps[position]
            step = item.step
            defined = step.kind == "eval" and step.operator.definition is not None
            opened = [defined and expand(step.operator) for expand in expands]
            if any(opened[k] and not opened[k + 1] for k in range(levels - 1)):
                raise ValueError(f"the cuts are not ordered from coarse to fine at {step.operator.symbol}")
            here = list(owner)
            for k in range(levels):
                if here[k] is None and not opened[k]:
                    here[k] = counters[k]
                    counters[k] += 1
            if opened[-1]:
                if item.child is None:
                    raise ValueError(f"the node of {step.operator.symbol} was not built")
                stack.append((node, position + 1, owner))
                stack.append((item.child, 0, tuple(here)))
                break
            owners.append(tuple(here))
    if counters != [len(view) for view in views]:
        raise ValueError(f"step counts {counters} do not match the flattened cuts")
    return views, owners


def flatten(root: Derivation, expand: Callable[[Operator], bool] | None = None,
            max_depth: int | None = None, max_steps: int | None = None) -> Trace:
    """The reducer trace of ``root.source`` at a cut: equal to
    ``Reducer(..., expand=expand, max_depth=max_depth, max_steps=max_steps).reduce(root.source)``."""
    steps = [v.step for v in flatten_view(root, expand, max_depth)]
    trace = Trace(root.source, steps)
    if max_steps is not None and len(steps) > max_steps:
        trace.steps, trace.truncated = steps[:max_steps], True
    return trace


def verify_tree(root: Derivation, oracle) -> int:
    """Check every node with :func:`opulse.verify.verify_trace`; returns the number of nodes."""
    from opulse.verify import VerificationError, verify_trace

    nodes = root.nodes()
    for node in nodes:
        verify_trace(node.trace, oracle)
        for item in node.steps:
            step = item.step
            if item.child is None:
                continue
            if step.kind != "eval" or step.operator.definition is None:
                raise VerificationError("only an eval step of a defined operator has a sub-derivation")
            child = item.child
            if child.operator is not step.operator or tuple(map(_key, child.inputs)) != tuple(map(_key, step.inputs)):
                raise VerificationError(f"the sub-derivation of {step.operator.symbol} is for other inputs")
            if not _same(child.value, step.output):
                raise VerificationError(f"the sub-derivation of {step.operator.symbol} ends at {child.value!r}, "
                                        f"the step gives {step.output!r}")
    return len(nodes)


# ------------------------------------------------------------------ JSON
def tree_to_json(node: Node) -> dict:
    if isinstance(node, Number):
        return {"num": None if node.value is NAN else node.value}
    if isinstance(node, Variable):
        return {"var": node.name}
    return {"op": node.operator.func_id, "args": [tree_to_json(arg) for arg in node.args]}


def tree_from_json(data: dict, registry) -> Node:
    if "num" in data:
        return Number(NAN if data["num"] is None else data["num"])
    if "var" in data:
        return Variable(data["var"])
    return Call(registry.get(data["op"]), tuple(tree_from_json(arg, registry) for arg in data["args"]))


def operator_kind(op: Operator) -> str:
    return {SIMPLE: "simple", BRANCH: "branch", RECURSIVE: "recursive"}.get(op.definition_type, "base") \
        if op.definition is not None else "base"


def operator_json(op: Operator) -> dict:
    return {"symbol": op.symbol, "n_ary": op.n_ary, "position": op.unary_position,
            "layer": op.recursive_layer, "kind": operator_kind(op), "priority": op.priority,
            "associativity": op.associativity_direction, "definition": op.definition}


def to_json(root: Derivation, renderer=None) -> dict:
    """The tree as JSON-compatible data (schema at the top of this module)."""
    nodes = root.nodes()
    ids = {id(node): f"n{i}" for i, node in enumerate(nodes)}
    operators: dict[str, Operator] = {}

    def note(tree: Node) -> None:
        if isinstance(tree, Call):
            operators[tree.operator.func_id] = tree.operator
            for arg in tree.args:
                note(arg)

    def text(tree: Node) -> str:
        return renderer.minimal(tree) if renderer is not None else ""

    out_nodes = {}
    for node in nodes:
        note(node.source)
        steps = []
        for item in node.steps:
            s = item.step
            note(s.after)
            written = {"kind": s.kind, "path": list(s.path), "operator": s.operator.func_id,
                       "inputs": [_json(v) for v in s.inputs], "depth": s.depth,
                       "before": tree_to_json(s.before), "after": tree_to_json(s.after),
                       "expression_after": tree_to_json(s.expression_after),
                       "branch": s.branch_index, "condition": s.condition, "reason": s.reason,
                       "child": ids[id(item.child)] if item.child is not None else None}
            if s.search_attempts is not None:
                written["search_attempts"] = s.search_attempts
            steps.append(written)
        out_nodes[ids[id(node)]] = {
            "operator": node.operator.func_id if node.operator is not None else None,
            "inputs": [_json(v) for v in node.inputs], "source": tree_to_json(node.source),
            "text": text(node.source), "value": _json(node.value), "steps": steps}
    return {"schema": SCHEMA, "expression": text(root.source), "value": _json(root.value), "root": ids[id(root)],
            "operators": {key: operator_json(op) for key, op in sorted(operators.items())}, "nodes": out_nodes}


def from_json(data: dict, registry) -> Derivation:
    """Rebuild a tree written by :func:`to_json` (operators are looked up in ``registry``)."""
    if data.get("schema") != SCHEMA:
        raise ValueError(f"not an {SCHEMA} document")
    built: dict[str, Derivation] = {}
    for key, raw in data["nodes"].items():
        source = tree_from_json(raw["source"], registry)
        current, steps = source, []
        for i, s in enumerate(raw["steps"]):
            path = tuple(s["path"])
            after_tree = tree_from_json(s["after"], registry)
            after = _replace_at(current, path, after_tree)
            if after != tree_from_json(s["expression_after"], registry):
                raise ValueError(f"node {key} step {i}: expression_after does not match the rewrite")
            steps.append(TraceStep(i, s["kind"], path, registry.get(s["operator"]),
                                   tuple(_value(v) for v in s["inputs"]), tree_from_json(s["before"], registry),
                                   after_tree, current, after, s["branch"], s["condition"], s["reason"], s["depth"],
                                   s.get("search_attempts")))
            current = after
        operator = registry.get(raw["operator"]) if raw["operator"] is not None else None
        built[key] = Derivation(source, Trace(source, steps), [TreeStep(s) for s in steps], operator,
                                tuple(_value(v) for v in raw["inputs"]))
    for key, raw in data["nodes"].items():
        for item, s in zip(built[key].steps, raw["steps"]):
            if s["child"] is not None:
                item.child = built[s["child"]]
    return built[data["root"]]


def dumps(root: Derivation, renderer=None, **kwargs) -> str:
    return json.dumps(to_json(root, renderer), ensure_ascii=False, allow_nan=False, **kwargs)


# ------------------------------------------------------------------ text
def render_text(root: Derivation, renderer, expand: Callable[[Operator], bool] | None = None,
                max_depth: int | None = None, open_levels: int = 0, indent: str = "    ") -> str:
    """Plain text: the derivation at a cut, one ``= expression`` line per step with its kind;
    the remaining one-step evaluations of defined operators are opened ``open_levels`` deep,
    indented under their step."""
    lines = [renderer.minimal(root.source)]
    _render_view(flatten_view(root, expand, max_depth), renderer, lines, "", open_levels, indent)
    return "\n".join(lines)


def _render_view(view: list[ViewStep], renderer, lines: list[str], pad: str, open_levels: int, indent: str) -> None:
    width = min(56, max((len(renderer.minimal(v.step.expression_after)) for v in view), default=0))
    for v in view:
        lines.append(f"{pad}= {renderer.minimal(v.step.expression_after):<{width}}   {_label(v.step, renderer)}")
        if v.child is not None and open_levels > 0:
            child = v.child
            inner = pad + indent
            lines.append(f"{inner}{renderer.minimal(child.source)}")
            sub = [ViewStep(item.step, item.child) for item in child.steps]
            _render_view(sub, renderer, lines, inner, open_levels - 1, indent)


def _label(step: TraceStep, renderer) -> str:
    symbol = step.operator.symbol
    if step.kind == "expand":
        branch = "" if step.condition is None else f", branch {step.branch_index + 1}: {step.condition}"
        trials = "" if step.search_attempts is None else f", search: {step.search_attempts}"
        return f"[expand {symbol}{branch}{trials}]"
    if step.kind == "undefined":
        return f"[undefined {symbol}: {step.reason}]"
    if step.kind == "eval" and step.branch_index is not None:
        return f"[search {symbol}, branch {step.branch_index + 1}: {step.condition}]"
    return f"[{'atom' if step.operator.definition is None else 'eval'} {symbol}]"


# ------------------------------------------------------------------ helpers
def _key(value):
    return "NaN" if value is NAN else value


def _json(value):
    return None if value is NAN else value


def _value(value):
    return NAN if value is None else value


def _same(a, b) -> bool:
    return (a is NAN and b is NAN) or (a is not NAN and b is not NAN and a == b)
