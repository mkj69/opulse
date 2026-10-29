"""Generate operators one at a time and grow a registry layer by layer.

``OperatorFactory.generate(kind, layer)`` loops until a candidate passes:

1. draw a symbol and shape;
2. build a draft (simple / branch / recursive) targeting ``layer``;
3. compile the definition to compute/count code (one code path for all kinds);
4. compute dependencies and the recursive layer, reject if not ``layer``;
5. run the acceptance checks (see :mod:`opulse.generation.checks`); the
   decisive one compiles nothing new: it requires the generated code to agree
   with the reference interpreter on boundary and random inputs, value and
   both counts (docs/reference/semantics.md section 9).

``build_layers`` fills a registry with a requested number of operators per
layer. Inside each layer recursive operators are generated first, because
simple and branch operators at layer L need some layer-L operator to exist.
"""

from __future__ import annotations

import logging
import random
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field

from opulse.config import Settings
from opulse.core.ids import new_func_id
from opulse.core.operator import BRANCH, RECURSIVE, SIMPLE, Operator
from opulse.core.registry import OperatorRegistry
from opulse.core.semantics import base_operation_name
from opulse.definition import ast
from opulse.definition.ast import render_definition
from opulse.definition.codegen import (
    UnknownOperatorError,
    compile_definition,
    registry_resolver,
)
from opulse.definition.complexity import definition_complexity
from opulse.expression.generator import ExpressionGenerator, NoCandidateError
from opulse.generation import checks
from opulse.generation.drafts import Draft, branch_draft, lhs, simple_draft
from opulse.generation.recursive import (
    primitive_draft,
    random_primitive_spec,
    random_spec,
    recursive_draft,
)
from opulse.generation.symbols import ShapeIndexFactory, SymbolFactory, draw_shape
from opulse.runtime import PythonRuntime
from opulse.verify import Oracle

logger = logging.getLogger(__name__)


class GenerationError(RuntimeError):
    pass


@dataclass
class GenerationStats:
    accepted: Counter = field(default_factory=Counter)  # by definition type
    rejected: Counter = field(default_factory=Counter)  # by reason

    def summary(self) -> dict:
        return {"accepted": dict(self.accepted), "rejected": dict(self.rejected.most_common())}


class OperatorFactory:
    def __init__(self, settings: Settings, registry: OperatorRegistry, rng: random.Random | None = None,
                 check_variety: bool = False, max_attempts: int = 2000) -> None:
        if settings.operators.definedness:
            from opulse.core.primitives import enable_definedness

            enable_definedness(registry)
        self.settings = settings
        self.registry = registry
        self.rng = rng or random.Random()
        naming = settings.operators.naming
        if naming not in ("shape_index", "legacy"):
            raise ValueError(f"unknown operators.naming {naming!r}")
        self.symbols = (ShapeIndexFactory(settings.operators, self.rng) if naming == "shape_index"
                        else SymbolFactory(settings.operators, self.rng))
        self.symbols.reserve(registry.symbols())
        if settings.symbols.nan and settings.symbols.nan[0] in self.symbols.alphabet:
            self.symbols.reserve(settings.symbols.nan)
        self.expressions = ExpressionGenerator(settings.expressions, self.rng,
                                               max_base=settings.numerals.max_base)
        self.semantics = settings.semantics.build()
        self.runtime = PythonRuntime(registry, self.semantics)
        self.oracle = Oracle(registry, settings.symbols, self.semantics)
        self.encoder = _encoder(self.oracle) if (settings.operators.reject_dead_branches or
                                                 settings.operators.reject_degenerate) else None
        _check_switches(settings)
        if settings.operators.reject_dead_branches or settings.operators.reject_degenerate:
            from opulse.solver import isolated

            isolated.restart()  # z3 answers then depend only on this run, as in a fresh process
        self.condition_atoms = _condition_atoms(settings, registry)
        _check_recursion_operations(settings, registry)
        self.check_variety = check_variety
        self.max_attempts = max_attempts
        self.stats = GenerationStats()
        # Optional observer of every rejected candidate: called with (operator or None, reason,
        # kind, layer); the operator is None when the draft could not be built or compiled.
        self.on_reject: Callable[[Operator | None, str, str, int], None] | None = None
        self._fingerprints = {checks.body_fingerprint(op) for op in registry if op.has_code}
        self._has_typed_values = any(op.result_type != "int" or any(t != "int" for t in op.parameter_types)
                                     for op in registry)
        # Opt-in behavioural deduplication and interest-guided selection (settings.interest).
        self.scorer = None
        if settings.interest.enabled:
            from opulse.generation.interest import Scorer

            self.scorer = Scorer(settings.interest, self.runtime.compute)
            for op in registry:
                self.scorer.add(op)

    # ------------------------------------------------------------------ public
    def generate(self, kind: str, layer: int) -> Operator:
        """Return one accepted operator (not yet added to the registry)."""
        if self.scorer is not None and self.settings.interest.selection != "off":
            return self._select(kind, layer)
        operator = self._generate(kind, layer)
        if self.scorer is not None:
            operator.interest = self.scorer.score(operator)
        return operator

    def _select(self, kind: str, layer: int) -> Operator:
        """Draw ``interest.pool`` accepted candidates and keep one by its interest score:
        the best (``best``) or one drawn with weight exp(score / temperature) (``sample``)."""
        import math

        interest = self.settings.interest
        pool: list[Operator] = []
        for _ in range(interest.pool):
            try:
                candidate = self._generate(kind, layer)
            except GenerationError:
                if pool:
                    break
                raise
            candidate.interest = self.scorer.score(candidate)
            # Out of the oracle's view, so the next candidate (possibly with the same symbol)
            # resolves its own name to itself; ``add`` registers the chosen one.
            self.oracle.forget(candidate)
            pool.append(candidate)
        scores = [op.interest["score"] if op.interest else 0.0 for op in pool]
        if interest.selection == "best":
            index = max(range(len(pool)), key=lambda i: (scores[i], -i))
        else:
            top = max(scores)
            weights = [math.exp((s - top) / interest.temperature) for s in scores]
            index = self.rng.choices(range(len(pool)), weights=weights)[0]
        for i, other in enumerate(pool):
            if i != index:
                self.runtime.unload(other)
                self.stats.accepted[kind] -= 1
                self.stats.rejected["not selected by interest"] += 1
        return pool[index]

    def _generate(self, kind: str, layer: int) -> Operator:
        for _ in range(self.max_attempts):
            try:
                draft = self._draft(kind, layer)
                operator = self._compile(draft)
            except (NoCandidateError, UnknownOperatorError) as exc:
                self.stats.rejected[f"draft: {type(exc).__name__}"] += 1
                if self.on_reject:
                    self.on_reject(None, f"draft: {type(exc).__name__}", kind, layer)
                continue
            reason = self._reject_reason(draft, operator, layer)
            if reason is None:
                self.stats.accepted[kind] += 1
                return operator
            self.runtime.unload(operator)
            self.oracle.forget(operator)
            self.stats.rejected[reason] += 1
            if self.on_reject:
                self.on_reject(operator, reason, kind, layer)
        raise GenerationError(f"no acceptable {kind} at layer {layer} after {self.max_attempts} attempts")

    def add(self, operator: Operator) -> None:
        operator.id = len(self.registry) + 1
        self.oracle.forget(operator)
        self.registry.add(operator)
        self.runtime.load(operator)
        self.oracle.register(operator)
        self._fingerprints.add(checks.body_fingerprint(operator))
        self.symbols.reserve(operator.symbol)
        if self.scorer is not None:
            self.scorer.add(operator)
        self._has_typed_values |= operator.result_type != "int" or any(
            t != "int" for t in operator.parameter_types)

    # ---------------------------------------------------------------- drafting
    def _draft(self, kind: str, layer: int) -> Draft:
        symbol = self.symbols.new_symbol()
        if kind == RECURSIVE and self._typed_world():
            from opulse.generation.typed import recursive_draft as typed_recursive_draft

            try:
                return typed_recursive_draft(symbol, self.registry, self.settings.symbols,
                                             self.rng, self.settings.recursion.direct_bound, layer)
            except ValueError as exc:
                raise NoCandidateError(str(exc)) from exc
        if kind != RECURSIVE and self._typed_world():
            from opulse.generation.typed import draft as typed_draft

            targets = [op for op in self.registry.select(layer=layer)
                       if op.result_type != "int" or any(t != "int" for t in op.parameter_types)]
            if not targets:
                raise NoCandidateError("no typed target at this layer")
            try:
                return typed_draft(symbol, self.rng.choice(targets), self.registry,
                                   self.settings.symbols, self.rng, kind)
            except ValueError as exc:
                raise NoCandidateError(str(exc)) from exc
        n_ary, position = self.symbols.new_shape()
        cap = self.settings.operators.max_arity
        if cap is not None and n_ary > cap:
            n_ary, position = draw_shape({k: w for k, w in self.settings.operators.arity_weights.items()
                                          if k <= cap}, self.rng)
        names = self.settings.symbols.operands(n_ary)

        if kind == RECURSIVE:
            if layer < 1:
                raise ValueError("recursive operators start at layer 1")
            callees = self.registry.select(layer=layer - 1)
            if not callees:
                raise NoCandidateError(f"no callee at layer {layer - 1}")
            callee = self.rng.choice(callees)
            styles = self.settings.recursion.styles
            style = self.rng.choice(styles) if styles is not None else self.settings.recursion.style
            if style == "primitive":
                spec = random_primitive_spec(symbol, n_ary, position, callee, self.registry, layer,
                                             self.settings.recursion, self.settings.symbols,
                                             self.expressions, self.rng)
                return primitive_draft(spec, self.settings.symbols, registry_resolver(self.registry))
            spec = random_spec(symbol, n_ary, position, callee,
                               self.settings.recursion, self.settings.symbols, self.rng, style)
            return recursive_draft(spec, self.settings.symbols)

        depth = self.settings.operators.max_substitution_depth
        if kind == SIMPLE:
            if self.settings.recursion.search_enabled and self.rng.random() < 0.2:
                (body,) = self.expressions.definition_bodies(self.registry, layer, 1, names, max_depth=depth)
                from opulse.expression.nodes import to_ast

                candidate = to_ast(body)
                bound = self.settings.recursion.search_bound
                available = {base_operation_name(op.symbol, op.n_ary, op.unary_position)
                             for op in self.registry if op.definition is None}
                if "mod" in available:
                    candidate = ast.Apply("%", (candidate, ast.Num(bound + 1)))
                search = ast.Search("i", bound, ast.Compare(ast.Var("i"), "==", candidate))
                definition = ast.Definition(lhs(symbol, n_ary, position, self.settings.symbols),
                                            (ast.Branch(search),))
                return Draft(symbol, n_ary, position, definition, SIMPLE)
            (body,) = self.expressions.definition_bodies(self.registry, layer, 1, names, max_depth=depth)
            return simple_draft(symbol, n_ary, position, body, self.settings.symbols)

        if kind == BRANCH:
            count = self.rng.randint(2, self.settings.operators.max_if_branches)
            bodies = self.expressions.definition_bodies(self.registry, layer, count, names, max_depth=depth)
            atom = self.rng.choice(self.condition_atoms) if self.condition_atoms else None
            defined = self.registry.find("defined", 1, "prefix")
            division = self.registry.find("/", 2)
            try:
                return branch_draft(symbol, n_ary, position, bodies, self.settings.operators,
                                    self.settings.symbols, self.rng, defined.symbol if defined else None,
                                    division.symbol if division else None, condition_atom=atom)
            except ValueError as exc:
                raise NoCandidateError(str(exc)) from exc

        raise ValueError(f"unknown definition type {kind!r}")

    def _typed_world(self) -> bool:
        return self._has_typed_values

    def _compile(self, draft: Draft) -> Operator:
        operator = Operator(
            func_id=new_func_id(self.rng),
            symbol=draft.symbol,
            n_ary=draft.n_ary,
            unary_position=draft.unary_position,
            definition=render_definition(draft.definition, self.settings.symbols,
                                         layout=self.settings.operators.definition_layout,
                                         min_length=self.settings.operators.piecewise_min_length),
            definition_type=draft.definition_type,
            parameter_types=draft.parameter_types,
            result_type=draft.result_type,
        )
        resolve = registry_resolver(self.registry, operator)
        from opulse.definition.typecheck import check_definition

        check_definition(draft.definition, operator, resolve)
        code = compile_definition(draft.definition, operator.func_id, resolve,
                                  operator.parameter_types if draft.parameter_types is not None else None,
                                  operator.result_type)
        operator.op_compute_func, operator.op_count_func = code.compute, code.count
        operator.dependencies = list(code.dependencies)
        operator.recursive_layer = self.registry.recursive_layer_of(operator)
        if draft.complexity is not None:
            operator.max_path_depth, operator.max_edge_count = draft.complexity
        else:
            metrics = definition_complexity(draft.definition, resolve)
            operator.max_path_depth, operator.max_edge_count = metrics.max_path_depth, metrics.max_edge_count
        self.runtime.load(operator)
        return operator

    # ------------------------------------------------------------------ checks
    def _reject_reason(self, draft: Draft, operator: Operator, layer: int,
                       sample_value_fn=None) -> str | None:
        reason = self._check_reason(draft, operator, layer, sample_value_fn)
        if reason is None and self.scorer is not None and self.settings.interest.dedup:
            duplicate = self.scorer.duplicate(operator)
            if duplicate is not None:
                reason = duplicate[0]
        return reason

    def _check_reason(self, draft: Draft, operator: Operator, layer: int,
                      sample_value_fn=None) -> str | None:
        if operator.recursive_layer != layer:
            return "wrong layer"
        for check in (checks.uses_all_parameters, checks.not_a_renaming, checks.distinct_branches):
            reason = check(draft)
            if reason:
                return reason
        if checks.body_fingerprint(operator) in self._fingerprints:
            return "duplicate body"
        if draft.parameter_types is not None:
            from opulse.generation.typed import defined_somewhere, sample_value

            sample = sample_value_fn or sample_value
            self.oracle.include(operator)
            for _ in range(12):
                args = tuple(sample(t, self.rng, self.registry) for t in operator.parameter_types)
                expected = self.oracle.evaluate(operator, args)
                actual = self.runtime.evaluate(operator)(*args)
                if actual != (expected.value, expected.base_ops, expected.calls):
                    return "compiled code disagrees with reference"
            return defined_somewhere(operator, self.runtime, self.registry)
        self.oracle.include(operator)
        reason = checks.agrees_with_reference(operator, self.runtime, self.oracle, self.rng)
        if reason is None:
            reason = checks.defined_somewhere(operator, self.runtime, self.rng)
        operators = self.settings.operators
        if reason is None and operators.min_defined_share > 0 and \
                not checks.intentionally_partial(draft, draft.recursion_style or self.settings.recursion.style):
            expressions = self.settings.expressions
            reason = checks.defined_share(operator, self.runtime, self.rng, operators.min_defined_share,
                                          (expressions.value_min, expressions.value_max))
        if reason is None and operators.reject_degenerate:
            try:
                reason = checks.degenerate_subexpression(draft, operator, self.oracle, self.encoder,
                                                         operators.degenerate_budget, operators.safety_timeout_ms)
            except TimeoutError:
                return "solver safety timeout in degenerate check"
        if (reason is None and operators.reject_dead_branches and self.encoder is not None
                and draft.definition_type in (BRANCH, RECURSIVE)):
            from opulse.solver.static import dead_branch_reason

            try:
                reason = dead_branch_reason(operator, self.encoder, timeout_ms=operators.safety_timeout_ms,
                                            budget=operators.dead_branch_budget,
                                            check_undefined=self.settings.operators.undefined_branch_check)
            except TimeoutError:
                return "solver safety timeout in dead branch check"
        if reason is None and self.check_variety:
            reason = checks.varied_outputs(operator, self.runtime, self.rng)
        return reason


# Encoding nodes for proving a subexpression degenerate. Degenerate subexpressions are small
# (a - a, a % a); deep suspects stay undecided and are accepted.

# Base operations each recursion style writes into its template (generation.recursive).
# ``primitive`` uses ``sub``/``add``, or ``pred``/``succ`` when those are missing.
RECURSION_OPERATIONS = {"bounded_mod": ("mod", "sub", "add"), "direct": ("sub", "add"), "peano": ("pred", "succ")}
BOUNDED_STYLES = ("direct", "peano", "bits", "primitive")  # recursion limited by recursion.direct_bound


def _check_switches(settings: Settings) -> None:
    operators, recursion = settings.operators, settings.recursion
    if operators.max_arity is not None:
        if type(operators.max_arity) is not int or operators.max_arity < 1:
            raise ValueError("operators.max_arity must be a positive integer")
        if not any(w > 0 for k, w in operators.arity_weights.items() if k <= operators.max_arity):
            raise ValueError("operators.max_arity leaves no arity with a positive weight in operators.arity_weights")
    if operators.max_if_branches < 2:
        raise ValueError("operators.max_if_branches must be at least 2")
    if operators.max_substitution_depth is not None and operators.max_substitution_depth < 1:
        raise ValueError("operators.max_substitution_depth must be at least 1")
    if operators.max_condition_comparisons is not None and operators.max_condition_comparisons < 1:
        raise ValueError("operators.max_condition_comparisons must be at least 1")
    styles = (*RECURSION_OPERATIONS, "bits", "primitive")
    if recursion.style not in styles:
        raise ValueError("recursion.style must be bounded_mod, direct, peano, bits or primitive")
    if recursion.styles is not None and (not recursion.styles or
                                         any(style not in styles for style in recursion.styles)):
        raise ValueError("recursion.styles must contain bounded_mod, direct, peano, bits or primitive")
    if recursion.max_recursive_calls not in (1, 2):
        raise ValueError("recursion.max_recursive_calls must be 1 or 2")


def _condition_atoms(settings: Settings, registry: OperatorRegistry) -> tuple[Operator, ...]:
    if not settings.operators.allow_branches:
        return ()
    requested = settings.operators.condition_atoms
    if not requested:
        return ()
    atoms = {base_operation_name(op.symbol, op.n_ary, op.unary_position): op
             for op in registry if op.definition is None}
    missing = sorted(set(requested) - atoms.keys())
    if missing:
        raise ValueError(f"operators.condition_atoms need base operations {missing} in the starting set")
    if any(atoms[name].n_ary > 2 for name in requested):
        raise ValueError("operators.condition_atoms takes unary or binary atoms")
    return tuple(atoms[name] for name in requested)


def _check_recursion_operations(settings: Settings, registry: OperatorRegistry) -> None:
    """Fail early when the starting set lacks what the recursion template is written with,
    or the operator shapes need more parameter names than ``symbols`` provides."""
    cap = settings.operators.max_arity
    largest = max((k for k, w in settings.operators.arity_weights.items()
                   if w > 0 and (cap is None or k <= cap)), default=1)
    settings.symbols.operands(largest)  # raises when the names run out
    if settings.recursion.search_enabled:
        if not 0 <= settings.recursion.search_bound <= 32:
            raise ValueError("recursion.search_bound must be between 0 and 32")
        if "i" in settings.symbols.operands(largest):
            raise ValueError("search index i must differ from operator parameters")
    if not settings.recursion.enabled:
        return
    available = {base_operation_name(op.symbol, op.n_ary, op.unary_position)
                 for op in registry if op.definition is None}
    styles = settings.recursion.styles or (settings.recursion.style,)
    if "primitive" in styles and not ({"sub", "add"} <= available or {"pred", "succ"} <= available):
        raise ValueError("recursion.style 'primitive' needs base operations ['sub', 'add'] (or ['pred', "
                         "'succ']), which the starting operator set does not have")
    bound = settings.semantics.bound
    if settings.semantics.mode == "exact" and bound is not None:
        style = settings.recursion
        size = max(style.direct_bound if name in BOUNDED_STYLES else style.modulus_max
                   for name in styles)
        if size > bound:
            raise ValueError(f"the recursion size {size} exceeds semantics.bound {bound}: the template's "
                             "threshold would itself be NaN and its negative branch unreachable")
    missing = []
    for name in styles:
        if name == "bits":
            missing += [] if registry.find("⇒", 2) is not None else ["shift_right"]
        elif name == "peano":
            needed = [(settings.recursion.step_down, 1, "postfix")]
            if not settings.recursion.nonnegative:
                needed.append((settings.recursion.step_up, 1, "postfix"))
            missing += [symbol for symbol, arity, position in needed
                        if registry.find(symbol, arity, position) is None]
        else:
            missing += [op for op in RECURSION_OPERATIONS.get(name, ()) if op not in available]
    missing = list(dict.fromkeys(missing))
    if missing:
        raise ValueError(f"recursion styles {styles!r} needs base operations {missing}, "
                         "which the starting operator set does not have")


def _encoder(oracle):
    """A z3 encoder for dead-branch checks; None in legacy mode (no exact encoding).

    z3 is imported here, so that generation with both solver checks switched off runs without
    it (the documentation playground grows operators that way under Pyodide)."""
    from opulse.solver.z3_encode import NotExpressible, Z3Encoder

    try:
        return Z3Encoder(oracle)
    except NotExpressible:
        return None


def layer_plan(count: int, layer: int, proportions: tuple[float, float, float],
               rng: random.Random) -> list[str]:
    """Definition kinds for ``count`` operators at ``layer``; recursive ones first.

    ``proportions`` is (simple, branch, recursive). Layer 0 cannot hold recursive
    operators, so their share goes to simple/branch at random.
    """
    simple, branch, recursive = (int(count * p) for p in proportions)
    simple += count - simple - branch - recursive  # rounding remainder
    if layer == 0:
        kinds = [SIMPLE] * simple + [BRANCH] * branch
        kinds += [rng.choice((SIMPLE, BRANCH)) for _ in range(recursive)]
        return kinds
    if recursive == 0 and count > 0:
        recursive = 1  # layer L needs at least one recursive seed
        if simple:
            simple -= 1
        else:
            branch -= 1
    plan = [RECURSIVE] * recursive + [SIMPLE] * simple + [BRANCH] * branch
    assert len(plan) == count
    return plan


def build_layers(factory: OperatorFactory, counts: list[int], proportions=(0.4, 0.4, 0.2),
                 on_accept: Callable[[Operator], None] | None = None) -> None:
    settings = factory.settings
    if not settings.recursion.enabled and any(counts[1:]):
        raise ValueError("higher layers require recursion.enabled")
    allowed = {kind for kind, enabled in ((SIMPLE, settings.operators.allow_simple),
                                          (BRANCH, settings.operators.allow_branches),
                                          (RECURSIVE, settings.recursion.enabled)) if enabled}
    if counts and counts[0] and not allowed.intersection((SIMPLE, BRANCH)):
        raise ValueError("layer 0 requires simple or branch definitions")
    needed = factory.symbols._index.size + sum(counts)
    if needed > factory.symbols.capacity():
        raise ValueError(f"{sum(counts)} new operators need {needed} distinct symbols, but "
                         f"{len(factory.symbols.alphabet)} characters up to length "
                         f"{factory.settings.operators.symbol_max_len} give at most {factory.symbols.capacity()}; "
                         "add characters (operators.symbol_sets / symbol_chars) or raise operators.symbol_max_len")
    for layer, count in enumerate(counts):
        plan = layer_plan(count, layer, proportions, factory.rng)
        if len(allowed) < 3:
            possible = tuple(kind for kind in (SIMPLE, BRANCH) if kind in allowed)
            plan = [kind if kind in allowed else factory.rng.choice(possible) for kind in plan]
        for kind in plan:
            operator = factory.generate(kind, layer)
            factory.add(operator)
            if on_accept:
                on_accept(operator)
        logger.info("layer %d done: %s", layer, factory.stats.summary())
