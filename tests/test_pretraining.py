import json
import random

import pytest

from opulse.canary import CANARY
from opulse.cli.main import main
from opulse.config import Settings
from opulse.core.operator import Operator
from opulse.core.registry import OperatorRegistry
from opulse.export.corpus import export_megatron, iter_text
from opulse.export.tokenizer import build_tokenizer
from opulse.expression.dataset import ExpressionDataset
from opulse.runtime import PythonRuntime


def _registry_with_custom(registry):
    return OperatorRegistry([*registry, Operator(func_id="custom", symbol="◆₁", n_ary=1,
                                                 unary_position="postfix")])


def test_corpus_export_layout(tmp_path):
    source = tmp_path / "source.jsonl"
    source.write_text(json.dumps({"text": "◆₁\n中文"}, ensure_ascii=False) + "\n" +
                      json.dumps({"prompt": "if a = 1", "answer_text": "2"}) + "\n", encoding="utf-8")
    output = tmp_path / "training.jsonl"
    assert export_megatron([source], output) == 2
    assert [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()] == [
        {"text": "◆₁\n中文", "meta": {"canary": CANARY}},
        {"text": "if a = 1\nAnswer: 2", "meta": {"canary": CANARY}}]
    assert list(iter_text([output])) == ["◆₁\n中文", "if a = 1\nAnswer: 2"]


@pytest.mark.parametrize("operator_mode", ["whole", "character"])
def test_tokenizer_generated_corpora_and_specials(tmp_path, registry, operator_mode):
    pytest.importorskip("tokenizers")
    transformers = pytest.importorskip("transformers")
    custom = _registry_with_custom(registry)
    corpus = []
    for settings in (Settings(), Settings.from_dict({"symbols": {"left_paren": "[", "right_paren": "]",
                                                              "nan": "未定义"},
                                                       "numerals": {"digits": "0123456789ABCDEF"},
                                                       "expressions": {"random_numeral_base": True}})):
        dataset = ExpressionDataset(settings, registry, PythonRuntime(registry), random.Random(4),
                                    keep_undefined=True)
        corpus.extend(record["text"] for record in dataset.records(8))
    corpus.extend(["a ◆₁ = 9; ▲₂ else ⁺ »\n", "if a ⊺⇮123 = NaN { 10 }", "中文 prose with ◆₁\n"])
    output = tmp_path / operator_mode
    tokenizer = build_tokenizer(custom, Settings(), output, corpus=corpus,
                                operator_mode=operator_mode, number_bound=20)
    assert tokenizer.token_to_id(CANARY) is not None
    assert CANARY in (output / "tokenizer.json").read_text()
    for name in ("tokenizer_config.json", "opulse_tokenizer.json"):
        assert json.loads((output / name).read_text())["meta"]["canary"] == CANARY
    fast = transformers.PreTrainedTokenizerFast.from_pretrained(output)
    assert fast.bos_token_id == tokenizer.token_to_id("<bos>")
    assert fast.eos_token_id == tokenizer.token_to_id("<eos>")
    assert fast.pad_token_id == tokenizer.token_to_id("<pad>")
    assert fast.unk_token_id == tokenizer.token_to_id("<unk>")
    for value in corpus:
        ids = fast.encode(value, add_special_tokens=False)
        assert fast.unk_token_id not in ids
        assert fast.decode(ids, skip_special_tokens=False, clean_up_tokenization_spaces=False) == value
    if operator_mode == "whole":
        assert tokenizer.encode("◆₁", add_special_tokens=False).tokens == ["◆₁"]
    else:
        assert tokenizer.encode("◆₁", add_special_tokens=False).tokens == ["◆", "₁"]
    assert tokenizer.encode("123", add_special_tokens=False).tokens == ["1", "2", "3"]
    assert tokenizer.encode("20", add_special_tokens=False).tokens == ["20"]
    assert tokenizer.encode("₉", add_special_tokens=False).tokens == ["₉"]


def test_deterministic_vocab_and_extension(tmp_path, registry):
    pytest.importorskip("tokenizers")
    base = _registry_with_custom(registry)
    settings = Settings()
    first = build_tokenizer(base, settings, tmp_path / "first")
    second = build_tokenizer(OperatorRegistry(reversed(list(base))), settings, tmp_path / "second")
    assert first.get_vocab() == second.get_vocab()
    grown = OperatorRegistry([*base, Operator(func_id="new", symbol="▲₂", n_ary=1,
                                              unary_position="postfix")])
    extended = build_tokenizer(grown, settings, tmp_path / "extended", extend_from=tmp_path / "first")
    assert all(extended.token_to_id(token) == index for token, index in first.get_vocab().items())
    assert extended.token_to_id("▲₂") >= first.get_vocab_size()
    assert extended.encode("▲₂", add_special_tokens=False).tokens == ["▲₂"]


def test_custom_nan_spelling_is_atomic(tmp_path, registry):
    pytest.importorskip("tokenizers")
    settings = Settings.from_dict({"symbols": {"nan": "未定义", "left_paren": "[", "right_paren": "]"}})
    tokenizer = build_tokenizer(registry, settings, tmp_path / "custom", corpus=["[1 + 2] = 未定义"])
    assert tokenizer.encode("未定义", add_special_tokens=False).tokens == ["未定义"]


def test_tokenizer_accepts_literal_unk_when_it_round_trips(tmp_path, registry):
    pytest.importorskip("tokenizers")
    tokenizer = build_tokenizer(registry, Settings(), tmp_path / "literal_unk", corpus=["<unk>"])
    encoded = tokenizer.encode("<unk>", add_special_tokens=False)
    assert tokenizer.decode(encoded.ids, skip_special_tokens=False) == "<unk>"


@pytest.mark.parametrize("naming", ["pseudo", "english"])
def test_benchmark_alias_is_one_token(tmp_path, registry, naming):
    pytest.importorskip("tokenizers")
    from opulse.expression.aliases import AliasMap

    defined = Operator(func_id="defined", symbol="◆₁", n_ary=1, unary_position="postfix",
                       definition="a ◆₁ = { a ⁺ }")
    set_with_alias = OperatorRegistry([*registry, defined])
    alias = AliasMap.build(set_with_alias, random.Random(20261019), style=naming).symbol_to_word[
        ("◆₁", 1, "postfix")]
    tokenizer = build_tokenizer(set_with_alias, Settings(), tmp_path / naming, naming=naming,
                                corpus=[f"a {alias} = 2"])
    assert tokenizer.encode(alias, add_special_tokens=False).tokens == [alias]


def test_export_cli(tmp_path, registry):
    pytest.importorskip("tokenizers")
    operators = tmp_path / "operators.jsonl"
    registry.to_jsonl(operators)
    corpus = tmp_path / "corpus.jsonl"
    corpus.write_text('{"text":"1 + 2 = 3"}\n', encoding="utf-8")
    tokenizer = tmp_path / "tok"
    assert main(["export", "tokenizer", "--operators", str(operators), "--out", str(tokenizer),
                 "--corpus", str(corpus)]) == 0
    output = tmp_path / "megatron.jsonl"
    assert main(["export", "megatron", "--input", str(corpus), "--out", str(output)]) == 0
    assert json.loads(output.read_text(encoding="utf-8"))["text"] == "1 + 2 = 3"
