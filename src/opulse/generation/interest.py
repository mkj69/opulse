"""Behavioural fingerprints, deduplication and interestingness scores.

In the spirit of the interestingness heuristics of Lenat's AM, an operator is judged by what it
does, not by how it is written. Everything here reads the operator's *value table*: its values on
a fixed probe grid built from :class:`opulse.config.InterestSettings` (``probe_ints``) and
:data:`TYPED_PROBES`. The grid is recorded in every score as a short hash (``probes``).

Deduplication
    A candidate is a behavioural duplicate when its value table equals an existing operator's,
    possibly after a cheap transformation: a permutation of the arguments, negating some
    arguments, negating the result, or both (negation is arithmetic for ``int`` and logical for
    ``bool``). Value tables cover the probe grid only, so two operators that agree there but
    differ elsewhere count as duplicates.

Scores (each in [0, 1], combined with ``interest.weights``)
    novelty         fraction of probe points where the operator differs from its nearest
                    earlier operator of the same signature, minimised over the transformations
                    above (1 when no earlier operator has its signature);
    regularity      share of the applicable regularities that hold: symmetry, monotonicity,
                    periodicity, fixed points, idempotence, involution; read on the value table
                    and, on request, confirmed or refuted by z3;
    reuse           r / (1 + r), where r is the number of later operators that call it;
    non_degeneracy  share of defined values times the output entropy over log2 of the grid size;
    compression     t / (t + d): t and d are the zlib-compressed sizes in bytes of the value
                    table and of the definition text. A short definition of a varied table scores
                    high; a constant table scores low.
"""

from __future__ import annotations

import hashlib
import itertools
import math
import zlib
from collections.abc import Callable, Iterable

import numpy as np

from opulse.config import INTEREST_COMPONENTS, InterestSettings
from opulse.core.operator import Operator
from opulse.core.semantics import NAN

TYPED_PROBES = {
    "bool": (False, True),
    "str": ("", "a", "b", "ab", "ba", "aab"),
    "list[int]": ((), (1,), (2,), (1, 2), (2, 1), (1, 2, 3)),
}
NEGATABLE = ("int", "bool")

# Transformation labels, in the order they are tried; used as rejection reasons.
IDENTITY = "behavioural duplicate"
SWAP = "behavioural duplicate up to argument order"
NEGATION = "behavioural duplicate up to negation"
SWAP_NEGATION = "behavioural duplicate up to argument order and negation"
DUPLICATE_REASONS = (IDENTITY, SWAP, NEGATION, SWAP_NEGATION)

_ERROR = object()  # a probe whose evaluation raised


def _same(x, y) -> bool:
    return (x is NAN and y is NAN) or (x is not NAN and y is not NAN and type(x) is type(y) and x == y)


def _negate(value):
    if value is NAN or value is _ERROR:
        return value
    if isinstance(value, bool):
        return not value
    return -value


def _key(value) -> str:
    if value is NAN:
        return "NaN"
    if value is _ERROR:
        return "error"
    return f"{type(value).__name__}:{value!r}"


def is_scored(operator: Operator) -> bool:
    """Operations with a definition; atoms take part in deduplication but get no score."""
    return operator.definition is not None and operator.has_code


class Fingerprinter:
    """Value tables on the probe grid, transformation tables and value codes."""

    def __init__(self, settings: InterestSettings) -> None:
        self.settings = settings
        ints = tuple(sorted(set(settings.probe_ints)))
        from opulse.worlds.metrics import probes

        self._lists = {"int": ints, **TYPED_PROBES,
                       "perm[5]": probes("perm", "perm[5]"),
                       "grid": probes("grid", "grid"),
                       "note": probes("pitch", "note"),
                       "melody": probes("pitch", "melody")}
        self._lists["str"] = (*TYPED_PROBES["str"], *probes("rel", "str"))
        self._grids: dict[tuple, tuple[tuple, list[tuple]]] = {}
        self._transforms: dict[tuple, list] = {}
        self._codes: dict[str, int] = {}
        self.probe_hash = hashlib.sha256(repr(sorted((k, v) for k, v in self._lists.items())).encode()
                                         + str(settings.max_probe_points).encode()).hexdigest()[:12]

    # -------------------------------------------------------------- the grid
    def supports(self, types: tuple[str, ...]) -> bool:
        return all(t in self._lists for t in types)

    def grid(self, types: tuple[str, ...]) -> tuple[tuple[tuple, ...], list[tuple]]:
        """Per-position probe values and deterministic points, in a fixed order.

        High arities first reduce each list to fit the cap. If this would leave
        an argument constant, a sparse grid varies each argument while staying
        closed under the supported argument permutations and negations.
        """
        cached = self._grids.get(types)
        if cached is not None:
            return cached
        cap = self.settings.max_probe_points
        longest = max((len(self._lists[t]) for t in types), default=1)
        m = longest
        while m > 1 and math.prod(min(m, len(self._lists[t])) for t in types) > cap:
            m -= 1
        columns = []
        for t in types:
            k = min(m, len(self._lists[t]))
            values = _spread(self._lists[t], k) if t == "int" else self._lists[t][:k]
            columns.append(tuple(sorted(values, key=_order)))
        if all(len(column) > 1 for column in columns):
            points = list(itertools.product(*columns))
        else:
            # A Cartesian cap can collapse an entire argument to its neutral value.
            # Use a sparse grid that varies one non-boolean argument at a time. All
            # boolean combinations are included so argument negation stays in the grid.
            if "int" in types and 0 not in self._lists["int"]:
                raise ValueError("interest.max_probe_points is too small for probe_ints without 0")
            minimum = 3 if "int" in types else 2
            for width in range(longest, minimum - 1, -1):
                sparse_columns = []
                for t in types:
                    values = (_spread(self._lists[t], min(width, len(self._lists[t]))) if t == "int"
                              else self._lists[t][:width])
                    sparse_columns.append(tuple(sorted(values, key=_order)))
                bool_count = sum(t == "bool" for t in types)
                size = 2 ** bool_count * (1 + sum(len(c) - 1 for t, c in zip(types, sparse_columns)
                                                    if t != "bool"))
                if size <= cap:
                    columns = sparse_columns
                    break
            else:
                raise ValueError("interest.max_probe_points is too small to vary every argument")
            centers = tuple(0 if t == "int" else column[0]
                            for t, column in zip(types, columns))
            bases = [tuple(values) for values in itertools.product(
                *((False, True) if t == "bool" else (center,)
                  for t, center in zip(types, centers)))]
            points = list(bases)
            for i, (t, column) in enumerate(zip(types, columns)):
                if t == "bool":
                    continue
                for base in bases:
                    for value in column:
                        if value != centers[i]:
                            point = list(base)
                            point[i] = value
                            points.append(tuple(point))
        result = (tuple(columns), points)
        self._grids[types] = result
        return result

    def code(self, value) -> int:
        key = _key(value)
        code = self._codes.get(key)
        if code is None:
            code = self._codes[key] = len(self._codes)
        return code

    # ------------------------------------------------------------- the table
    def values(self, operator: Operator, compute: Callable) -> list:
        _, points = self.grid(tuple(operator.parameter_types))
        return [_call(compute, point) for point in points]

    def codes(self, values: Iterable) -> np.ndarray:
        return np.fromiter((self.code(v) for v in values), dtype=np.int64)

    def transforms(self, types: tuple[str, ...]) -> list[tuple[str, tuple[str, ...], np.ndarray, tuple, bool]]:
        """``(label, new_types, index, flips, output_negated)`` for every transformation.

        A transformed table lists ``g(y) = o(f(z))`` over the grid of ``new_types``, where
        ``z[perm[i]] = n_i(y[i])``: ``index[j]`` is the position of ``z`` in ``f``'s grid,
        ``flips`` the negated positions and ``o`` negation when ``output_negated``. The first
        entry is the identity. Arities above three use transpositions and single negations only.
        """
        cached = self._transforms.get(types)
        if cached is not None:
            return cached
        n = len(types)
        _, points = self.grid(types)
        lookup = {point: i for i, point in enumerate(points)}
        if n <= 3:
            perms = list(itertools.permutations(range(n)))
        else:
            perms = [tuple(range(n))]
            for i, j in itertools.combinations(range(n), 2):
                p = list(range(n))
                p[i], p[j] = j, i
                perms.append(tuple(p))
        negatable = [i for i, t in enumerate(types) if t in NEGATABLE]
        if len(negatable) <= 3:
            masks = [frozenset(c) for r in range(len(negatable) + 1) for c in itertools.combinations(negatable, r)]
        else:
            masks = [frozenset()] + [frozenset((i,)) for i in negatable]
        result = []
        for output in (False, True):
            for mask in masks:
                for perm in perms:
                    moved = perm != tuple(range(n))
                    negated = output or bool(mask)
                    label = (SWAP_NEGATION if moved and negated else SWAP if moved
                             else NEGATION if negated else IDENTITY)
                    new_types = tuple(types[perm[i]] for i in range(n))
                    _, new_points = self.grid(new_types)
                    index = np.empty(len(new_points), dtype=np.int64)
                    for j, y in enumerate(new_points):
                        z = [None] * n
                        for i in range(n):
                            z[perm[i]] = _negate(y[i]) if perm[i] in mask else y[i]
                        index[j] = lookup[tuple(z)]
                    result.append((label, new_types, index, tuple(sorted(mask)), output))
        order = {label: rank for rank, label in enumerate(DUPLICATE_REASONS)}
        result.sort(key=lambda item: order[item[0]])  # stable: identity first
        self._transforms[types] = result
        return result

    def variant(self, values: list, index: np.ndarray, output_negated: bool) -> np.ndarray:
        picked = [values[i] for i in index]
        if output_negated:
            picked = [_negate(v) for v in picked]
        return self.codes(picked)


def _spread(values: tuple[int, ...], k: int) -> tuple[int, ...]:
    """At most ``k`` of the integer probes, closed under negation and spread over the whole
    range: 0 (when present), then evenly spaced positive values with their negatives."""
    positives = sorted(v for v in values if v > 0)
    zero = (0,) if 0 in values else ()
    pairs = (k - len(zero)) // 2
    if pairs >= len(positives):
        chosen = positives
    elif pairs <= 0:
        chosen = []
    else:  # indices spread from the smallest to the largest positive probe
        chosen = [positives[round(i * (len(positives) - 1) / max(pairs - 1, 1))] for i in range(pairs)]
        if pairs == 1:
            chosen = [positives[len(positives) // 2]]
    chosen = sorted(set(chosen))
    return (*zero, *chosen, *(-v for v in chosen))


def _order(value):
    if isinstance(value, (tuple, str)):
        return (len(value), value)
    return (0, value)


def _call(compute: Callable, args: tuple):
    try:
        return compute(*args)
    except Exception:  # noqa: BLE001 - a probe that raises is recorded, not fatal
        return _ERROR


def _digest(types, result_type, codes: np.ndarray) -> tuple:
    return (types, result_type, hashlib.sha256(codes.tobytes()).hexdigest())


class Scorer:
    """Keeps the value tables of the operators seen so far; scores and deduplicates candidates.

    ``compute(operator)`` returns the operator's value function (``PythonRuntime.compute``).
    Operators are added in registry order with :meth:`add`.
    """

    def __init__(self, settings: InterestSettings, compute: Callable[[Operator], Callable]) -> None:
        self.settings = settings
        self.compute = compute
        self.fp = Fingerprinter(settings)
        self._exact: dict[tuple, str] = {}  # (types, result type, table hash) -> symbol
        self._groups: dict[tuple, tuple[list[str], list[np.ndarray]]] = {}
        self._matrices: dict[tuple, np.ndarray] = {}

    # ----------------------------------------------------------- the index
    def add(self, operator: Operator) -> None:
        types = tuple(operator.parameter_types)
        if not self.fp.supports(types) or not _applicable(operator):
            return
        values = self.fp.values(operator, self.compute(operator))
        codes = self.fp.codes(values)
        self._exact.setdefault(_digest(types, operator.result_type, codes), operator.symbol)
        names, tables = self._groups.setdefault((types, operator.result_type), ([], []))
        names.append(operator.symbol)
        tables.append(codes)
        self._matrices.pop((types, operator.result_type), None)

    def _matrix(self, key) -> np.ndarray | None:
        group = self._groups.get(key)
        if group is None:
            return None
        matrix = self._matrices.get(key)
        if matrix is None:
            matrix = self._matrices[key] = np.vstack(group[1])
        return matrix

    # -------------------------------------------------------------- queries
    def duplicate(self, operator: Operator) -> tuple[str, str] | None:
        """``(reason, symbol)`` when a transformed value table equals an existing operator's."""
        types = tuple(operator.parameter_types)
        if not self.fp.supports(types):
            return None
        values = self.fp.values(operator, self.compute(operator))
        for label, new_types, index, _, output in self.fp.transforms(types):
            if output and operator.result_type not in NEGATABLE:
                continue
            found = self._exact.get(_digest(new_types, operator.result_type,
                                            self.fp.variant(values, index, output)))
            if found is not None:
                return label, found
        return None

    def novelty(self, operator: Operator, values: list | None = None) -> tuple[float, str | None, str | None]:
        """``(distance, nearest symbol, transformation label)``; distance 1.0 without a peer."""
        types = tuple(operator.parameter_types)
        if values is None:
            values = self.fp.values(operator, self.compute(operator))
        best, nearest, how = 1.0, None, None
        for label, new_types, index, _, output in self.fp.transforms(types):
            if output and operator.result_type not in NEGATABLE:
                continue
            matrix = self._matrix((new_types, operator.result_type))
            if matrix is None:
                continue
            table = self.fp.variant(values, index, output)
            distances = (matrix != table).mean(axis=1)
            k = int(np.argmin(distances))
            if distances[k] < best or nearest is None and distances[k] <= best:
                best, nearest, how = float(distances[k]), self._groups[(new_types, operator.result_type)][0][k], label
            if best == 0.0:
                break
        return best, nearest, how

    def score(self, operator: Operator, callers: int = 0, regularities: dict | None = None) -> dict | None:
        """The interest record of ``operator`` against the operators added so far."""
        types = tuple(operator.parameter_types)
        if not self.fp.supports(types) or not is_scored(operator):
            return None
        compute = self.compute(operator)
        values = self.fp.values(operator, compute)
        novelty, nearest, how = self.novelty(operator, values)
        if regularities is None:
            regularities = detect_regularities(operator, compute, self.fp, self.settings)
        regularities = dict(regularities)
        applicable = regularities.pop("_applicable")
        held = {name: info for name, info in regularities.items() if info["status"] != "refuted"}
        regularity = len(held) / applicable if applicable else 0.0
        size = len(values)
        defined = sum(v is not NAN and v is not _ERROR for v in values) / size
        counts = {}
        for v in values:
            counts[_key(v)] = counts.get(_key(v), 0) + 1
        entropy = -sum(c / size * math.log2(c / size) for c in counts.values())
        spread = entropy / math.log2(size) if size > 1 else 0.0
        table_bytes = len(zlib.compress("\n".join(_key(v) for v in values).encode(), 9))
        definition_bytes = len(zlib.compress((operator.definition or "").encode(), 9))
        components = {
            "novelty": novelty,
            "regularity": regularity,
            "reuse": callers / (1 + callers),
            "non_degeneracy": defined * spread,
            "compression": table_bytes / (table_bytes + definition_bytes),
        }
        weights = self.settings.weights
        total = sum(weights[c] * components[c] for c in INTEREST_COMPONENTS) / sum(weights.values())
        return {
            "score": _round(total),
            **{name: _round(value) for name, value in components.items()},
            "nearest": nearest,
            "nearest_transform": how,
            "regularities": regularities,
            "regularities_tested": applicable,
            "callers": callers,
            "defined_share": _round(defined),
            "entropy_bits": _round(entropy),
            "table_bytes": table_bytes,
            "definition_bytes": definition_bytes,
            "probes": self.fp.probe_hash,
        }


def _applicable(operator: Operator) -> bool:
    from opulse.solver.smt import is_operation

    return is_operation(operator)


def _round(x: float) -> float:
    return round(float(x), 6)


# ------------------------------------------------------------------ regularities
def detect_regularities(operator: Operator, compute: Callable, fp: Fingerprinter,
                        settings: InterestSettings) -> dict:
    """Regularities that hold on the value table, each ``{"status": "table", ...}``.

    The key ``_applicable`` holds how many regularities were tested. ``status`` becomes
    ``proved`` or ``refuted`` once :func:`confirm_regularities` asks z3.
    """
    types = tuple(operator.parameter_types)
    n = len(types)
    columns, points = fp.grid(types)
    table = dict(zip(points, (_call(compute, p) for p in points)))
    found: dict = {}
    applicable = 0

    # Symmetry: invariance under exchanging two arguments of the same type; odd / even for
    # a unary operator on integers.
    pairs = [(i, j) for i, j in itertools.combinations(range(n), 2) if types[i] == types[j]]
    if pairs:
        applicable += 1
        if all(_same(table[p], table[_swapped(p, i, j)]) for i, j in pairs for p in points):
            found["symmetric"] = {"status": "table", "pairs": [list(pair) for pair in pairs]}
    if n == 1 and types[0] == "int" and operator.result_type == "int":
        applicable += 2
        if all(_same(table[(-x,)], _negate(table[(x,)])) for (x,) in points):
            found["odd"] = {"status": "table"}
        if all(_same(table[(-x,)], table[(x,)]) for (x,) in points):
            found["even"] = {"status": "table"}

    # Monotonicity and periodicity in each integer argument, on [-R, R] with the other
    # arguments at their probe values.
    lines = _lines(types, columns, settings)
    monotone, periodic = [], []
    for i, bases in lines.items():
        r = settings.regularity_range
        near = range(-r, r + 1)
        wide = sorted(set(near) | set(columns[i]))  # monotonicity also reads the far probes
        rows = [{x: _call(compute, base[:i] + (x,) + base[i:]) for x in wide} for base in bases]
        if operator.result_type == "int":
            direction = _monotone([[row[x] for x in wide] for row in rows])
            if direction:
                monotone.append([i, direction])
        period = _period([[row[x] for x in near] for row in rows], settings.max_period)
        if period:
            periodic.append([i, period])
    if lines:
        applicable += 1 + (operator.result_type == "int")
        if monotone:
            found["monotone"] = {"status": "table", "positions": monotone}
        if periodic:
            found["periodic"] = {"status": "table", "positions": periodic}

    # Fixed points, idempotence and involution need the result type among the inputs.
    if all(t == operator.result_type for t in types):
        r = settings.regularity_range
        domain = range(-r, r + 1) if operator.result_type == "int" else fp.grid((types[0],))[0][0]
        diagonal = [(x, _call(compute, (x,) * n)) for x in domain]
        applicable += 2
        fixed = [x for x, y in diagonal if _same(x, y)]
        if 0 < len(fixed) < len(diagonal):
            found["fixed_points"] = {"status": "witness", "values": [_jsonable(x) for x in fixed[:8]],
                                     "count": len(fixed)}
        if n == 1:
            applicable += 1
            images = [(x, y, _call(compute, (y,))) for x, y in diagonal if y is not NAN and y is not _ERROR]
            if images and all(_same(z, y) for _, y, z in images):
                found["idempotent"] = {"status": "table"}
            if images and all(_same(z, x) for x, _, z in images):
                found["involution"] = {"status": "table"}
        elif all(_same(x, y) for x, y in diagonal):
            found["idempotent"] = {"status": "table"}
    found["_applicable"] = applicable
    return found


def _jsonable(value):
    return list(value) if isinstance(value, tuple) else value


def _swapped(point: tuple, i: int, j: int) -> tuple:
    p = list(point)
    p[i], p[j] = p[j], p[i]
    return tuple(p)


def _lines(types, columns, settings: InterestSettings) -> dict[int, list[tuple]]:
    """For each integer position, the settings of the other arguments (at most 64 of them)."""
    out = {}
    for i, t in enumerate(types):
        if t != "int":
            continue
        others = [c for k, c in enumerate(columns) if k != i]
        out[i] = list(itertools.islice(itertools.product(*others), 64))
    return out


def _monotone(sequences) -> str | None:
    """``increasing`` / ``decreasing`` when every line is so on its defined values and some
    line changes; constant or mixed lines give None."""
    up = down = True
    changes = False
    for seq in sequences:
        defined = [v for v in seq if v is not NAN and v is not _ERROR]
        if not all(isinstance(v, int) and not isinstance(v, bool) for v in defined):
            return None
        for a, b in itertools.pairwise(defined):
            up &= a <= b
            down &= a >= b
            changes |= a != b
    if not changes:
        return None
    return "increasing" if up else "decreasing" if down else None


def _period(sequences, max_period: int) -> int | None:
    """Smallest p in 2..max_period with seq[x + p] == seq[x] on every line, when some line is
    not constant (period 1)."""
    if all(all(_same(v, seq[0]) for v in seq) for seq in sequences):
        return None
    for p in range(2, max_period + 1):
        if all(len(seq) >= 2 * p + 1 and all(_same(seq[x + p], seq[x]) for x in range(len(seq) - p))
               for seq in sequences):
            return p
    return None


def confirm_regularities(operator: Operator, regularities: dict, encoder, checker, timeout_ms: int) -> None:
    """Ask z3 about every table regularity of an integer operator, in place.

    ``proved``: no counterexample in the value domain; ``refuted``: a counterexample checked
    with the reference interpreter. Questions z3 cannot answer in time keep ``table``.
    """
    import z3

    from opulse.solver.z3_encode import NotExpressible, ZVal

    if any(t != "int" for t in operator.parameter_types) or operator.result_type != "int":
        return
    if not encoder.expressible(operator):
        return
    law = {"symmetric": "commutative" if operator.n_ary == 2 else "symmetric",
           "odd": "odd", "even": "even", "idempotent": "idempotent", "involution": "involution"}
    for name, info in regularities.items():
        if name.startswith("_") or info["status"] != "table":
            continue
        if name in law:
            if name == "symmetric" and len(info["pairs"]) != operator.n_ary * (operator.n_ary - 1) // 2:
                continue
            try:
                verdict = checker.check(operator, law[name]).status
            except Exception:  # noqa: BLE001, S112 - an encoding failure leaves the table verdict
                continue
            if verdict in ("proved", "refuted"):
                info["status"] = verdict
            continue
        if name not in ("monotone", "periodic"):
            continue
        statuses = []
        for position, detail in info["positions"]:
            try:
                encoder.reset()  # the encoder node budget bounds the formula
                xs = [z3.Int(f"x{k}") for k in range(operator.n_ary)]
                ys = list(xs)
                y = z3.Int("y")
                ys[position] = y
                left = encoder._apply(operator, [ZVal(z3.BoolVal(True), x) for x in xs], 0)
                right = encoder._apply(operator, [ZVal(z3.BoolVal(True), v) for v in ys], 0)
            except NotExpressible:
                statuses.append("table")
                continue
            domain = [encoder.in_bound(v) for v in (*xs, y)]
            x = xs[position]
            if name == "monotone":
                worse = left.value > right.value if detail == "increasing" else left.value < right.value
                question = [x < y, left.defined, right.defined, worse]
            else:
                differ = z3.Or(left.defined != right.defined,
                               z3.And(left.defined, right.defined, left.value != right.value))
                question = [y == x + detail, differ]
            solver = z3.Solver()
            solver.set("timeout", timeout_ms)
            solver.add(*domain, *question)
            result = solver.check()
            if result == z3.sat:  # keep a counterexample only if the reference interpreter agrees
                model = solver.model()
                point = [model.eval(v, model_completion=True).as_long() for v in xs]
                other = list(point)
                other[position] = model.eval(y, model_completion=True).as_long()
                left_value = encoder.oracle.evaluate(operator, tuple(point)).value
                right_value = encoder.oracle.evaluate(operator, tuple(other)).value
                if name == "monotone":
                    confirmed = (left_value is not NAN and right_value is not NAN
                                 and (left_value > right_value if detail == "increasing" else left_value < right_value))
                else:
                    confirmed = not _same(left_value, right_value)
                statuses.append("refuted" if confirmed else "table")
            else:
                statuses.append("proved" if result == z3.unsat else "table")
        if statuses and all(s == "proved" for s in statuses):
            info["status"] = "proved"
        elif "refuted" in statuses:
            info["status"] = "refuted"


# ------------------------------------------------------------------ whole registries
def score_registry(registry, settings, solver: bool = False) -> dict[str, dict]:
    """Interest records of every defined operator, keyed by ``func_id``.

    Novelty compares each operator with the operators before it in registry order; reuse counts
    the later operators whose code calls it. ``settings`` is :class:`opulse.config.Settings`.
    With ``solver`` (exact semantics only) z3 confirms or refutes the table regularities.
    """
    from opulse.runtime import PythonRuntime

    semantics = settings.semantics.build()
    runtime = PythonRuntime(registry, semantics)
    scorer = Scorer(settings.interest, runtime.compute)
    callers = {op.func_id: 0 for op in registry}
    for op in registry:
        for dep in set(op.dependencies or ()):
            if dep in callers and dep != op.func_id:
                callers[dep] += 1
    encoder = checker = None
    if solver:
        from opulse.solver.properties import PropertyChecker
        from opulse.solver.z3_encode import NotExpressible, Z3Encoder
        from opulse.verify import Oracle

        try:
            encoder = Z3Encoder(Oracle(registry, settings.symbols, semantics))
        except NotExpressible:
            encoder = None
        if encoder is not None:
            checker = PropertyChecker(encoder, timeout_ms=settings.interest.solver_timeout_ms)
    records = {}
    for op in registry:
        if is_scored(op) and scorer.fp.supports(tuple(op.parameter_types)):
            regularities = detect_regularities(op, runtime.compute(op), scorer.fp, settings.interest)
            if encoder is not None:
                confirm_regularities(op, regularities, encoder, checker, settings.interest.solver_timeout_ms)
            records[op.func_id] = scorer.score(op, callers[op.func_id], regularities)
        scorer.add(op)
    return records


def duplicate_rate(registry, settings) -> tuple[int, int]:
    """``(duplicates, defined operators)``: defined operators whose transformed value table
    repeats an earlier operator's."""
    from opulse.runtime import PythonRuntime

    runtime = PythonRuntime(registry, settings.semantics.build())
    scorer = Scorer(settings.interest, runtime.compute)
    duplicates = total = 0
    for op in registry:
        if is_scored(op) and scorer.fp.supports(tuple(op.parameter_types)):
            total += 1
            duplicates += scorer.duplicate(op) is not None
        scorer.add(op)
    return duplicates, total


def featured_operators(registry, settings, k: int = 6, per_layer: int | None = None,
                       records: dict[str, dict] | None = None) -> list[tuple[Operator, dict]]:
    """The ``k`` highest-scoring defined operators, at most ``per_layer`` from one layer.

    Ties go to the earlier operator, so the choice is deterministic. Pass ``records`` from
    :func:`score_registry` to avoid scoring twice.
    """
    if records is None:
        records = score_registry(registry, settings)
    order = {op.func_id: i for i, op in enumerate(registry)}
    ranked = sorted((op for op in registry if records.get(op.func_id)),
                    key=lambda op: (-records[op.func_id]["score"], order[op.func_id]))
    chosen, per = [], {}
    for op in ranked:
        layer = op.recursive_layer
        if per_layer is not None and per.get(layer, 0) >= per_layer:
            continue
        per[layer] = per.get(layer, 0) + 1
        chosen.append((op, records[op.func_id]))
        if len(chosen) == k:
            break
    return chosen


def summarize(records: Iterable[dict]) -> dict:
    """Mean and quartiles of the total score and of each component."""
    rows = [r for r in records if r]
    out = {"operators": len(rows), "duplicates": sum(r["novelty"] == 0 for r in rows)}
    for name in ("score", *INTEREST_COMPONENTS):
        values = np.array([r[name] for r in rows], dtype=float)
        if not len(values):
            continue
        q = np.quantile(values, [0.0, 0.25, 0.5, 0.75, 1.0])
        out[name] = {"mean": _round(values.mean()), "min": _round(q[0]), "q1": _round(q[1]),
                     "median": _round(q[2]), "q3": _round(q[3]), "max": _round(q[4])}
    return out
