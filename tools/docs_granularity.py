"""Precompute the data of the granularity explorer (docs/guide/step-by-step.md).

    python tools/docs_granularity.py

Grows an operator set with ``opulse operators --layers 6 4 3 --seed 7``, assigns
shape and subscript names while preserving each definition and function id (written to
outputs/docs_granularity/operators.jsonl), picks expressions whose operators span every layer
and all three kinds of definition, and writes one JSON file per expression to
docs/assets/data/granularity_<n>.json:

* ``tree``: the derivation tree (schema ``opulse.derivation/1``, :mod:`opulse.trace.tree`),
  every node checked by the reference interpreter;
* ``graph``: the defined operators the expression reaches, with layers and edges;
* ``explain``: formula, behaviour table and outline of each of them
  (:mod:`opulse.trace.explain`);
* ``checks``: the derivation at every layer cut, as text, computed by the reducer. The page
  script flattens the tree itself; these lines let it (and the screenshots) confirm that it
  shows the same steps.

It also writes docs/snippets/granularity_tree.md and granularity_explain.md (plain text output
of the first example), and the data of the granularity animation
(docs/assets/data/granularity_anim.json, :func:`animation`): one short expression over a small
operator set grown from ``+ - * %`` and negation, derived at every cut: each of the 2^k subsets
of its k defined operators made known. Each cut is aligned (:func:`opulse.trace.tree.align`) with
the cut where every operator is known and the one where everything unfolds, and the file also
holds the tree of one-step evaluations for the zoom view. Every step there is the reducer's step
at that cut and is checked by the reference interpreter.

    python tools/docs_granularity.py            # everything
    python tools/docs_granularity.py --anim     # only the animation data
"""

from __future__ import annotations

import io
import json
import logging
import random
import sys
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from opulse.cli.main import main as cli
from opulse.cli.operators import DEFAULT_CONFIG
from opulse.config import Settings
from opulse.core import NAN, OperatorRegistry
from opulse.core.primitives import write_initial_set
from opulse.definition import ast
from opulse.definition.parser import DefinitionParser
from opulse.expression.generator import ExpressionGenerator, OperatorPool
from opulse.expression.nodes import Call, Number, iter_calls, literal_form
from opulse.expression.render import ExpressionRenderer
from opulse.runtime import PythonRuntime
from opulse.trace import Reducer
from opulse.trace.explain import Explainer, operator_form, render_explanation
from opulse.trace.tree import (
    align,
    build_tree,
    cut,
    operator_kind,
    render_text,
    to_json,
    verify_tree,
)
from opulse.verify import Oracle
from opulse.verify.records import verify_trace

OUT = ROOT / "docs" / "assets" / "data"
SNIPPETS = ROOT / "docs" / "snippets"
OPERATORS = ROOT / "outputs" / "docs_granularity" / "operators.jsonl"
SEED = 7
LAYERS = [6, 4, 3]
EXAMPLES = 3
SHAPES = "■□▲△▼▽◆◇●○★☆"
SUBSCRIPT = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")


def legacy_config(directory: Path) -> Path:
    """A config that grows the set with the legacy random symbols; ``named_operators`` then
    gives them consecutive shape and index names (◆₁, ◆₂, ...) in generation order."""
    path = directory / "legacy_names.yaml"
    path.write_text("operators: {naming: legacy}\n", encoding="utf-8")
    return path


def named_operators(registry: OperatorRegistry, settings: Settings) -> OperatorRegistry:
    """Give the generated operators short display names without changing their code or ids."""
    parser = DefinitionParser(settings.symbols, registry)
    definitions = {op.func_id: parser.parse(op.definition) for op in registry if op.definition}
    names = {op.symbol: SHAPES[i % len(SHAPES)] + str(i // len(SHAPES) + 1).translate(SUBSCRIPT)
             for i, op in enumerate(op for op in registry if op.definition)}

    def expr(node):
        if isinstance(node, ast.Apply):
            return ast.Apply(names.get(node.symbol, node.symbol), tuple(expr(arg) for arg in node.args),
                             node.unary_position)
        return node

    def condition(node):
        if isinstance(node, ast.Compare):
            return ast.Compare(expr(node.left), node.op, expr(node.right))
        if isinstance(node, (ast.And, ast.Or)):
            return type(node)(condition(node.left), condition(node.right))
        return ast.Not(condition(node.operand))

    renamed = []
    for op in registry:
        if op.definition is None:
            renamed.append(op)
            continue
        parsed = definitions[op.func_id]
        rewritten = ast.Definition(expr(parsed.lhs), tuple(
            ast.Branch(expr(branch.expr), condition(branch.condition) if branch.condition else None,
                       branch.is_else) for branch in parsed.branches))
        renamed.append(replace(op, symbol=names[op.symbol],
                               definition=ast.render_definition(rewritten, settings.symbols)))
    result = OperatorRegistry(renamed)
    check = DefinitionParser(settings.symbols, result)
    for op in result:
        if op.definition:
            check.parse(op.definition)
    return result


def closure(ops, registry) -> list:
    seen, stack = {}, list(ops)
    while stack:
        op = stack.pop()
        if op.func_id in seen or op.definition is None:
            continue
        seen[op.func_id] = op
        stack.extend(registry.get(d) for d in op.dependencies if d in registry)
    return list(seen.values())


def main(operators_only: bool = False) -> None:
    # The operator set comes from the command line, so the commands shown on the page reproduce it.
    OPERATORS.parent.mkdir(parents=True, exist_ok=True)
    OPERATORS.unlink(missing_ok=True)
    logging.disable(logging.INFO)
    with redirect_stdout(io.StringIO()):
        cli(["operators", "--config", str(legacy_config(OPERATORS.parent)), "--out", str(OPERATORS),
             "--layers", *map(str, LAYERS), "--seed", str(SEED)])
    settings = Settings.load(DEFAULT_CONFIG)
    registry = named_operators(OperatorRegistry.from_jsonl(OPERATORS), settings)
    registry.to_jsonl(OPERATORS)
    if operators_only:
        return
    runtime = PythonRuntime(registry, settings.semantics.build())
    parser = DefinitionParser(settings.symbols, registry)
    oracle = Oracle(registry, settings.symbols, settings.semantics.build())
    renderer = ExpressionRenderer(settings.symbols)
    explainer = Explainer(registry, oracle, runtime, renderer, timeout_ms=3000)
    top = max(op.recursive_layer or 0 for op in registry if op.definition)

    generator = ExpressionGenerator(settings.expressions, random.Random(SEED))
    pool = OperatorPool.from_registry(registry)
    chosen, used_tops = [], set()
    for _ in range(4000):
        tree = generator.tree(pool)
        if not isinstance(tree, Call):
            continue
        tree = literal_form(tree, registry)
        calls = list(iter_calls(tree))
        if any(c.operator.symbol == "-" and c.operator.n_ary == 1 for c in calls):
            continue  # no negative literals, so every step on the page applies an operator
        defined = [c.operator for c in calls if c.operator.definition]
        if not defined or len(calls) > 4 or max(op.recursive_layer for op in defined) < top:
            continue
        ops = closure(defined, registry)
        kinds = {operator_kind(op) for op in ops}
        if kinds != {"simple", "branch", "recursive"} or not 4 <= len(ops) <= 12:
            continue
        full = Reducer(registry, runtime, parser).reduce(tree)
        if full.truncated or full.value is NAN or full.value == 0 or not 30 <= len(full.steps) <= 200:
            continue
        key = tuple(sorted(op.func_id for op in defined))
        if key in used_tops:
            continue
        used_tops.add(key)
        chosen.append((tree, ops))
        if len(chosen) == EXAMPLES:
            break
    if len(chosen) < EXAMPLES:
        raise SystemExit(f"found only {len(chosen)} examples")

    OUT.mkdir(parents=True, exist_ok=True)
    index = []
    for number, (tree, ops) in enumerate(chosen, 1):
        root = build_tree(tree, registry, runtime, parser)
        nodes = verify_tree(root, oracle)
        ids = {op.func_id for op in ops}
        graph = [{"id": op.func_id, "symbol": op.symbol, "form": operator_form(op), "layer": op.recursive_layer,
                  "kind": operator_kind(op), "definition": op.definition,
                  "uses": sorted(d for d in set(op.dependencies) if d in ids and d != op.func_id)}
                 for op in sorted(ops, key=lambda o: (o.recursive_layer, o.symbol))]
        checks = []
        for layers in range(top + 2):
            trace = Reducer(registry, runtime, parser, expand=cut(known_layers=layers)).reduce(tree)
            checks.append({"known_layers": layers, "kinds": [s.kind for s in trace.steps],
                           "lines": [renderer.minimal(s.expression_after) for s in trace.steps]})
        data = {"schema": "opulse.granularity/1", "seed": SEED, "layers": LAYERS, "top_layer": top,
                "operators_file": str(OPERATORS.relative_to(ROOT)),
                "symbols": {"left_paren": settings.symbols.left_paren, "right_paren": settings.symbols.right_paren,
                            "nan": settings.symbols.nan},
                "tree": to_json(root, renderer), "graph": graph,
                "explain": {op.func_id: explainer.explain(op) for op in ops}, "checks": checks}
        name = f"granularity_{number}.json"
        (OUT / name).write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False),
                                encoding="utf-8")
        index.append({"file": name, "expression": data["tree"]["expression"], "value": data["tree"]["value"]})
        print(f"wrote {name}: {data['tree']['expression']} = {data['tree']['value']}, {nodes} nodes, "
              f"{len(checks[0]['lines'])} steps at the finest cut, {(OUT / name).stat().st_size // 1024} KiB")
    (OUT / "granularity_index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")

    # Text fragments for the page (opulse trace / opulse explain output on the first example).
    tree, ops = chosen[0]
    root = build_tree(tree, registry, runtime, parser)
    text = render_text(root, renderer, cut(known_layers=top + 1), open_levels=1)
    ops_file = OPERATORS.relative_to(ROOT)
    write_snippet("granularity_tree.md",
                  f"```bash\npython tools/docs_granularity.py\n"
                  f"opulse trace --operators {ops_file} --expression \"{renderer.minimal(tree)}\" "
                  f"--known-layers {top + 1} --open 1\n```\n\n```text\n{text}\n```")
    every = list({op.func_id: op for _, example_ops in chosen for op in example_ops}.values())
    proved = [op for op in sorted(every, key=lambda o: (operator_kind(o) != "branch", o.recursive_layer, o.symbol))
              if any((row["simplified_check"] or {}).get("status") == "proved"
                     for row in explainer.formula(op)["branches"])]
    shown = proved[0] if proved else ops[0]
    write_snippet("granularity_explain.md",
                  f"```bash\npython tools/docs_granularity.py --operators-only\n"
                  f"opulse explain --operators {ops_file} --operator \"{shown.symbol}\"\n```\n\n"
                  f"```text\n{render_explanation(explainer.explain(shown))}\n```")


# ------------------------------------------------------------------ animation
ANIM_OPERATORS = ROOT / "outputs" / "docs_granularity" / "anim_operators.jsonl"
ANIM_INITIAL = ROOT / "outputs" / "docs_granularity" / "anim_initial.jsonl"
ANIM_ATOMS = ("add", "sub", "mul", "mod", "neg")
ANIM_LAYERS = [3, 3, 3]
ANIM_SEED = 43
# Picked from this operator set by a search over short expressions: three applications, small
# non-negative numbers, three defined operators (so 8 cuts), 3 steps with every operator known
# and 10 with everything unfolded, and expansions of all three kinds of definition, including a
# recursive call.
ANIM_EXPRESSION = ("+", ("■₁", 2), ("●₁", 3, 6))
ANIM_OUT = OUT / "granularity_anim.json"


def animation_registry(settings: Settings, workdir: Path | None = None) -> OperatorRegistry:
    """The operator set of the animation: ``opulse operators`` over a start set of five atoms."""
    initial = ANIM_INITIAL if workdir is None else workdir / ANIM_INITIAL.name
    operators = ANIM_OPERATORS if workdir is None else workdir / ANIM_OPERATORS.name
    operators.parent.mkdir(parents=True, exist_ok=True)
    write_initial_set(initial, ANIM_ATOMS)
    operators.unlink(missing_ok=True)
    logging.disable(logging.INFO)
    with redirect_stdout(io.StringIO()):
        cli(["operators", "--config", str(legacy_config(operators.parent)), "--initial", str(initial),
             "--out", str(operators), "--layers", *map(str, ANIM_LAYERS), "--seed", str(ANIM_SEED)])
    registry = named_operators(OperatorRegistry.from_jsonl(operators), settings)
    registry.to_jsonl(operators)
    return registry


def expression_from_spec(spec, registry: OperatorRegistry):
    """``("sym", arg, ...)`` or an int, with operators looked up by symbol and arity."""
    if isinstance(spec, (int, str)):
        return Number(spec)
    symbol, *args = spec
    matches = [op for op in registry if op.symbol == symbol and op.n_ary == len(args)]
    if len(matches) != 1:
        raise ValueError(f"no unique {len(args)}-ary operator {symbol!r}")
    return Call(matches[0], tuple(expression_from_spec(arg, registry) for arg in args))


class _MarkedRenderer(ExpressionRenderer):
    """``minimal`` text with the subtree ``target`` (by identity) between two marker characters."""

    target = None

    def _render(self, node, parent, side, minimal):
        text = super()._render(node, parent, side, minimal)
        return "\x01" + text + "\x02" if node is self.target else text


def marked_text(renderer: _MarkedRenderer, expression, path) -> tuple[str, list[int] | None]:
    """The text of ``expression`` and the character span of the subtree at ``path``."""
    node = expression
    for index in path:
        node = node.args[index]
    renderer.target = node
    try:
        text = renderer.minimal(expression)
    finally:
        renderer.target = None
    if "\x01" not in text:
        return text, None
    start = text.index("\x01")
    end = text.index("\x02") - 1
    return text.replace("\x01", "").replace("\x02", ""), [start, end]


def step_class(step) -> str:
    """Colour class of a step: expand/branch/recursion by the kind of the unfolded definition,
    atom for a base operation, known for a defined operator computed in one step."""
    if step.kind == "expand":
        return {"simple": "expand", "branch": "branch", "recursive": "recursion"}[operator_kind(step.operator)]
    if step.kind == "undefined":
        return "undefined"
    return "atom" if step.operator.definition is None else "known"


def step_json(step, renderer: _MarkedRenderer) -> dict:
    text, hit = marked_text(renderer, step.expression_after, step.path)
    cls = step_class(step)
    return {"cls": cls, "kind": step.kind, "op": step.operator.symbol, "text": text, "hit": hit,
            "cond": step.condition,
            "otherwise": cls in ("branch", "recursion") and step.condition is None}


def chip_operators(root) -> list:
    """The defined operators the derivation of ``root`` applies, ordered by layer and symbol.

    These are the operators a cut can make known or unfold; base operations are always
    applied directly."""
    used = {}
    for node in root.nodes():
        for item in node.steps:
            op = item.step.operator
            if op.definition is not None:
                used[op.func_id] = op
    return sorted(used.values(), key=lambda op: (op.recursive_layer or 0, op.symbol))


def animation(settings: Settings, workdir: Path | None = None) -> dict:
    """The data of docs/snippets/granularity_anim.html (schema ``opulse.granularity-anim/2``).

    ``chips`` lists the k defined operators of the derivation. ``cuts[mask]`` is the derivation
    in which ``chips[i]`` is known (computed in one step) exactly when bit ``i`` of ``mask`` is
    set, for all 2^k masks. ``coarse`` is the cut with every operator known and ``fine`` the cut
    with everything unfolded to atoms. Each cut lists its own steps (``owner``: the coarse step
    and the step of this cut it belongs to) and, for every fine step, the step of this cut that
    contains it (``fine``). Raises ``SystemExit`` unless every cut equals the reducer's trace
    with the same known operators and verifies."""
    registry = animation_registry(settings, workdir)
    return animation_for(settings, registry, ANIM_EXPRESSION, ANIM_SEED, ANIM_LAYERS,
                         ANIM_ATOMS, ANIM_OPERATORS)


def animation_for(settings: Settings, registry: OperatorRegistry, spec, seed: int, layers: list[int],
                  atoms: tuple[str, ...], operators_file: Path) -> dict:
    """Build and check every cut of one generated expression."""
    runtime = PythonRuntime(registry, settings.semantics.build())
    parser = DefinitionParser(settings.symbols, registry)
    oracle = Oracle(registry, settings.symbols, settings.semantics.build())
    renderer = _MarkedRenderer(settings.symbols)
    expression = expression_from_spec(spec, registry)
    root = build_tree(expression, registry, runtime, parser)
    verify_tree(root, oracle)
    chips = chip_operators(root)
    if not 1 <= len(chips) <= 5:
        raise SystemExit(f"the animation expression uses {len(chips)} defined operators; pick one with 1 to 5")

    def known_cut(mask: int):
        return cut(known=[op.func_id for i, op in enumerate(chips) if mask >> i & 1])

    def checked_trace(mask: int, view) -> None:
        trace = Reducer(registry, runtime, parser, expand=known_cut(mask)).reduce(expression)
        verify_trace(trace, oracle)
        if [(s.kind, s.operator.func_id, s.path, s.expression_after) for s in trace.steps] != \
                [(v.step.kind, v.step.operator.func_id, v.step.path, v.step.expression_after) for v in view]:
            raise SystemExit(f"cut {mask:0{len(chips)}b}: the tree does not give the reducer's trace")

    full = (1 << len(chips)) - 1
    cuts = []
    coarse = fine = None
    for mask in range(full + 1):
        views, owners = align(root, [known_cut(full), known_cut(mask), known_cut(0)])
        checked_trace(mask, views[1])
        first = {}
        for owner in owners:
            first.setdefault(owner[1], owner[:2])
        steps = []
        for index, item in enumerate(views[1]):
            row = step_json(item.step, renderer)
            row["owner"] = list(first[index])
            steps.append(row)
        cuts.append({"known": [op.symbol for i, op in enumerate(chips) if mask >> i & 1],
                     "count": len(steps), "steps": steps, "fine": [owner[1] for owner in owners]})
        if mask == 0:
            checked_trace(full, views[0])
            coarse = [dict(step_json(item.step, renderer), owner=[index]) for index, item in enumerate(views[0])]
            fine = [dict(step_json(item.step, renderer), owner=[owner[0]])
                    for item, owner in zip(views[2], owners)]

    top = max(op.recursive_layer or 0 for op in chips)
    presets = {"all": full, "top": sum(1 << i for i, op in enumerate(chips) if (op.recursive_layer or 0) < top),
               "none": 0}

    nodes = root.nodes()
    ids = {id(node): f"n{i}" for i, node in enumerate(nodes)}
    zoom = {}
    for node in nodes:
        rows = []
        for item in node.steps:
            row = step_json(item.step, renderer)
            row["child"] = ids[id(item.child)] if item.child is not None else None
            rows.append(row)
        zoom[ids[id(node)]] = {"op": node.operator.symbol if node.operator is not None else None,
                               "text": renderer.minimal(node.source),
                               "value": None if node.value is NAN else node.value, "steps": rows}

    used = {}
    for node in nodes:
        for call in iter_calls(node.source):
            used[call.operator.symbol] = call.operator
        for item in node.steps:
            for call in iter_calls(item.step.after):
                used[call.operator.symbol] = call.operator
    operators = {symbol: {"kind": operator_kind(op), "layer": op.recursive_layer, "definition": op.definition}
                 for symbol, op in sorted(used.items()) if op.definition is not None}
    return {"schema": "opulse.granularity-anim/2", "seed": seed, "layers": layers,
            "atoms": list(atoms), "operators_file": str(operators_file.relative_to(ROOT)),
            "expression": renderer.minimal(expression), "value": None if root.value is NAN else root.value,
            "operators": operators, "chips": [op.symbol for op in chips], "presets": presets,
            "coarse": coarse, "fine": fine, "cuts": cuts, "zoom": {"root": ids[id(root)], "nodes": zoom}}


def write_animation() -> dict:
    data = animation(Settings.load(DEFAULT_CONFIG))
    ANIM_OUT.parent.mkdir(parents=True, exist_ok=True)
    ANIM_OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n",
                        encoding="utf-8")
    counts = {"".join("K" if c in item["known"] else "u" for c in data["chips"]): item["count"]
              for item in data["cuts"]}
    print(f"wrote {ANIM_OUT.name}: {data['expression']} = {data['value']}, {len(data['cuts'])} cuts over "
          f"{' '.join(data['chips'])} (K known, u unfolded): {counts}, {ANIM_OUT.stat().st_size} bytes")
    return data


def write_snippet(name: str, text: str) -> None:
    (SNIPPETS / name).write_text(text.rstrip() + "\n", encoding="utf-8")
    print("wrote", name)


if __name__ == "__main__":
    if "--operators-only" in sys.argv[1:]:
        main(operators_only=True)
    elif "--anim" not in sys.argv[1:]:
        main()
        write_animation()
    else:
        write_animation()
