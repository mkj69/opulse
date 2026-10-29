"""Shared exclusion list for example generators.

Generators run in a fixed order. Each one excludes its own existing export,
loads every other published puzzle, and reserves accepted replacements as it
goes. This keeps regeneration deterministic and fails loudly if a curated
candidate would repeat a rule, overuse a template, or reuse a Target card set.
"""

from __future__ import annotations

from collections import defaultdict

from tools.audit_examples import (FAMILY_OWNERS, Puzzle, load_puzzles, normalize_rule,
                                  quality_problems, recurring_family, trivial_template)


class ExampleRegistry:
    def __init__(self, exclude_source: str):
        self.rules: dict[str, set[str]] = defaultdict(set)
        self.templates: dict[str, dict[str, str]] = defaultdict(dict)
        self.families: dict[str, set[str]] = defaultdict(set)
        self.number_sets: dict[tuple[int, ...], set[str]] = defaultdict(set)
        self.qa: dict[tuple[str, str], set[str]] = defaultdict(set)
        self.questions: dict[str, set[str]] = defaultdict(set)
        for puzzle in load_puzzles():
            if puzzle.source != exclude_source:
                self._add(puzzle)

    def _add(self, puzzle: Puzzle) -> None:
        tier = puzzle.source.endswith(('expert.json', 'master.json', 'legend.json'))
        for text in puzzle.rules:
            self.rules[normalize_rule(text, atom_symbols=puzzle.atom_symbols)].add(puzzle.identifier)
            template = normalize_rule(text, blind=True, atom_symbols=puzzle.atom_symbols)
            if not trivial_template(template):
                self.templates[template][puzzle.identifier] = puzzle.source
            family = recurring_family(template)
            if family:
                self.families[family].add(puzzle.identifier)
        if tier and puzzle.question not in ('""', '{}', '[]', ''):
            self.questions[puzzle.question].add(puzzle.identifier)
        if puzzle.numbers:
            self.number_sets[puzzle.numbers].add(puzzle.identifier)
        if puzzle.question not in ('""', '{}', '[]', '') and puzzle.answer not in ('""', '{}', '[]', ''):
            self.qa[(puzzle.question, puzzle.answer)].add(puzzle.identifier)

    def problems(self, puzzle: Puzzle) -> list[str]:
        problems = []
        tier = puzzle.source.endswith(('expert.json', 'master.json', 'legend.json'))
        for text in puzzle.rules:
            problems.extend(quality_problems(text))
            key = normalize_rule(text, atom_symbols=puzzle.atom_symbols)
            owners = self.rules[key] - {puzzle.identifier}
            if owners:
                problems.append(f"rule {key!r} already used by {sorted(owners)}")
            template = normalize_rule(text, blind=True, atom_symbols=puzzle.atom_symbols)
            if not trivial_template(template):
                owners = {owner: source for owner, source in self.templates[template].items()
                          if owner != puzzle.identifier and source == puzzle.source}
                if len(owners) >= 3:
                    problems.append(f"template {template!r} already used by {owners}")
            family = recurring_family(template)
            if family and puzzle.identifier not in FAMILY_OWNERS[family]:
                problems.append(f"reserved family {family!r} belongs to {sorted(FAMILY_OWNERS[family])}")
        if tier and self.questions[puzzle.question] - {puzzle.identifier}:
            problems.append('tier question already used by ' +
                            str(sorted(self.questions[puzzle.question] - {puzzle.identifier})))
        if puzzle.numbers and self.number_sets[puzzle.numbers] - {puzzle.identifier}:
            problems.append(f"number cards {puzzle.numbers} already used by "
                            f"{sorted(self.number_sets[puzzle.numbers])}")
        if (puzzle.question, puzzle.answer) in self.qa and (
            self.qa[(puzzle.question, puzzle.answer)] - {puzzle.identifier}
        ):
            problems.append("question and answer already used by " +
                            str(sorted(self.qa[(puzzle.question, puzzle.answer)] - {puzzle.identifier})))
        return problems

    def reserve(self, puzzle: Puzzle) -> None:
        problems = self.problems(puzzle)
        if problems:
            raise ValueError(f"{puzzle.identifier}: " + "; ".join(problems))
        self._add(puzzle)
