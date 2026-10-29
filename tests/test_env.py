"""Multi-turn environments: determinism, grading, budgets, actions, self-play and replay."""

import importlib.util
import json
import random
import sys
import threading
import types
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from conftest import INITIAL_OPERATORS

from opulse.bench.check import answer_from_prompt, base_registry
from opulse.cli.main import main
from opulse.config import Settings
from opulse.core import OperatorRegistry
from opulse.core.semantics import NAN
from opulse.definition.parser import DefinitionParser
from opulse.env import (
    BlackBoxEnv,
    EnvError,
    SelfPlay,
    SelfPlayEnv,
    parse_action,
    proposer_reward,
    replay,
    score_transcripts,
    solver_reward,
)
from opulse.expression.nodes import from_ast
from opulse.generation.drafts import Draft
from opulse.generation.pipeline import OperatorFactory, build_layers
from opulse.verify import Oracle

ROOT = Path(__file__).resolve().parents[1]
INITIAL = INITIAL_OPERATORS

PLUS2 = "a ⊕ b = { (a + b) * 2 }"
STEP = "a ⊞ b = { a - b, if a > 10; b, else }"
LOOP = ("a ⊛ b = { b, if a % 4 == 0; (((a % 4) - 1) ⊛ b) ⊕ b, if a % 4 > 0; "
        "(((a % 4) + 1) ⊛ b) ⊕ b, if a % 4 < 0 }")
UNUSED = "a ⊗ b = { a * 7 }"  # defined, but not a callee of anything above


def _define(factory: OperatorFactory, text: str) -> None:
    from opulse.core.operator import BINARY, BRANCH, RECURSIVE, Operator
    from opulse.env.submission import Shape, definition_kind

    symbol = text.split()[1]
    parser = DefinitionParser(factory.settings.symbols, factory.registry)
    parser.add(Operator(func_id="stub", symbol=symbol, n_ary=BINARY))
    definition = parser.parse(text)
    kind = definition_kind(definition, Shape(symbol, BINARY, None))
    draft = Draft(symbol, BINARY, None, definition, kind, complexity=(3, 3) if kind == RECURSIVE else None)
    operator = factory._compile(draft)
    assert kind in (BRANCH, RECURSIVE) or operator.definition_type
    factory.add(operator)


@pytest.fixture(scope="module")
def hand() -> OperatorRegistry:
    registry = OperatorRegistry.from_jsonl(INITIAL)
    factory = OperatorFactory(Settings(), registry, random.Random(0))
    for text in (PLUS2, STEP, LOOP, UNUSED):
        _define(factory, text)
    return registry


@pytest.fixture(scope="module")
def generated() -> OperatorRegistry:
    registry = OperatorRegistry.from_jsonl(INITIAL)
    build_layers(OperatorFactory(Settings(), registry, random.Random(5)), [6, 3])
    return registry


def _env(registry, symbol=None, **options) -> BlackBoxEnv:
    """A black-box env whose hidden operator is ``symbol`` (found by trying seeds)."""
    options.setdefault("rlimit", 5_000_000)
    env = BlackBoxEnv(registry, **options)
    if symbol is None:
        env.reset(0)
        return env
    for seed in range(200):
        env.reset(seed)
        if env.target.symbol == symbol:
            return env
    raise AssertionError(f"no seed hides {symbol}")


# ------------------------------------------------------------------ determinism
def test_same_seed_same_episode(generated):
    actions = ["QUERY 3 5", "QUERY -2 7", "QUERY 4", "nonsense", "SUBMIT a ⊕ b = { a }"]

    def run(seed):
        env = BlackBoxEnv(generated, query_budget=3, rlimit=1_000_000)
        env.reset(seed)
        for action in actions:
            if env.step(action)[2]:
                break
        return env.transcript()

    first, second = run(4), run(4)
    assert first == second
    observations = {BlackBoxEnv(generated).reset(seed) for seed in range(8)}
    assert len(observations) > 1  # different seeds hide different operators


def test_self_play_task_is_deterministic(generated):
    play = SelfPlay(generated, visible=2)
    assert play.task(7) == play.task(7)
    assert play.task(7).prompt != play.task(8).prompt or play.task(7).symbol != play.task(8).symbol


# --------------------------------------------------------------------- grading
def test_equivalent_definition_written_differently_is_accepted(hand):
    env = _env(hand, "⊕")
    _observation, reward, done, info = env.step("SUBMIT a ⊕ b = { (b + a) + (a + b) }")
    assert (reward, done) == (1.0, True)
    assert info["verdict"]["status"] == "proved"
    assert env.transcript()["info"]["solved"] is True


def test_near_miss_is_rejected_with_a_real_counterexample(hand):
    env = _env(hand, "⊞", submissions=2)
    _, reward, done, info = env.step("SUBMIT a ⊞ b = { a - b, if a >= 10; b, else }")
    assert (reward, done) == (0.0, False)
    verdict = info["verdict"]
    assert verdict["status"] == "refuted"
    point = (verdict["counterexample"]["a"], verdict["counterexample"]["b"])
    oracle = Oracle(hand)
    expected = oracle.evaluate(env.target, point).value
    assert verdict["expected"] == (None if expected is NAN else expected)
    assert verdict["expected"] != verdict["got"]
    assert point[0] == 10  # the only inputs where the two definitions differ
    _, reward, done, info = env.step("SUBMIT a ⊞ b = { a - b, if 10 < a; b, else }")
    assert (reward, done) == (1.0, True)


def test_recursive_definition_in_another_form_is_accepted(hand):
    env = _env(hand, "⊛")
    text = ("a ⊛ b = { b, if a % 4 == 0; b ⊕ (((a % 4) - 1) ⊛ b), if a % 4 > 0; "
            "b ⊕ (((a % 4) + 1) ⊛ b), if a % 4 < 0 }")
    _, reward, _, info = env.step("SUBMIT " + text)
    assert reward == 1.0 and info["verdict"]["equivalent"]
    same = _env(hand, "⊛")
    assert same.step("SUBMIT " + LOOP)[3]["verdict"]["status"] == "identical"


def test_query_shaping(hand):
    env = _env(hand, "⊕", shaping=0.5, query_budget=4)
    env.step("QUERY 1 2")
    _, reward, _, _ = env.step("SUBMIT " + PLUS2)
    assert reward == pytest.approx(1 - 0.5 * 1 / 4)


# ---------------------------------------------------------------------- budgets
def test_query_budget(hand):
    env = _env(hand, "⊕", query_budget=2)
    assert env.step("QUERY 1 2")[0].startswith("1 ⊕ 2 = 6")
    env.step("QUERY 3 4")
    observation, _, done, info = env.step("QUERY 5 6")
    assert not done and info["action"] == "invalid" and "no queries left" in observation
    assert env.queries_used == 2


def test_turn_budget(hand):
    env = _env(hand, "⊕", turn_budget=3)
    assert not env.step("QUERY 1 2")[2]
    assert not env.step("hello")[2]
    _observation, reward, done, info = env.step("QUERY 2 2")
    assert done and reward == 0.0 and info["end"] == "turn budget"
    with pytest.raises(EnvError):
        env.step("QUERY 1 1")


def test_submission_budget_and_order(hand):
    with pytest.raises(EnvError):
        BlackBoxEnv(hand).step("QUERY 1 1")
    env = _env(hand, "⊕", submissions=2)
    assert not env.step("SUBMIT a ⊕ b = { a + b }")[2]
    _observation, reward, done, info = env.step("SUBMIT a ⊕ b = { a * b }")
    assert done and reward == 0.0 and info["end"] == "submission budget"


# ---------------------------------------------------------------------- actions
@pytest.mark.parametrize("action, message", [
    ("hello", "write QUERY or SUBMIT"),
    ("QUERY 1", "QUERY needs 2 integer inputs"),
    ("QUERY 1 2 3", "QUERY needs 2 integer inputs"),
    ("QUERY 1 x", "QUERY needs 2 integer inputs"),
    ("QUERY 500 1", "must lie in [-100, 100]"),
    ("QUERY ⊞ 1 2", "unknown operator"),
])
def test_invalid_queries(hand, action, message):
    env = _env(hand, "⊕")
    observation, reward, done, info = env.step(action)
    assert message in observation and info["action"] == "invalid" and not done and reward == 0.0
    assert env.queries_used == 0


@pytest.mark.parametrize("definition, message", [
    ("a ⊕ b = { a + }", "parse error"),
    ("a ⊞ b = { a + b }", "must define '⊕'"),
    ("a ⊕ b = { a ⊗ b }", "not available"),  # a real operator, but not one the agent was shown
    ("a ⊕ b = { (a + 1) ⊕ b, if a > 0; b, else }", "recursion forms"),
    ("a ⊕ b = { b, if a == 0; (a - 1) ⊕ b, if a > 0; (a + 1) ⊕ b, if a < 0 }", "recursion forms"),
])
def test_invalid_submissions(hand, definition, message):
    env = _env(hand, "⊕")
    observation, reward, done, info = env.step("SUBMIT " + definition)
    assert message in observation and reward == 0.0 and done and info["valid"] is False


def test_bounded_direct_recursion_is_accepted_as_valid(hand):
    env = _env(hand, "⊕", submissions=2)
    text = "a ⊕ b = { b, if a == 0; ((a - 1) ⊕ b) + 1, if a > 0 and a <= 5; ((a + 1) ⊕ b) - 1, if a < 0 and a >= - 5 }"
    _, _reward, done, info = env.step("SUBMIT " + text)
    assert info["valid"] is True and info["verdict"]["status"] == "refuted" and not done


def test_hidden_callees_can_be_queried(hand):
    env = _env(hand, "⊛", callees="hidden")
    assert "(((a % 4) - 1)" not in env.transcript()["observation"].split("Operators you may use")[1]
    assert "  a ⊕ b (binary)" in env.transcript()["observation"]
    observation, _, _, info = env.step("QUERY ⊕ 2 3")
    assert observation.startswith("2 ⊕ 3 = 10") and info["operator"] == "⊕"
    observation, _, _, _ = env.step("QUERY -3 4")
    assert observation.startswith("(-3) ⊛ 4 = ")


def test_parse_action():
    assert parse_action("<think>QUERY 1 2</think>\nI will submit.\nSUBMIT a ⊕ b = { a }", ("QUERY", "SUBMIT")).keyword == "SUBMIT"
    action = parse_action("Reasoning...\n**SUBMIT**\n`a ⊕ b = { a }`", ("QUERY", "SUBMIT"))
    assert action.keyword == "SUBMIT" and action.argument == "a ⊕ b = { a }"
    assert parse_action("query 3 4", ("QUERY",)).argument == "3 4"
    assert parse_action("nothing here", ("QUERY",)) is None


# -------------------------------------------------------------------- self-play
def _task(play: SelfPlay, n_ary=2):
    for seed in range(100):
        task = play.task(seed)
        if task.n_ary == n_ary:
            return task
    raise AssertionError("no binary task")


def test_self_play_rejects_and_accepts(hand):
    play = SelfPlay(hand, visible=4)
    task = _task(play)
    f = task.symbol
    assert {hand.get(i).symbol for i in task.shown} >= {"⊕"}
    bad_loop = play.evaluate(task, f"a {f} b = {{ (a + 1) {f} b, if a > 0; b, else }}")
    assert not bad_loop.valid and "recursion forms" in bad_loop.reason
    unbounded = play.evaluate(task, f"a {f} b = {{ b, if a == 0; (a - 1) {f} b, if a > 0; (a + 1) {f} b, if a < 0 }}")
    assert not unbounded.valid
    ignored = play.evaluate(task, f"a {f} b = {{ (a * 3) + 1 }}")
    assert not ignored.valid and ignored.reason == "unused parameter ['b']"
    renaming = play.evaluate(task, f"a {f} b = {{ b ⊕ a }}")
    assert not renaming.valid and renaming.reason == "single call of the same arity"
    good = play.evaluate(task, f"a {f} b = {{ (a * 3) + (b ⊕ a) }}")
    assert good.valid and good.reason == "accepted" and good.layer == 0 and len(good.questions) == play.questions
    looped = play.evaluate(task, f"a {f} b = {{ b, if a % 5 == 0; (((a % 5) - 1) {f} b) + b, if a % 5 > 0; "
                                 f"(((a % 5) + 1) {f} b) - b, if a % 5 < 0 }}")
    assert looped.valid and looped.kind == "recursive_definition" and looped.layer == 1
    # Validation leaves the operator set unchanged.
    assert hand.find(f, 2) is None


def test_self_play_answers_match_the_interpreter(hand):
    play = SelfPlay(hand, visible=4, questions=6, question_depth=2)
    task = _task(play)
    proposal = play.evaluate(task, f"a {task.symbol} b = {{ (a * 3) + (b ⊕ a) }}")
    assert proposal.valid
    base = base_registry(hand)
    registry = OperatorRegistry(list(hand))
    from opulse.core.operator import Operator

    registry.add(Operator.from_dict({**proposal.operator, "id": len(hand) + 1}))
    oracle = Oracle(registry)
    parser = DefinitionParser(Settings().symbols, registry)
    for question in proposal.questions:
        tree = parser.parse_expr(question["expression"], expression_mode=True)
        value = oracle.evaluate_expr(tree, {}).value
        assert question["answer"] == (None if value is NAN else value)
        assert from_ast(tree, registry) is not None
        assert answer_from_prompt(question, base) == value  # derivable from the prompt alone
        assert solver_reward(question, f"work...\nAnswer: {question['answer_text']}") == 1.0
        assert solver_reward(question, "Answer: 123456789") == 0.0


def test_proposer_reward(hand):
    play = SelfPlay(hand)
    task = _task(play)
    good = play.evaluate(task, f"a {task.symbol} b = {{ (a * 3) + (b ⊕ a) }}")
    bad = play.evaluate(task, f"a {task.symbol} b = {{ a }}")
    assert proposer_reward(bad, 0.5) == 0.0
    assert proposer_reward(good) == 1.0
    assert proposer_reward(good, 0.5) == 1.0
    assert proposer_reward(good, 0.0) == proposer_reward(good, 1.0) == 0.5
    assert proposer_reward(good, 0.25) == pytest.approx(0.75)


def test_self_play_env(hand):
    env = SelfPlayEnv(SelfPlay(hand), attempts=2)
    seed = next(s for s in range(100) if env.selfplay.task(s).n_ary == 2)
    env.reset(seed)
    f = env.task.symbol
    observation, reward, done, info = env.step(f"SUBMIT a {f} b = {{ a }}")
    assert not done and "Rejected" in observation
    observation, reward, done, info = env.step(f"SUBMIT a {f} b = {{ (a * 3) + (b ⊕ a) }}")
    assert done and reward == 1.0 and info["valid"]
    summary = env.transcript()["info"]
    assert summary["valid"] and len(summary["questions"]) == 8


# ------------------------------------------------------------- replay and CLI
def test_replay_reproduces_and_detects_changes(hand):
    env = _env(hand, "⊞", submissions=2)
    env.step("QUERY 11 3")
    env.step("SUBMIT a ⊞ b = { b }")
    env.step("SUBMIT " + STEP)
    transcript = json.loads(json.dumps(env.transcript()))
    result = replay(transcript, registry=hand)
    assert result["match"] and result["reward"] == 1.0 and result["solved"]
    transcript["steps"][0]["observation"] = "11 ⊞ 3 = 0"
    assert not replay(transcript, registry=hand)["match"]
    _results, summary = score_transcripts([env.transcript()], hand)
    assert summary["reproduced"] == 1 and summary["mean_reward"] == 1.0


def test_cli_play_and_replay(tmp_path, hand, capsys):
    ops = tmp_path / "ops.jsonl"
    hand.to_jsonl(ops)
    transcripts = tmp_path / "episodes.jsonl"
    for seed in range(3):
        env = BlackBoxEnv.from_files(ops)
        env.reset(seed)
        moves = tmp_path / f"moves{seed}.txt"
        moves.write_text(f"QUERY 2 3\nSUBMIT {env.target.definition}\n", encoding="utf-8")
        assert main(["env", "play", "--operators", str(ops), "--seed", str(seed), "--actions", str(moves),
                     "--transcript", str(transcripts)]) == 0
    assert "reward: 1" in capsys.readouterr().out
    moves = tmp_path / "self.txt"
    moves.write_text("SUBMIT nothing\n", encoding="utf-8")
    assert main(["env", "play", "--env", "selfplay", "--operators", str(ops), "--seed", "1", "--actions",
                 str(moves), "--transcript", str(transcripts)]) == 0
    capsys.readouterr()
    out = tmp_path / "scores.jsonl"
    assert main(["env", "replay", "--transcripts", str(transcripts), "--out", str(out)]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["episodes"] == 4 and summary["reproduced"] == 4 and summary["solved"] == 3
    assert len(out.read_text().splitlines()) == 4
    from opulse.canary import CANARY

    assert all(json.loads(line)["meta"]["canary"] == CANARY for line in transcripts.read_text().splitlines())
    assert all(json.loads(line)["meta"]["canary"] == CANARY for line in out.read_text().splitlines())


# -------------------------------------------------------- endpoint and gymnasium
def test_endpoint_example_with_a_local_server(tmp_path, hand):
    replies = iter(["Let me look.\nQUERY 1 1", "SUBMIT a ⊕ b = { a }"] * 10)

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            body = json.dumps({"choices": [{"message": {"content": next(replies)}, "finish_reason": "stop"}]})
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body.encode())

        def log_message(self, *args):
            pass

    try:
        server = HTTPServer(("127.0.0.1", 0), Handler)
    except PermissionError:
        pytest.skip("local sockets are unavailable in this sandbox")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    ops = tmp_path / "ops.jsonl"
    hand.to_jsonl(ops)
    spec = importlib.util.spec_from_file_location("run_endpoint", ROOT / "examples" / "env" / "run_endpoint.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        module.main(["--operators", str(ops), "--episodes", "2", "--out", str(tmp_path / "run"), "--model", "m",
                     "--base-url", f"http://127.0.0.1:{server.server_port}/v1"])
    finally:
        server.shutdown()
    summary = json.loads((tmp_path / "run" / "summary.json").read_text())
    assert summary["episodes"] == 2 and summary["reproduced"] == 2
    rows = [json.loads(line) for line in (tmp_path / "run" / "transcripts.jsonl").read_text().splitlines()]
    assert all(len(row["steps"]) == 2 and row["steps"][0]["info"]["action"] == "query" for row in rows)


def test_gymnasium_adapter(monkeypatch, hand):
    gymnasium = types.ModuleType("gymnasium")
    spaces = types.ModuleType("gymnasium.spaces")

    class Env:
        def reset(self, *, seed=None, options=None):
            self.seeded = seed

    class Text:
        def __init__(self, max_length, charset):
            self.max_length, self.charset = max_length, charset

    gymnasium.Env, spaces.Text, gymnasium.spaces = Env, Text, spaces
    monkeypatch.setitem(sys.modules, "gymnasium", gymnasium)
    monkeypatch.setitem(sys.modules, "gymnasium.spaces", spaces)
    from opulse.env.gym import to_gymnasium

    env = to_gymnasium(BlackBoxEnv(hand, turn_budget=2))
    observation, info = env.reset(seed=1)
    assert "Hidden operator" in observation and info == {}
    assert set(observation) <= env.observation_space.charset
    _, _, terminated, truncated, _ = env.step("QUERY 1 1")
    assert not terminated and not truncated
    _, _, terminated, truncated, _ = env.step("QUERY 1 2")
    assert truncated and not terminated


def test_replay_checks_info_and_options(hand):
    env = _env(hand, "⊕")
    env.step("SUBMIT a ⊕ b = { a }")
    transcript = json.loads(json.dumps(env.transcript()))
    assert replay(transcript, registry=hand)["match"]
    transcript["steps"][0]["info"]["verdict"]["expected"] = 0
    assert not replay(transcript, registry=hand)["match"]
    with pytest.raises(ValueError):
        BlackBoxEnv(hand, shaping=float("nan"))


def test_direct_recursion_form_is_recognised(hand):
    from dataclasses import replace

    settings = Settings()
    settings = replace(settings, recursion=replace(settings.recursion, style="direct"))
    play = SelfPlay(hand, settings)
    task = _task(play)
    f = task.symbol
    text = (f"a {f} b = {{ b, if a == 0; ((a - 1) {f} b) + (- a), if a > 0 and a <= 6; "
            f"((a + 1) {f} b) - b, if a < 0 and a >= - 6 }}")
    proposal = play.evaluate(task, text)
    assert "form" not in proposal.reason, proposal.reason


def test_black_box_three_argument_prompt_and_default_domain():
    from opulse.compile.demo import operator_set
    from opulse.core.operator import SIMPLE

    ops = operator_set(["⊕(a, b, c) = { (a + b) + c }"])
    next(op for op in ops.registry if op.definition).definition_type = SIMPLE
    env = BlackBoxEnv(ops.registry)
    prompt = env.reset(0)
    assert "⊕(a, b, c) (3 arguments)" in prompt
    assert "QUERY <x> <y> <z>" in prompt
    assert "[-2, 2] is checked" in prompt
    env.grader.searcher = None
    env.grader.encoder = None
    _, reward, done, info = env.step("SUBMIT ⊕(a, b, c) = { (a + c) + b }")
    assert reward == 1 and done
    assert info["verdict"]["status"] == "exhaustive"


def test_primitive_self_play_describes_and_accepts_form_d():
    from opulse.env.selfplay import ProposerTask

    registry = OperatorRegistry.from_jsonl(INITIAL)
    play = SelfPlay(registry, Settings.from_dict({"recursion": {"style": "primitive", "direct_bound": 3}}),
                    visible=0)
    task = ProposerTask(0, "⊠", 2, None, [], "")
    prompt = play.task(0).prompt
    assert "  D:" in prompt
    definition = ("a ⊠ b = { a, if b == 0; ((a ⊠ (b - 1)) + (b - 1)), "
                  "if b > 0 and b <= 3; ((a ⊠ (b + 1)) + (b + 1)), "
                  "if b < 0 and b >= - 3 }")
    assert play.evaluate(task, definition).valid
    missing_counter = definition.replace("+ (b - 1)", "+ a").replace("+ (b + 1)", "+ a")
    assert "form D needs" in play.evaluate(task, missing_counter).reason
    wrong_counter = definition.replace("if b == 0", "if a == 0")
    assert not play.evaluate(task, wrong_counter).valid
