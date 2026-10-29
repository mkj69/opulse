"""Check compiled and stitched networks against the reference interpreter, slot by slot.

For every input row the verifier computes, with the reference interpreter only, the exact value
each slot stands for: the subexpression, condition, rest of a branch chain or call that the
compiler recorded for it, evaluated on the reference values of the slots it was bound to. It then
runs the network and compares token by token.

A slot can differ from its reference value in two allowed ways, both counted separately:

* it holds OOV and the block that wrote it read an OOV token (or a don't-care constant), so the
  network reports "out of range" instead of a value;
* the slot lies on a branch or inlined call that is not reached for this row's parameter values;
  the compiler pruned such code, and the slot is "don't care". A slot is checked only when its
  frame's parameter slots are checked themselves and hold a tuple the compiler kept.

Anything else is a failure. The output slot is also checked against an independent reference
function (by default the interpreter applied to the operator).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

import torch

from opulse.compile.compiler import COND, Const
from opulse.compile.network import CompiledNetwork
from opulse.compile.values import COND_NAN, COND_OOV, FALSE, OOV, TRUE
from opulse.core.semantics import NAN, base_operation_name
from opulse.definition import ast
from opulse.definition.interpreter import _Counter, _Undefined


@dataclass
class Report:
    rows: int = 0
    output_exact: int = 0
    output_oov: int = 0
    output_wrong: int = 0
    slot_checks: int = 0
    slot_exact: int = 0
    slot_oov: int = 0
    slot_dont_care: int = 0
    slot_wrong: int = 0
    one_hot: bool = True
    failures: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.output_wrong == 0 and self.slot_wrong == 0 and self.one_hot

    @property
    def exact(self) -> bool:
        """Correct, with every output an exact value (no OOV)."""
        return self.ok and self.output_oov == 0

    def to_dict(self) -> dict:
        data = {k: v for k, v in self.__dict__.items() if k != "failures"}
        data["failures"] = [str(f) for f in self.failures[:10]]
        data["ok"], data["exact"] = self.ok, self.exact
        return data


def _chain_value(interpreter, definition, start: int, env: dict):
    """Value of branches ``start..`` of a definition: what the remaining select chain computes."""
    counter = _Counter()
    try:
        for branch in definition.branches[start:]:
            if branch.condition is None or interpreter._condition(branch.condition, env, counter, 0):
                return interpreter._eval(branch.expr, env, counter, 0)
    except _Undefined:
        return NAN
    return NAN


def reference_value(oracle, origin: tuple, env: dict):
    """Exact value of one slot given the reference values of the refs it was bound to."""
    interpreter = oracle.interpreter
    kind = origin[0]
    if kind == "expr":
        return interpreter.evaluate_expr(origin[1], env).value
    if kind == "cond":
        try:
            return TRUE if interpreter._condition(origin[1], env, _Counter(), 0) else FALSE
        except _Undefined:
            return COND_NAN
    if kind == "chain":
        return _chain_value(interpreter, origin[1], origin[2], env)
    if kind == "frame":
        return oracle.evaluate(origin[1], tuple(env.values())).value
    raise ValueError(f"no reference for slot origin {kind!r}")


def _env_of(origin: tuple) -> dict:
    return origin[3] if origin[0] == "chain" else origin[2]


def verify(network: CompiledNetwork, oracle, rows: Iterable[tuple],
           reference: Callable[[tuple], object]) -> Report:
    """Run ``network`` on every row and compare every slot and the output with the interpreter."""
    rows = [tuple(row) for row in rows]
    vocab = network.vocab
    report = Report(rows=len(rows))
    with torch.no_grad():
        x = network(network.embed(rows))
    for name, info in network.slots.items():
        block = x[:, info.start:info.stop]
        if not bool(((block == 0) | (block == 1)).all()) or not bool((block.sum(1) == 1).all()):
            report.one_hot = False
            report.failures.append(f"slot {name} is not one-hot")
    tokens = {name: network.tokens(x, name).tolist() for name in network.slots}

    def held(name: str, r: int):
        index = tokens[name][r]
        return index if network.slots[name].kind == COND else vocab.value(index)

    def is_oov(name: str, r: int) -> bool:
        index = tokens[name][r]
        return index == (COND_OOV if network.slots[name].kind == COND else vocab.oov_index)

    for r, row in enumerate(rows):
        ref: dict[str, object] = dict(zip(network.inputs, row))
        checked = set(network.inputs)  # slots this row holds to their reference value
        exact_slots = set()
        for name, info in network.slots.items():
            if info.origin[0] == "input":
                continue
            env = {}
            for param, bound in _env_of(info.origin).items():
                env[param] = bound.value if isinstance(bound, Const) else ref.get(bound, OOV)
            unknown = any(value is OOV for value in env.values())
            node = info.origin[1] if info.origin[0] == "expr" else None
            defined_var = (isinstance(node, ast.Apply) and len(node.args) == 1
                           and isinstance(node.args[0], ast.Var)
                           and base_operation_name(node.symbol, node.n_ary, node.unary_position) == "defined"
                           and oracle._resolve(node).definition is None)
            ref[name] = OOV if unknown and not defined_var else reference_value(oracle, info.origin, env)
            if defined_var and vocab.clamp(ref[name]) is not OOV:
                exact_slots.add(name)
            if info.regions and not any(
                    all(isinstance(b, Const) or b in checked for b in refs)
                    and tuple((True, b.value) if isinstance(b, Const) else (False, held(b, r)) for b in refs) in tuples
                    for refs, tuples in info.regions):
                report.slot_dont_care += 1
                continue
            checked.add(name)
            report.slot_checks += 1
            expected = ref[name] if info.kind == COND else vocab.index(ref[name]) if ref[name] is not OOV else None
            got = tokens[name][r]
            if expected is not None and got == expected:
                report.slot_exact += 1
            elif is_oov(name, r) and name not in exact_slots and (
                    info.dont_care or expected is None or any(is_oov(s, r) for s in info.reads)
                                       or expected == vocab.oov_index):
                report.slot_oov += 1
            else:
                report.slot_wrong += 1
                report.failures.append((name, info.text, row, ref[name], held(name, r)))
        value = reference(row)
        got = tokens[network.output][r]
        if got == vocab.index(value):
            report.output_exact += 1
        elif is_oov(network.output, r) and network.output not in exact_slots:
            report.output_oov += 1
        else:
            report.output_wrong += 1
            report.failures.append(("output", row, value, held(network.output, r)))
    return report
