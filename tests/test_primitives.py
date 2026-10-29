"""User-defined atoms run through every stage: generation, interpretation, the benchmark, z3."""

import json
import random

import pytest
import z3

from opulse.cli.main import main
from opulse.core import NAN
from opulse.core.primitives import (
    CUSTOM,
    atom_records,
    register_primitive,
    rule_for,
    unregister_primitive,
    write_initial_set,
)
from opulse.core.semantics import Semantics


@pytest.fixture
def atoms():
    register_primitive("cube", "⊛", lambda a: a ** 3, rule="a ⊛ is a * a * a.")
    register_primitive("maxab", "⩔", lambda a, b: max(a, b), n_ary=2, position=None,
                       rule="a ⩔ b is the larger of a and b.", z3=lambda a, b: z3.If(a > b, a, b))
    yield
    for name in list(CUSTOM):
        unregister_primitive(name)


def test_registration_is_validated(atoms):
    with pytest.raises(ValueError, match="built-in"):
        register_primitive("add", "⊕", lambda a, b: a + b, n_ary=2, position=None, rule="x")
    with pytest.raises(ValueError, match="already denotes"):
        register_primitive("other", "+", lambda a, b: a, n_ary=2, position=None, rule="x")
    with pytest.raises(ValueError, match="digits"):
        register_primitive("sq", "²", lambda a: a * a, rule="x")
    with pytest.raises(ValueError, match="rule"):
        register_primitive("sq", "⊡", lambda a: a * a, rule=" ")
    assert rule_for("cube") == "a ⊛ is a * a * a." and rule_for("add").startswith("a + b")


def test_semantics_wraps_nan_and_the_bound(atoms):
    ops = Semantics("exact", 1000).operations()
    assert ops["cube"](3) == 27 and ops["cube"](NAN) is NAN
    assert ops["cube"](11) is NAN  # 1331 is beyond the bound
    assert ops["maxab"](-4, 2) == 2


def test_generation_and_benchmark_with_custom_atoms(atoms, tmp_path):
    initial = write_initial_set(tmp_path / "initial.jsonl", ["succ", "pred", "neg", "add", "sub", "mod",
                                                             "cube", "maxab"])
    ops = tmp_path / "ops.jsonl"
    assert main(["operators", "--initial", str(initial), "--out", str(ops), "--layers", "10", "6", "3",
                 "--seed", "3"]) == 0
    definitions = [json.loads(line)["definition"] for line in ops.read_text().splitlines()]
    assert any(d and ("⊛" in d or "⩔" in d) for d in definitions)
    expressions = tmp_path / "expr.jsonl"
    assert main(["expressions", "--operators", str(ops), "--out", str(expressions), "--count", "20",
                 "--cot", "en"]) == 0
    assert main(["verify", "--operators", str(ops), "--expressions", str(expressions)]) == 0
    tasks = tmp_path / "tasks.jsonl"
    assert main(["bench", "build", "--operators", str(ops), "--out", str(tasks), "--count", "10",
                 "--max-depth", "2"]) == 0
    assert main(["bench", "check", "--tasks", str(tasks), "--operators", str(ops)]) == 0
    prompts = [json.loads(line)["prompt"] for line in tasks.read_text().splitlines()]
    uses = [p for p in prompts if "⊛" in p.split("Definitions:")[-1] or "⩔" in p.split("Definitions:")[-1]]
    assert all("a ⊛ is a * a * a." in p or "larger of a and b" in p for p in uses)


def test_atom_with_z3_encoding_is_solvable(atoms, tmp_path):
    from opulse.core.registry import OperatorRegistry
    from opulse.solver.z3_encode import Z3Encoder
    from opulse.verify import Oracle

    path = tmp_path / "start.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in atom_records(["add", "cube", "maxab"],
                                                                       random.randrange(100))))
    registry = OperatorRegistry.from_jsonl(path)
    encoder = Z3Encoder(Oracle(registry))
    by_symbol = {op.symbol: op for op in registry}
    assert encoder.expressible(by_symbol["⩔"])      # supplied an encoding
    assert not encoder.expressible(by_symbol["⊛"])  # none: skipped by solver-based analyses
