"""Compiled networks with hand-set weights, and stitching them (opulse.compile)."""

import itertools

import pytest

from opulse.compile import OOV, CompileError, Compiler, Vocab
from opulse.compile.demo import operator_set
from opulse.core import NAN

N = 6
VOCAB = Vocab(-N, 2 * N + 1)


@pytest.fixture(scope="module")
def ops():
    return operator_set()


@pytest.fixture
def torch():
    return pytest.importorskip("torch")


def _op(ops, symbol):
    return next(op for op in ops.registry if op.symbol == symbol and op.definition is not None)


def _rows(arity):
    return list(itertools.product(range(N), repeat=arity))


def test_vocab_tokens():
    vocab = Vocab(-2, 3)
    assert vocab.size == 8
    assert [vocab.index(v) for v in (-2, 3, NAN, 4, -3)] == [0, 5, 6, 7, 7]
    assert vocab.value(6) is NAN and vocab.value(7) is OOV
    assert all(vocab.value(vocab.index(v)) is v or vocab.value(vocab.index(v)) == v for v in vocab.values())


def test_compiler_without_torch_gives_blocks(ops):
    program = Compiler(ops.oracle, VOCAB).compile(_op(ops, "▲₂"))
    assert program.inputs == ["in0_a", "in1_b"]
    kinds = sorted(block.kind for block in program.blocks)
    assert kinds == ["select", "table", "table", "table"]
    widest = max(block.hidden for block in program.blocks)
    assert widest == VOCAB.size ** 2  # one hidden unit per pair of tokens


@pytest.mark.parametrize("symbol", ["◆₁", "▲₂", "★₃", "⬢₄", "⬟₅", "⬡₆", "♣₇"])
def test_compiled_network_matches_interpreter(ops, torch, symbol):
    from opulse.compile.network import build_network
    from opulse.compile.verify import verify

    op = _op(ops, symbol)
    network = build_network(Compiler(ops.oracle, VOCAB).compile(op))
    report = verify(network, ops.oracle, _rows(op.n_ary), lambda row: ops.oracle.evaluate(op, row).value)
    assert report.exact, report.to_dict()
    assert report.slot_checks > 0 and report.slot_wrong == 0


def test_undefined_values_are_exact(torch):
    from opulse.compile.network import build_network
    from opulse.compile.verify import verify

    ops = operator_set(["a ⊘₁ b = { (a / b) + 1, if a > 2; a % b, else }"])
    op = _op(ops, "⊘₁")
    network = build_network(Compiler(ops.oracle, VOCAB).compile(op))
    rows = _rows(2)
    report = verify(network, ops.oracle, rows, lambda row: ops.oracle.evaluate(op, row).value)
    assert report.exact
    assert network.run([(3, 0), (1, 0)]) == [NAN, NAN]


def test_out_of_range_values_become_oov_not_wrong(torch):
    from opulse.compile.network import build_network
    from opulse.compile.verify import verify

    ops = operator_set(["a ⊗₁ b = { (a * b) % 7 }"])
    op = _op(ops, "⊗₁")
    network = build_network(Compiler(ops.oracle, VOCAB).compile(op))
    report = verify(network, ops.oracle, _rows(2), lambda row: ops.oracle.evaluate(op, row).value)
    assert report.ok and not report.exact  # a * b leaves -6..11 for some rows
    assert report.output_oov > 0 and report.output_wrong == 0


def test_defined_is_exact_for_out_of_vocabulary_input(torch):

    from opulse.bench.check import prompt_registry
    from opulse.compile.network import build_network
    from opulse.compile.verify import verify
    from opulse.core.primitives import enable_definedness
    from opulse.core.starting_sets import starting_registry

    registry = starting_registry()
    enable_definedness(registry)
    ops = prompt_registry(["◉ a = { defined a }"], registry)
    op = ops.registry.find("◉", 1, "prefix")
    network = build_network(Compiler(ops.oracle, Vocab(-2, 2)).compile(op))
    report = verify(network, ops.oracle, [(3,)], lambda row: ops.oracle.evaluate(op, row).value)
    assert network.run([(3,)]) == [1]
    assert report.exact, report.to_dict()

    block = next(block for block in network.blocks if block.label == "defined")
    output = network.slots[block.write]
    unit = block.hidden[0] + network.vocab.oov_index
    with torch.no_grad():
        weights = network.layers[block.layer].down.weight
        weights[output.start + network.vocab.index(1), unit] = 0
        weights[output.start + network.vocab.oov_index, unit] = 1
    bad = verify(network, ops.oracle, [(3,)], lambda row: ops.oracle.evaluate(op, row).value)
    assert not bad.ok


@pytest.mark.parametrize("condition,answer", [
    ("a > 0 or (⊖ a) == 0", [2, 1]),
    ("a < 0 and (⊖ a) == 0", [2, 2]),
])
def test_short_circuit_condition_prunes_unreachable_recursive_call(torch, condition, answer):
    from opulse.compile.network import build_network

    ops = operator_set([
        ("⊖ a = { 1, if a == 0; (⊖ (a - 1)) + 1, if a > 0 and a <= 2; "
         "(⊖ (a + 1)) - 1, if a < 0 and a >= - 2 }"),
        f"◉ a = {{ 1, if {condition}; 2, else }}",
    ])
    op = _op(ops, "◉")
    network = build_network(Compiler(ops.oracle, Vocab(-2, 2), input_values=[0, 1], max_depth=1).compile(op))
    assert network.run([(0,), (1,)]) == answer


def test_select_with_shared_branch_body(torch):
    from opulse.compile.network import build_network
    from opulse.compile.verify import verify

    ops = operator_set(["◉ a = { a, if a > 0; a, else }"])
    op = _op(ops, "◉")
    network = build_network(Compiler(ops.oracle, Vocab(-2, 2)).compile(op))
    rows = [(-1,), (0,), (1,)]
    assert network.run(rows) == [-1, 0, 1]
    assert verify(network, ops.oracle, rows, lambda row: ops.oracle.evaluate(op, row).value).exact


def test_stitched_network_computes_the_composition(ops, torch):
    from opulse.compile.network import build_network, stitch
    from opulse.compile.verify import verify

    compiler = Compiler(ops.oracle, VOCAB)
    f = build_network(compiler.compile(_op(ops, "◆₁")))
    g = build_network(compiler.compile(_op(ops, "▲₂")))
    joined = stitch([("f", f), ("g", g)], {"g.in0_a": f"f.{f.output}"}, f"g.{g.output}")
    assert joined.inputs == ["f.in0_a", "g.in1_b"]
    assert len(joined.layers) == len(f.layers) + len(g.layers)
    star = _op(ops, "★₃")
    report = verify(joined, ops.oracle, _rows(2), lambda row: ops.oracle.evaluate(star, row).value)
    assert report.exact and report.slot_wrong == 0
    whole = build_network(compiler.compile(star))
    assert whole.run(_rows(2)) == joined.run(_rows(2))


def test_snap_layer_keeps_exact_networks_exact_and_cleans_noise(ops, torch):
    from opulse.compile.network import build_network, stitch
    from opulse.compile.verify import verify

    compiler = Compiler(ops.oracle, VOCAB)
    f = build_network(compiler.compile(_op(ops, "◆₁")))
    g = build_network(compiler.compile(_op(ops, "▲₂")))
    joined = stitch([("f", f), ("g", g)], {"g.in0_a": f"f.{f.output}"}, f"g.{g.output}", snap=True)
    assert len(joined.layers) == len(f.layers) + len(g.layers) + 1
    star = _op(ops, "★₃")
    report = verify(joined, ops.oracle, _rows(2), lambda row: ops.oracle.evaluate(star, row).value)
    assert report.exact and report.slot_wrong == 0
    snap_layer = joined.layers[len(f.layers)]
    out = joined.slots[f"f.{f.output}"]
    x = torch.zeros(1, joined.d_model)
    x[0, out.start:out.stop] = 0.3  # every coordinate off by 0.3, token 2 at 0.7
    x[0, out.start + 2] = 0.7
    snapped = joined.slots[f"f.{f.output}~snap"]
    with torch.no_grad():
        y = snap_layer(x)[0, snapped.start:snapped.stop]
    assert y.tolist() == [1.0 if i == 2 else 0.0 for i in range(VOCAB.size)]


def test_compact_matches_whole_compile_depth(ops, torch):
    from collections import Counter

    from opulse.compile.network import build_network, compact, stitch

    compiler = Compiler(ops.oracle, VOCAB)
    f = build_network(compiler.compile(_op(ops, "◆₁")))
    g = build_network(compiler.compile(_op(ops, "▲₂")))
    whole = build_network(compiler.compile(_op(ops, "⬢₄")))
    joined = stitch([("f1", f), ("f2", f), ("g", g)],
                    {"g.in0_a": f"f1.{f.output}", "g.in1_b": f"f2.{f.output}"}, f"g.{g.output}")
    packed = compact(joined)
    assert len(joined.layers) == 6 and len(packed.layers) == len(whole.layers) == 4
    assert packed.run(_rows(2)) == joined.run(_rows(2)) == whole.run(_rows(2))
    assert Counter(b.signature for b in whole.blocks) == Counter(b.signature for b in joined.blocks)


def test_whole_compile_folds_constants(ops, torch):
    from opulse.compile.network import build_network, stitch

    compiler = Compiler(ops.oracle, VOCAB)
    f = build_network(compiler.compile(_op(ops, "◆₁")))
    g = build_network(compiler.compile(_op(ops, "▲₂")))
    whole = build_network(compiler.compile(_op(ops, "⬡₆")))
    joined = stitch([("f", f), ("g", g)], {"g.in0_a": f"f.{f.output}"}, f"g.{g.output}")
    assert whole.run([(a,) for a in range(N)]) == joined.run([(a, 7) for a in range(N)])
    assert whole.stats()["max_hidden"] < joined.stats()["max_hidden"]


def test_verifier_reports_a_corrupted_weight(ops, torch):
    from opulse.compile.network import build_network
    from opulse.compile.verify import verify

    op = _op(ops, "▲₂")
    network = build_network(Compiler(ops.oracle, VOCAB).compile(op))
    block = next(b for b in network.blocks if b.kind == "select")
    layer = network.layers[block.layer]
    out = network.slots[block.write]
    with torch.no_grad():  # route the hidden unit for "then = 3" to token 4 instead
        unit = next(u for u in range(*block.hidden) if layer.down.weight[out.start + VOCAB.index(3), u] == 1)
        layer.down.weight[out.start + VOCAB.index(3), unit] = 0
        layer.down.weight[out.start + VOCAB.index(4), unit] = 1
    report = verify(network, ops.oracle, _rows(2), lambda row: ops.oracle.evaluate(op, row).value)
    assert not report.ok and report.output_wrong > 0


def test_unsupported_forms_raise(ops):
    with pytest.raises(CompileError):  # a base operation has no definition to compile
        Compiler(ops.oracle, VOCAB).compile(ops.registry.find("+", 2))
    searching = operator_set(["a ⊙₁ b = { search(i, 4, (i + a) == b) }"])
    with pytest.raises(CompileError):
        Compiler(searching.oracle, VOCAB).compile(_op(searching, "⊙₁"))


def test_slot_map_covers_the_stream(ops, torch):
    from opulse.compile.network import build_network

    network = build_network(Compiler(ops.oracle, VOCAB).compile(_op(ops, "★₃")))
    assert isinstance(network, torch.nn.Module)
    spans = sorted(network.slot_map.values())
    assert spans[0][0] == 0 and spans[-1][1] == network.d_model
    assert all(a[1] == b[0] for a, b in itertools.pairwise(spans))


def test_trained_module_stitches(ops, torch):
    from opulse.compile.network import build_network, stitch
    from opulse.compile.trained import train_operator

    vocab = Vocab(-3, 6)
    compiler = Compiler(ops.oracle, vocab)
    f = build_network(compiler.compile(_op(ops, "◆₁")))
    g = build_network(compiler.compile(_op(ops, "▲₂")))
    trained = train_operator(f, 32, extra_steps=500)
    joined = stitch([("f", trained), ("g", g)], {"g.in0_a": f"f.{trained.output}"}, f"g.{g.output}")
    rows = list(itertools.product(range(3), repeat=2))
    star = _op(ops, "★₃")
    assert joined.run(rows) == [vocab.clamp(ops.oracle.evaluate(star, row).value) for row in rows]


def test_command_line(torch, capsys):
    from opulse.compile.__main__ import main

    assert main(["--n", "4"]) == 0
    assert "stitched_compact" in capsys.readouterr().out
