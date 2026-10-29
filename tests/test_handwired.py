"""CPU smoke tests for the two opt-in compiled operator studies."""

import json

import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("transformers")

from opulse.compile import Compiler, Vocab
from opulse.compile.demo import operator_set
from opulse.compile.handwired.analysis import analyze
from opulse.compile.handwired.data import (
    compiled_states,
    examples,
    slot_activity,
    tokenized_examples,
)
from opulse.compile.handwired.injection import (
    Injection,
    ReadAdapter,
    WriteAdapter,
    evaluate,
    fit_probe_from_prompts,
    fit_writer_from_prompts,
    nnsight_forward,
)
from opulse.compile.handwired.train_small import train
from opulse.compile.network import build_network


@pytest.fixture(scope="module")
def case():
    ops = operator_set(["a ◆₁ = { (a % 3) + 1 }"])
    op = next(op for op in ops.registry if op.symbol == "◆₁")
    network = build_network(Compiler(ops.oracle, Vocab(0, 9), input_values=range(3)).compile(op))
    return ops, op, network


def test_exact_slots_and_mock_identity_path(case):
    _, _, network = case
    rows = [(0,), (1,), (2,)]
    states, labels = compiled_states(network, rows)
    assert len(states) == len(network.layers) + 1
    assert [network.vocab.value(int(i)) for i in labels[network.output]] == [1, 2, 3]

    class IdentityLM(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.model = torch.nn.Module()
            self.model.layers = torch.nn.ModuleList([torch.nn.Identity()])

        def forward(self, input_ids, attention_mask=None):
            state = torch.zeros(*input_ids.shape, network.vocab.size)
            state = self.model.layers[0](state)
            return type("Output", (), {"logits": state})()

    model = IdentityLM()
    reader = ReadAdapter(network.vocab, network.inputs, token_ids={v: v + 20 for v in range(3)})
    writer = WriteAdapter(network.vocab, network.vocab.size, directions=torch.eye(network.vocab.size))
    injection = Injection(model, network, reader, writer, 0, 0)
    ids = torch.tensor([[20, 0], [21, 0], [22, 0]])
    positions = torch.zeros(3, 1, dtype=torch.long)
    before = model(ids).logits.clone()
    got = injection.forward(ids, positions).logits[:, -1].argmax(-1).tolist()
    assert got == [network.vocab.index(v) for v in (1, 2, 3)]
    assert torch.equal(model(ids).logits, before)
    assert injection.last_values == [1, 2, 3]


def test_branch_slots_have_activity_mask():
    ops = operator_set(["a ▲₂ = { a + 1, if a > 1; a + 2, else }"])
    op = next(op for op in ops.registry if op.symbol == "▲₂")
    network = build_network(Compiler(ops.oracle, Vocab(0, 9), input_values=range(4)).compile(op))
    _, labels = compiled_states(network, [(i,) for i in range(4)])
    activity = slot_activity(network, labels)
    assert all(bool(activity[name].all()) for name in network.inputs)
    assert any(not bool(mask.all()) for name, mask in activity.items() if name not in network.inputs)


def test_tiny_hf_hooks_and_nnsight(case):
    from transformers import AutoModelForCausalLM, AutoTokenizer

    pytest.importorskip("nnsight")
    name = "hf-internal-testing/tiny-random-LlamaForCausalLM"
    try:
        model = AutoModelForCausalLM.from_pretrained(name, local_files_only=True).eval()
        tokenizer = AutoTokenizer.from_pretrained(name, local_files_only=True, use_fast=True)
    except OSError:
        pytest.skip("tiny random Llama is not cached")
    tokenizer.pad_token = tokenizer.eos_token
    ops, op, network = case
    items = examples(ops.oracle, op, range(3))
    mapping = {}
    for item in items:
        enc, positions = tokenized_examples(tokenizer, [item])
        mapping[item.operands[0]] = int(enc["input_ids"][0, positions[0, 0]])
    reader = ReadAdapter(network.vocab, network.inputs, token_ids=mapping)
    directions = torch.zeros(network.vocab.size, model.get_output_embeddings().weight.shape[1])
    for value in (1, 2, 3):
        token = tokenizer("= " + str(value), return_tensors="pt")["input_ids"][0, -1]
        directions[network.vocab.index(value)] = model.get_output_embeddings().weight[token]
    writer = WriteAdapter(network.vocab, directions.shape[1], directions=directions)
    injection = Injection(model, network, reader, writer, 0, 1)
    enc, positions = tokenized_examples(tokenizer, [items[0]])
    with torch.no_grad():
        first = injection.forward(enc["input_ids"], positions, enc["attention_mask"]).logits
        second = injection.forward(enc["input_ids"], positions, enc["attention_mask"]).logits
        traced = nnsight_forward(injection, enc["input_ids"], positions, enc["attention_mask"])
    assert first.shape == second.shape == traced.shape
    assert torch.equal(first, second)
    assert torch.allclose(first, traced, atol=1e-5)
    report = evaluate(injection, tokenizer, items)
    assert len(report["examples"]) == 6
    assert [row["compiled_value"] for row in report["examples"]] == [str(i) for i in (1, 1, 2, 2, 3, 3)]
    direct = [item for item in items if item.form == "direct"]
    probe = ReadAdapter(network.vocab, network.inputs, mode="probe", hidden_size=directions.shape[1])
    fit_probe_from_prompts(probe, model, tokenizer, direct, 0)
    linear = WriteAdapter(network.vocab, directions.shape[1], mode="linear")
    fit_writer_from_prompts(linear, network, model, tokenizer, direct, 1)
    fitted_injection = Injection(model, network, probe, linear, 0, 1)
    fitted = evaluate(fitted_injection, tokenizer, items)
    assert len(fitted["examples"]) == 6
    assert fitted["reader_accuracy"] == 1.0
    with torch.no_grad():
        fitted_plain = fitted_injection.forward(enc["input_ids"], positions, enc["attention_mask"]).logits
        fitted_trace = nnsight_forward(fitted_injection, enc["input_ids"], positions, enc["attention_mask"])
    assert torch.allclose(fitted_plain, fitted_trace, atol=1e-5)


def test_train_and_report_cpu(tmp_path):
    from opulse.canary import CANARY

    meta = train(tmp_path, steps=2, hidden=16, layers=1, heads=2, values=range(8))
    assert json.loads((tmp_path / "metadata.json").read_text())["meta"]["canary"] == CANARY
    assert len(meta["losses"]) == 2
    result = analyze(tmp_path)
    assert result["examples"] == 8
    assert "answer_position" in result["probe_accuracy"]
    assert len(result["linear_cka"]) == 2
    assert len(result["activation_patching"]) == 1
    assert result["activation_patching"]["0"]
    assert all(row["slot"] not in ("in0_a",) for row in result["activation_patching"]["0"])
    assert (tmp_path / "report" / "report.json").is_file()
    assert all((tmp_path / "report" / f"{name}.png").is_file() for name in ("probes", "cka", "patching"))
    assert json.loads((tmp_path / "report" / "report.json").read_text())["examples"] == 8
    assert json.loads((tmp_path / "report" / "report.json").read_text())["meta"]["canary"] == CANARY


def test_two_selected_operators(tmp_path):
    definitions = ["a ◆₁ = { (a % 3) + 1 }", "a ♧₂ = { (a % 2) + 2 }"]
    result = train(tmp_path, steps=1, hidden=16, layers=1, heads=2, values=range(4),
                   definitions=definitions, symbols=["◆₁", "♧₂"])
    assert len(result["examples"]) == 8
    assert set(result["operators"]) == {"◆₁", "♧₂"}
    report = analyze(tmp_path, symbol="♧₂")
    assert report["symbol"] == "♧₂"
    assert (tmp_path / "report_♧₂" / "report.json").is_file()
