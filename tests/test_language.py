"""Language output follows the parsed definition and recorded derivations."""

import io
import json
from contextlib import redirect_stdout

import pytest
from conftest import INITIAL_OPERATORS

from opulse.cli.main import main
from opulse.config import Settings
from opulse.core import (
    BINARY,
    BRANCH,
    NAN,
    PREFIX,
    RECURSIVE,
    UNARY,
    Operator,
    OperatorRegistry,
)
from opulse.definition.parser import DefinitionParser
from opulse.expression.nodes import Call, Number
from opulse.expression.render import ExpressionRenderer
from opulse.language import annotate, describe, narrate, narrate_reverse
from opulse.runtime import PythonRuntime
from opulse.solver.holes import HoleSolver
from opulse.solver.z3_encode import Z3Encoder
from opulse.trace import Reducer
from opulse.verify import Oracle, verify_trace


def _defined(registry, symbol, text, kind, n_ary=BINARY, position=None):
    operator = Operator(f"language{len(registry)}", symbol, n_ary, position,
                        definition=text, definition_type=kind)
    registry.add(operator)
    return operator


def test_base_descriptions_state_exact_semantics(registry):
    for symbol in ("/", "%"):
        op = registry.find(symbol, BINARY)
        for lang, truncation in (("zh", "向零截断"), ("en", "truncat")):
            description = describe(op, None, registry, lang)
            assert truncation in description
            assert "NaN" in description and "[-B, B]" in description
    assert "符号" in describe(registry.find("@", UNARY, "postfix"), None, registry)


def test_partial_branch_and_recursive_control(registry):
    branch = _defined(registry, "⊕", "a ⊕ b = { a + b, if a > b }", BRANCH)
    recursive = _defined(registry, "⋮", "⋮ a = { a, if a % 7 == 0; "
                         "⋮ ((a % 7) - 1), if a % 7 > 0; "
                         "⋮ ((a % 7) + 1), if a % 7 < 0 }", RECURSIVE, UNARY, PREFIX)
    direct = _defined(registry, "⋯", "⋯ a = { a, if a == 0; "
                      "⋯ (a - 1), if a > 0 and a <= 8; "
                      "⋯ (a + 1), if a < 0 and a >= - 8 }", RECURSIVE, UNARY, PREFIX)
    oracle = Oracle(registry)
    assert "否则未定义（NaN）" in describe(branch, oracle._definition_of(branch), registry)
    description = describe(recursive, oracle._definition_of(recursive), registry)
    assert "`|a % 7|`" in description and "最多嵌套 6 层" in description
    direct_description = describe(direct, oracle._definition_of(direct), registry)
    assert "`|a|`" in direct_description and "最多嵌套 8 层" in direct_description
    assert "否则未定义（NaN）" in direct_description
    rows = list(annotate(registry))
    assert rows[-1]["nl_description_zh"] == rows[-1]["nl_description_math_zh"]
    assert "nl_description_chain_en" in rows[-1]


def test_forward_narration_contains_every_intermediate(registry):
    plus, times = registry.find("+", BINARY), registry.find("*", BINARY)
    tree = Call(times, (Call(plus, (Number(2), Number(3))), Number(4)))
    settings = Settings()
    oracle = Oracle(registry)
    trace = Reducer(registry, PythonRuntime(registry, settings.semantics.build()),
                    DefinitionParser(settings.symbols)).reduce(tree)
    verify_trace(trace, oracle)
    renderer = ExpressionRenderer(settings.symbols)
    text = narrate(trace, renderer, "zh")
    for step in trace.steps:
        assert renderer.full(step.expression_before) in text
        assert renderer.full(step.expression_after) in text
    assert "最终答案：`20`" in text


def test_branch_narration_uses_recorded_condition_and_undefined(registry):
    operator = _defined(registry, "⊕", "a ⊕ b = { a + b, if a > b }", BRANCH)
    operator.op_compute_func = f"def {operator.compute_name}(a, b):\n    return a + b\n"
    operator.op_count_func = f"def {operator.count_name}(a, b):\n    return 1\n"
    settings = Settings()
    reducer = Reducer(registry, PythonRuntime(registry, settings.semantics.build()),
                      DefinitionParser(settings.symbols))
    oracle = Oracle(registry)
    renderer = ExpressionRenderer(settings.symbols)
    matched = reducer.reduce(Call(operator, (Number(3), Number(2))))
    verify_trace(matched, oracle)
    text = narrate(matched, renderer, "zh")
    assert f"条件 `{matched.steps[0].condition}` 成立" in text
    assert "选择第 1 个分支" in text
    unmatched = reducer.reduce(Call(operator, (Number(2), Number(3))))
    verify_trace(unmatched, oracle)
    assert unmatched.steps[0].reason == "no_branch"
    assert "没有任何分支的条件成立" in narrate(unmatched, renderer, "zh")
    guarded = _defined(registry, "⊗", "a ⊗ b = { a, if (a / b) > 0; b, else }", BRANCH)
    guarded.op_compute_func = f"def {guarded.compute_name}(a, b):\n    return a\n"  # resolvable; unused
    guarded.op_count_func = f"def {guarded.count_name}(a, b):\n    return 0\n"
    nan_condition = reducer.reduce(Call(guarded, (Number(2), Number(0))))
    verify_trace(nan_condition, oracle)
    assert nan_condition.steps[0].reason == "nan_condition"
    assert "某个条件的比较一侧为 NaN" in narrate(nan_condition, renderer, "zh")


def test_reverse_narration_states_unique_answer(registry):
    plus, times = registry.find("+", BINARY), registry.find("*", BINARY)
    tree = Call(times, (Call(plus, (Number(2), Number(3))), Number(4)))
    oracle = Oracle(registry)
    problem = HoleSolver(Z3Encoder(oracle), oracle).problem(tree, (0, 0))
    text = narrate_reverse(problem, ExpressionRenderer(Settings().symbols), "zh")
    assert "`(x + 3) * 4` 必须等于 20" in text and "右参数是 4" in text and "左参数 `x + 3` 只能取 {5}" in text
    assert "所以 x = 2" in text and "没有别的 x" in text
    english = narrate_reverse(problem, ExpressionRenderer(Settings().symbols), "en")
    assert "Its right argument is 4, so its left argument `x + 3` must be one of {5}" in english
    assert "position" not in english and "So x = 2" in english


def test_describe_and_expressions_cot_cli(tmp_path, registry):
    branch = _defined(registry, "⊕", "a ⊕ b = { a + b, if a > b }", BRANCH)
    branch.op_compute_func = f"def {branch.compute_name}(a, b):\n    return a + b\n"
    branch.op_count_func = f"def {branch.count_name}(a, b):\n    return 1\n"
    operators = tmp_path / "operators.jsonl"
    registry.to_jsonl(operators)
    described = tmp_path / "described.jsonl"
    assert main(["describe", "--operators", str(operators), "--out", str(described)]) == 0
    rows = [json.loads(line) for line in described.read_text().splitlines()]
    assert len(rows) > 10
    assert rows[0]["nl_description_zh"] == rows[0]["nl_description_math_zh"]
    assert "否则未定义（NaN）" in rows[-1]["nl_description_zh"]
    expressions = tmp_path / "expressions.jsonl"
    assert main(["expressions", "--operators", str(INITIAL_OPERATORS), "--out", str(expressions),
                 "--count", "2", "--seed", "4", "--cot", "zh"]) == 0
    records = [json.loads(line) for line in expressions.read_text().splitlines()]
    assert len(records) == 2
    assert all("最终答案" in record["cot"] for record in records)
    assert all("cot" not in row for row in rows)


def test_exhaustive_recursion_is_not_called_partial(registry):
    op = _defined(registry, "⊛", "a ⊛ b = { a, if b % 3 == 0; (a ⊛ ((b % 3) - 1)) + a, if b % 3 > 0; "
                  "(a ⊛ ((b % 3) + 1)) - a, if b % 3 < 0 }", "recursive_definition")
    text = describe(op, DefinitionParser(Settings().symbols, registry).parse(op.definition), registry, "en")
    assert "otherwise undefined" not in text
    partial = _defined(registry, "⊚", "a ⊚ b = { a + b, if a > b }", BRANCH)
    text = describe(partial, DefinitionParser(Settings().symbols, registry).parse(partial.definition), registry, "en")
    assert "otherwise undefined (NaN)" in text


def _narration_setup():
    import random

    from opulse.expression.generator import ExpressionGenerator, OperatorPool
    from opulse.expression.nodes import literal_form
    from opulse.generation.pipeline import OperatorFactory, build_layers

    settings = Settings()
    registry = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
    build_layers(OperatorFactory(settings, registry, random.Random(7)), [10, 6, 4])
    reducer = Reducer(registry, PythonRuntime(registry, settings.semantics.build()),
                      DefinitionParser(settings.symbols, registry))
    generator = ExpressionGenerator(settings.expressions, random.Random(1))
    pool = OperatorPool.from_registry(registry)
    traces = []
    while len(traces) < 25:
        tree = generator.tree(pool, max_depth=2, atoms="number")
        if isinstance(tree, Call):
            trace = reducer.reduce(literal_form(tree, registry))
            if not trace.truncated:
                traces.append(trace)
    return settings, registry, traces


def _trace_numbers(trace, oracle) -> set[int]:
    from opulse.expression.nodes import Number as N
    from opulse.verify.differential import literals

    def walk(node):
        if isinstance(node, N):
            yield node.value
        elif isinstance(node, Call):
            for arg in node.args:
                yield from walk(arg)

    found = set()
    for node in [trace.source] + [s.expression_after for s in trace.steps]:
        found |= {v for v in walk(node) if v is not NAN}
    for step in trace.steps:
        found |= {v for v in step.inputs if v is not NAN}
        if step.branch_index is not None:
            found |= set(range(1, step.branch_index + 2))
        if step.operator.definition is not None:
            definition = oracle._definition_of(step.operator)
            found |= literals(definition) | set(range(1, len(definition.branches) + 1))
    return found


def test_every_number_in_a_narration_comes_from_the_trace():
    """Each stated value is re-parsed: equations are recomputed by the interpreter, comparisons
    re-evaluated, and every other number must be a value of the trace."""
    import re

    from opulse.definition.interpreter import COMPARISONS

    settings, registry, traces = _narration_setup()
    oracle = Oracle(registry)
    parser = DefinitionParser(settings.symbols, registry)
    renderer = ExpressionRenderer(settings.symbols)
    read = lambda text: NAN if text == "NaN" else int(text)
    checked = 0
    for trace in traces:
        allowed = _trace_numbers(trace, oracle)
        for lang in ("en", "zh"):
            for style, collapse in (("terse", None), ("explained", None), ("terse", "atoms"), ("explained", "known")):
                text = narrate(trace, renderer, lang, style, registry=registry, collapse=collapse)
                derived = set()
                for span in re.findall(r"`([^`]+)`", text):
                    if " = " in span:
                        left, right = span.rsplit(" = ", 1)
                        if left.strip() in ("a", "b"):
                            assert read(right) in allowed or read(right) is NAN
                            continue
                        value = oracle.evaluate_expr(parser.parse_expr(left, expression_mode=True), {}).value
                        assert value is read(right) or value == read(right), (span, value)
                        if value is not NAN:
                            derived.add(value)
                        checked += 1
                        continue
                    compare = re.fullmatch(r"(-?\d+) (==|!=|>=|<=|>|<) (-?\d+)", span)
                    if compare:
                        truth = COMPARISONS[compare.group(2)](int(compare.group(1)), int(compare.group(3)))
                        after = text.split(f"`{span}`", 1)[1]
                        stated_false = after.startswith((" is false", " 不成立"))
                        assert truth != stated_false, span
                        checked += 1
                for number in re.findall(r"(?<![\w⁺⁻])-?\d+", text):
                    assert int(number) in allowed | derived or -int(number) in allowed | derived, (number, text)
    assert checked > 200


def test_narration_styles_and_collapse():
    settings, registry, traces = _narration_setup()
    renderer = ExpressionRenderer(settings.symbols)
    trace = next(t for t in traces if any(s.kind == "expand" and s.condition for s in t.steps))
    whole = renderer.full(trace.source)
    terse = narrate(trace, renderer, "en", "terse")
    assert terse.count(whole) == 1  # the whole expression is not repeated on every line
    assert len(terse.splitlines()) == len(trace.steps) + 2
    explained = narrate(trace, renderer, "en", "explained", registry=registry)
    assert "applies" in explained and "Since " in explained
    collapsed = narrate(trace, renderer, "zh", "terse", collapse="known")
    assert len(collapsed.splitlines()) < len(trace.steps) + 2 and "计算：" in collapsed
    with pytest.raises(ValueError, match="registry"):
        narrate(trace, renderer, "en", "explained")
    # The default stays the stored chain-of-thought format.
    assert narrate(trace, renderer, "en").startswith("Starting expression:")


def test_explained_narration_uses_the_trace_semantics(registry):
    settings = Settings.from_dict({"semantics": {"bound": 5}})
    operator = _defined(registry, "◆₁", "◆₁ a = { 0, if a + 10 > 0; 1, else }",
                        BRANCH, UNARY, PREFIX)
    semantics = settings.semantics.build()
    trace = Reducer(registry, PythonRuntime(registry, semantics),
                    DefinitionParser(settings.symbols, registry)).reduce(Call(operator, (Number(0),)))
    assert trace.steps[0].reason == "nan_condition"
    text = narrate(trace, ExpressionRenderer(settings.symbols), "en", "explained",
                   registry=registry, semantics=semantics)
    assert "`0 + 10 = NaN`" in text and "compares a NaN" in text


NARRATE_DEFAULT = "813e327d3908b43b07277b2b9a57e40d046840dd55818edad320beb8f40d5178"


def test_default_narration_is_unchanged(tmp_path):
    """The hash of the default narrations of a fixed set of traces, as written before the styles."""
    import hashlib
    import random

    from opulse.expression.generator import ExpressionGenerator, OperatorPool
    from opulse.expression.nodes import literal_form

    config, ops = tmp_path / "legacy.yaml", tmp_path / "ops.jsonl"
    config.write_text("operators: {naming: legacy}\n")
    with redirect_stdout(io.StringIO()):
        main(["operators", "--config", str(config), "--out", str(ops), "--layers", "10", "6", "3",
              "--seed", "4"])
    registry = OperatorRegistry.from_jsonl(ops)
    settings = Settings.from_dict({"operators": {"naming": "legacy"}})
    renderer = ExpressionRenderer(settings.symbols)
    reducer = Reducer(registry, PythonRuntime(registry, settings.semantics.build()),
                      DefinitionParser(settings.symbols, registry))
    generator = ExpressionGenerator(settings.expressions, random.Random(1))
    pool = OperatorPool.from_registry(registry)
    digest = hashlib.sha256()
    count = 0
    while count < 20:
        tree = generator.tree(pool, max_depth=2, atoms="number")
        if not isinstance(tree, Call):
            continue
        trace = reducer.reduce(literal_form(tree, registry))
        if trace.truncated:
            continue
        for lang in ("en", "zh"):
            digest.update(narrate(trace, renderer, lang).encode())
        count += 1
    assert digest.hexdigest() == NARRATE_DEFAULT
