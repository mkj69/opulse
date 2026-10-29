"""How varied a grown operator set is, measured on a fixed probe set per world.

``measure`` evaluates every generated operator on the same probe inputs (all combinations of
a few values per input type) and reports:

* ``forms``: how many operators use substitution, branches and recursion;
* ``behaviours``: the number of distinct behaviour fingerprints, where a fingerprint is the
  input types plus the outputs on the probes;
* ``constant``: operators with one output on every probe (NaN counts as an output);
* ``near_constant``: operators with at most two distinct outputs;
* ``wrappers``: substitutions that apply a single operation to the inputs and constants;
* ``layers``: operators per recursive layer, and ``calls_lower``: the share of operators above
  layer zero whose definition applies a generated operator.

The probes are fixed per world, so fingerprints from different seeds can be compared:
``novel`` counts the fingerprints of one seed that no other measured seed has.
"""

from __future__ import annotations

import itertools
from collections import Counter

PROBES = {
    "int": (0, 1, 2, 3, 5, 7, 9, 12, -1, -4),
    "bool": (False, True),
    "str": ("", "a", "Ab", "xyz", "Hello"),
    "list[int]": ((), (1,), (2, 3), (3, 1, 4), (5, 5, 0, 2)),
}
WORLD_INTS = {
    "successor": (0, 1, 2, 3, 4, 6, 9, 13),
    "bits": (0, 1, 2, 3, 5, 6, 12, 31),
    "clock": (0, 1, 3, 5, 7, 11, 14, 23),
}


def probes(world: str, kind: str):
    if kind == "int" and world in WORLD_INTS:
        return WORLD_INTS[world]
    if kind == "str" and world == "rel":
        return ("Ana", "Bo", "Cora", "Dev", "Eli", "Gio", "Ivo", "Luz")
    if kind in PROBES:
        return PROBES[kind]
    if kind.startswith("perm["):
        from opulse.worlds.perm import Permutation

        size = int(kind[5:-1])
        base = list(range(size))
        return (Permutation(base), Permutation(base[1:] + base[:1]), Permutation(base[::-1]),
                Permutation([1, 0, *base[2:]]))
    if kind == "grid":
        return (((1, 0, 2), (0, 3, 0), (4, 0, 5)), ((0, 0, 0, 0), (0, 6, 6, 0), (0, 0, 7, 0)),
                ((8,), (0,)), ((1, 2), (3, 4)))
    if kind == "note":
        return (60, 64, 67, 72, 0, 127)
    if kind == "melody":
        return ((), ((60, 1),), ((60, 1), (64, 1), (67, 2)), ((72, 2), (71, 1)))
    raise ValueError(f"no probes for {kind!r}")


def _applications(definition, symbols: set) -> tuple[int, int]:
    """(number of applications, number of applications of generated operators)."""
    from opulse.definition import ast

    total = generated = 0

    def visit(node):
        nonlocal total, generated
        if isinstance(node, ast.Apply):
            total += 1
            generated += node.symbol in symbols
            for arg in node.args:
                visit(arg)

    for branch in definition.branches:
        visit(branch.expr)
    return total, generated


def fingerprint(op, oracle, world: str, limit: int = 64) -> tuple:
    pools = [probes(world, kind) for kind in op.parameter_types]
    outputs = []
    for args in itertools.islice(itertools.product(*pools), limit):
        try:
            outputs.append(repr(oracle.evaluate(op, args).value))
        except (RecursionError, OverflowError, ValueError, TypeError):
            outputs.append("error")
    return (tuple(op.parameter_types), tuple(outputs))


def measure(world: str, registry, generated, oracle, parser) -> dict:
    forms = Counter(op.definition_type for op in generated)
    generated_symbols = {op.symbol for op in generated}
    prints, constant, near, wrappers, lower = [], 0, 0, 0, 0
    above = 0
    for op in generated:
        print_ = fingerprint(op, oracle, world)
        prints.append(print_)
        distinct = set(print_[1])
        constant += len(distinct) == 1
        near += len(distinct) <= 2
        definition = parser.parse(op.definition)
        total, calls = _applications(definition, generated_symbols - {op.symbol})
        if op.definition_type == "simple_definition" and total <= 1:
            wrappers += 1
        if op.recursive_layer > 0:
            above += 1
            lower += calls > 0
    count = len(generated)
    return {
        "operators": count,
        "forms": {"composition": forms.get("simple_definition", 0), "branching": forms.get("branch_definition", 0),
                  "recursion": forms.get("recursive_definition", 0)},
        "behaviours": len(set(prints)),
        "constant": constant,
        "near_constant": near,
        "wrappers": wrappers,
        "layers": {str(layer): n for layer, n in sorted(Counter(op.recursive_layer for op in generated).items())},
        "calls_lower": round(lower / above, 3) if above else None,
        "_prints": prints,
    }


def add_novelty(results: list[dict]) -> None:
    """Fill ``novel`` for each seed: fingerprints absent from every other seed."""
    for index, result in enumerate(results):
        others = set().union(*(set(other["_prints"]) for j, other in enumerate(results) if j != index))
        mine = set(result["_prints"])
        result["novel"] = len(mine - others)
    for result in results:
        result.pop("_prints", None)
