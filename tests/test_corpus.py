import hashlib
import json
import random
from dataclasses import replace

import pytest

from opulse.cli.main import main
from opulse.cli.operators import DEFAULT_CONFIG
from opulse.config import Settings
from opulse.core.operator import Operator
from opulse.core.presets import PRESETS, register_preset
from opulse.core.primitives import atom_records
from opulse.core.registry import OperatorRegistry
from opulse.core.semantics import NAN
from opulse.corpus import CorpusOptions, build_corpus, estimate_tokens
from opulse.corpus.build import ExactDeduper
from opulse.corpus.documents import SplitGenerator
from opulse.corpus.options import kind_counts
from opulse.corpus.splits import split_operators
from opulse.definition.parser import DefinitionParser
from opulse.expression.dataset import ExpressionDataset
from opulse.expression.nodes import Call, Number, from_ast, to_ast
from opulse.runtime import PythonRuntime
from opulse.verify import Oracle

TOKENIZER = "openai-community/gpt2"


def _rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _files(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def _documents(root, split):
    return [row["text"] for path in sorted((root / split).glob("*.jsonl")) for row in _rows(path)]


def _probes(root, split):
    return [row for path in sorted((root / "probe").glob(f"{split}-*.jsonl")) for row in _rows(path)]


@pytest.mark.parametrize("world,symbol,args", [
    ("strings", "⊕", ("", "")),
    ("lists", "⊞", ((), ())),
    ("strings", "≡", ("", "")),
    ("strings", "≡", ("", "x")),
])
def test_decimal_corpus_values_use_typed_literals(world, symbol, args):
    register_preset(world)
    registry = OperatorRegistry(Operator.from_dict(row) for row in atom_records(PRESETS[world]))
    settings = Settings()
    tree = Call(registry.find(symbol, 2), tuple(Number(value) for value in args))
    record = ExpressionDataset(settings, registry, PythonRuntime(registry), random.Random(1)).record(
        0, tree, cot=False)
    generator = SplitGenerator("train", settings, registry, [], CorpusOptions())
    assert generator._value_line(record, tree) == f"{record['expression_full_brackets']} = {record['result_text']}"


def test_large_finite_mix_weights_preserve_allocation():
    mix = {"values": 1e308, "derivations": 1e308}
    CorpusOptions(mix=mix)
    assert kind_counts(3, mix) == {"definitions": 0, "values": 2, "derivations": 1,
                                    "descriptions": 0}


def test_large_finite_split_ratios_preserve_allocation():
    registry = OperatorRegistry(
        Operator(func_id=f"h{i}", symbol=symbol, n_ary=2,
                 definition=f"a {symbol} b = {{ a }}")
        for i, symbol in enumerate(("◇", "◆", "◈"))
    )
    assert split_operators(registry, {"train": 1e308, "test": 1e308}, 0) == split_operators(
        registry, {"train": 1, "test": 1}, 0)


@pytest.fixture(scope="module")
def corpus(tmp_path_factory, operators):
    root = tmp_path_factory.mktemp("corpus") / "out"
    options = CorpusOptions(seed=9, documents={"train": 12},
                            mix={"definitions": 1, "values": 2, "derivations": 3},
                            expressions_per_document=2, definitions_per_document=5,
                            cot_depth=1, max_steps=30, shard_size=3, block_size=2, probe=True)
    build_corpus(Settings.load(DEFAULT_CONFIG), {"train": operators}, options, root, workers=1)
    return root, options


def test_determinism_across_runs_and_workers(tmp_path, operators, corpus):
    from opulse.canary import CANARY

    first, options = corpus
    settings = Settings.load(DEFAULT_CONFIG)
    second = tmp_path / "again"
    third = tmp_path / "workers"
    build_corpus(settings, {"train": operators}, options, second, workers=1)
    build_corpus(settings, {"train": operators}, options, third, workers=3)
    assert _files(first) == _files(second) == _files(third)
    assert "manifest.json" in _files(first)
    assert "splits.json" in _files(first)
    assert any(name.startswith("probe/") for name in _files(first))
    assert all(CANARY in data.decode("utf-8") for name, data in _files(first).items()
               if name.endswith((".json", ".jsonl")))


def test_operator_splits_do_not_leak_held_out_symbols(tmp_path, operators):
    options = CorpusOptions(seed=5, split="operator", split_ratios={"train": 0.6, "val": 0.2, "test": 0.2},
                            documents={"train": 8, "val": 8, "test": 8}, mix={"values": 1},
                            expressions_per_document=2, shard_size=3)
    root = tmp_path / "split"
    build_corpus(Settings.load(DEFAULT_CONFIG), {"train": operators}, options, root)
    splits = json.loads((root / "splits.json").read_text())
    owned = {name: set(info["owned"]) for name, info in splits.items()}
    for name, ids in owned.items():
        assert all(ids.isdisjoint(other) for other_name, other in owned.items() if other_name != name)
    registry = OperatorRegistry.from_jsonl(operators)
    symbols = {op.func_id: op.symbol for op in registry if op.definition is not None}
    all_symbols = {op.symbol for op in registry}
    for held in ("val", "test"):
        for split, info in splits.items():
            if split == held:
                continue
            assert owned[held].isdisjoint(info["mentioned"])
            for symbol in (symbols[fid] for fid in owned[held]):
                if any(symbol in other for other in all_symbols if other != symbol):
                    continue
                for text in _documents(root, split):
                    assert symbol not in text, (held, split, symbol, text)


def test_dedup_and_duplicate_reporting(tmp_path, operators, corpus):
    root, _ = corpus
    texts = [text for split in ("train",) for text in _documents(root, split)]
    assert len(texts) == len(set(texts))
    settings = Settings.load(DEFAULT_CONFIG)
    common = {"seed": 3, "documents": {"train": 12}, "mix": {"definitions": 1},
              "definitions_per_document": 100, "shard_size": 4}
    keep = tmp_path / "keep"
    drop = tmp_path / "drop"
    keep_manifest = build_corpus(settings, {"train": operators}, CorpusOptions(**common, dedup=False), keep)
    drop_manifest = build_corpus(settings, {"train": operators}, CorpusOptions(**common, dedup=True), drop)
    kept = _documents(keep, "train")
    dropped = _documents(drop, "train")
    assert len(kept) > len(set(kept))
    assert len(dropped) == len(set(dropped))
    assert keep_manifest["splits"]["train"]["kinds"]["definitions"]["duplicates_dropped"] == 0
    assert drop_manifest["splits"]["train"]["kinds"]["definitions"]["duplicates_dropped"] > 0


def test_invalid_split_name_and_worker_count(tmp_path, operators):
    with pytest.raises(ValueError, match="invalid split name"):
        CorpusOptions(documents={"..": 1})
    options = CorpusOptions(documents={"train": 1}, mix={"values": 1})
    with pytest.raises(ValueError, match="workers must be at least 1"):
        build_corpus(Settings.load(DEFAULT_CONFIG), {"train": operators}, options, tmp_path / "out", workers=0)
    assert not (tmp_path / "out").exists()


def test_exact_dedup_spills_to_disk(tmp_path):
    deduper = ExactDeduper(tmp_path / "seen.sqlite", memory_limit=2)
    try:
        assert deduper.add("a")
        assert not deduper.add("a")
        assert deduper.add("b")
        assert deduper.add("c")
        assert not deduper.add("a")
        assert not deduper.add("c")
    finally:
        deduper.close()


def test_numbered_operator_name_parses(operators):
    settings = Settings.load(DEFAULT_CONFIG)
    original = OperatorRegistry.from_jsonl(operators)
    selected = next(op for op in original if op.definition is not None and op.n_ary == 1)
    renamed = replace(selected, symbol="◆₁", definition=selected.definition.replace(selected.symbol, "◆₁"))
    registry = OperatorRegistry(renamed if op is selected else op for op in original)
    expression = "◆₁ 2" if selected.unary_position == "prefix" else "2 ◆₁"
    parsed = DefinitionParser(settings.symbols, registry).parse_expr(expression, expression_mode=True)
    assert from_ast(parsed, registry).operator.func_id == selected.func_id


def test_manifest_matches_shards(corpus):
    root, options = corpus
    manifest = json.loads((root / "manifest.json").read_text())
    assert manifest["format"] == "opulse-corpus/1"
    for report in manifest["splits"].values():
        totals = {key: 0 for key in ("documents", "chars", "bytes", "tokens_estimate")}
        for shard in report["shards"]:
            path = root / shard["path"]
            raw = path.read_bytes()
            texts = [row["text"] for row in _rows(path)]
            actual = {"documents": len(texts), "chars": sum(map(len, texts)), "bytes": len(raw),
                      "tokens_estimate": sum(estimate_tokens(text) for text in texts)}
            assert 1 <= len(texts) <= options.shard_size
            assert shard["sha256"] == hashlib.sha256(raw).hexdigest()
            for key, value in actual.items():
                assert shard[key] == value
                totals[key] += value
        for key, value in totals.items():
            assert report[key] == value
        assert sum(kind["written"] for kind in report["kinds"].values()) == report["documents"]
        probe = report["probe"]
        assert probe["records"] == sum(s["documents"] for s in probe["shards"])
        for shard in probe["shards"]:
            raw = (root / shard["path"]).read_bytes()
            assert shard["sha256"] == hashlib.sha256(raw).hexdigest()
            assert shard["documents"] <= options.shard_size
    for key in ("documents", "chars", "bytes", "tokens_estimate"):
        assert manifest["totals"][key] == sum(r[key] for r in manifest["splits"].values())


@pytest.mark.parametrize("style", ["chain", "en"])
def test_probe_spans_parse_and_match_oracle(tmp_path, operators, corpus, style):
    if style == "chain":
        root = corpus[0]
    else:
        root = tmp_path / "en"
        options = CorpusOptions(seed=9, documents={"train": 5}, mix={"derivations": 1},
                                derivation_style="en", cot_depth=1, max_steps=30, probe=True,
                                shard_size=2)
        build_corpus(Settings.load(DEFAULT_CONFIG), {"train": operators}, options, root)
    settings = Settings.load(DEFAULT_CONFIG)
    registry = OperatorRegistry.from_jsonl(operators)
    parser = DefinitionParser(settings.symbols, registry)
    oracle = Oracle(registry, settings.symbols, settings.semantics.build())
    texts = set(_documents(root, "train"))
    probes = _probes(root, "train")
    assert probes
    for probe in probes:
        assert probe["text"] in texts
        assert probe["style"] == style
        assert probe["steps"]
        for span in probe["steps"] + [probe["answer"]]:
            fragment = probe["text"][span["start"]:span["end"]]
            node = from_ast(parser.parse_expr(fragment, expression_mode=True), registry)
            value = oracle.evaluate_expr(to_ast(node), {}).value
            assert (value is NAN) == span["undefined"]
            assert (value is NAN and span["value"] is None) or value == span["value"]
        answer = probe["answer"]
        assert answer["value"] == probe["value"]
        assert probe["text"][answer["start"]:answer["end"]]


def test_cli_layout_prefix_and_set_split(tmp_path, operators):
    root = tmp_path / "cli"
    base = ["corpus", "--operators", str(operators), "--out", str(root),
            "--documents", "6", "--mix", "values=1,derivations=1", "--definitions", "prefix",
            "--expressions-per-document", "2", "--cot-depth", "1", "--probe", "--shard-size", "2"]
    assert main(base) == 0
    assert (root / "manifest.json").is_file() and (root / "splits.json").is_file()
    assert list((root / "train").glob("train-*.jsonl"))
    assert list((root / "probe").glob("train-*.jsonl"))
    definitions = [op.definition for op in OperatorRegistry.from_jsonl(operators) if op.definition]
    prefixed = [text for text in _documents(root, "train") if "\n\n" in text]
    assert prefixed
    assert all(any(text.startswith(definition) for definition in definitions) for text in prefixed)
    assert any("\n= " in text for text in prefixed)
    assert any(" = " in text.split("\n\n", 1)[1] for text in prefixed)
    with pytest.raises(SystemExit, match="definitions none"):
        main(["corpus", "--operators", str(operators), "--out", str(tmp_path / "invalid"),
              "--documents", "2", "--definitions", "none", "--mix", "definitions=1,values=1"])

    other = tmp_path / "other.jsonl"
    assert main(["operators", "--out", str(other), "--layers", "4", "2", "--seed", "4"]) == 0
    set_root = tmp_path / "sets"
    assert main(["corpus", "--split", "set", "--operators", f"alpha={operators}",
                 "--operators", f"beta={other}", "--out", str(set_root),
                 "--documents", "2", "--mix", "definitions=1", "--shard-size", "1"]) == 0
    manifest = json.loads((set_root / "manifest.json").read_text())
    assert set(manifest["splits"]) == {"alpha", "beta"}
    assert manifest["splits"]["alpha"]["operator_set"] != manifest["splits"]["beta"]["operator_set"]
    assert all(_documents(set_root, name) for name in ("alpha", "beta"))


def test_offline_tokenizer_probe_spans(tmp_path, monkeypatch, operators):
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    transformers = pytest.importorskip("transformers")
    try:
        tokenizer = transformers.AutoTokenizer.from_pretrained(TOKENIZER, use_fast=True)
    except Exception as exc:  # noqa: BLE001 - any offline cache/loading failure means unavailable
        pytest.skip(f"gpt2 tokenizer unavailable offline: {exc}")
    root = tmp_path / "tokens"
    options = CorpusOptions(seed=2, documents={"train": 2}, mix={"derivations": 1},
                            cot_depth=1, max_steps=30, probe=True, tokenizer=TOKENIZER)
    build_corpus(Settings.load(DEFAULT_CONFIG), {"train": operators}, options, root)
    probes = _probes(root, "train")
    assert probes
    for probe in probes:
        offsets = tokenizer(probe["text"], add_special_tokens=False, return_offsets_mapping=True)["offset_mapping"]
        for span in probe["steps"] + [probe["answer"]]:
            start, end = span["token_start"], span["token_end"]
            assert start is not None and end is not None and start < end
            assert offsets[start][0] <= span["start"] < span["end"] <= offsets[end - 1][1]
