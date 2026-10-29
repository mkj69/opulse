"""The published challenge ladder follows its written definitions."""

import json
from collections import Counter
from difflib import SequenceMatcher

from tools.audit_examples import (
    load_puzzles,
    normalize_rule,
    quality_problems,
    recurring_family,
    trivial_template,
)
from tools.challenge_candidates import (
    OUTPUT,
    RECIPES,
    Spec,
    definitions,
    generate,
    guesses,
    hints,
    page_steps,
    readable_rules,
    rule_template,
    small_intermediates,
    trace_data,
)


def test_challenge_json_is_reproducible():
    expected = (json.dumps(generate(), ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()
    assert OUTPUT.read_bytes() == expected


def test_every_published_derivation_and_mutation_verifies():
    data = json.loads(OUTPUT.read_text(encoding="utf-8"))
    assert data["schema"] == "opulse.challenge/1"
    rows = data["challenges"]
    assert len(rows) == 30
    assert [row["level"] for row in rows] == ["easy"] * 8 + ["medium"] * 14 + ["hard"] * 8
    assert Counter(row["level"] for row in rows) == {"easy": 8, "medium": 14, "hard": 8}
    assert sum(RECIPES[row["parameters"]["recipe"]].recursive for row in rows if row["level"] == "hard") >= 1
    specs = [Spec(**row["parameters"]) for row in rows]
    assert len({rule_template(definitions(spec), spec.symbols) for spec in specs}) == 30
    bodies = [rule["text"] for row in rows for rule in row["rules"]]
    assert len({normalize_rule(body) for body in bodies}) == len(bodies)
    assert max(Counter(normalize_rule(body, blind=True) for body in bodies
                       if not trivial_template(normalize_rule(body, blind=True))).values()) <= 3
    published = [puzzle for puzzle in load_puzzles()
                 if puzzle.source == "docs/assets/data/challenge/challenges.json"]
    all_templates = [normalize_rule(body, blind=True) for puzzle in published for body in puzzle.rules]
    assert max(Counter(template for template in all_templates
                       if not trivial_template(template)).values()) <= 3
    assert not any(quality_problems(body) for body in bodies)
    assert not any(recurring_family(normalize_rule(body, blind=True)) for body in bodies)
    assert len({atom["name"] for row in rows for atom in row["atoms"]} - {"add", "sub", "mul"}) >= 5
    assert len({tuple(spec.symbols) for spec in specs}) > 8
    assert len({RECIPES[spec.recipe].question_shape for spec in specs}) > 2
    limits = {"easy": (4, 8, 2), "medium": (7, 16, 3), "hard": (10, 17, None)}
    for row, spec in zip(rows, specs):
        texts = definitions(spec)
        low, high, rule_count = limits[row["level"]]
        assert len(row["rules"]) == (rule_count or len(RECIPES[spec.recipe].bodies))
        assert row["level"] != "hard" or len(row["rules"]) in (3, 4)
        assert [rule["text"] for rule in row["rules"]] == texts
        assert readable_rules(spec, [rule["text"] for rule in row["rules"]])
        assert [rule["hint"] for rule in row["rules"]] == hints(spec)
        assert all(rule["hint"] and "stated number" not in rule["hint"].lower() for rule in row["rules"])
        assert all("\n" not in rule["text"] for rule in row["rules"])
        trace = trace_data(spec, texts)  # verifies every step through verify_trace
        for key in ("question", "answer", "step_count", "derivation"):
            assert row[key] == trace[key]
        assert row["steps"] == page_steps(row["question"], row["derivation"])
        assert low <= row["step_count"] <= high
        assert small_intermediates(trace)
        assert row["trap_answers"] == guesses(spec, row["answer"])
        assert row["trap_answers"]
        assert all(value != row["answer"] for value in row["trap_answers"].values())
        variant = row["variant"]
        varied = definitions(spec, variant["mutation"])
        assert readable_rules(spec, varied)
        index = variant["rule_index"]
        assert [(a != b) for a, b in zip(texts, varied)] == [i == index for i in range(len(texts))]
        assert (variant["before"], variant["after"]) == (texts[index], varied[index])
        edits = [op for op in SequenceMatcher(None, variant["before"], variant["after"]).get_opcodes()
                 if op[0] != "equal"]
        assert len(edits) == 1
        _, start, end, new_start, new_end = edits[0]
        assert max(end - start, new_end - new_start) == 1
        checked = trace_data(spec, varied)
        for key in ("answer", "step_count", "derivation"):
            assert variant[key] == checked[key]
        assert variant["steps"] == page_steps(row["question"], variant["derivation"])
        assert variant["answer"] != row["answer"]
        assert variant["answer"] not in row["trap_answers"].values()
        assert row["single_symbol_mutations"] == {variant["mutation"]: variant["answer"]}
        assert low <= variant["step_count"] <= high
        assert small_intermediates(checked)


def test_readability_filter_rejects_unhelpful_binary_rules():
    data = json.loads(OUTPUT.read_text(encoding="utf-8"))
    spec = Spec(**data["challenges"][0]["parameters"])
    first, second = spec.symbols
    texts = definitions(spec)
    bad_bodies = (
        "(a + b) * 1", "1 * (a + b)", "(a + b) + 0",
        "0 + (a + b)", "(a + b) - 0", "(a + b) / 1",
        "- (- (a + b))", "(a - a) + b", "a + 2", "b + 2",
        f"a {second} b", f"b {second} a",
    )
    for body in bad_bodies:
        changed = texts.copy()
        changed[0] = f"a {first} b = {{ {body} }}"
        assert not readable_rules(spec, changed), body
    cancelled = [f"a {first} b = {{ a - b }}",
                 f"a {second} b = {{ (a + b) {first} b }}"]
    assert not readable_rules(spec, cancelled)
    same_branches = texts.copy()
    same_branches[0] = f"a {first} b = {{ a + b, if a > 2; a + b, else }}"
    assert not readable_rules(spec, same_branches)
