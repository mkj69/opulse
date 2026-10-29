"""Deterministic reader-facing selection from a complete grown library.

The names and derivation indices of the complete library stay stable for task tabs.  The
browser uses ``curated`` as an ordered list of those names.
"""

from __future__ import annotations

import itertools
import re
from collections import Counter, defaultdict

from opulse.core.semantics import NAN

TARGET = 24
MAX_WORDS = 22
PREFERRED_TERMS = {
    "successor": ("add one", "subtract one", "stopping at zero", "repeat"),
    "integer": ("multiply", "add", "subtract", "negate", "count", "reverse"),
    "clock": ("add", "subtract", "negate", "count", "repeat"),
    "bits": ("shift", "XOR", "AND", "OR", "count"),
    "strings": ("reverse", "append", "uppercase", "lowercase", "count", "drop"),
    "lists": ("append", "first element", "sum", "drop", "front", "count"),
    "logic": ("AND", "OR", "XOR", "implies", "negate"),
    "perm": ("rotate", "reverse", "invert", "swap", "follow"),
    "rel": ("neighbour", "colleague", "parent"),
    "grid": ("rotate", "mirror", "transpose", "crop", "count", "fill", "recolour", "wrap"),
    "pitch": ("transpose", "triad", "mirror", "reverse", "append", "semitones"),
}
REASONS = ("undefined", "constant", "near_constant", "unused_argument",
           "atom_equivalent", "duplicate", "shape_duplicate", "cancelled_constant", "alias",
           "bad_helper", "long_sentence", "opaque_sentence")


def _key(value):
    return "NaN" if value is NAN else f"{type(value).__name__}:{value!r}"


def _sample(op, spec, oracle, points=None):
    if points is None:
        pools = [list(spec.values(kind))[:8] for kind in op.parameter_types]
        points = list(itertools.product(*pools))[:96]
    results = []
    for args in points:
        try:
            results.append(_key(oracle.evaluate(op, args).value))
        except (ValueError, TypeError, OverflowError, RecursionError):
            results.append("NaN")
    return points, tuple(results)


def _points_by_signature(operators, spec, tools):
    grouped = defaultdict(list)
    for op in operators:
        grouped[tuple(op.parameter_types)].append(op)
    result = {}
    for signature, members in grouped.items():
        points, seen = [], set()
        def add(args):
            marker = repr(args)
            if marker not in seen and len(points) < 96:
                seen.add(marker)
                points.append(args)
        if tools is not None and spec.extra_inputs:
            for op in members:
                if op.definition is None or len(points) >= 32:
                    continue
                for args in list(spec.extra_inputs(op, tools))[:2]:
                    add(args)
        pools = [list(spec.values(kind))[:8] for kind in signature]
        for args in itertools.product(*pools):
            add(args)
        result[signature] = points
    return result


def _uses_every_argument(points, outputs, arity):
    if arity < 2:
        return True
    for position in range(arity):
        groups = defaultdict(set)
        for args, value in zip(points, outputs):
            groups[tuple(repr(arg) for index, arg in enumerate(args) if index != position)].add(value)
        if not any(len(values) > 1 for values in groups.values()):
            return False
    return True


def _cancelled_constant(definition):
    # Neutral arithmetic and identical operands are transparent in a written rule.
    return bool(re.search(r"(?:\+\s*0\b|\b0\s*\+|\*\s*1\b|\b1\s*\*|\-\s*0\b|/\s*1\b|\b([ab])\s*-\s*\1\b)", definition)
                or re.search(r"(?:by 0 (?:rows|columns|bits)|append (?:\"\"|\[\]) to it)", definition))


def _alias(row):
    body = row["definition"].split("= {", 1)[-1].strip().rstrip("}").strip()
    params = [param["name"] for param in row["params"]]
    if len(params) == 1:
        return bool(re.fullmatch(r"[^\s,;()]+\s+" + re.escape(params[0]) + r"|" +
                                 re.escape(params[0]) + r"\s+[^\s,;()]+", body))
    if len(params) == 2:
        return bool(re.fullmatch(re.escape(params[0]) + r"\s+[^\s,;()]+\s+" +
                                 re.escape(params[1]), body))
    return False


def _numeric_shape(outputs):
    if not outputs or not all(value.startswith("int:") for value in outputs):
        return None
    numbers = [int(value[4:]) for value in outputs]
    return tuple(value - numbers[0] for value in numbers)


def _contrived_plain(world, row):
    plain = row["plain"]
    if world == "bits" and re.search(
            r"shift (?:a|the result) (?:left|right) by (?:a|itself) bits", plain, re.I):
        return True
    if re.search(r"remainder when dividing \d+ by -?a\b", plain, re.I):
        return True
    if row["kind"] == "recursion":
        match = re.match(r"Start with (-?\d+)\. Repeat", plain)
        if match and abs(int(match[1])) > 20:
            return True
    return False


def curate(generated, rows, spec, oracle, registry, names, tools=None):
    """Return display names and exclusive rejection counts for one seeded world."""
    atoms = [op for op in registry if op.definition is None]
    sampled = {}
    point_groups = _points_by_signature([*atoms, *generated], spec, tools)
    for op in [*atoms, *generated]:
        sampled[op.func_id] = _sample(op, spec, oracle, point_groups[tuple(op.parameter_types)])
    atom_tables = defaultdict(set)
    for atom in atoms:
        atom_tables[(tuple(atom.parameter_types), atom.result_type)].add(sampled[atom.func_id][1])
    reasons = Counter({reason: 0 for reason in REASONS})
    def structural_bad(row):
        return (_alias(row) or _contrived_plain(spec.world, row)
                or _cancelled_constant(row["definition"] + " " + row["plain"])
                or (spec.world == "grid" and row.get("uses")
                    and re.search(r"\s0\s*}\s*$", row["definition"])))

    bad_helpers = {row["name"] for row in rows if structural_bad(row)}
    tainted = set(bad_helpers)
    while True:
        expanded = tainted | {row["name"] for row in rows
                              if any(helper in tainted for helper in row.get("uses", ()))}
        if expanded == tainted:
            break
        tainted = expanded
    eligible = []
    seen = defaultdict(set)
    seen_shapes = defaultdict(set)
    for op, row in zip(generated, rows):
        points, outputs = sampled[op.func_id]
        counts = Counter(outputs)
        key = (tuple(op.parameter_types), op.result_type)
        reason = None
        if not outputs or all(value == "NaN" for value in outputs) or all(
                example["output"]["t"] == "nan" for example in row["examples"]):
            reason = "undefined"
        elif len(counts) == 1:
            reason = "constant"
        elif max(counts.values()) / len(outputs) >= 0.85 and len(outputs) >= 8:
            reason = "near_constant"
        elif not _uses_every_argument(points, outputs, op.n_ary):
            reason = "unused_argument"
        elif outputs in atom_tables[key]:
            reason = "atom_equivalent"
        elif outputs in seen[key]:
            reason = "duplicate"
        elif _numeric_shape(outputs) is not None and _numeric_shape(outputs) in seen_shapes[key]:
            reason = "shape_duplicate"
        elif (_cancelled_constant(row["definition"] + " " + row["plain"])
              or (spec.world == "grid" and row.get("uses")
                  and re.search(r"\s0\s*}\s*$", row["definition"]))):
            reason = "cancelled_constant"
        elif _alias(row):
            reason = "alias"
        elif any(helper in bad_helpers for helper in row.get("uses", ())):
            reason = "bad_helper"
        elif len(row["plain"].split()) > MAX_WORDS:
            reason = "long_sentence"
        elif (_contrived_plain(spec.world, row) or row.get("reading") == "summary"
              or row["plain"].startswith("Compute ")
              or len(row.get("uses", [])) > 2):
            reason = "opaque_sentence"
        if reason:
            reasons[reason] += 1
            continue
        seen[key].add(outputs)
        shape = _numeric_shape(outputs)
        if shape is not None:
            seen_shapes[key].add(shape)
        interest = row.get("interest") or {}
        # Short descriptions, defined outputs and original atoms are easier to read.
        quality = (interest.get("score", 0) + 0.16 * interest.get("defined_share", 0)
                   + 0.08 * interest.get("novelty", 0) - 0.008 * len(row["plain"].split())
                   - 0.14 * len(row.get("uses", []))
                   + (0.12 if not row.get("uses") else 0))
        features = tuple(term for term in PREFERRED_TERMS.get(spec.world, ())
                         if term.lower() in row["plain"].lower())
        quality += min(2, len(features)) * 0.055
        if row["kind"] == "recursion" and not row.get("uses"):
            quality += 0.35
        if any(helper in tainted for helper in row.get("uses", ())):
            quality -= 0.25
        eligible.append((quality, op, row))

    # Lead with short substitutions that a reader can understand before introducing
    # branches and bounded repetition. Keep all three forms in the complete selection.
    selected = []
    for form in ("composition", "branching", "recursion"):
        match = max((item for item in eligible if item[2]["kind"] == form), default=None,
                    key=lambda item: item[0])
        if match is not None:
            selected.append(match)
    for item in sorted((item for item in eligible if item[2]["kind"] == "composition" and item not in selected),
                       key=lambda item: -item[0]):
        if len(selected) >= 5:
            break
        selected.append(item)
    remaining = sorted((item for item in eligible if item not in selected), key=lambda item: -item[0])
    while len(selected) < TARGET and remaining:
        counts = Counter(item[2]["kind"] for item in selected)
        layers = Counter(item[2]["layer"] for item in selected)
        best = max(remaining, key=lambda item: item[0] - 0.025 * counts[item[2]["kind"]]
                   - 0.015 * layers[item[2]["layer"]])
        selected.append(best)
        remaining.remove(best)
    # Feature simple compositions first; retain the selected branch and recursion
    # in the remaining list, which progresses through layers and forms.
    first = sorted((item for item in selected if item[2]["kind"] == "composition"),
                   key=lambda item: (item[2]["layer"], -item[0]))[:5]
    rest = sorted((item for item in selected if item not in first), key=lambda item: (item[2]["layer"],
                  {"composition": 0, "branching": 1, "recursion": 2}[item[2]["kind"]], -item[0]))
    return [item[2]["name"] for item in first + rest], dict(reasons)
