"""Compile operators with Cython and load them as extension modules.

Operators are written in dependency (topological) order into chunks of
``chunk_size`` operators. Each chunk is built once and cached by a hash of
its source. Generated code refers to other operators, to base operations and
to ``NAN`` as module globals; after loading, every module's globals are
filled with one shared table (all compiled operators plus the base bindings
from :class:`~opulse.core.semantics.Semantics`), so calls across chunks
resolve and the arithmetic has a single implementation.

Same interface as :class:`opulse.runtime.PythonRuntime`.
"""

from __future__ import annotations

import hashlib
import importlib
import logging
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from opulse.core.operator import Operator
from opulse.core.registry import OperatorRegistry
from opulse.core.semantics import NAN, Semantics
from opulse.definition.codegen import evaluator_name, is_base
from opulse.runtime.python_backend import base_bindings

logger = logging.getLogger(__name__)

_NAME = re.compile(r"\b(?:op_count_|op_|_e_)[A-Za-z0-9]+\b|\bNAN\b")
_DEFINED = re.compile(r"^def ((?:op_count_|op_|_e_)[A-Za-z0-9]+)\(", re.MULTILINE)


def _placeholders(body: str) -> str:
    """Declare the external globals a chunk uses; Cython rejects undeclared names."""
    external = sorted(set(_NAME.findall(body)) - set(_DEFINED.findall(body)))
    return "".join(f"{name} = None\n" for name in external)


class CythonRuntime:
    def __init__(self, registry: OperatorRegistry, build_dir: str | Path, semantics: Semantics | None = None,
                 chunk_size: int = 500, jobs: int = 8) -> None:
        semantics = semantics or Semantics()
        self.build_dir = Path(build_dir).resolve()
        self.build_dir.mkdir(parents=True, exist_ok=True)
        table: dict[str, Callable] = {"NAN": NAN}
        compiled = []
        for operator in registry.topological_order():
            if is_base(operator):
                table.update(base_bindings(operator, semantics))
            elif operator.has_code:
                compiled.append(operator)
        chunks = [compiled[i : i + chunk_size] for i in range(0, len(compiled), chunk_size)]
        # Compiled modules are cached per process; the semantics is part of their identity so that
        # runtimes with different modes or bounds never share module globals (review finding).
        modules = self._build(chunks, jobs, f"{semantics.mode}:{semantics.bound}:{semantics.modulus}:"
                              f"{semantics.max_string_length}:{semantics.max_list_length}")
        for module in modules:
            table.update({k: v for k, v in vars(module).items()
                          if k.startswith(("op_", "_e_")) and v is not None})  # skip placeholders
        for module in modules:
            vars(module).update(table)
        self._functions = table

    def compute(self, operator: Operator) -> Callable:
        return self._functions[operator.compute_name]

    def count(self, operator: Operator) -> Callable[..., int]:
        return self._functions[operator.count_name]

    def evaluate(self, operator: Operator) -> Callable[..., tuple]:
        return self._functions[evaluator_name(operator.func_id)]

    # ------------------------------------------------------------------
    def _build(self, chunks: list[list[Operator]], jobs: int, semantics_key: str):
        names, pending = [], []
        for index, chunk in enumerate(chunks):
            body = "\n\n".join(f"{op.op_compute_func}\n{op.op_count_func}" for op in chunk)
            source = (f"# cython: language_level=3\n# semantics: {semantics_key}\n"
                      f"from opulse.worlds.perm import Permutation\n\n{_placeholders(body)}\n{body}\n")
            digest = hashlib.sha256(source.encode()).hexdigest()[:12]
            name = f"opulse_ops_{index:04d}_{digest}"
            names.append(name)
            if not any(self.build_dir.glob(f"{name}.*.so")) and not (self.build_dir / f"{name}.so").exists():
                (self.build_dir / f"{name}.pyx").write_text(source, encoding="utf-8")
                pending.append(f"{name}.pyx")
        if pending:
            logger.info("cythonizing %d chunk(s) in %s", len(pending), self.build_dir)
            subprocess.run([sys.executable, "-m", "Cython.Build.Cythonize",
                            "-i", "-q", "-j", str(jobs), *pending], cwd=self.build_dir, check=True)
        if str(self.build_dir) not in sys.path:
            sys.path.insert(0, str(self.build_dir))
        return [importlib.import_module(name) for name in names]
