"""Compile operator definitions into residual MLP networks with hand-set weights, and stitch them.

The compiler (:mod:`opulse.compile.compiler`) needs only numpy. Building, stitching and
verifying networks (:mod:`~opulse.compile.network`, :mod:`~opulse.compile.verify`) need torch.
See docs/guide/compiled-models.md.
"""

from opulse.compile.compiler import CompileError, Compiler, Const, Program
from opulse.compile.values import OOV, Vocab

__all__ = ["OOV", "CompileError", "Compiler", "Const", "Program", "Vocab"]
