"""Evidence for correspondences and deterministic matched probes."""

from __future__ import annotations

import itertools
import random

from opulse.config import Settings
from opulse.core.semantics import NAN
from opulse.core.types import freeze
from opulse.definition.parser import DefinitionParser
from opulse.expression.nodes import Call, Number
from opulse.runtime import PythonRuntime
from opulse.trace import Reducer
from opulse.verify import Oracle


def _key(value):
    value = freeze(value)
    return (type(value).__name__, repr(value))


def _domains(raw):
    domains = {kind: tuple(freeze(value) for value in values) for kind, values in raw.items()}
    if any(not values or len({_key(value) for value in values}) != len(values)
           for values in domains.values()):
        raise ValueError("domains must contain distinct values and cannot be empty")
    return domains


def _law(oracle, op, name, domain, element=None, other=None):
    """Check one listed equation on every input in the supplied finite domain."""
    apply = lambda atom, *args: oracle.evaluate(atom, args).value
    equal = lambda a, b: a is NAN and b is NAN or a is not NAN and b is not NAN and a == b
    if name in ("associativity", "commutativity", "idempotence") and op.n_ary != 2 and \
            (name != "idempotence" or op.n_ary != 1):
        raise ValueError(f"{name} needs a binary atom")
    if name in ("identity", "absorbing") and (op.n_ary != 2 or element is None):
        raise ValueError(f"{name} needs a binary atom and an element")
    if name in ("involution", "inverse_pair") and op.n_ary != 1:
        raise ValueError(f"{name} needs a unary atom")
    if name == "inverse_pair" and (other is None or other.n_ary != 1):
        raise ValueError("inverse_pair needs another unary atom")
    if name == "associativity":
        return all(equal(apply(op, apply(op, a, b), c), apply(op, a, apply(op, b, c)))
                   for a, b, c in itertools.product(domain, repeat=3))
    if name == "commutativity":
        return all(equal(apply(op, a, b), apply(op, b, a)) for a, b in itertools.product(domain, repeat=2))
    if name == "identity":
        return all(equal(apply(op, element, a), a) and equal(apply(op, a, element), a) for a in domain)
    if name == "absorbing":
        return all(equal(apply(op, element, a), element) and equal(apply(op, a, element), element) for a in domain)
    if name == "involution":
        return all(equal(apply(op, apply(op, a)), a) for a in domain)
    if name == "idempotence":
        return all(equal(apply(op, a, a), a) if op.n_ary == 2 else
                   equal(apply(op, apply(op, a)), apply(op, a)) for a in domain)
    if name == "inverse_pair":
        return all(equal(apply(other, apply(op, a)), a) and equal(apply(op, apply(other, a)), a)
                   for a in domain)
    raise ValueError(f"unknown equation {name!r}")


def correspondence_grade(source, target, correspondence: dict[str, str], *,
                         type_map: dict[str, str] | None = None, equations: list[dict] | None = None,
                         source_domains: dict[str, list] | None = None,
                         target_domains: dict[str, list] | None = None,
                         partial: bool = False, max_bijections: int = 100000,
                         settings: Settings | None = None) -> dict:
    """Grade mapped atoms on declared finite domains.

    G3 concerns the supplied bounded algebras. With ``partial=True``, an output
    outside its declared domain is an undefined operation in that algebra.
    """
    type_map = type_map or {}
    equations = equations or []
    left = _domains(source_domains or {})
    right = _domains(target_domains or {})
    pairs = [(source.get(a), target.get(b)) for a, b in sorted(correspondence.items())]
    if not pairs:
        raise ValueError("correspondence is empty")
    used_types = {kind for a, _ in pairs for kind in (*a.parameter_types, a.result_type)}
    for a, b in pairs:
        if a.n_ary != b.n_ary or tuple(type_map.get(t, t) for t in a.parameter_types) != b.parameter_types or \
                type_map.get(a.result_type, a.result_type) != b.result_type:
            raise ValueError(f"signature mismatch for {a.func_id} and {b.func_id}")
    report = {"grade": "G1", "method": "signature", "equations": [],
              "isomorphism": "not established"}
    settings = settings or Settings()
    source_oracle = Oracle(source, settings.symbols, settings.semantics.build())
    target_oracle = Oracle(target, settings.symbols, settings.semantics.build())
    laws_ok = bool(equations)
    for spec in equations:
        atom = spec["atom"]
        if atom not in correspondence:
            raise ValueError(f"equation atom {atom} is not mapped")
        a, b = source.get(atom), target.get(correspondence[atom])
        kind = a.parameter_types[0]
        mapped_kind = type_map.get(kind, kind)
        if kind not in left or mapped_kind not in right:
            raise ValueError(f"missing finite domain for {kind}")
        if spec["law"] in ("identity", "absorbing") and (
            _key(spec.get("source_element")) not in {_key(value) for value in left[kind]} or
            _key(spec.get("target_element")) not in {_key(value) for value in right[mapped_kind]}
        ):
            raise ValueError("identity and absorbing elements must belong to their finite domains")
        extra = spec.get("other")
        if extra is not None and extra not in correspondence:
            raise ValueError(f"inverse atom {extra} is not mapped")
        source_ok = _law(source_oracle, a, spec["law"], left[kind],
                         freeze(spec.get("source_element")) if "source_element" in spec else None,
                         source.get(extra) if extra else None)
        target_ok = _law(target_oracle, b, spec["law"], right[mapped_kind],
                         freeze(spec.get("target_element")) if "target_element" in spec else None,
                         target.get(correspondence[extra]) if extra else None)
        report["equations"].append({"atom": atom, "law": spec["law"], "source": source_ok,
                                    "target": target_ok, "method": "bounded exhaustive"})
        laws_ok &= source_ok and target_ok
    if laws_ok:
        report["grade"] = "G2"
        report["method"] = "bounded exhaustive equations"
    if not used_types <= left.keys() or any(type_map.get(t, t) not in right for t in used_types):
        return report
    if any(len(left[t]) != len(right[type_map.get(t, t)]) for t in used_types):
        return report
    # One value type cannot map to two distinct source types in a bijection.
    if len({type_map.get(t, t) for t in used_types}) != len(used_types):
        return report
    permutations = 1
    for kind in used_types:
        for size in range(2, len(left[kind]) + 1):
            permutations *= size
    if permutations > max_bijections:
        report["isomorphism"] = "not established: search limit"
        return report
    kinds = sorted(used_types)
    for choices in itertools.product(*(itertools.permutations(right[type_map.get(t, t)]) for t in kinds)):
        maps = {kind: {_key(a): b for a, b in zip(left[kind], values)} for kind, values in zip(kinds, choices)}
        valid = True
        for a, b in pairs:
            for args in itertools.product(*(left[t] for t in a.parameter_types)):
                source_value = source_oracle.evaluate(a, args).value
                mapped_args = tuple(maps[t][_key(value)] for t, value in zip(a.parameter_types, args))
                target_value = target_oracle.evaluate(b, mapped_args).value
                if source_value is NAN or target_value is NAN:
                    if (source_value is NAN) != (target_value is NAN):
                        valid = False
                        break
                    continue
                codomain = maps[a.result_type]
                outside_left = _key(source_value) not in codomain
                outside_right = _key(target_value) not in {
                    _key(v) for v in right[type_map.get(a.result_type, a.result_type)]}
                if outside_left or outside_right:
                    if not partial or outside_left != outside_right:
                        valid = False
                        break
                elif _key(codomain[_key(source_value)]) != _key(target_value):
                    valid = False
                    break
            if not valid:
                break
        if valid and (not equations or laws_ok):
            report["grade"] = "G3"
            report["method"] = "bounded exhaustive partial isomorphism" if partial else "bounded exhaustive isomorphism"
            report["isomorphism"] = "established"
            report["bijection"] = {kind: [[a, maps[kind][_key(a)]] for a in left[kind]] for kind in kinds}
            break
    return report


def probe_instance(registry, operator, *, inputs: list[list] | None = None, count: int = 16,
                   seed: int = 0, sample_values: dict[str, list] | None = None,
                   settings=None) -> dict:
    """Measure undefined rate and finest unfolded trace length on fixed inputs."""
    from opulse.generation.typed import sample_value

    settings = settings or Settings()
    if (inputs is None and count < 1) or (inputs is not None and not inputs):
        raise ValueError("probe inputs cannot be empty")
    rng = random.Random(seed)
    if inputs is None:
        inputs = [[freeze(rng.choice(sample_values[kind])) if sample_values and kind in sample_values
                   else sample_value(kind, rng) for kind in operator.parameter_types]
                  for _ in range(count)]
    reducer = Reducer(registry, PythonRuntime(registry, settings.semantics.build()),
                      DefinitionParser(settings.symbols, registry))
    oracle = Oracle(registry, settings.symbols, settings.semantics.build())
    lengths, undefined = [], 0
    for row in inputs:
        args = tuple(freeze(value) for value in row)
        trace = reducer.reduce(Call(operator, tuple(Number(value) for value in args)))
        if trace.truncated:
            raise ValueError("probe trace exceeded the step limit")
        result = oracle.evaluate(operator, args).value
        if not ((result is NAN and trace.value is NAN) or
                (result is not NAN and trace.value is not NAN and result == trace.value)):
            raise ValueError("probe trace disagrees with the reference interpreter")
        undefined += result is NAN
        lengths.append(len(trace.steps))
    return {"count": len(inputs), "inputs": inputs, "nan_rate": undefined / len(inputs),
            "unfolded_length": sum(lengths) / len(lengths), "lengths": lengths}
