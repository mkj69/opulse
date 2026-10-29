"""The reference oracle over a registry: parse each definition once, interpret on demand."""

from __future__ import annotations

from opulse.config import Symbols
from opulse.core.operator import Operator
from opulse.core.registry import OperatorRegistry
from opulse.core.semantics import Semantics
from opulse.definition import ast
from opulse.definition.codegen import registry_resolver
from opulse.definition.interpreter import ReferenceInterpreter, Result
from opulse.definition.parser import DefinitionParser


class Oracle:
    """Evaluates operators of ``registry`` by their definition text only."""

    def __init__(self, registry: OperatorRegistry, symbols: Symbols | None = None,
                 semantics: Semantics | None = None) -> None:
        symbols = symbols or Symbols()
        semantics = semantics or Semantics()
        self.registry = registry
        self.parser = DefinitionParser(symbols, registry)
        self.semantics = semantics
        self._parsed: dict[str, ast.Definition] = {}
        self._extra: dict[str, Operator] = {}
        self.interpreter = ReferenceInterpreter(self._resolve, self._definition_of, semantics)
        self._resolved: dict[tuple, Operator] = {}

    def include(self, operator: Operator) -> None:
        """Make a not-yet-registered candidate visible (for acceptance checks)."""
        self._extra[operator.func_id] = operator
        self._parsed.pop(operator.func_id, None)
        self._resolved.clear()
        self.interpreter.forget(operator.func_id)

    def register(self, operator: Operator) -> None:
        """The registry gained ``operator``: make its symbol known (O(1))."""
        self.parser.add(operator)
        self._resolved.clear()

    def refresh(self) -> None:
        """Re-read operator roles after the registry grew."""
        self.parser.refresh()
        self._resolved.clear()

    def forget(self, operator: Operator) -> None:
        self._extra.pop(operator.func_id, None)
        self._parsed.pop(operator.func_id, None)
        self._resolved.clear()
        self.interpreter.forget(operator.func_id)

    def evaluate(self, operator: Operator, args) -> Result:
        return self.interpreter.evaluate(operator, tuple(args))

    def evaluate_expr(self, node: ast.Expr, env: dict) -> Result:
        return self.interpreter.evaluate_expr(node, env)

    # ---------------------------------------------------------------- internals
    def _resolve(self, node: ast.Apply) -> Operator:
        key = (node.symbol, node.n_ary, node.unary_position)
        found = self._resolved.get(key)
        if found is None:
            found = self._resolved[key] = self._lookup(node)
        return found

    def _lookup(self, node: ast.Apply) -> Operator:
        for candidate in self._extra.values():
            if (candidate.symbol, candidate.n_ary, candidate.unary_position) == \
                    (node.symbol, node.n_ary, node.unary_position):
                return candidate
        return registry_resolver(self.registry)(node)

    def _definition_of(self, operator: Operator) -> ast.Definition:
        parsed = self._parsed.get(operator.func_id)
        if parsed is None:
            parsed = self.parser.parse(operator.definition)
            if operator.result_type != "int" or any(t != "int" for t in operator.parameter_types):
                from opulse.definition.typecheck import check_definition

                check_definition(parsed, operator, registry_resolver(self.registry, operator))
            self._parsed[operator.func_id] = parsed
        return parsed
