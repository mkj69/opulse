"""Site-wide checks for published example puzzles."""

import json
from pathlib import Path

import pytest

from tools.audit_examples import (Puzzle, _featured_rules, collisions, load_puzzles,
                                  normalize_rule, publication_quality, recurring_family,
                                  trivial_template, violations)
from tools.example_registry import ExampleRegistry, quality_problems

ROOT = Path(__file__).resolve().parents[1]


def test_normalization_keeps_atoms_but_renames_custom_symbols_and_constants():
    first = "a ◆ b = { (a ★ b) + 3 }"
    second = "a ♣ b = { (a ▲ b) + 3 }"
    third = "a ♣ b = { (a ▲ b) + 5 }"
    assert normalize_rule(first) == normalize_rule(second)
    assert normalize_rule(first) != normalize_rule(third)
    assert normalize_rule(first, blind=True) == normalize_rule(third, blind=True)
    assert normalize_rule("a ◆ b = { a * b }") != normalize_rule("a ◆ b = { a + b }")
    assert normalize_rule("a ◆ b = { (a $) + b }") != normalize_rule("a ◆ b = { (# a) + b }")
    assert normalize_rule("a ◆ b = { a ⊕ b }", atom_symbols=("⊕",)) == "a ⊕ b"


def test_registry_excludes_other_puzzles_and_reserves_new_ones():
    registry = ExampleRegistry("docs/assets/data/challenge/target.json")
    text = "a ◆ b = { (a * b) + (a - b) }"
    puzzle = Puzzle("docs/assets/data/challenge/target.json", "new-target", "create",
                    (text,), "", "", (2, 3, 5, 7))
    registry.reserve(puzzle)
    assert registry.problems(Puzzle(puzzle.source, "other-target", "create",
                                    (text,), "", "", (2, 3, 5, 7)))


def test_reserved_recursion_cannot_move_to_another_puzzle():
    definition = "a ◆ b = { a, if b <= 0; (a ◆ (b - 1)) + (b * 2), else }"
    assert recurring_family(normalize_rule(definition, blind=True)) == "repeated-addition recursion"
    registry = ExampleRegistry("docs/assets/data/challenge/shorten.json")
    puzzle = Puzzle("docs/assets/data/challenge/shorten.json", "shorten-08", "create",
                    (definition,), "", "")
    assert any("reserved family" in problem for problem in registry.problems(puzzle))
    swapped_counter = "a ◆ b = { b, if a <= 0; ((a - 1) ◆ b) + b, else }"
    assert recurring_family(normalize_rule(swapped_counter, blind=True)) == "repeated-addition recursion"


def test_closure_helpers_are_not_tier_rules():
    row = {"question": "2 ★₉ 3", "rules": [
        {"symbol": "★₉", "text": "a ★₉ b = { a + b }"},
        {"symbol": "◈₁", "text": "a ◈₁ b = { a * b }"},
    ]}
    assert _featured_rules(row, "docs/assets/data/challenge/expert.json") == (row["rules"][0]["text"],)
    assert _featured_rules(row, "docs/assets/data/challenge/master.json") == (row["rules"][0]["text"],)
    assert _featured_rules(row, "docs/assets/data/challenge/legend.json") == (row["rules"][0]["text"],)
    row["variant"] = {"before": "a ◈₁ b = { a * b }",
                      "after": "a ◈₁ b = { a - b }"}
    assert _featured_rules(row, "docs/assets/data/challenge/expert.json") == (row["rules"][0]["text"],)


def test_published_tier_helper_variants_are_not_featured():
    legend = json.loads((ROOT / "docs/assets/data/challenge/legend.json").read_text())
    last = legend["challenges"][-1]
    assert "a - a" not in " ".join(_featured_rules(last, "docs/assets/data/challenge/legend.json"))
    row = {"question": "2 ★₁₀ 3", "rules": [
        {"symbol": "★₁", "text": "a ★₁ b = { a + b }"},
        {"symbol": "★₁₀", "text": "a ★₁₀ b = { a * b }"},
    ], "variant": {"after": "a ★₁ b = { a - b }"}}
    assert _featured_rules(row, "docs/assets/data/challenge/legend.json") == (
        row["rules"][1]["text"],)


def test_nested_tier_question_operators_are_helpers():
    row = {"question": "(2 ★₁₀ (◈₁ 3)) + (◈₁ 4)", "rules": [
        {"symbol": "★₁₀", "text": "a ★₁₀ b = { a + b }"},
        {"symbol": "◈₁", "text": "◈₁ a = { a * 2 }"},
    ]}
    assert set(_featured_rules(row, "docs/assets/data/challenge/expert.json")) == {
        rule["text"] for rule in row["rules"]}
    row["question"] = "2 ★₁₀ (◈₁ 3)"
    assert _featured_rules(row, "docs/assets/data/challenge/expert.json") == (
        row["rules"][0]["text"],)


@pytest.mark.parametrize(("rule", "reason"), [
    ("a ◈ b = { a * 1 + b }", "multiplication by one"),
    ("a ◈ b = { a, if a >= b; b, else }", "reserved family"),
])
def test_publication_filter_rejects_weak_or_reserved_rules(rule, reason):
    with pytest.raises(ValueError, match=reason):
        publication_quality([Puzzle("test.json", "new", "reason", (rule,), "", "")])


def test_publication_filter_rejects_published_rule():
    published_rule = load_puzzles()[0].rules[0]
    with pytest.raises(ValueError, match="duplicate featured rule"):
        publication_quality([Puzzle("test.json", "new", "reason", (published_rule,), "", "")])


def test_publication_filter_limits_constant_blind_templates():
    puzzles = [Puzzle("test.json", f"new-{number}", "reason",
                      (f"a ◈ b = {{ (a * b) + {number} }}",), "", "")
               for number in (41, 42, 43, 44)]
    publication_quality(puzzles[:3])
    with pytest.raises(ValueError, match="repeated template"):
        publication_quality(puzzles)


def test_tour_examples_and_embedded_snippets_match_generator():
    from tools.docs_induce_tour import RECIPES, make

    rows = json.loads((ROOT / "docs/assets/data/induce_tour.json").read_text())["puzzles"]
    assert rows == [make(recipe, index) for index, recipe in enumerate(RECIPES)]
    for language in ("docs", "docs_zh"):
        snippet = ROOT / language / "snippets/vis_induce.html"
        if language == "docs_zh" and not (ROOT / language).exists():
            continue
        html = snippet.read_text()
        embedded = html.split('<script type="application/json">', 1)[1].split("</script>", 1)[0]
        assert json.loads(embedded)["puzzles"] == rows


def test_world_challenges_count_against_other_angles_but_showcase_helpers_do_not():
    source = "docs/assets/data/worlds/integer/challenge.json"
    row = {"question": {"expression": "2 ◆ 3"}, "rules": [
        {"symbol": "◆", "text": "a ◆ b = { a + b }"},
        {"symbol": "◇", "text": "a ◇ b = { a * b }"},
    ]}
    assert _featured_rules(row, source) == (row["rules"][0]["text"],)
    first = Puzzle(source, "a", "integer", ("a ◆ b = { a + b }",), '"1 ◆ 2"', '"3"')
    second = Puzzle(source, "b", "integer", ("a ◇ b = { a + b }",), '"2 ◇ 3"', '"5"')
    other = Puzzle("docs/assets/data/challenge/target.json", "c", "create",
                   ("a ◆ b = { a + b }",), '"1 ◆ 2"', '"3"')
    assert violations([first, second])["rules"]
    assert violations([first, other])["rules"]
    assert not violations([first, other])["templates"]


def test_templates_allow_three_puzzles_in_two_angles():
    source = "docs/assets/data/challenge/target.json"
    def puzzle(identifier, angle, constant):
        return Puzzle(source, identifier, angle,
                      (f"a ★ b = {{ (a * b) + {constant} }}",),
                      f'"{identifier}"', f'"{identifier}"')
    first, second, third = (puzzle("first", "create", 2), puzzle("second", "reason", 3),
                            puzzle("third", "induce", 4))
    assert not violations([first, second])["templates"]
    assert not violations([first, second, third])["templates"]
    assert violations([first, second, third, puzzle("fourth", "create", 5)])["templates"]
    assert not violations([first, puzzle("same", "create", 3)])["templates"]
    assert not violations([first, puzzle("same", "create", 3), puzzle("same2", "create", 4)])["templates"]


def test_trivial_templates_and_recurring_families():
    assert trivial_template("b - a")
    assert trivial_template("a * #")
    assert trivial_template("(@OP1@ a) % #")
    assert not trivial_template("a + (b * #)")
    assert recurring_family("a - b, if a >= b; b - a, else") == "distance"
    assert recurring_family("(a + b) * #") == "(a + b) * #"
    rows = [Puzzle("test", f"id-{i}", "compute" if i < 2 else "reason",
                   (f"a ★ b = {{ (a + b) * {i + 2} }}",), str(i), str(i)) for i in range(4)]
    assert violations(rows)["families"]
    assert violations(rows)["templates"]


def test_quality_filter_rejects_inert_arithmetic_and_aliases():
    assert "multiplication by one" in quality_problems("a ★ b = { (a * 1) + b }")
    assert "subtracting an input from itself" in quality_problems("a ★ b = { (a - a) + b }")
    assert "unused parameter b" in quality_problems("a ★ b = { a + 2 }")
    assert "pure alias" in quality_problems("a ★ b = { a ◆ b }")
    assert "pure alias" in quality_problems("★ a = { ◆ a }")
    assert not quality_problems("a ★ b = { a - b }")
    assert "multiplication by zero" in quality_problems("a ★ b = { (a * 0) + b }")
    assert "double negation" in quality_problems("a ★ b = { - - a + b }")
    assert not quality_problems("a ★ b = { (a * b) + (a - b) }")


def test_published_puzzles_have_no_degenerate_featured_rules():
    for puzzle in load_puzzles():
        for rule in puzzle.rules:
            assert not quality_problems(rule), (puzzle.source, puzzle.identifier, rule)


def test_published_examples_are_unique_site_wide():
    puzzles = load_puzzles()
    assert len(puzzles) >= 200
    repeated = collisions(puzzles)
    bad = violations(puzzles)
    def summary(groups):
        return [(key, [row.identifier for row in owners])
                for key, owners in list(groups.items())[:3]]
    assert not bad["rules"], f"{len(bad['rules'])} identical rule bodies: {summary(bad['rules'])}"
    assert not bad["templates"], f"{len(bad['templates'])} overused templates: {summary(bad['templates'])}"
    assert not bad["families"], f"{len(bad['families'])} overused rule families: {summary(bad['families'])}"
    assert not bad["quality"], f"{len(bad['quality'])} degenerate rules: {summary(bad['quality'])}"
    assert not bad["number_sets"], f"repeated Target cards: {summary(bad['number_sets'])}"
    assert not bad["qa"], f"repeated question-answer pairs: {summary(bad['qa'])}"
    assert not bad["tier_questions"], f"repeated tier questions: {summary(bad['tier_questions'])}"
    assert not bad["atom_sets"], f"missing or dominant atom sets: {summary(bad['atom_sets'])}"
    assert not bad["missing_atoms"], f"puzzles without atom metadata: {summary(bad['missing_atoms'])}"
    # A repeated question with a different answer can be a deliberate contrast.
    assert all(len({row.answer for row in owners}) > 1
               for owners in repeated["questions"].values())


def test_every_published_puzzle_has_full_atom_entries():
    paths = sorted((ROOT / "docs/assets/data/challenge").glob("*.json"))
    paths += sorted((ROOT / "docs/assets/data/worlds").glob("*/challenge.json"))
    for path in paths:
        for row in json.loads(path.read_text(encoding="utf-8"))["challenges"]:
            assert row.get("atoms"), (path, row["id"])
            for atom in row["atoms"]:
                assert set(atom) == {"symbol", "name", "plain", "plain_zh", "example"}, (path, row["id"])
                assert all(atom[key] for key in atom), (path, row["id"], atom)
    for row in json.loads((ROOT / "docs/assets/data/induce_tour.json").read_text())["puzzles"]:
        assert row["atoms"] and all(set(atom) == {"symbol", "name", "plain", "plain_zh", "example"}
                                    for atom in row["atoms"])
