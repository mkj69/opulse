"""Self-play over an operator set: one role proposes definitions, the other computes with them.

Proposer
    :meth:`SelfPlay.task` gives a new operator symbol and shape, the base
    operations and a few existing definitions. The proposer writes a
    definition. :meth:`SelfPlay.evaluate` validates it with the acceptance
    checks of the operator generator (:meth:`OperatorFactory._reject_reason`:
    parameters used, not a renaming, distinct branches, not a duplicate, code
    agrees with the reference interpreter, defined on enough inputs, no
    degenerate subexpression, no dead branch) after checking that it parses,
    has the requested shape, uses only the listed operators and, if it calls
    itself, follows the configured recursion form.

Solver
    An accepted definition yields compute questions in the format of
    ``opulse bench`` (rules, definitions, ``What is the value of `...`?``) with
    reference answers from the interpreter. :func:`solver_reward` grades a
    response; :func:`proposer_reward` combines validity with a solve rate the
    caller measured.

Everything is plain functions over text, so any training framework can call
them. :class:`SelfPlayEnv` wraps the proposer role in the :class:`TextEnv`
interface.
"""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass, field
from pathlib import Path

from opulse.bench.context import closure
from opulse.bench.score import score_response
from opulse.config import Settings
from opulse.core.operator import RECURSIVE, Operator
from opulse.core.registry import OperatorRegistry
from opulse.core.semantics import NAN
from opulse.definition import ast
from opulse.definition.parser import DefinitionParser
from opulse.env.base import TextEnv, parse_action
from opulse.env.prompts import base_operators, base_rules, recursion_text, shape_text
from opulse.env.submission import (
    Shape,
    SubmissionError,
    applications,
    check_callees,
    check_recursion,
    definition_kind,
    parse_submission,
)
from opulse.expression.nodes import Call, Number, Variable, to_ast
from opulse.expression.render import ExpressionRenderer
from opulse.generation.drafts import Draft
from opulse.generation.pipeline import OperatorFactory
from opulse.generation.symbols import SymbolFactory

STYLE_FORM = {"bounded_mod": "A", "direct": "B", "peano": "C", "primitive": "D"}
INTRO = ("You are given operators defined from a few base operations. Use the rules and the "
         "definitions exactly as written; do not assume any familiar meaning of the symbols.")


@dataclass
class ProposerTask:
    seed: int
    symbol: str
    n_ary: int
    unary_position: str | None
    shown: list[str]  # func_ids of the definitions shown to the proposer
    prompt: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Proposal:
    valid: bool
    reason: str  # "accepted" or why the definition was rejected
    definition: str | None = None  # canonical text of the accepted definition
    kind: str | None = None
    layer: int | None = None
    questions: list[dict] = field(default_factory=list)
    operator: dict | None = None  # the accepted operator record (compiled code included)

    def to_dict(self) -> dict:
        return asdict(self)


def solver_reward(question: dict, response: str) -> float:
    """1.0 when the response's last ``Answer:`` line equals the reference answer, else 0.0."""
    return 1.0 if score_response(question, response)["correct"] else 0.0


def proposer_reward(proposal: Proposal, solve_rate: float | None = None, target: float = 0.5,
                    validity_weight: float = 0.5) -> float:
    """0 for an invalid proposal. A valid one earns 1.0 when no solve rate is given; with a solve
    rate ``s`` in [0, 1] it earns ``validity_weight + (1 - validity_weight) * d`` with
    ``d = 1 - |s - target| / max(target, 1 - target)``, which is largest when solvers succeed
    ``target`` of the time and smallest for questions every solver or no solver gets right."""
    if not proposal.valid:
        return 0.0
    if solve_rate is None:
        return 1.0
    if not 0.0 <= solve_rate <= 1.0:
        raise ValueError("solve_rate must lie in [0, 1]")
    difficulty = 1.0 - abs(solve_rate - target) / max(target, 1.0 - target)
    return validity_weight + (1.0 - validity_weight) * difficulty


class SelfPlay:
    """Prompts and rewards for the proposer and solver roles.

    ``visible`` existing operators (drawn per task, at most ``max_layer``) are shown with
    the definitions they depend on; ``questions`` compute questions are generated per
    accepted definition, each applying the new operator to inputs from the expression value
    range, nested ``question_depth - 1`` times.
    """

    def __init__(self, registry: OperatorRegistry, settings: Settings | None = None, *, visible: int = 4,
                 max_layer: int | None = None, questions: int = 8, question_depth: int = 1,
                 allow_nan: bool = False, operators_path: str | None = None,
                 config_path: str | None = None) -> None:
        if question_depth < 1:
            raise ValueError("question_depth must be at least 1")
        self.registry = registry
        self.settings = settings or Settings()
        self.visible, self.max_layer = visible, max_layer
        self.questions, self.question_depth, self.allow_nan = questions, question_depth, allow_nan
        self.operators_path, self.config_path = operators_path, config_path
        self.factory = OperatorFactory(self.settings, registry, random.Random(0))
        self.semantics = self.factory.semantics
        self.renderer = ExpressionRenderer(self.settings.symbols)
        self._bases = base_operators(registry)
        self._defined = [op for op in registry if op.definition is not None and op.is_base is None
                         and (max_layer is None or (op.recursive_layer or 0) <= max_layer)]

    @classmethod
    def from_files(cls, operators: str | Path, config: str | Path | None = None, **options) -> SelfPlay:
        settings = Settings.load(config) if config else Settings()
        return cls(OperatorRegistry.from_jsonl(operators), settings, operators_path=str(operators),
                   config_path=str(config) if config else None, **options)

    def config(self) -> dict:
        return {"operators": self.operators_path, "settings": self.config_path, "visible": self.visible,
                "max_layer": self.max_layer, "questions": self.questions, "question_depth": self.question_depth,
                "allow_nan": self.allow_nan}

    # ---------------------------------------------------------------- proposer
    def task(self, seed: int, attempts: int | None = None) -> ProposerTask:
        rng = random.Random(seed)
        symbols = SymbolFactory(self.settings.operators, rng)
        symbols.reserve(self.registry.symbols())
        symbol = symbols.new_symbol()
        n_ary, position = symbols.new_shape()
        picked = rng.sample(self._defined, min(self.visible, len(self._defined)))
        needed: set[str] = set()
        for op in picked:
            operands = tuple(Variable(n) for n in self.settings.symbols.operands(op.n_ary))
            needed |= {o.func_id for o in closure(self.registry, Call(op, operands))}
        shown = [op.func_id for op in self.registry.topological_order() if op.func_id in needed]
        stub = Operator(func_id="proposed", symbol=symbol, n_ary=n_ary, unary_position=position)
        return ProposerTask(seed, symbol, n_ary, position, shown, self._proposer_prompt(stub, shown, attempts))

    def _proposer_prompt(self, stub: Operator, shown: list[str], attempts: int | None) -> str:
        s = self.settings
        ops = s.operators
        lo, hi = s.expressions.value_min, s.expressions.value_max
        form = STYLE_FORM.get(s.recursion.style, "A")
        lines = [
            "Invent a new operator. Define it from the base operations"
            + (" and the operators below." if shown else "."),
            "",
            f"New operator: {shape_text(stub, s.symbols)}",
            "",
            "Rules:",
            base_rules(self.registry, self.semantics, s.symbols.nan),
            "",
            recursion_text(self.registry, (form,)),
        ]
        if shown:
            lines += ["", "Definitions you may use:", *(self.registry.get(f).definition for f in shown)]
        checks = [
            "it parses and defines the new operator with the parameters " + ", ".join(s.symbols.operands(stub.n_ary)),
            "it uses only the base operations and the operators listed above",
            "every parameter is used",
            "it is not a single call of another operator with the same number of arguments",
            "its branch bodies are all different",
            "it is not a copy of an existing definition",
        ]
        if ops.min_defined_share > 0:
            checks.append(f"it gives a value (not {s.symbols.nan}) on at least {ops.min_defined_share:.0%} of inputs "
                          f"in [{lo}, {hi}], unless it has no else branch or uses recursion form B, C or D")
        else:
            checks.append(f"it gives a value (not {s.symbols.nan}) on some inputs")
        if ops.reject_degenerate:
            checks.append("no subexpression that uses a parameter always has the same value (like a - a)")
        if ops.reject_dead_branches:
            checks.append("every branch can be taken" + (" and can give a value" if ops.undefined_branch_check else ""))
        lines += ["", "Your definition is accepted when:", *(f"  - {c}" for c in checks)]
        example = stub.apply_str(*s.symbols.operands(stub.n_ary))
        lines += ["", "Action: write one line SUBMIT <definition>, for example SUBMIT " + example + " = { ... }"]
        if attempts:
            lines.append(f"You have {attempts} attempt{'s' if attempts > 1 else ''}.")
        return "\n".join(lines)

    def evaluate(self, task: ProposerTask, text: str) -> Proposal:
        """Validate a proposed definition and, when it is accepted, build the solver's questions."""
        s = self.settings
        shape = Shape(task.symbol, task.n_ary, task.unary_position)
        stub = Operator(func_id="proposed", symbol=task.symbol, n_ary=task.n_ary, unary_position=task.unary_position)
        parser = DefinitionParser(s.symbols, self.registry)
        parser.add(stub)
        allowed = {op.func_id for op in self._bases} | set(task.shown)
        resolve = self.factory.oracle._resolve
        try:
            definition = parse_submission(text, parser, shape, s.symbols.operands(task.n_ary))
            check_callees(definition, shape, resolve, allowed)
            kind = definition_kind(definition, shape)
            if kind == RECURSIVE:
                wanted = STYLE_FORM.get(s.recursion.style, "A")
                check_recursion(definition, shape, resolve, primitive=wanted == "D")
                form = "D" if wanted == "D" else _recursion_form(definition)
                if form != wanted:
                    raise SubmissionError(f"recursion must use form {wanted} (this definition uses form {form})")
        except SubmissionError as exc:
            return Proposal(False, str(exc))
        draft = Draft(task.symbol, task.n_ary, task.unary_position, definition, kind,
                      complexity=_recursive_complexity(definition, shape, resolve) if kind == RECURSIVE else None)
        factory = self.factory
        factory.rng = random.Random(task.seed)
        try:
            operator = factory._compile(draft)
        except Exception as exc:  # noqa: BLE001 - any compile failure rejects the proposal
            return Proposal(False, f"cannot compile: {exc}")
        try:
            reason = factory._reject_reason(draft, operator, operator.recursive_layer)
            if reason is not None:
                return Proposal(False, reason)
            questions = self._questions(task, operator, definition)
            return Proposal(True, "accepted", operator.definition, kind, operator.recursive_layer, questions,
                            operator.to_dict())
        finally:
            factory.runtime.unload(operator)
            factory.oracle.forget(operator)

    # ------------------------------------------------------------------ solver
    def _questions(self, task: ProposerTask, operator: Operator, definition: ast.Definition) -> list[dict]:
        s = self.settings
        rng = random.Random(task.seed)
        oracle = self.factory.oracle
        callees: set[str] = set()
        for node in applications(definition):
            callee = oracle._resolve(node)
            if callee.definition is not None and callee.func_id != operator.func_id:
                operands = tuple(Variable(n) for n in s.symbols.operands(callee.n_ary))
                callees |= {o.func_id for o in closure(self.registry, Call(callee, operands))}
        context = [op.definition for op in self.registry.topological_order() if op.func_id in callees]
        context.append(operator.definition)
        lo, hi = s.expressions.value_min, s.expressions.value_max
        nan = s.symbols.nan

        def term(level: int):
            args = []
            for _ in range(operator.n_ary):
                if level > 1 and rng.random() < 0.5:
                    args.append(term(level - 1))
                else:
                    args.append(Number(rng.randint(lo, hi)))
            return Call(operator, tuple(args))

        questions, seen = [], set()
        for _ in range(self.questions * 50):
            if len(questions) >= self.questions:
                break
            tree = term(self.question_depth)
            expression = self.renderer.full(tree)
            if expression in seen:
                continue
            seen.add(expression)
            value = oracle.evaluate_expr(to_ast(tree), {}).value
            if value is NAN and not self.allow_nan:
                continue
            prompt = "\n".join([
                INTRO, "", "Rules:", base_rules(self.registry, self.semantics, nan), "",
                "Definitions:", *context, "",
                (f"What is the value of `{expression}`?\nReason step by step if you wish, then finish with a "
                 f"line of the form \"Answer: <integer or {nan}>\"."),
            ])
            answer = None if value is NAN else value
            questions.append({"id": f"selfplay-{task.seed}-{len(questions):03d}", "family": "compute",
                              "prompt": prompt, "answer": answer, "answer_text": nan if answer is None else str(answer),
                              "expression": expression, "definitions": context, "nan": nan})
        return questions


def _recursion_form(definition: ast.Definition) -> str:
    first = definition.branches[0].condition
    if not isinstance(first.left, ast.Var):
        return "A"
    # check_recursion admitted only ``v - 1`` or ``v ⁻`` in the loop slot of a recursive call:
    # a unary step there is form C.
    own = definition.lhs
    calls = [n for n in ast.iter_applications(definition.branches[1].expr)
             if (n.symbol, n.n_ary, n.unary_position) == (own.symbol, own.n_ary, own.unary_position)]
    slot = definition.parameters.index(first.left.name)
    step = calls[0].args[slot]
    return "C" if isinstance(step, ast.Apply) and step.n_ary == 1 else "B"


def _recursive_complexity(definition: ast.Definition, shape: Shape, resolve) -> tuple[int, int]:
    """Worst-case unfoldings and calls of a recursive definition (as recorded for generated ones)."""
    from opulse.solver.z3_encode import recursion_depth

    unfold = recursion_depth(definition)
    slots = sum(1 for n in ast.iter_applications(definition.branches[1].expr) if shape.matches(n))
    calls = 2**unfold - 1 if slots >= 2 else unfold
    return unfold, calls


class SelfPlayEnv(TextEnv):
    """The proposer role as a text environment: ``SUBMIT <definition>`` until one is accepted.

    The reward of an accepted definition is :func:`proposer_reward` without a solve rate
    (1.0); the episode's ``info`` holds the generated questions, so a caller can run solvers
    and compute the difficulty-aware reward afterwards.
    """

    name = "selfplay"

    def __init__(self, selfplay: SelfPlay, attempts: int = 3) -> None:
        super().__init__(selfplay.registry, attempts)
        self.selfplay = selfplay
        self.settings = selfplay.settings
        self.attempts = attempts

    @classmethod
    def from_files(cls, operators: str | Path, config: str | Path | None = None, attempts: int = 3,
                   **options) -> SelfPlayEnv:
        return cls(SelfPlay.from_files(operators, config, **options), attempts)

    def config(self) -> dict:
        return {**self.selfplay.config(), "attempts": self.attempts}

    def _start(self, seed: int) -> str:
        self.task = self.selfplay.task(seed, self.attempts)
        self.proposal: Proposal | None = None
        return self.task.prompt

    def _act(self, action: str) -> tuple[str, float, bool, dict]:
        parsed = parse_action(action, ("SUBMIT",))
        left = self.turns_left - 1
        if parsed is None:
            return (f"Invalid action: write SUBMIT <definition> on its own line.\nAttempts left: {left}.",
                    0.0, False, {"action": "invalid", "error": "no action"})
        proposal = self.selfplay.evaluate(self.task, parsed.argument)
        self.proposal = proposal
        info = {"action": "submit", "submission": parsed.argument, "valid": proposal.valid, "reason": proposal.reason}
        if not proposal.valid:
            return f"Rejected: {proposal.reason}.\nAttempts left: {left}.", 0.0, False, info
        info.update(kind=proposal.kind, layer=proposal.layer, questions=len(proposal.questions))
        text = (f"Accepted: {proposal.definition}\nKind: {proposal.kind.split('_')[0]}, layer {proposal.layer}. "
                f"{len(proposal.questions)} compute questions were generated from it.")
        return text, proposer_reward(proposal), True, info

    def _summary(self) -> dict:
        proposal = self.proposal
        summary = {"symbol": self.task.symbol, "n_ary": self.task.n_ary, "unary_position": self.task.unary_position,
                   "shown": self.task.shown, "valid": bool(proposal and proposal.valid)}
        if proposal is not None and proposal.valid:
            summary.update(definition=proposal.definition, kind=proposal.kind, layer=proposal.layer,
                           questions=[{k: q[k] for k in ("id", "expression", "answer", "answer_text")}
                                      for q in proposal.questions])
        return summary
