"""Compile an operator definition into residual MLP blocks with hand-set weights.

The compiler walks the definition tree once. Every operator application whose arguments are not
all constants becomes one block that reads its argument slots and writes a new slot:

* a base operation with one slot argument is a unary lookup table (one hidden unit per token);
* a base operation or comparison with two slot arguments is a binary lookup table (one hidden
  unit per pair of tokens);
* a branch definition is a chain of select blocks, ``then`` if the condition holds, otherwise
  the rest of the chain;
* a call of a defined operator is compiled inline: its parameters are bound to the argument
  slots and its body becomes more blocks.

A hidden unit that tests k one-hot coordinates has weight 2 on each and bias 1 - 2k: it is 1
when all k are set and at most -1 otherwise, so every unit has a margin of 1 before the ReLU.

Constants fold at compile time with the reference interpreter. A recursive call is unrolled as
far as the inputs can reach. To keep this finite, each inlined call is compiled only for the
argument tokens that can arrive on an evaluated path; a branch no such argument takes is dropped,
and its slots hold values nobody reads ("don't care"). The verifier checks every slot on the
inputs it is responsible for.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

import numpy as np

from opulse.compile.values import (
    COND_LABELS,
    COND_NAN,
    COND_OOV,
    COND_SIZE,
    FALSE,
    OOV,
    TRUE,
    Vocab,
    apply_atom,
    compare,
    logic_and,
    logic_not,
    logic_or,
    select,
)
from opulse.core.semantics import NAN, base_operation_name
from opulse.definition import ast
from opulse.definition.interpreter import COMPARISONS

INT, COND = "int", "cond"


class CompileError(ValueError):
    """The definition uses a form the compiler does not support, or exceeds a size limit."""


@dataclass(frozen=True)
class Const:
    """A compile-time constant: an exact integer or NaN (OOV marks a don't-care value)."""

    value: object


DONT_CARE = Const(OOV)

Ref = str | Const  # a slot name or a constant


@dataclass(frozen=True)
class Ctx:
    """Where an expression is compiled: the frame's parameters and the tuples that reach it."""

    params: tuple[str, ...]
    refs: tuple
    tuples: frozenset

    @property
    def region(self) -> tuple:
        return (self.refs, self.tuples)


@dataclass
class Slot:
    name: str
    kind: str  # INT or COND
    size: int
    origin: tuple  # how the verifier computes the reference value
    text: str = ""  # readable form of the value
    # (parameter refs, set of abstract parameter tuples): the slot is exact whenever the
    # frame's parameters hold one of these tuples. No regions means "on every input".
    regions: list = field(default_factory=list)


@dataclass
class Block:
    kind: str  # "table", "select" or "const"
    reads: tuple[str, ...]
    write: str
    w_in: np.ndarray  # hidden x (sum of read sizes)
    b_in: np.ndarray  # hidden
    w_out: np.ndarray  # write size x hidden
    label: str
    dont_care: bool = False  # reads a don't-care constant

    @property
    def hidden(self) -> int:
        return self.w_in.shape[0]

    def signature(self) -> tuple:
        """What the block computes, independent of slot names (for comparing networks)."""
        return (self.kind, self.w_in.shape, self.w_in.tobytes(), self.b_in.tobytes(), self.w_out.tobytes())


@dataclass
class Program:
    """Compiler output: slots, blocks in dependency order, input and output slots."""

    name: str
    vocab: Vocab
    inputs: list[str]
    output: str
    slots: dict[str, Slot]
    blocks: list[Block]


class Compiler:
    """Compiles operators of an :class:`~opulse.verify.Oracle` to :class:`Program` objects.

    ``input_values`` lists the values each input may hold. The default is every token of the
    vocabulary, including NaN and OOV, so the compiled module is correct for anything another
    module can write into its input slot. A narrower list gives a smaller network that is only
    correct on those inputs.
    """

    def __init__(self, oracle, vocab: Vocab, *, input_values: Iterable | None = None,
                 max_depth: int = 64, max_blocks: int = 20_000) -> None:
        self.oracle = oracle
        self.vocab = vocab
        self.input_values = list(input_values) if input_values is not None else vocab.values()
        self.max_depth = max_depth
        self.max_blocks = max_blocks
        self._frame_memo: dict[tuple, object] = {}

    # ------------------------------------------------------------------ entry
    def compile(self, operator, name: str | None = None) -> Program:
        definition = self._definition(operator)
        self.slots: dict[str, Slot] = {}
        self.blocks: list[Block] = []
        self._cse: dict[tuple, str] = {}
        self._calls: dict[tuple, list] = {}
        inputs = []
        for index, param in enumerate(definition.parameters):
            slot = self._new_slot(INT, ("input",), text=param, stem=f"in{index}_{param}")
            inputs.append(slot)
        env = dict(zip(definition.parameters, inputs))
        tuples = set(itertools.product(*[[(False, self.vocab.clamp(v)) for v in self.input_values]] * len(inputs)))
        result = self._frame(operator, env, tuples, depth=0)
        output = self._as_slot(result, ("frame", operator, env), text=f"{operator.symbol}(...)",
                               region=(tuple(inputs), tuples))
        return Program(name or operator.symbol, self.vocab, inputs, output, self.slots, self.blocks)

    # ------------------------------------------------------------- operators
    def _definition(self, operator) -> ast.Definition:
        if operator.definition is None:
            raise CompileError(f"{operator.symbol!r} is a base operation, not a definition")
        if operator.result_type != "int" or any(t != "int" for t in operator.parameter_types):
            raise CompileError("only integer operators are supported")
        return self.oracle._definition_of(operator)

    def _primitive(self, operator):
        return self.oracle.interpreter._primitive(operator)

    def _frame(self, operator, env: dict[str, Ref], tuples: set, depth: int) -> Ref:
        """Inline one call: ``env`` binds parameters, ``tuples`` are the arguments that reach it."""
        if depth > self.max_depth:
            raise CompileError(f"inlining {operator.symbol!r} deeper than {self.max_depth} calls")
        definition = self._definition(operator)
        params = definition.parameters
        param_refs = tuple(env[p] for p in params)
        remaining = frozenset(tuples)
        pieces = []
        final = None
        for index, branch in enumerate(definition.branches):
            if branch.condition is None:
                final = self._expr(branch.expr, env, Ctx(params, param_refs, remaining), depth) \
                    if remaining else DONT_CARE
                break
            tokens = {t: self.eval_cond(branch.condition, dict(zip(params, t)))[1] for t in remaining}
            seen = set(tokens.values())
            if seen <= {FALSE}:
                continue  # never holds where this branch is reached
            taken = frozenset(t for t in remaining if tokens[t] == TRUE)
            if seen == {TRUE}:
                final = self._expr(branch.expr, env, Ctx(params, param_refs, taken), depth)
                break
            cond = self._cond(branch.condition, env, Ctx(params, param_refs, remaining), depth)
            then = self._expr(branch.expr, env, Ctx(params, param_refs, taken), depth) if taken else DONT_CARE
            pieces.append((cond, then, index, remaining))
            remaining = frozenset(t for t in remaining if tokens[t] == FALSE)
        if final is None:
            final = Const(NAN) if remaining else DONT_CARE  # no branch matched
        result = final
        for cond, then, index, region in reversed(pieces):
            result = self._select(cond, then, result, ("chain", definition, index, env),
                                  (param_refs, region), f"{operator.symbol}[branch {index}:]")
        return result

    # ------------------------------------------------------------ expressions
    def _expr(self, node: ast.Expr, env: dict, ctx: Ctx, depth: int) -> Ref:
        if isinstance(node, ast.Var):
            return env[node.name]
        if isinstance(node, ast.Num):
            return Const(node.value)
        if isinstance(node, ast.NaN):
            return Const(NAN)
        if not isinstance(node, ast.Apply):
            raise CompileError(f"{type(node).__name__} is not supported")
        refs = [self._expr(arg, env, ctx, depth) for arg in node.args]
        callee = self.oracle._resolve(node)
        primitive = self._primitive(callee)
        is_defined = base_operation_name(callee.symbol, callee.n_ary, callee.unary_position) == "defined"
        if all(isinstance(ref, Const) for ref in refs):
            values = tuple(ref.value for ref in refs)
            if any(value is OOV for value in values):
                return DONT_CARE
            if primitive is not None:
                return Const(primitive(*values))
            return Const(self.oracle.evaluate(callee, values).value)
        origin = ("expr", node, env)
        text = node.symbol
        if primitive is not None:
            if len(refs) > 2:
                raise CompileError("base operations with more than two arguments are not supported")
            return self._table(("atom", callee.func_id), refs, INT,
                               lambda avs: apply_atom(primitive, avs, self.vocab, defined=is_defined)[1],
                               origin, ctx.region, text)
        # A defined operator: inline its body for the argument tuples that reach this call.
        params = self._definition(callee).parameters
        frame = {
            tuple(self.eval_expr(arg, dict(zip(ctx.params, t))) for arg in node.args)
            for t in ctx.tuples
        }
        if not frame:
            return DONT_CARE
        key = (callee.func_id, tuple(refs))
        for known, ref in self._calls.get(key, []):
            if frame <= known:
                return ref
        result = self._frame(callee, dict(zip(params, refs)), frame, depth + 1)
        result = self._as_slot(result, ("frame", callee, dict(zip(params, refs))), text=f"{callee.symbol}(...)",
                               region=(tuple(refs), frame))
        self._calls.setdefault(key, []).append((frame, result))
        return result

    def _cond(self, node: ast.Condition, env: dict, ctx: Ctx, depth: int) -> Ref:
        if isinstance(node, ast.Compare):
            left = self._expr(node.left, env, ctx, depth)
            right = self._expr(node.right, env, ctx, depth)
            op = COMPARISONS[node.op]
            return self._logic(("cmp", node.op), [left, right], lambda avs: compare(op, *avs)[1],
                               ("cond", node, env), ctx.region, node.op)
        if isinstance(node, (ast.And, ast.Or)):
            left = self._cond(node.left, env, ctx, depth)
            needed = TRUE if isinstance(node, ast.And) else FALSE
            right_tuples = frozenset(t for t in ctx.tuples
                                     if self.eval_cond(node.left, dict(zip(ctx.params, t)))[1] == needed)
            right = (self._cond(node.right, env, Ctx(ctx.params, ctx.refs, right_tuples), depth)
                     if right_tuples else Const(FALSE))
            fn = logic_and if isinstance(node, ast.And) else logic_or
            name = "and" if isinstance(node, ast.And) else "or"
            return self._logic((name,), [left, right], lambda avs: fn(*avs)[1], ("cond", node, env), ctx.region, name)
        if isinstance(node, ast.Not):
            operand = self._cond(node.operand, env, ctx, depth)
            return self._logic(("not",), [operand], lambda avs: logic_not(*avs)[1], ("cond", node, env), ctx.region, "not")
        raise CompileError("conditions on bool-valued expressions are not supported")

    def _logic(self, key, refs, fn, origin, region, text) -> Ref:
        if all(isinstance(ref, Const) for ref in refs):
            if any(ref.value is OOV for ref in refs):
                return DONT_CARE
            return Const(fn([(True, ref.value) for ref in refs]))
        return self._table(key, refs, COND, fn, origin, region, text)

    # ----------------------------------------------------------------- blocks
    def _kind_of(self, ref: Ref) -> str:
        return self.slots[ref].kind

    def _tokens(self, kind: str) -> list:
        return self.vocab.values() if kind == INT else list(range(COND_SIZE))

    def _index(self, kind: str, value) -> int:
        return self.vocab.index(value) if kind == INT else value

    def _table(self, key, refs: list[Ref], kind: str, fn: Callable, origin, region, text) -> str:
        """A lookup-table block: ``fn`` maps abstract argument values to the output token."""
        cse = (key, tuple(refs))
        if cse in self._cse:
            slot = self.slots[self._cse[cse]]
            self._add_region(slot, region)
            return slot.name
        slot_refs = list(dict.fromkeys(ref for ref in refs if not isinstance(ref, Const)))  # x * x reads x once
        sizes = [self.slots[ref].size for ref in slot_refs]
        token_lists = [self._tokens(self.slots[ref].kind) for ref in slot_refs]
        combos = list(itertools.product(*[range(n) for n in sizes]))
        out_size = self.vocab.size if kind == INT else COND_SIZE
        w_in = np.zeros((len(combos), sum(sizes)))
        b_in = np.full(len(combos), 1.0 - 2.0 * len(slot_refs))
        w_out = np.zeros((out_size, len(combos)))
        offsets = np.cumsum([0, *sizes])
        for unit, combo in enumerate(combos):
            held = {ref: tokens[i] for ref, tokens, i in zip(slot_refs, token_lists, combo)}
            avs = [(True, ref.value) if isinstance(ref, Const) else (False, held[ref]) for ref in refs]
            for position, i in enumerate(combo):
                w_in[unit, offsets[position] + i] = 2.0
            w_out[self._index(kind, fn(avs)), unit] = 1.0
        name = self._new_slot(kind, origin, text=_describe(text, refs, self.slots), region=region)
        dont_care = any(isinstance(ref, Const) and ref.value is OOV for ref in refs)
        self._add_block(Block("table", tuple(slot_refs), name, w_in, b_in, w_out, text, dont_care))
        self._cse[cse] = name
        return name

    def _select(self, cond: Ref, then: Ref, other: Ref, origin, region, text) -> Ref:
        if isinstance(cond, Const):
            if cond.value is OOV:
                return DONT_CARE
            chosen = select(cond.value, then, other)
            return chosen if isinstance(chosen, (str, Const)) else Const(chosen)
        cse = (("select",), (cond, then, other))
        if cse in self._cse:
            slot = self.slots[self._cse[cse]]
            self._add_region(slot, region)
            return slot.name
        reads = [cond] + [ref for ref in (then, other) if not isinstance(ref, Const)]
        offsets = {cond: 0}
        width = COND_SIZE
        for ref in (then, other):
            if not isinstance(ref, Const) and ref not in offsets:
                offsets[ref] = width
                width += self.slots[ref].size
        rows, biases, targets = [], [], []

        def unit(columns, target):  # fires (value 1) when every listed coordinate is 1
            row = np.zeros(width)
            row[columns] = 2.0
            rows.append(row)
            biases.append(1.0 - 2.0 * len(columns))
            targets.append(target)

        for branch_token, ref in ((TRUE, then), (FALSE, other)):
            if isinstance(ref, Const):
                unit([branch_token], self.vocab.index(ref.value))
            else:
                for i in range(self.vocab.size):
                    unit([branch_token, offsets[ref] + i], i)
        unit([COND_NAN], self.vocab.nan_index)
        unit([COND_OOV], self.vocab.oov_index)
        w_in = np.stack(rows)
        w_out = np.zeros((self.vocab.size, len(rows)))
        w_out[targets, np.arange(len(rows))] = 1.0
        reads = tuple(dict.fromkeys(reads))
        name = self._new_slot(INT, origin, text=text, region=region)
        dont_care = any(isinstance(ref, Const) and ref.value is OOV for ref in (then, other))
        self._add_block(Block("select", reads, name, w_in, np.array(biases), w_out, "select", dont_care))
        self._cse[cse] = name
        return name

    def _as_slot(self, ref: Ref, origin, text: str, region=None) -> str:
        if not isinstance(ref, Const):
            return ref
        name = self._new_slot(INT, origin, text=f"{text} = {ref.value!r}", region=region)
        w_out = np.zeros((self.vocab.size, 1))
        w_out[self.vocab.index(ref.value), 0] = 1.0
        self._add_block(Block("const", (), name, np.zeros((1, 0)), np.ones(1), w_out, "const",
                              ref.value is OOV))
        return name

    def _add_block(self, block: Block) -> None:
        if len(self.blocks) >= self.max_blocks:
            raise CompileError(f"more than {self.max_blocks} blocks")
        self.blocks.append(block)

    def _new_slot(self, kind: str, origin, *, text: str = "", stem: str | None = None, region=None) -> str:
        name = stem or f"s{len(self.slots)}"
        size = self.vocab.size if kind == INT else COND_SIZE
        slot = Slot(name, kind, size, origin, text)
        self._add_region(slot, region)
        self.slots[name] = slot
        return name

    @staticmethod
    def _add_region(slot: Slot, region) -> None:
        if region is not None:
            slot.regions.append((region[0], frozenset(region[1])))

    # ---------------------------------------------- abstract evaluation (pruning)
    def eval_expr(self, node: ast.Expr, env: dict) -> tuple:
        """The value a compiled expression holds, given abstract parameter values."""
        if isinstance(node, ast.Var):
            return env[node.name]
        if isinstance(node, ast.Num):
            return True, node.value
        if isinstance(node, ast.NaN):
            return True, NAN
        if not isinstance(node, ast.Apply):
            raise CompileError(f"{type(node).__name__} is not supported")
        args = tuple(self.eval_expr(arg, env) for arg in node.args)
        callee = self.oracle._resolve(node)
        primitive = self._primitive(callee)
        if primitive is not None:
            is_defined = base_operation_name(callee.symbol, callee.n_ary, callee.unary_position) == "defined"
            return apply_atom(primitive, args, self.vocab, defined=is_defined)
        if all(is_const for is_const, _ in args):
            return True, self.oracle.evaluate(callee, tuple(v for _, v in args)).value
        return False, self.vocab.clamp(self._eval_frame(callee, args, 0))

    def _eval_frame(self, operator, args: tuple, depth: int):
        key = (operator.func_id, args)
        if key in self._frame_memo:
            return self._frame_memo[key]
        if depth > self.max_depth:
            raise CompileError(f"recursion of {operator.symbol!r} deeper than {self.max_depth}")
        definition = self._definition(operator)
        env = dict(zip(definition.parameters, args))
        value = NAN
        for branch in definition.branches:
            token = TRUE if branch.condition is None else self.eval_cond(branch.condition, env)[1]
            if token == TRUE:
                value = self.eval_expr(branch.expr, env)[1]
                break
            if token != FALSE:
                value = NAN if token == COND_NAN else OOV
                break
        self._frame_memo[key] = value
        return value

    def eval_cond(self, node: ast.Condition, env: dict) -> tuple:
        if isinstance(node, ast.Compare):
            return compare(COMPARISONS[node.op], self.eval_expr(node.left, env), self.eval_expr(node.right, env))
        if isinstance(node, ast.And):
            left = self.eval_cond(node.left, env)
            return logic_and(left, self.eval_cond(node.right, env) if left[1] == TRUE else (True, FALSE))
        if isinstance(node, ast.Or):
            left = self.eval_cond(node.left, env)
            return logic_or(left, self.eval_cond(node.right, env) if left[1] == FALSE else (True, FALSE))
        if isinstance(node, ast.Not):
            return logic_not(self.eval_cond(node.operand, env))
        raise CompileError("conditions on bool-valued expressions are not supported")


def _describe(op: str, refs: list[Ref], slots: dict) -> str:
    parts = [repr(ref.value) if isinstance(ref, Const) else ref for ref in refs]
    return f"{op}({', '.join(parts)})"


__all__ = [
    "COND",
    "COND_LABELS",
    "COND_OOV",
    "DONT_CARE",
    "INT",
    "Block",
    "CompileError",
    "Compiler",
    "Const",
    "Program",
    "Slot",
]
