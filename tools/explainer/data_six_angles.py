"""Interpreter-backed examples for six distinct reasoning tasks."""
from opulse.playground import Workspace, check_equivalent

from data import RULES


def build() -> dict:
    definitions = "\n".join((*RULES.values(), "a ■ b = { a, if a >= b; b, else }"))
    workspace = Workspace(definitions)

    def value(expression: str) -> str:
        result = workspace.evaluate(expression)
        assert result["agrees"] and not result["truncated"], expression
        return result["value"]

    computation = "3 ★ 2"
    inversion = "5 ◆ 4"
    creation = "3 ★ 3"
    examples = ["1 ■ 2", "4 ■ 2", "5 ■ 9"]
    checked_pair = ["3 ▲ 7", "7 ▲ 3"]
    assert value(computation) == "9"
    assert value(inversion) == "41"
    assert all(value(f"{candidate} ◆ 4") != value(inversion)
               for candidate in range(10) if candidate != 5)
    assert [value(expression) for expression in checked_pair] == ["4", "4"]
    equivalence = check_equivalent(definitions, "▲",
                                   "a ▲ b = { b - a, if b >= a; a - b, else }", [-9, 9])
    assert equivalence["equivalent"] and equivalence["parse_error"] is None
    assert [value(expression) for expression in examples] == ["2", "4", "9"]
    assert value(creation) == "27"

    return {"angles": [
        {"name": "Compute", "meaning": "Follow rules to a result",
         "expression": computation, "result": value(computation)},
        {"name": "Invert", "meaning": "Work back to an input",
         "symbol": "◆", "given": "4", "target": value(inversion), "candidate": inversion.split()[0]},
        {"name": "Decide", "meaning": "Prove or refute a claim",
         "claim": "a ▲ b = b ▲ a", "checks": [
             {"expression": expression, "value": value(expression)} for expression in checked_pair],
         "equivalent": equivalence["equivalent"], "domain": [-9, 9]},
        {"name": "Describe", "meaning": "Rule into plain language",
         "rule": RULES["squares"], "words": ["the sum of the squares", "of a and b"]},
        {"name": "Induce", "meaning": "Infer a rule from examples",
         "rule": "a ■ b = { a, if a >= b; b, else }",
         "examples": [{"expression": expression, "value": value(expression)} for expression in examples],
         "words": "the larger of a and b"},
        {"name": "Create", "meaning": "Build for a target",
         "expression": creation, "target": value(creation)},
    ]}
