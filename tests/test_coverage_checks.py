"""Optional generation checks distinguish useful variation from constant or echoing outputs."""

import random
from types import SimpleNamespace

from opulse.core import NAN, Operator
from opulse.generation.checks import defined_share, defined_somewhere, varied_outputs


def _runtime(function):
    return SimpleNamespace(compute=lambda operator: function)


def test_variety_check_rejects_constants_and_echoes():
    operator = Operator(func_id="candidate", symbol="⊕", n_ary=1, unary_position="prefix")
    assert varied_outputs(operator, _runtime(lambda a: 7), random.Random(1), trials=20) == "nearly constant"
    assert varied_outputs(operator, _runtime(lambda a: a), random.Random(1), trials=20) == (
        "mostly returns an input")
    assert varied_outputs(operator, _runtime(lambda a: a * a + 1), random.Random(1), trials=20) is None


def test_definedness_checks_use_values_computed_on_probes():
    operator = Operator(func_id="candidate", symbol="⊕", n_ary=1, unary_position="prefix")
    never = _runtime(lambda a: NAN)
    sometimes = _runtime(lambda a: a if a >= 0 else NAN)
    always = _runtime(lambda a: a + 1)

    assert defined_somewhere(operator, never, random.Random(0), trials=5) == "undefined on all samples"
    assert defined_somewhere(operator, always, random.Random(0), trials=5) is None
    assert defined_share(operator, sometimes, random.Random(0), 0.75, (-10, 10), trials=80) == (
        "defined on too few inputs")
    assert defined_share(operator, always, random.Random(0), 1.0, (-10, 10), trials=80) is None
