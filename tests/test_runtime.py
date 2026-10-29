import random
import shutil

import pytest

from opulse.config import Settings
from opulse.generation.pipeline import OperatorFactory, build_layers

cython = pytest.importorskip("Cython")


@pytest.mark.skipif(shutil.which("gcc") is None, reason="needs a C compiler")
def test_cython_runtime_matches_python_runtime(registry, tmp_path):
    from opulse.runtime.cython_backend import CythonRuntime

    build_layers(OperatorFactory(Settings(), registry, random.Random(5)), [10, 6, 4])
    compiled = CythonRuntime(registry, tmp_path / "build", chunk_size=8)
    from opulse.verify import Oracle, check_operator

    oracle = Oracle(registry)
    for op in registry:
        if op.definition is None:
            continue
        assert not check_operator(op, compiled.evaluate(op), oracle, random.Random(1), 100)
    # second construction hits the cache
    CythonRuntime(registry, tmp_path / "build", chunk_size=8)


def test_cython_runtimes_with_different_semantics_are_isolated(tmp_path):
    """Review finding: a compiled chunk was shared between exact and legacy runtimes."""
    pytest.importorskip("Cython")
    from conftest import INITIAL_OPERATORS

    from opulse.config import Symbols
    from opulse.core import SIMPLE, Operator, OperatorRegistry, Semantics
    from opulse.definition.codegen import compile_definition, registry_resolver
    from opulse.definition.parser import DefinitionParser
    from opulse.runtime.cython_backend import CythonRuntime
    from opulse.verify import Oracle

    registry = OperatorRegistry.from_jsonl(INITIAL_OPERATORS)
    op = Operator("cyiso", "⊕", 2, definition="a ⊕ b = { a + b }", definition_type=SIMPLE)
    code = compile_definition(DefinitionParser(Symbols(), registry).parse(op.definition), op.func_id,
                              registry_resolver(registry, op))
    op.op_compute_func, op.op_count_func, op.dependencies = code.compute, code.count, list(code.dependencies)
    registry.add(op)
    exact = CythonRuntime(registry, tmp_path, Semantics("exact", 5), jobs=1)
    legacy = CythonRuntime(registry, tmp_path, Semantics("legacy", 5), jobs=1)
    for runtime, mode in ((exact, "exact"), (legacy, "legacy")):
        expected = Oracle(registry, semantics=Semantics(mode, 5)).evaluate(op, (4, 4)).value
        assert runtime.evaluate(op)(4, 4)[0] is expected or runtime.evaluate(op)(4, 4)[0] == expected
    assert exact.evaluate(op)(4, 4)[0] is not legacy.evaluate(op)(4, 4)[0]
