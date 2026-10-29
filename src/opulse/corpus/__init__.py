"""Pretraining corpora and probe data built from operator sets (``opulse corpus``)."""

from opulse.corpus.build import build_corpus, estimate_tokens
from opulse.corpus.options import CorpusOptions

__all__ = ["CorpusOptions", "build_corpus", "estimate_tokens"]
