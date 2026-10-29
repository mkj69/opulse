"""Deterministic Opulse vocabulary with exact UTF-8 byte coverage."""

from __future__ import annotations

import json
import random
from collections.abc import Iterable
from pathlib import Path

from opulse.canary import CANARY, marked
from opulse.config import Settings
from opulse.core.registry import OperatorRegistry

SPECIAL = ("<bos>", "<eos>", "<pad>", "<unk>")
SUBSCRIPTS = "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎"
SYNTAX = ("[", "]", "(", ")", "{", "}", ",", "=", ";", "if", "else", "and", "or", "not",
          "<", ">", "<=", ">=", "==", "!=", "!", " ", "\n", "\t", "\r")


def opulse_tokens(registry: OperatorRegistry, settings: Settings, *, operator_mode: str = "whole",
                  number_bound: int = 0, naming: str = "symbols") -> list[str]:
    """Return sorted atomic tokens; existing vocabulary order is handled by the builder."""
    if operator_mode not in ("whole", "character"):
        raise ValueError("operator_mode must be 'whole' or 'character'")
    if number_bound < 0:
        raise ValueError("number_bound must be nonnegative")
    if naming not in ("symbols", "pseudo", "english"):
        raise ValueError("naming must be symbols, pseudo, or english")
    names = registry.symbols()
    if naming != "symbols":
        from opulse.expression.aliases import AliasMap

        aliases = AliasMap.build(registry, random.Random(20261019), style=naming,
                                 symbols=settings.symbols, digits=settings.numerals.digits)
        names.update(aliases.symbol_to_word.values())
    if operator_mode == "character":
        names = {character for name in names for character in name}
    s = settings.symbols
    values = set(names)
    values.update(settings.numerals.digits)
    values.update(SUBSCRIPTS)
    values.update(SYNTAX)
    values.update((s.left_operand, s.right_operand, s.left_paren, s.right_paren,
                   s.equals, s.nan, s.inf, s.neg_inf))
    values.update(settings.expressions.variables)
    values.update(str(number) for number in range(number_bound + 1))
    values.difference_update(SPECIAL)
    return sorted(value for value in values if value)


def build_tokenizer(registry: OperatorRegistry, settings: Settings, output_dir: str | Path, *,
                    operator_mode: str = "whole", number_bound: int = 0,
                    naming: str = "symbols", corpus: Iterable[str] = (),
                    extend_from: str | Path | None = None):
    """Write tokenizer.json and tokenizer_config.json, then check optional corpus text.

    The byte alphabet covers arbitrary UTF-8 prose. Added tokens keep whole Opulse
    symbols intact. Extending a saved vocabulary only appends missing tokens.
    """
    try:
        from tokenizers import AddedToken, Tokenizer, decoders, models, pre_tokenizers
        from tokenizers.pre_tokenizers import ByteLevel
    except ImportError as exc:
        raise RuntimeError("install tokenizers to build an Opulse tokenizer") from exc

    output_dir = Path(output_dir)
    if extend_from is None:
        vocab = {value: index for index, value in enumerate(SPECIAL)}
        for value in sorted(ByteLevel.alphabet()):
            if value not in vocab:
                vocab[value] = len(vocab)
        tokenizer = Tokenizer(models.BPE(vocab=vocab, merges=[], unk_token="<unk>"))
        tokenizer.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
        tokenizer.decoder = decoders.ByteLevel()
        tokenizer.add_special_tokens(list(SPECIAL))
    else:
        previous = Path(extend_from)
        metadata = json.loads((previous / "opulse_tokenizer.json").read_text(encoding="utf-8"))
        if (metadata["operator_mode"] != operator_mode or metadata["number_bound"] != number_bound
                or metadata["naming"] != naming):
            raise ValueError("extension must use the original operator mode, number bound, and naming")
        tokenizer = Tokenizer.from_file(str(previous / "tokenizer.json"))

    whole_numbers = {str(number) for number in range(10, number_bound + 1)}
    tokens = [AddedToken(value, normalized=False, single_word=value in whole_numbers)
              for value in opulse_tokens(
        registry, settings, operator_mode=operator_mode, number_bound=number_bound, naming=naming)
        if tokenizer.token_to_id(value) is None]
    tokenizer.add_tokens(tokens)
    tokenizer.add_special_tokens([AddedToken(CANARY, normalized=False)])
    for index, value in enumerate(corpus):
        encoding = tokenizer.encode(value, add_special_tokens=False)
        if tokenizer.decode(encoding.ids, skip_special_tokens=False) != value:
            raise ValueError(f"corpus record {index} does not round trip")

    output_dir.mkdir(parents=True, exist_ok=True)
    tokenizer.save(str(output_dir / "tokenizer.json"))
    config = {"tokenizer_class": "PreTrainedTokenizerFast", "tokenizer_file": "tokenizer.json",
              "bos_token": "<bos>", "eos_token": "<eos>", "pad_token": "<pad>", "unk_token": "<unk>",
              "clean_up_tokenization_spaces": False, "add_bos_token": False}
    (output_dir / "tokenizer_config.json").write_text(
        json.dumps(marked(config), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output_dir / "opulse_tokenizer.json").write_text(
        json.dumps(marked({"operator_mode": operator_mode, "number_bound": number_bound, "naming": naming}), indent=2) + "\n",
        encoding="utf-8")
    return tokenizer
