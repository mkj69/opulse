"""Several checkable views of one concept, all computed from one parsed definition.

    from opulse.language.views import Views

    views = Views(registry, settings)
    views.render(op, "prose", lang="en", seed=3)   # controlled English
    views.parse("prose", text)                       # back to the definition
    views.check_code(op)                             # [] when the code agrees with the interpreter

Views: ``symbolic`` (definition text), ``formula`` (LaTeX), ``code`` (Python), ``prose``
(controlled English or Chinese), ``examples`` (input/output table) and ``summary`` (proved
facts). The first four are definitions and parse back to the same syntax tree; ``examples``
and ``summary`` state values and facts established by the interpreter and z3.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from opulse.config import Settings
from opulse.core.operator import Operator
from opulse.core.registry import OperatorRegistry
from opulse.core.semantics import NAN
from opulse.definition import ast
from opulse.definition.parser import DefinitionParser
from opulse.expression.numerals import NumeralWriter
from opulse.language.ir import Concept, OperatorRef, normalize, signatures
from opulse.language.views import code as code_view
from opulse.language.views import latex
from opulse.language.views.controlled import ControlledLanguage, ProseError
from opulse.language.views.examples import ExampleTable, examples
from opulse.language.views.summary import Summary, summarize
from opulse.verify import Oracle
from opulse.verify.differential import literals

VIEWS = ("symbolic", "formula", "code", "prose", "examples", "summary")
DEFINITION_VIEWS = ("symbolic", "formula", "code", "prose")


@dataclass
class RoundTrip:
    view: str
    text: str
    same_tree: bool
    problems: list[str]

    @property
    def ok(self) -> bool:
        return not self.problems


class _TextOracle(Oracle):
    """The reference oracle reading operators from their definition text alone: an operator
    with a definition needs no compiled code to be described."""

    def _lookup(self, node: ast.Apply) -> Operator:
        found = self.registry.find(node.symbol, node.n_ary, node.unary_position)
        if found is not None and found.definition is not None:
            return found
        return super()._lookup(node)


class Views:
    """Views of the defined operators of ``registry`` under ``settings`` (notation, numerals,
    semantics)."""

    def __init__(self, registry: OperatorRegistry, settings: Settings | None = None) -> None:
        settings = settings or Settings()
        self.registry = registry
        self.settings = settings
        self.symbols = settings.symbols
        self.semantics = settings.semantics.build()
        self.oracle = _TextOracle(registry, self.symbols, self.semantics)
        self.parser = DefinitionParser(self.symbols, registry, settings.numerals.digits)
        self.oracle.parser = self.parser  # definitions are read with the configured digits
        self.numerals = NumeralWriter(registry, settings.numerals.digits, nan=self.symbols.nan)
        self.table = signatures(registry)
        self._languages: dict[str, ControlledLanguage] = {}

    # ---------------------------------------------------------- the IR
    def definition(self, operator: Operator) -> ast.Definition:
        if operator.definition is None:
            raise ValueError(f"{operator.symbol!r} is an atom; it has a rule, not a definition")
        return self.oracle._definition_of(operator)

    def concept(self, operator: Operator) -> Concept:
        return Concept.of(self.definition(operator))

    def language(self, lang: str) -> ControlledLanguage:
        if lang not in self._languages:
            self._languages[lang] = ControlledLanguage(lang, self.symbols, self.table)
        return self._languages[lang]

    # ---------------------------------------------------------- views
    def symbolic(self, operator: Operator) -> str:
        return ast.render_definition(self.definition(operator), self.symbols, self.numerals.write)

    def formula(self, operator: Operator) -> str:
        return latex.render(self.definition(operator), self.symbols)

    def code(self, operator: Operator) -> str:
        return code_view.render(self.definition(operator), self.symbols, self.table)

    def prose(self, operator: Operator, lang: str = "en", seed: int = 0) -> str:
        return self.language(lang).render(self.definition(operator), seed)

    def examples(self, operator: Operator, seed: int = 0) -> ExampleTable:
        return examples(operator, self.definition(operator), self.oracle, self.symbols, seed=seed)

    def summary(self, operator: Operator, timeout_ms: int = 3000, properties: bool = True) -> Summary:
        return summarize(operator, self.definition(operator), self.oracle, self.symbols, timeout_ms, properties)

    def render(self, operator: Operator, view: str, lang: str = "en", seed: int = 0) -> str:
        if view == "symbolic":
            return self.symbolic(operator)
        if view == "formula":
            return self.formula(operator)
        if view == "code":
            return self.code(operator)
        if view == "prose":
            return self.prose(operator, lang, seed)
        if view == "examples":
            return self.examples(operator, seed).text(self.symbols)
        if view == "summary":
            return self.summary(operator).text(self.symbols, lang)
        raise ValueError(f"view must be one of {VIEWS}")

    # ---------------------------------------------------------- parse back
    def parse(self, view: str, text: str, lang: str = "en") -> ast.Definition:
        """The definition a ``symbolic``, ``formula``, ``code`` or ``prose`` text states."""
        if view == "symbolic":
            return self.parser.parse(text)
        if view == "formula":
            return latex.parse(text, self.symbols)
        if view == "code":
            names = {code_view.function_name(OperatorRef.of(op), self.table): OperatorRef.of(op)
                     for op in self.registry if op.definition is not None}
            found = code_view.parse(text, self.symbols, names)
            if len(found) != 1:
                raise code_view.CodeError("expected exactly one function")
            return found[0]
        if view == "prose":
            return self.language(lang).parse(text)
        raise ValueError(f"only {DEFINITION_VIEWS} parse back to a definition")

    def round_trip(self, operator: Operator, view: str, lang: str = "en", seed: int = 0) -> RoundTrip:
        """Render ``view``, parse it back and compare with the definition; for ``code`` also run it."""
        original = self.definition(operator)
        text = self.render(operator, view, lang, seed)
        problems = []
        try:
            parsed = self.parse(view, text, lang)
            same = normalize(parsed) == normalize(original)
        except (ValueError, ProseError) as exc:
            return RoundTrip(view, text, False, [f"does not parse: {exc}"])
        if not same:
            problems.append("parses to a different definition")
        if view == "code":
            problems += self.check_code(operator, text)
        return RoundTrip(view, text, same, problems)

    def check_code(self, operator: Operator, text: str | None = None, seed: int = 0,
                   count: int = 200) -> list[str]:
        """Run the code view and compare it with the interpreter on boundary and random inputs."""
        text = text or self.code(operator)
        definition = self.definition(operator)
        helpers = {}
        for ref in Concept.of(definition).calls():
            callee = self.oracle._resolve(ref.apply(tuple(ast.Var("a") for _ in range(ref.arity))))
            if callee.definition is not None:
                helpers[code_view.function_name(ref, self.table)] = (
                    lambda *args, callee=callee: self.oracle.evaluate(callee, args).value)
        namespace = code_view.run(text, self.semantics, helpers)
        function = namespace[code_view.function_name(OperatorRef.of(operator), self.table)]
        rng = random.Random(seed)
        points = code_view.sample_inputs(operator.n_ary, self.semantics.bound, literals(definition), rng, count)
        points += [tuple(NAN if i == j else 0 for i in range(operator.n_ary)) for j in range(operator.n_ary)]
        problems = []
        for point in points:
            expected = self.oracle.evaluate(operator, point).value
            got = function(*point)
            if not ((got is NAN and expected is NAN) or (got is not NAN and expected is not NAN and got == expected)):
                problems.append(f"at {point}: code gives {got!r}, interpreter {expected!r}")
                if len(problems) >= 5:
                    break
        return problems


__all__ = ["DEFINITION_VIEWS", "VIEWS", "ExampleTable", "RoundTrip", "Summary", "Views"]
