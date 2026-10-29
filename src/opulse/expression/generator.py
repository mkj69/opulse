"""Random expression trees.

Shape control
    A tree has at most ``max_depth`` levels and at most ``leaf_budget`` leaves.
    Binary nodes split the budget between their children; a node whose budget
    is 1 can only be unary or an atom. A call-form node (an operator with k >= 3
    arguments) splits the budget into k positive parts, so it needs a budget of
    at least k. Its weight is ``type_weights["call"]`` (default: the binary weight).

Numbers
    Values are drawn as ``randint(lo, randint(lo, hi))``, which favours small
    numbers (as in the legacy generator).

Definition bodies
    :meth:`ExpressionGenerator.definition_bodies` builds the right-hand sides
    for a new operator at a target recursive layer ``L``: trees use operators of
    layer <= L, then one operator occurring in them is swapped for a randomly
    chosen operator of layer exactly ``L``. This guarantees the new operator
    depends on layer ``L``.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Literal

from opulse.config import ExpressionSettings
from opulse.core.operator import Operator
from opulse.core.registry import OperatorRegistry
from opulse.expression.nodes import (
    Call,
    Node,
    Number,
    Variable,
    iter_calls,
    map_operators,
)

AtomChoice = Literal["variable", "number", "mixed"]


@dataclass
class OperatorPool:
    binary: list[Operator] = field(default_factory=list)
    prefix: list[Operator] = field(default_factory=list)
    postfix: list[Operator] = field(default_factory=list)
    call: list[Operator] = field(default_factory=list)  # three or more arguments
    # Relative sampling weight per func_id; None samples uniformly within each kind.
    weights: dict[str, float] | None = None

    @classmethod
    def from_registry(cls, registry: OperatorRegistry, max_layer: int | None = None) -> OperatorPool:
        return cls(
            binary=registry.binary(max_layer=max_layer),
            prefix=registry.prefix(max_layer=max_layer),
            postfix=registry.postfix(max_layer=max_layer),
            call=registry.call_form(max_layer=max_layer),
        )

    def all(self) -> list[Operator]:
        return self.binary + self.prefix + self.postfix + self.call

    def with_frequency(self, spec: str | None, seed: int = 0) -> OperatorPool:
        """Sampling frequencies over the defined operators: ``uniform`` or ``zipf:ALPHA``.

        An operator is drawn in two stages: first its kind (binary, prefix or postfix, by
        ``expressions.type_weights``), then one operator of that kind. With ``zipf:ALPHA`` the
        second stage follows a long tail: the defined operators of each kind are ranked in a seeded
        random order and the one of rank r is drawn with weight proportional to r^-ALPHA, so a few
        concepts are frequent and most are rare. Base operations keep weight 1, and the defined
        operators' weights of each kind sum to their number, as under ``uniform``; so the expected
        mix of base and defined operators is unchanged and only how the draws spread over the
        defined operators changes. ``zipf:0`` is uniform.
        """
        if spec in (None, "", "uniform"):
            return OperatorPool(self.binary, self.prefix, self.postfix, self.call)
        kind, _, value = spec.partition(":")
        if kind != "zipf" or not value:
            raise ValueError(f"operator frequency must be 'uniform' or 'zipf:ALPHA', got {spec!r}")
        try:
            alpha = float(value)
        except ValueError:
            raise ValueError(f"the Zipf exponent must be a number, got {value!r}") from None
        if not math.isfinite(alpha) or alpha < 0:
            raise ValueError(f"the Zipf exponent must be a finite non-negative number, got {value!r}")
        if alpha and not any(len(group) > 1 for group in self.frequency_ranking(seed).values()):
            raise ValueError("operator frequency cannot change this world: it needs at least two defined "
                             "operators of the same kind")
        weights: dict[str, float] = {op.func_id: 1.0 for op in self.all()}
        for defined in self.frequency_ranking(seed).values():
            raw = [(rank + 1) ** -alpha for rank in range(len(defined))]  # rank 1 keeps weight 1: never all zero
            if any(weight == 0 for weight in raw):
                raise ValueError("Zipf exponent underflows a defined operator rank weight to zero")
            weights.update({fid: w * len(defined) / sum(raw) for fid, w in zip(defined, raw)})
        return OperatorPool(self.binary, self.prefix, self.postfix, self.call, weights)

    def frequency_ranking(self, seed: int = 0) -> dict[str, list[str]]:
        """The defined operators of each kind, most frequent first, as ``with_frequency`` ranks them."""
        rng = random.Random(seed)
        ranking = {}
        for name, ops in (
            ("binary", self.binary), ("prefix", self.prefix), ("postfix", self.postfix), ("call", self.call)
        ):
            defined = sorted(op.func_id for op in ops if op.definition is not None)
            rng.shuffle(defined)
            ranking[name] = defined
        return ranking


class NoCandidateError(RuntimeError):
    pass


class ExpressionGenerator:
    def __init__(self, settings: ExpressionSettings, rng: random.Random | None = None,
                 max_base: int = 16) -> None:
        self.settings = settings
        self.rng = rng or random.Random()
        self.max_base = max_base

    # ------------------------------------------------------------------ atoms
    def number(self, base: int | None = None) -> Number:
        lo, hi = self.settings.value_min, self.settings.value_max
        value = self.rng.randint(lo, self.rng.randint(lo, hi))
        return Number(value, base or self._numeral_base())

    def typed_tree(self, pool: OperatorPool, max_depth: int | None = None) -> Node:
        """Draw a closed, well-typed tree with a defined operator at its root."""
        from opulse.generation.typed import sample_value

        roots = [op for op in pool.all() if op.definition is not None]
        if not roots:
            raise NoCandidateError("a typed benchmark needs a defined operator")
        custom_type_weights = self.settings.type_weights != ExpressionSettings().type_weights
        root = self._choose_operator(roots, pool, by_type=custom_type_weights)
        max_depth = self.settings.max_depth if max_depth is None else max_depth

        def grow(kind: str, depth: int) -> Node:
            candidates = [op for op in pool.all() if op.result_type == kind]
            if depth <= 0 or not candidates:
                return self.number() if kind == "int" else Number(sample_value(kind, self.rng))
            if custom_type_weights:
                operator_mass = sum(self._operator_type_weight(op) for op in candidates)
                atom_mass = self.settings.type_weights["atom"]
                choose_atom = self.rng.random() * (operator_mass + atom_mass) < atom_mass
            else:
                choose_atom = self.rng.random() < 0.5
            if choose_atom:
                return self.number() if kind == "int" else Number(sample_value(kind, self.rng))
            chosen = self._choose_operator(candidates, pool, by_type=custom_type_weights)
            return Call(chosen, tuple(grow(t, depth - 1) for t in chosen.parameter_types))

        return Call(root, tuple(grow(t, max_depth - 1) for t in root.parameter_types))

    def _choose_operator(self, candidates: list[Operator], pool: OperatorPool, *, by_type: bool = False) -> Operator:
        # Keep the uniform path's RNG calls unchanged for existing seeded data.
        if pool.weights is None and not by_type:
            return self.rng.choice(candidates)
        return self.rng.choices(candidates, [(pool.weights[op.func_id] if pool.weights else 1.0)
                                             * (self._operator_type_weight(op) if by_type else 1.0)
                                             for op in candidates])[0]

    def _operator_type_weight(self, op: Operator) -> float:
        kind = ("call" if op.n_ary > 2 else "binary" if op.n_ary == 2 else
                "unary_prefix" if op.unary_position == "prefix" else "unary_postfix")
        return self._type_weight(kind)

    def atom(self, choice: AtomChoice, variables: tuple[str, ...]) -> Node:
        if choice == "mixed":
            weights = self.settings.atom_weights
            choice = self.rng.choices(["variable", "number"], [weights["variable"], weights["number"]])[0]
        if choice == "variable":
            return Variable(self.rng.choice(variables))
        return self.number()

    def _numeral_base(self) -> int:
        if self.settings.random_numeral_base:
            return self.rng.randint(2, self.max_base)
        return self.settings.numeral_base

    # ------------------------------------------------------------------ trees
    def tree(
        self,
        pool: OperatorPool,
        *,
        max_depth: int | None = None,
        leaf_budget: int | None = None,
        atoms: AtomChoice = "number",
        variables: tuple[str, ...] = (),
    ) -> Node:
        max_depth = self.settings.max_depth if max_depth is None else max_depth
        leaf_budget = leaf_budget or 2 ** max(max_depth - 1, 0)
        return self._grow(pool, 0, max_depth, leaf_budget, atoms, variables or self.settings.variables)

    def _leaf(self, pool, atoms, variables) -> Node:
        """An atom; a negative number is written as unary minus of its magnitude (spec section 7)."""
        node = self.atom(atoms, variables)
        if isinstance(node, Number) and node.value < 0:
            neg = next((op for op in pool.prefix if op.symbol == "-" and op.definition is None), None)
            if neg is None:
                raise ValueError("expressions.value_min < 0 needs the prefix negation operator '-'")
            return Call(neg, (Number(-node.value, node.base),))
        return node

    def _grow(self, pool, depth, max_depth, leaves, atoms, variables) -> Node:
        if depth >= max_depth:
            return self._leaf(pool, atoms, variables)
        kinds = {
            "binary": pool.binary if leaves > 1 else [],
            "unary_prefix": pool.prefix,
            "unary_postfix": pool.postfix,
            "call": [op for op in pool.call if op.n_ary <= leaves] if pool.call else [],
        }
        options = [kind for kind, ops in kinds.items() if ops] + ["atom"]
        weights = [self._type_weight(kind) for kind in options]
        kind = self.rng.choices(options, weights)[0] if any(weights) else "atom"
        if kind == "atom":
            return self._leaf(pool, atoms, variables)
        ops = kinds[kind]
        if pool.weights is None:
            op = self.rng.choice(ops)
        else:
            op = self.rng.choices(ops, [pool.weights[o.func_id] for o in ops])[0]
        if kind == "call":
            cuts = sorted(self.rng.sample(range(1, leaves), op.n_ary - 1))
            parts = [b - a for a, b in zip([0, *cuts], [*cuts, leaves])]
            args = tuple(self._grow(pool, depth + 1, max_depth, part, atoms, variables) for part in parts)
        elif kind == "binary":
            left = self.rng.randint(1, leaves - 1)
            args = (
                self._grow(pool, depth + 1, max_depth, left, atoms, variables),
                self._grow(pool, depth + 1, max_depth, leaves - left, atoms, variables),
            )
        else:
            args = (self._grow(pool, depth + 1, max_depth, leaves, atoms, variables),)
        return Call(op, args)

    def _type_weight(self, kind: str) -> float:
        weights = self.settings.type_weights
        if kind == "call":
            return weights.get("call", weights["binary"])
        return weights[kind]

    def single_operator_tree(self, operator: Operator, max_depth: int | None = None) -> Node:
        """A tree whose only operator is ``operator`` (for per-operator datasets)."""
        pool = OperatorPool(
            binary=[operator] if operator.n_ary == 2 else [],
            prefix=[operator] if operator.unary_position == "prefix" else [],
            postfix=[operator] if operator.unary_position == "postfix" else [],
            call=[operator] if operator.n_ary > 2 else [],
        )
        budget = None if operator.n_ary <= 2 else max(operator.n_ary, 2 ** max(
            (self.settings.max_depth if max_depth is None else max_depth) - 1, 0))
        while True:
            node = self.tree(pool, max_depth=max_depth, leaf_budget=budget)
            if isinstance(node, Call):
                return node

    # ------------------------------------------------------- definition bodies
    def definition_bodies(
        self,
        registry: OperatorRegistry,
        layer: int,
        count: int,
        variables: tuple[str, ...],
        max_attempts: int = 1000,
        max_depth: int | None = None,
    ) -> list[Node]:
        """``count`` right-hand sides that together use an operator of exactly ``layer``."""
        targets = registry.select(layer=layer)
        if not targets:
            raise NoCandidateError(f"no operator at layer {layer}")
        target = self.rng.choice(targets)
        pool = OperatorPool.from_registry(registry, max_layer=layer)
        depth_limit = self.settings.max_depth if max_depth is None else max_depth
        # A call-form operator needs one leaf per argument.
        max_leaves = max([2 ** max(depth_limit - 1, 0), *(op.n_ary for op in pool.call)])

        for _ in range(max_attempts):
            depth = self.rng.randint(1, depth_limit)
            trees = [
                self.tree(pool, max_depth=depth, leaf_budget=self.rng.randint(2, max(2, max_leaves)),
                          atoms="mixed", variables=variables)
                for _ in range(count)
            ]
            used = {call.operator.func_id: call.operator for tree in trees for call in iter_calls(tree)}
            # Swapping a prefix for a postfix operator is fine: position only affects rendering.
            same_arity = [op for op in used.values() if op.n_ary == target.n_ary]
            if not same_arity:
                continue
            replaced = self.rng.choice(same_arity)
            return [map_operators(tree, lambda op, replaced=replaced: target if op is replaced else op) for tree in trees]
        raise NoCandidateError(f"could not place a layer-{layer} operator after {max_attempts} attempts")
