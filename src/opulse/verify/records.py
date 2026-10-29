"""Independent re-computation of dataset records and traces (spec section 9, items 5-7).

Records are produced with compiled code (Python or Cython); these checks redo
the arithmetic with the reference oracle, which reads only definition text.
"""

from __future__ import annotations

from opulse.core.semantics import NAN
from opulse.expression.nodes import Node, to_ast
from opulse.verify.oracle import Oracle


class VerificationError(AssertionError):
    """A produced answer disagrees with the reference semantics. Nothing is written."""


def expected_value(node: Node, oracle: Oracle, env: dict | None = None):
    result = oracle.evaluate_expr(to_ast(node), env or {})
    return result.value, result.base_ops


def verify_evaluation(node: Node, value, expansion: int, oracle: Oracle) -> None:
    want_value, want_expansion = expected_value(node, oracle)
    from opulse.core.types import same_value

    if not same_value(want_value, value):
        raise VerificationError(f"value {value!r} != reference {want_value!r}")
    if want_expansion != expansion:
        raise VerificationError(f"expansion {expansion} != reference {want_expansion}")


def verify_trace(trace, oracle: Oracle) -> None:
    """Check every step on its own, not only the value of the whole expression.

    For each step: it continues from the previous expression; its focus is the application
    at ``path`` with the recorded number arguments; the new expression is the old one with
    exactly that subtree replaced; the replacement has the operator's value (an ``eval``
    step gives that value directly, an ``undefined`` step needs it to be NaN); an ``expand``
    step takes the branch the reference semantics selects. Finally the whole expression
    keeps its value and the trace ends at it.
    """
    from opulse.analysis.coverage import (
        _condition,
        _UndefinedCondition,
        selected_branch,
    )
    from opulse.definition import ast
    from opulse.expression.nodes import Call, Number

    if trace.truncated:
        raise VerificationError("trace truncated before reaching a number")
    want, _ = expected_value(trace.source, oracle)
    current = trace.source
    for expected_index, step in enumerate(trace.steps):
        where = f"step {step.index} ({step.kind} {step.operator.symbol!r})"
        if step.index != expected_index:
            raise VerificationError(f"{where}: index must be {expected_index}")
        if step.kind not in ("eval", "expand", "undefined"):
            raise VerificationError(f"{where}: unknown rewrite kind")
        if step.reason is not None and (step.kind != "undefined" or step.reason not in
                                        ("nan_condition", "no_branch")):
            raise VerificationError(f"{where}: invalid reason")
        if step.kind == "undefined" and step.reason is None:
            raise VerificationError(f"{where}: missing undefined reason")
        if step.expression_before != current:
            raise VerificationError(f"{where} does not continue from the previous expression")
        focus = _subtree(current, step.path)
        if focus != step.before or not isinstance(focus, Call) or focus.operator is not step.operator:
            raise VerificationError(f"{where}: the focus is not the recorded application")
        if tuple(arg.value if isinstance(arg, Number) else None for arg in focus.args) != tuple(step.inputs):
            raise VerificationError(f"{where}: the focus arguments are not the recorded numbers")
        if step.expression_after != _replace(current, step.path, step.after):
            raise VerificationError(f"{where}: more than the focus was rewritten")
        value = oracle.evaluate(step.operator, step.inputs).value
        got, _ = expected_value(step.after, oracle)
        if not same_value(got, value):
            raise VerificationError(f"{where}: the rewrite has value {got!r}, the operator gives {value!r}")
        if step.kind == "eval":
            if step.search_attempts is not None:
                raise VerificationError(f"{where}: an evaluation has no nested search trials")
            if not isinstance(step.after, Number):
                raise VerificationError(f"{where}: an evaluation must produce a number")
            if step.branch_index is not None:
                if step.operator.definition is None:
                    raise VerificationError(f"{where}: a base operation has no branch")
                branch = selected_branch(step.operator, step.inputs, oracle)
                definition = oracle._definition_of(step.operator)
                if branch != step.branch_index or branch is None or not isinstance(
                        definition.branches[branch].expr, ast.Search):
                    raise VerificationError(f"{where}: invalid evaluation branch")
                expected_condition = _search_condition(definition.branches[branch].expr,
                                                       dict(zip(definition.parameters, step.inputs)), oracle)
            else:
                expected_condition = None
            if step.condition != expected_condition:
                raise VerificationError(f"{where}: condition text does not match the selected branch")
        if step.kind == "undefined" and (
                step.operator.definition is None or value is not NAN or step.branch_index is not None
                or selected_branch(step.operator, step.inputs, oracle) is not None
                or not isinstance(step.after, Number) or step.after.value is not NAN
                or step.condition is not None or step.search_attempts is not None):
            raise VerificationError(f"{where}: invalid undefined rewrite")
        if step.kind == "undefined":
            definition = oracle._definition_of(step.operator)
            env = dict(zip(definition.parameters, step.inputs))
            expected_reason = "no_branch"
            try:
                for branch in definition.branches:
                    if branch.condition is None or _condition(branch.condition, env, oracle):
                        break
            except _UndefinedCondition:
                expected_reason = "nan_condition"
            if step.reason != expected_reason:
                raise VerificationError(f"{where}: undefined reason should be {expected_reason}")
        if step.kind == "expand":
            if step.operator.definition is None:
                raise VerificationError(f"{where}: a base operation cannot expand")
            branch = selected_branch(step.operator, step.inputs, oracle)
            if branch is None or branch != step.branch_index:
                raise VerificationError(f"{where}: took branch {step.branch_index}, the semantics selects {branch}")
            # The replacement must be that branch's body with the arguments substituted, not
            # merely something with the right value (review finding).
            definition = oracle._definition_of(step.operator)
            env = dict(zip(definition.parameters, step.inputs))
            from opulse.definition.ast import render_condition
            from opulse.trace.reducer import _substitute_condition

            condition = definition.branches[branch].condition
            expected_condition = (render_condition(_substitute_condition(condition, env), oracle.parser.symbols)
                                  if condition is not None else None)
            if step.condition != expected_condition:
                raise VerificationError(f"{where}: condition text does not match the selected branch")
            trials: list[str] = []
            expected = _instantiate(definition.branches[branch].expr, env, oracle, trials)
            if step.after != expected:
                raise VerificationError(f"{where}: the rewrite is not the body of branch {branch}")
            if step.search_attempts != ("; ".join(trials) or None):
                raise VerificationError(f"{where}: search trials do not match the selected branch")
        got, _ = expected_value(step.expression_after, oracle)
        if not same_value(got, want):
            raise VerificationError(f"{where} changes the value {want!r} -> {got!r}")
        current = step.expression_after
    final = trace.value
    if not same_value(final, want):
        raise VerificationError(f"trace ends at {final!r}, reference {want!r}")


def _search_condition(search, env: dict, oracle: Oracle) -> str:
    """Reproduce the bounded-search trials displayed by a reducer eval step."""
    from opulse.definition.interpreter import _Counter, _Undefined

    attempts = []
    for index in range(search.bound + 1):
        try:
            truth = oracle.interpreter._condition(search.condition, {**env, search.index: index},
                                                  _Counter(), 0)
        except _Undefined:
            truth = NAN
        attempts.append(f"{search.index}={index}: " + ("NaN" if truth is NAN else str(truth)))
        if truth is NAN or truth:
            break
    return "; ".join(attempts)


def _instantiate(node, env: dict, oracle, trials: list[str] | None = None):
    """A definition body as an expression tree, parameters replaced by their values."""
    from opulse.definition import ast
    from opulse.expression.nodes import Call, Number

    if isinstance(node, ast.Var):
        return Number(env[node.name])
    if isinstance(node, ast.Num):
        return Number(node.value)
    if isinstance(node, ast.NaN):
        return Number(NAN)
    if isinstance(node, ast.Search):
        if trials is not None:
            trials.append(_search_condition(node, env, oracle))
        return Number(oracle.evaluate_expr(node, env).value)
    if isinstance(node, ast.Literal):
        return Number(node.value)
    return Call(oracle._resolve(node), tuple(_instantiate(arg, env, oracle, trials) for arg in node.args))


def _subtree(node, path):
    for i in path:
        node = node.args[i]
    return node


def _replace(node, path, new):
    from opulse.expression.nodes import Call

    if not path:
        return new
    head, *rest = path
    args = list(node.args)
    args[head] = _replace(args[head], tuple(rest), new)
    return Call(node.operator, tuple(args))


def same_value(a, b) -> bool:
    from opulse.core.types import same_value as equal

    return equal(a, b)


def _stored(value):
    """Normalize typed values to their JSON record representation for comparison."""
    from opulse.core.types import freeze
    from opulse.worlds.perm import Permutation

    return tuple(value) if isinstance(value, Permutation) else freeze(value)


def audit_record(row: dict, registry, oracle: Oracle, settings, runtime=None,
                 trace_cache: dict | None = None) -> list[str]:
    """Every field of a released expression record, re-derived independently; returns problems.

    Checks the value and expansion (reference interpreter), that the expression texts parse
    back to the tree, that the result text decodes to the result, the combined text, every
    evaluation step, the provenance (same operator set), and, when present, that the
    step-by-step solution is reproduced exactly from its recorded settings.
    """
    from opulse.definition.parser import DefinitionParser
    from opulse.expression.dataset import operator_set_hash
    from opulse.expression.nodes import Call, Number, from_ast, from_dict

    problems: list[str] = []
    tree = from_dict(row["tree"], registry)
    if row.get("undefined") and row.get("result") is not None:
        problems.append("result must be null when undefined is true")
    if not row.get("undefined") and row.get("result") is None:
        problems.append("result must be present when undefined is false")
    value = NAN if row.get("undefined") else row["result"]
    if isinstance(value, list):
        if row.get("result_text", "").startswith("P["):
            from opulse.worlds.perm import Permutation

            value = Permutation(value)
        else:
            value = tuple(value)
    try:
        verify_evaluation(tree, value, row["expansion"], oracle)
    except VerificationError as exc:
        problems.append(f"value: {exc}")

    def decimal(node):
        if isinstance(node, Number):
            return Number(node.value)
        if isinstance(node, Call):
            return Call(node.operator, tuple(decimal(arg) for arg in node.args))
        return node

    parser = DefinitionParser(settings.symbols, registry)
    for key, expected in (("expression", tree), ("expression_plain", decimal(tree)),
                          ("expression_full_brackets", decimal(tree))):
        try:
            if from_ast(parser.parse_expr(row[key], expression_mode=True), registry) != expected:
                problems.append(f"{key} does not parse back to the tree")
        except Exception as exc:  # noqa: BLE001 - any parse failure is a finding
            problems.append(f"{key} does not parse: {exc}")

    text = row["result_text"]
    if value is NAN:
        if text != settings.symbols.nan:
            problems.append("result_text of an undefined result is not the NaN spelling")
    elif isinstance(value, (str, bool, tuple)):
        from opulse.core.types import literal

        if text != literal(value):
            problems.append("result_text does not represent the typed result")
    else:
        from opulse.expression.numerals import from_base

        markers = {op.symbol for op in registry if op.is_base is not None}
        digits = text.lstrip("-")
        marker = next((m for m in sorted(markers, key=len, reverse=True) if digits.startswith(m)), "")
        try:
            decoded = from_base(("-" if text.startswith("-") else "") + digits[len(marker):],
                                row["result_base"], settings.numerals.digits)
        except ValueError as exc:
            problems.append(f"result_text does not decode: {exc}")
        else:
            if decoded != value:
                problems.append(f"result_text decodes to {decoded}, not {value}")
    if row.get("text") != f"{row['expression']} = {text}":
        problems.append("text is not 'expression = result_text'")
    if "reverse_text" in row and row["reverse_text"] != f"{text} = {row['expression']}":
        problems.append("reverse_text is not 'result_text = expression'")

    for i, step in enumerate(row.get("steps", [])):
        op = registry.get(step["func_id"])
        from opulse.worlds.perm import Permutation

        inputs = tuple(NAN if v is None else Permutation(v) if kind.startswith("perm[")
                       else tuple(v) if isinstance(v, list) else v
                       for v, kind in zip(step["inputs"], op.parameter_types))
        result = oracle.evaluate(op, inputs)
        output = NAN if step["output"] is None else step["output"]
        if isinstance(output, list):
            output = Permutation(output) if op.result_type.startswith("perm[") else tuple(output)
        # A base operation step counts its own application; a defined operator counts the base
        # operations its call executes (oracle.evaluate does not count the call itself).
        expected_ops = 1 if op.definition is None else result.base_ops
        if not same_value(result.value, output) or expected_ops != step["base_ops"]:
            problems.append(f"step {i} ({step['symbol']}) recorded {step['output']}/{step['base_ops']}, "
                            f"reference {result.value}/{result.base_ops}")

    # Reconstruct every application even for older records without operation_count.
    if "steps" not in row:
        problems.append("steps are missing")
    if "steps" in row or "operation_count" in row:
        from opulse.core.types import freeze
        from opulse.expression.evaluator import Step, structure_stats
        from opulse.expression.nodes import defined_operators
        from opulse.expression.numerals import NumeralWriter

        stats = structure_stats(tree, registry)
        for key, expected in stats.items():
            if key in row and row[key] != expected:
                problems.append(f"{key} differs from the tree")
        if "defined_operators" in row and row["defined_operators"] != defined_operators(tree):
            problems.append("defined_operators differs from the tree")
        def graph_stats(node):
            if isinstance(node, Number):
                return 0, 0
            children = [graph_stats(arg) for arg in node.args]
            return (max((path for path, _ in children), default=0) + node.operator.max_path_depth,
                    sum(edges for _, edges in children) + node.operator.max_edge_count)

        path_depth, edge_count = graph_stats(tree)
        for key, expected in (("max_path_depth", path_depth), ("max_edge_count", edge_count)):
            if key in row and row[key] != expected:
                problems.append(f"{key} differs from the tree")
        writer = NumeralWriter(registry, settings.numerals.digits, nan=settings.symbols.nan)
        write = lambda result: writer.write(result, settings.expressions.cot_base)

        expected_steps = []

        def walk(node, depth):
            if isinstance(node, Number):
                return node.value
            inputs = tuple(walk(arg, depth + 1) for arg in node.args)
            result = oracle.evaluate(node.operator, inputs)
            expected_steps.append((node.operator, inputs, result.value,
                                   1 if node.operator.definition is None else result.base_ops, depth))
            return result.value

        walk(tree, 0)
        recorded_steps = row.get("steps", [])
        if len(recorded_steps) != len(expected_steps):
            problems.append(f"steps: recorded {len(recorded_steps)} applications, "
                            f"reference {len(expected_steps)}")
        def step_value(value, kind):
            if value is None:
                return NAN
            if kind.startswith("perm[") and isinstance(value, list):
                from opulse.worlds.perm import Permutation

                return Permutation(value)
            return freeze(value)

        for i, (recorded, (op, inputs, output, base_ops, depth)) in enumerate(
                zip(recorded_steps, expected_steps)):
            got_inputs = tuple(step_value(v, kind) for v, kind in
                               zip(recorded["inputs"], op.parameter_types))
            got_output = step_value(recorded["output"], op.result_type)
            if (recorded["func_id"] != op.func_id or recorded["symbol"] != op.symbol
                    or len(got_inputs) != len(inputs)
                    or any(not same_value(_stored(got), _stored(want))
                           for got, want in zip(got_inputs, inputs))
                    or not same_value(_stored(got_output), _stored(output)) or recorded["base_ops"] != base_ops
                    or recorded["depth"] != depth):
                problems.append(f"steps: application {i} differs from the reference derivation")
            if "text" in recorded and recorded["text"] != Step(op, inputs, output, base_ops, depth).render(
                    write, settings.symbols):
                problems.append(f"steps: application {i} has incorrect text")

    if row.get("provenance", {}).get("operator_set") not in (None, operator_set_hash(registry)):
        problems.append("provenance: the record was made from a different operator set")

    if row.get("cot") is not None and runtime is not None:
        from opulse.expression.render import ExpressionRenderer
        from opulse.language.narrate import narrate
        from opulse.trace import Reducer

        cfg = row.get("cot_settings") or {"lang": "en", "depth": None, "known_layers": 0, "known": []}
        known = set(cfg["known"])
        expand = (lambda op: op.definition is not None and (op.recursive_layer or 0) >= cfg["known_layers"]
                  and op.symbol not in known)
        key = (cfg["depth"], cfg["known_layers"], tuple(sorted(known)))
        reducer = trace_cache.get(key) if trace_cache is not None else None
        if reducer is None:
            reducer = Reducer(registry, runtime, parser, expand=expand, max_depth=cfg["depth"])
            if trace_cache is not None:
                trace_cache[key] = reducer
        trace = reducer.reduce(tree)
        try:
            verify_trace(trace, oracle)
        except VerificationError as exc:
            problems.append(f"cot trace: {exc}")
        if narrate(trace, ExpressionRenderer(settings.symbols), cfg["lang"]) != row["cot"]:
            problems.append("cot is not reproduced from its settings")
    return problems
