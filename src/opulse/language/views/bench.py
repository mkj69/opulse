"""Benchmark prompts whose definitions are written in another view, and reading them back.

``opulse bench build --definition-format`` chooses how the definitions of a task are shown:

* ``symbolic`` (default): definition lines, exactly as before;
* ``prose``: controlled English (:mod:`opulse.language.views.controlled`);
* ``code``: Python functions (:mod:`opulse.language.views.code`);
* ``latex``: LaTeX piecewise functions (:mod:`opulse.language.views.latex`);
* ``examples``: input/output tables instead of definitions (an induction task);
* ``mixed``: each definition in one of ``symbolic``, ``prose``, ``code`` or ``latex``.

Non-symbolic definitions are fenced blocks whose info string names the view. The prompt check
reads every block back with the view's own parser, so an answer is re-derived from prose, code
or a formula exactly as from definition lines; an examples prompt is checked by recomputing
every table row with the reference interpreter.
"""

from __future__ import annotations

import random
import re

from opulse.config import Settings, Symbols
from opulse.core.operator import Operator
from opulse.core.registry import OperatorRegistry
from opulse.core.semantics import BASE_OPERATIONS, NAN
from opulse.definition import ast
from opulse.language.ir import OperatorRef, parameter_names, parse_lhs, signatures
from opulse.language.views import code as code_view
from opulse.language.views import latex
from opulse.language.views.controlled import ControlledLanguage, ProseError, tokenize
from opulse.language.views.examples import examples as example_table
from opulse.language.views.examples import parse_table

FORMATS = ("symbolic", "prose", "code", "latex", "examples", "mixed")
MIXED = ("symbolic", "prose", "code", "latex")
FENCE = {"symbolic": "opulse", "prose": "text", "code": "python", "latex": "latex", "examples": "examples"}
UNFENCE = {fence: view for view, fence in FENCE.items()}
BLOCK = re.compile(r"```(\w+)\n(.*?)\n```", re.DOTALL)

HEADERS = {
    "prose": "Definitions, in controlled English (the cases of a definition are tried in order and the first "
             "that applies gives the value; base operations are named in words or by their symbol in backticks):",
    "code": "Definitions, as Python functions:",
    "latex": "Definitions, as LaTeX piecewise functions (rows are tried from top to bottom; the first row whose "
             "condition holds gives the value):",
    "examples": "Examples of the operators (values computed from definitions that are not shown):",
    "mixed": "Definitions, each written in one of several equivalent forms (definition lines, controlled English, "
             "Python functions or LaTeX):",
}


class PromptViews:
    """Renders the definitions of one display registry in a chosen format."""

    def __init__(self, registry: OperatorRegistry, settings: Settings, definition_format: str, seed: int = 0) -> None:
        if definition_format not in FORMATS:
            raise ValueError(f"definition format must be one of {FORMATS}")
        from opulse.language.views import Views

        self.format = definition_format
        self.views = Views(registry, settings)
        self.settings = settings
        self.seed = seed

    def choose(self, operator: Operator, index: int) -> str:
        if self.format != "mixed":
            return self.format
        return random.Random(f"{self.seed}:{index}:{operator.func_id}").choice(MIXED)

    def block(self, operator: Operator, index: int) -> tuple[str, str]:
        """(view, text) of one definition."""
        view = self.choose(operator, index)
        if view == "symbolic":
            return view, operator.definition
        if view == "prose":
            seed = random.Random(f"{self.seed}:{index}:{operator.func_id}:prose").randrange(2**31)
            return view, self.views.prose(operator, "en", seed)
        if view == "code":
            return view, self.views.code(operator)
        if view == "latex":
            return view, self.views.formula(operator)
        return view, self.views.examples(operator).text(self.views.symbols, cases=False)

    def section(self, blocks: list[tuple[str, str]]) -> list[str]:
        """Prompt lines for the definitions section."""
        lines = [HEADERS[self.format]]
        if any(view == "code" for view, _ in blocks):
            lines += code_legend([text for view, text in blocks if view == "code"], self.views.symbols)
        for view, text in blocks:
            lines += [f"```{FENCE[view]}", text, "```"]
        return lines


def code_legend(texts: list[str], symbols: Symbols) -> list[str]:
    """How the code view names base operations and comparisons, for the atoms the code calls."""
    used = set()
    for text in texts:
        used |= set(re.findall(r"\b([A-Za-z_]\w*)\(", text))
    a, b = symbols.left_operand, symbols.right_operand
    lines = ["In the code, base operations are called by name:"]
    for (symbol, n_ary, position), name in BASE_OPERATIONS.items():
        if name not in used:
            continue
        form = (f"{a} {symbol} {b}" if n_ary == 2 else f"{symbol} {a}" if position == "prefix" else f"{a} {symbol}")
        call = f"{name}({a}, {b})" if n_ary == 2 else f"{name}({a})"
        lines.append(f"  - `{call}` is `{form}`.")
    lines += [("`gt`, `lt`, `ge`, `le`, `eq` and `ne` compare (>, <, >=, <=, ==, !=); a comparison that reads "
              f"{symbols.nan} makes the whole call {symbols.nan}. `NAN` is {symbols.nan}, and a function that "
              f"returns `NO_CASE` has no case that applies, so its value is {symbols.nan}."),
              "Each function is decorated with the operator it defines; other functions are called by name."]
    return lines


# ------------------------------------------------------------------ reading prompts


def prompt_blocks(prompt: str) -> list[tuple[str, str]]:
    """(view, text) of every fenced definition block of a prompt."""
    marker = "\nDefinitions" if "\nDefinitions" in prompt else "\nExamples of the operators"
    if marker not in prompt:
        return []
    section = prompt.split(marker, 1)[1]
    blocks = []
    for fence, text in BLOCK.findall(section):
        if fence not in UNFENCE:
            raise ValueError(f"unknown block type {fence!r}")
        blocks.append((UNFENCE[fence], text))
    return blocks


def blocks_of(texts: list[str]) -> list[tuple[str, str]]:
    """(view, text) of stored definition texts, recognising each view by its form."""
    blocks = []
    for text in texts:
        stripped = text.lstrip()
        if stripped.startswith("@definition"):
            blocks.append(("code", text))
        elif "\\begin{cases}" in text or "\\mathbin" in text or "\\text{" in text:
            blocks.append(("latex", text))
        elif stripped.startswith("`") or "`" in stripped.splitlines()[0]:
            blocks.append(("prose", text))
        else:
            blocks.append(("symbolic", text))
    return blocks


def _lhs(view: str, text: str, symbols: Symbols) -> ast.Apply:
    params = parameter_names(symbols, 6)
    if view == "symbolic":
        return parse_lhs(text.split(f" {symbols.equals} ", 1)[0], params, symbols)
    if view == "prose":
        first = text.strip().splitlines()[0]
        symbol = next(tok.text for tok in tokenize(first, (symbols.nan,)) if tok.kind == "sym")
        return parse_lhs(symbol, params, symbols)
    if view == "code":
        match = re.search(r"@definition\((['\"])(.*?)\1\)", text)
        if match is None:
            raise ValueError("a code block needs an @definition decorator")
        return parse_lhs(match.group(2), params, symbols)
    if view == "latex":
        reader = latex._Reader(text, symbols)
        return reader.node()
    raise ValueError(f"{view} blocks do not define operators")


def read_definitions(blocks: list[tuple[str, str]], base: OperatorRegistry, symbols: Symbols) -> list[str]:
    """Definition lines equivalent to the given blocks, each parsed with its own view's parser."""
    heads = [OperatorRef.of(_lhs(view, text, symbols)) for view, text in blocks]
    table = signatures(list(base) + heads)
    names = {code_view.function_name(ref, table): ref for ref in heads}
    prose = ControlledLanguage("en", symbols, table)
    out = []
    for view, text in blocks:
        if view == "symbolic":
            out.append(text)
            continue
        try:
            if view == "prose":
                definition = prose.parse(text)
            elif view == "latex":
                definition = latex.parse(text, symbols)
            else:
                found = code_view.parse(text, symbols, names)
                if len(found) != 1:
                    raise ValueError("a code block holds one function")
                definition = found[0]
        except (ProseError, ValueError) as exc:
            raise ValueError(f"cannot read a {view} definition: {exc}") from exc
        out.append(ast.render_definition(definition, symbols))
    return out


def check_examples(task: dict, registry: OperatorRegistry, symbols: Symbols, semantics) -> list[str]:
    """Every row of every examples table equals the reference value."""
    from opulse.verify import Oracle

    display = registry
    naming = task.get("axes", {}).get("naming", "symbols")
    if naming != "symbols":
        from opulse.expression.aliases import AliasMap, aliased_registry

        alias = AliasMap.build(registry, random.Random(20261019), style=naming, symbols=symbols)
        display = aliased_registry(registry, alias)
    oracle = Oracle(display, symbols, semantics)
    problems = []
    blocks = prompt_blocks(task["prompt"])
    if [text for _, text in blocks] != task["definitions"]:
        problems.append("the prompt's tables differ from the task record")
    if not blocks:
        problems.append("the prompt has no example tables")
    for view, text in blocks:
        if view != "examples":
            problems.append(f"an examples prompt holds a {view} block")
            continue
        try:
            lhs_text, rows = parse_table(text, symbols)
        except (IndexError, ValueError) as exc:
            problems.append(f"cannot read an example table: {exc}")
            continue
        if not rows:
            problems.append(f"the table for {lhs_text!r} has no values")
            continue
        lhs = parse_lhs(lhs_text, parameter_names(symbols, 6), symbols)
        operator = display.find(lhs.symbol, len(lhs.args), lhs.unary_position)
        if operator is None:
            problems.append(f"no operator {lhs_text!r}")
            continue
        for args, value in rows:
            expected = oracle.evaluate(operator, args).value
            if not ((expected is NAN and value is NAN) or (expected is not NAN and value is not NAN
                                                            and expected == value)):
                problems.append(f"{lhs_text} at {args}: the table says {value!r}, the interpreter {expected!r}")
    return problems


__all__ = ["FORMATS", "PromptViews", "check_examples", "example_table", "prompt_blocks", "read_definitions"]
