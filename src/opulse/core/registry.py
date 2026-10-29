"""In-memory collection of operators with the lookups the generators need."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable, Iterator
from pathlib import Path

from opulse.core.operator import BINARY, POSTFIX, PREFIX, RECURSIVE, UNARY, Operator
from opulse.core.semantics import base_operation_name

logger = logging.getLogger(__name__)

# Calls to other operators inside generated code look like ``op_<func_id>(``.
# func ids are alphanumeric, so ``op_count_<id>(`` never matches.
_CALL_PATTERN = re.compile(r"\bop_([A-Za-z0-9]+)\(")

OperatorKey = tuple[str, int, "str | None"]


def _key(symbol: str, n_ary: int, unary_position: str | None) -> OperatorKey:
    return (symbol, n_ary, unary_position if n_ary == UNARY else None)


class OperatorRegistry:
    """Operators indexed by ``func_id`` and by ``(symbol, arity, position)``."""

    def __init__(self, operators: Iterable[Operator] = ()) -> None:
        self._by_id: dict[str, Operator] = {}
        self._by_key: dict[OperatorKey, Operator] = {}
        # select() results are reused until the registry changes: generation asks for the same
        # pools many times per accepted operator, and rebuilding them is O(n).
        self._select_cache: dict[tuple, list[Operator]] = {}
        for operator in operators:
            self.add(operator)

    # ---------------------------------------------------------------- loading
    @classmethod
    def from_jsonl(cls, path: str | Path) -> OperatorRegistry:
        registry = cls()
        with open(path, encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                row = json.loads(line)
                from opulse.core.presets import register_for_symbol

                register_for_symbol(row.get("symbol"), row.get("parameter_types"),
                                    row.get("primitive_name"), row.get("n_ary"),
                                    row.get("unary_position"), row.get("result_type", "int"))
                operator = Operator.from_dict(row)
                # Numeral-base markers (``is_base``) are symbols only and carry no code; base
                # operations are bound from the semantics (opulse.core.semantics), not from code.
                base = operator.definition is None and base_operation_name(
                    operator.symbol, operator.n_ary, operator.unary_position) is not None
                if not operator.has_code and operator.is_base is None and not base:
                    logger.warning("skip %s line %d: missing compute/count code", path, line_no)
                    continue
                registry.add(operator)
        logger.info("loaded %d operators from %s", len(registry), path)
        return registry

    def to_jsonl(self, path: str | Path) -> None:
        with open(path, "w", encoding="utf-8") as handle:
            handle.writelines(operator.to_json() + "\n" for operator in self)

    # --------------------------------------------------------------- mutation
    def add(self, operator: Operator) -> None:
        if operator.func_id in self._by_id:
            raise ValueError(f"duplicate func_id {operator.func_id}")
        key = _key(operator.symbol, operator.n_ary, operator.unary_position)
        if key in self._by_key:
            raise ValueError(f"duplicate operator {key}")
        self._by_id[operator.func_id] = operator
        self._by_key[key] = operator
        self._select_cache.clear()

    # ---------------------------------------------------------------- lookups
    def __len__(self) -> int:
        return len(self._by_id)

    def __iter__(self) -> Iterator[Operator]:
        return iter(self._by_id.values())

    def __contains__(self, func_id: object) -> bool:
        return func_id in self._by_id

    def get(self, func_id: str) -> Operator:
        try:
            return self._by_id[func_id]
        except KeyError:
            raise KeyError(f"unknown operator func_id {func_id!r}") from None

    def find(self, symbol: str, n_ary: int, unary_position: str | None = None) -> Operator | None:
        return self._by_key.get(_key(symbol, n_ary, unary_position))

    def base_marker(self, base: int) -> Operator | None:
        """The prefix symbol that marks a numeral written in ``base``."""
        for operator in self:
            if operator.is_base == base:
                return operator
        return None

    def symbols(self) -> set[str]:
        return {operator.symbol for operator in self}

    def select(
        self,
        *,
        n_ary: int | None = None,
        unary_position: str | None = None,
        max_layer: int | None = None,
        layer: int | None = None,
        include_base: bool = False,
        min_n_ary: int | None = None,
    ) -> list[Operator]:
        """Filter operators. ``include_base=False`` drops numeral-base operators.

        The returned list is shared by later calls with the same filters; do not modify it.
        """
        cache_key = (n_ary, unary_position, max_layer, layer, include_base, min_n_ary)
        cached = self._select_cache.get(cache_key)
        if cached is not None:
            return cached
        selected = []
        for operator in self:
            if n_ary is not None and operator.n_ary != n_ary:
                continue
            if min_n_ary is not None and operator.n_ary < min_n_ary:
                continue
            if unary_position is not None and operator.unary_position != unary_position:
                continue
            operator_layer = operator.recursive_layer or 0
            if max_layer is not None and operator_layer > max_layer:
                continue
            if layer is not None and operator_layer != layer:
                continue
            if not include_base and operator.is_base is not None:
                continue
            selected.append(operator)
        self._select_cache[cache_key] = selected
        return selected

    def binary(self, **filters) -> list[Operator]:
        return self.select(n_ary=BINARY, **filters)

    def prefix(self, **filters) -> list[Operator]:
        return self.select(n_ary=UNARY, unary_position=PREFIX, **filters)

    def postfix(self, **filters) -> list[Operator]:
        return self.select(n_ary=UNARY, unary_position=POSTFIX, **filters)

    def call_form(self, **filters) -> list[Operator]:
        """Operators with three or more arguments (written ``symbol(a, b, c)``)."""
        return self.select(min_n_ary=BINARY + 1, **filters)

    # ------------------------------------------------------ derived properties
    def dependencies_of(self, compute_source: str, own_func_id: str | None = None) -> list[str]:
        """func ids called by ``compute_source`` (sorted, without the operator itself)."""
        called = set(_CALL_PATTERN.findall(compute_source))
        called.discard(own_func_id)
        return sorted(called)

    def recursive_layer_of(self, operator: Operator) -> int:
        """0 without dependencies; recursion adds one layer on top of its callees."""
        if not operator.dependencies:
            return 0
        deepest = max(self.get(dep).recursive_layer or 0 for dep in operator.dependencies)
        return deepest + 1 if operator.definition_type == RECURSIVE else deepest

    def topological_order(self) -> list[Operator]:
        """Operators sorted so that every operator follows its dependencies."""
        ordered: list[Operator] = []
        visiting: set[str] = set()
        done: set[str] = set()

        def visit(func_id: str) -> None:
            if func_id in done:
                return
            if func_id in visiting:
                raise ValueError(f"dependency cycle through {func_id}")
            visiting.add(func_id)
            for dep in self.get(func_id).dependencies:
                visit(dep)
            visiting.discard(func_id)
            done.add(func_id)
            ordered.append(self.get(func_id))

        for func_id in self._by_id:
            visit(func_id)
        return ordered
