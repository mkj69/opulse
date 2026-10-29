"""Audit the rulebooks and prompts visible in the example puzzle sites.

Run ``PYTHONPATH=$PWD/src python tools/audit_examples.py`` from any directory.
The JSON exports are the publication boundary: a generator's unused candidates
are deliberately not counted as examples.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs/assets/data"
DEFINITION = re.compile(r"=\s*\{(.*)\}\s*$", re.S)
NUMBER = re.compile(r"(?<![\w₀-₉])-?\d+(?![\w₀-₉])")
HOME_RULE = re.compile(r"(?:[a-z] [^\s<>]+ [a-z]|[^\s<>]+ [a-z]) = \{[^{}]+\}")
BUILTIN_ATOMS = {"&", "$", "#", "@"}
FAMILY_OWNERS = {
    "max branch": {"laws-12"},
    "distance": {"tour-distance"},
    "cap": {"induce-03"},
    "parity switch": {"describe-09"},
    "(a + b) * #": {"shorten-03"},
    "a - (b * #)": {"describe-01"},
    "a + (b * #)": {"hole-03"},
    "(a * #) + b": {"induce-01"},
    "repeated-addition recursion": {"shorten-04"},
}
QUALITY_PATTERNS = {
    "multiplication by one": r"\*\s*1\b|\b1\s*\*",
    "addition of zero": r"\+\s*0\b|\b0\s*\+",
    "subtraction of zero": r"-\s*0\b",
    "division by one": r"/\s*1\b",
    "multiplication by zero": r"\*\s*0\b|\b0\s*\*",
    "subtracting an input from itself": r"\b([ab])\s*-\s*\1\b",
    "double negation": r"-\s*\(?\s*-\s*[a-d(]",
}


def quality_problems(text: str) -> list[str]:
    """Reject arithmetic that adds no insight to an example rule."""
    if "= {" not in text:
        return []
    lhs, body = text.split("= {", 1)
    body = body.rsplit("}", 1)[0].strip()
    problems = [reason for reason, pattern in QUALITY_PATTERNS.items()
                if re.search(pattern, body)]
    names = re.findall(r"\b[a-d]\b", lhs)
    for name in names:
        if not re.search(rf"\b{name}\b", body):
            problems.append(f"unused parameter {name}")
    binary = re.fullmatch(r"[a-d]\s+([^\w\s]+[₀-₉]*)\s+[a-d]", body)
    if len(names) == 2 and binary and binary.group(1) not in {"+", "-", "*", "/", "%"}:
        problems.append("pure alias")
    unary = re.fullmatch(r"(?:([^\w\s]+[₀-₉]*)\s+[a-d]|[a-d]\s+([^\w\s]+[₀-₉]*))", body)
    if len(names) == 1 and unary and (unary.group(1) or unary.group(2)) not in {"-", "+", "#", "&", "$"}:
        problems.append("pure alias")
    return problems


@dataclass(frozen=True)
class Puzzle:
    source: str
    identifier: str
    angle: str
    rules: tuple[str, ...]
    question: str
    answer: str
    numbers: tuple[int, ...] = ()
    atoms: tuple[str, ...] = ()
    atom_symbols: tuple[str, ...] = ()
    atom_field: bool = True


def _value(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _rule_texts(row: dict) -> tuple[str, ...]:
    texts = [r.get("text", r.get("definition", "")) for r in row.get("rules", ())]
    for key in ("reference_definition", "reference", "text"):
        value = row.get(key)
        if isinstance(value, str):
            texts.append(value)
    if isinstance(row.get("rule"), dict):
        texts.append(row["rule"].get("text", ""))
    edit = row.get("edit", {})
    if isinstance(edit, dict):
        texts.extend(edit.get(key, "") for key in ("before", "after"))
    variant = row.get("variant", {})
    if isinstance(variant, dict):
        texts.extend(variant.get(key, "") for key in ("before", "after"))
    if isinstance(row.get("reference_definition"), dict):
        texts.append(row["reference_definition"].get("text", ""))
    return tuple(dict.fromkeys(t for t in texts if DEFINITION.search(t)))


def _featured_rules(row: dict, source: str) -> tuple[str, ...]:
    """Exclude closure helpers; retain only the operators a puzzle asks about."""
    if source.endswith(('expert.json', 'master.json', 'legend.json')):
        question = row['question']
        featured = _question_roots(question, [rule['symbol'] for rule in row['rules']])
        if row.get('featured_symbol'):
            assert row['featured_symbol'] in featured, row['id']
            featured = {row['featured_symbol']}
        return tuple(dict.fromkeys(
            [rule['text'] for rule in row['rules']
             if rule['symbol'] in featured and DEFINITION.search(rule['text'])] +
            [text for text in _rule_texts({'variant': row.get('variant', {})})
             if any(rule['symbol'] in featured and re.search(
                    rf"{re.escape(rule['symbol'])}(?![₀-₉])", text.split('= {', 1)[0])
                    for rule in row['rules'])]))
    if '/worlds/' in source:
        if 'question' not in row:
            return _rule_texts(row)
        expression = row['question']['expression']
        return tuple(dict.fromkeys(
            [rule['text'] for rule in row['rules']
             if rule.get('symbol') and rule['symbol'] in expression
             and DEFINITION.search(rule['text'])] +
            list(_rule_texts({'edit': row.get('edit', {}), 'variant': row.get('variant', {})}))))
    return _rule_texts(row)


def _question_roots(expression: str, symbols: list[str]) -> set[str]:
    expression = expression.strip()
    while expression.startswith('(') and expression.endswith(')'):
        depth = 0
        for position, char in enumerate(expression):
            depth += (char == '(') - (char == ')')
            if depth == 0:
                break
        if position != len(expression) - 1:
            break
        expression = expression[1:-1].strip()
    if expression.startswith('- '):
        return _question_roots(expression[2:], symbols)
    depth = 0
    parts = []
    start = 0
    for position, char in enumerate(expression):
        depth += (char == '(') - (char == ')')
        if (depth == 0 and char in '+-*/%' and 0 < position < len(expression) - 1
                and expression[position - 1] == expression[position + 1] == ' '):
            parts.append(expression[start:position])
            start = position + 1
    if parts:
        return set().union(*(_question_roots(part, symbols) for part in
                             [*parts, expression[start:]]))
    pattern = re.compile('|'.join(re.escape(symbol) + r'(?![₀-₉])'
                                  for symbol in sorted(set(symbols), key=len, reverse=True)))
    depth = 0
    matches = []
    for position, char in enumerate(expression):
        depth += (char == '(') - (char == ')')
        match = pattern.match(expression, position)
        if match:
            matches.append((depth, match.group()))
    return {min(matches)[1]} if matches else set()


def _question_answer(row: dict) -> tuple[object, object]:
    if "numbers" in row:
        return (row["numbers"], row["target"], row["allowed"]), row["solution"]
    if "left" in row and "right" in row:
        return (row["left"], row["right"], row.get("domain")), (row.get("same"), row.get("counterexample"))
    if "statement" in row:
        return (row["statement"], row.get("domain")), (row.get("holds"), row.get("counterexample"))
    if "items" in row:
        return [item["expr"] for item in row["items"]], [item["changed"] for item in row["items"]]
    if "reference_definition" in row and "examples" in row:
        return ([item["inputs"] for item in row["examples"]], row.get("query", row.get("queries"))), row.get("answer")
    if "reference" in row and "direction" in row:
        return (row["direction"], row["reference"], row.get("description")), row.get("answer_index", row.get("reference"))
    if "text" in row and "reference" in row:
        return row["text"], row["reference"]
    if "branches" in row:
        return row["branches"], row.get("reason")
    return row.get("question", row.get("source", "")), row.get("answer", "")


def load_puzzles() -> list[Puzzle]:
    puzzles = []
    paths = sorted((DATA / "challenge").glob("*.json"))
    paths += sorted((DATA / "worlds").glob("*/challenge.json"))
    for path in paths:
        document = json.loads(path.read_text(encoding="utf-8"))
        source = str(path.relative_to(ROOT))
        angle = document.get("group", document.get("world", "compute"))
        for row in document["challenges"]:
            question, answer = _question_answer(row)
            if isinstance(question, dict):
                question = question.get("expression", question)
            atom_field = bool(row.get("atoms")) and all(isinstance(atom, dict) for atom in row["atoms"])
            atoms = row.get("atoms", ())
            if not atom_field:
                from tools.example_atoms import atom_entries
                atoms = atom_entries(row, document.get("world", "integer"))
            puzzles.append(Puzzle(source, row["id"], angle, _featured_rules(row, source),
                                  _value(question), _value(answer),
                                  tuple(sorted(row.get("numbers", ()))),
                                  tuple(sorted(atom["name"] if isinstance(atom, dict) else atom
                                               for atom in atoms)),
                                  tuple(sorted(atom["symbol"] if isinstance(atom, dict) else atom
                                               for atom in atoms)), atom_field))
    tour = json.loads((DATA / "induce_tour.json").read_text(encoding="utf-8"))
    for row in tour["puzzles"]:
        puzzles.append(Puzzle("docs/assets/data/induce_tour.json", "tour-" + row["key"],
                              "induce", tuple(dict.fromkeys(row["candidates"])),
                              _value([x["inputs"] for x in row["examples"] + row["queries"]]),
                              _value([x["output"] for x in row["queries"]]),
                              atoms=tuple(sorted(atom.get("name", atom["symbol"])
                                                 for atom in row.get("atoms", ()))),
                              atom_symbols=tuple(sorted(atom["symbol"]
                                                        for atom in row.get("atoms", ())))))
    page = (ROOT / "docs/index.md").read_text(encoding="utf-8")
    flagship = page.split('<div class="op-grid op-flagships">', 1)[1].split("## Data laws", 1)[0]
    for i, rule in enumerate(HOME_RULE.findall(flagship), 1):
        puzzles.append(Puzzle("docs/index.md", f"flagship-{i}",
                              "induce" if i == 1 else "invert", (rule,),
                              _value(flagship[flagship.find(rule) - 150:flagship.find(rule)]), ""))
    return puzzles


def normalize_rule(text: str, *, blind: bool = False,
                   atom_symbols: tuple[str, ...] = ()) -> str:
    """Keep atoms and inputs; consistently rename derived operator symbols."""
    match = DEFINITION.search(text)
    if not match:
        raise ValueError(f"not a definition: {text}")
    body = match.group(1)
    # Custom symbols are non-ASCII punctuation/symbol runs (possibly subscripted).
    symbols = [symbol for symbol in dict.fromkeys(
        re.findall(r"[^\w\s()+\-*/%<>=!,;{}.$&|]+[₀-₉]*", text))
        if symbol not in atom_symbols and symbol not in BUILTIN_ATOMS]
    for index, symbol in enumerate(symbols):
        body = body.replace(symbol, f"@OP{index}@")
    body = re.sub(r"\s+", " ", body).strip()
    return NUMBER.sub("#", body) if blind else body


def trivial_template(body: str) -> bool:
    """A single application of an atom, with no branch or composition."""
    return bool(re.fullmatch(r"(?:[ab] [+*/%-] [ab#]|"
                             r"\(?[#$&] [ab]\)?|[ab] [#$&]|\(@OP\d+@ [ab]\) % #)", body))


def recurring_family(body: str) -> str | None:
    """Identify the formerly ubiquitous textbook shapes independent of constants."""
    if body == "a, if a >= b; b, else":
        return "max branch"
    if body == "a - b, if a >= b; b - a, else":
        return "distance"
    if re.fullmatch(r"a \+ b, if a \+ b <= #; #, else", body):
        return "cap"
    if re.fullmatch(r"a \+ b, if b % # == #; a - b, else", body):
        return "parity switch"
    if body in {"(a + b) * #", "a - (b * #)", "a + (b * #)", "(a * #) + b"}:
        return body
    if (re.search(r"\ba @OP\d+@ \(b - #\)\)?\s*\+\s*(?:#|b|\(b \* #\)), else", body)
            or re.fullmatch(r"b, if a <= #; \(\(a - #\) @OP\d+@ b\) \+ b, else", body)):
        return "repeated-addition recursion"
    return None


def publication_quality(puzzles: list[Puzzle], *, allow: dict[str, str] | None = None) -> None:
    """Reject weak or reserved featured rules before publishing an export."""
    allow = allow or {}
    existing = {normalize_rule(text, atom_symbols=puzzle.atom_symbols)
                for puzzle in load_puzzles() if puzzle.source not in {row.source for row in puzzles}
                for text in puzzle.rules}
    templates: Counter[str] = Counter()
    seen: set[str] = set()
    for puzzle in puzzles:
        for text in puzzle.rules:
            problems = quality_problems(text)
            if problems:
                raise ValueError(f"{puzzle.identifier}: {', '.join(problems)}: {text}")
            rule = normalize_rule(text, atom_symbols=puzzle.atom_symbols)
            template = normalize_rule(text, blind=True, atom_symbols=puzzle.atom_symbols)
            family = recurring_family(template)
            if family and (allow.get(puzzle.identifier) != family or
                           puzzle.identifier not in FAMILY_OWNERS[family]):
                raise ValueError(f"{puzzle.identifier}: reserved family {family}: {text}")
            if rule in seen or (rule in existing and
                                not (family and allow.get(puzzle.identifier) == family)):
                raise ValueError(f"{puzzle.identifier}: duplicate featured rule: {text}")
            seen.add(rule)
            if not trivial_template(template):
                templates[template] += 1
                if templates[template] > 3:
                    raise ValueError(f"{puzzle.identifier}: repeated template: {text}")


def collisions(puzzles: list[Puzzle]) -> dict[str, dict[object, list[Puzzle]]]:
    groups: dict[str, dict[object, list[Puzzle]]] = {
        name: defaultdict(list) for name in ("rules", "templates", "number_sets", "questions", "answers", "qa")
    }
    for puzzle in puzzles:
        for rule in {normalize_rule(text, atom_symbols=puzzle.atom_symbols) for text in puzzle.rules}:
            groups['rules'][rule].append(puzzle)
        for rule in {normalize_rule(text, blind=True, atom_symbols=puzzle.atom_symbols)
                     for text in puzzle.rules}:
            if not trivial_template(rule):
                groups['templates'][rule].append(puzzle)
        if puzzle.numbers:
            groups["number_sets"][puzzle.numbers].append(puzzle)
        if puzzle.question not in ('""', '{}', '[]'):
            groups["questions"][puzzle.question].append(puzzle)
        if puzzle.answer not in ('""', '{}', '[]'):
            groups["answers"][puzzle.answer].append(puzzle)
        if puzzle.question not in ('""', '{}', '[]') and puzzle.answer not in ('""', '{}', '[]'):
            groups["qa"][(puzzle.question, puzzle.answer)].append(puzzle)
    return {name: {key: rows for key, rows in entries.items() if len(rows) > 1}
            for name, entries in groups.items()}


def violations(puzzles: list[Puzzle]) -> dict[str, dict[object, list[Puzzle]]]:
    repeated = collisions(puzzles)
    by_mode: dict[str, list[Puzzle]] = defaultdict(list)
    for puzzle in puzzles:
        if puzzle.source.startswith("docs/assets/data/challenge/"):
            by_mode[puzzle.source].append(puzzle)
    atom_sets = {}
    for mode, rows in by_mode.items():
        if len(rows) != 12:
            continue
        counts = Counter(row.atoms for row in rows)
        for atom_set, count in counts.items():
            if count > len(rows) // 2 or not atom_set:
                atom_sets[(mode, atom_set)] = [row for row in rows if row.atoms == atom_set]
    missing_atoms = {row.identifier: [row] for row in puzzles if not row.atom_field}
    quality = {(row.identifier, text): [row] for row in puzzles for text in row.rules
               if quality_problems(text)}
    tier_questions = {key: rows for key, rows in repeated['questions'].items()
                      if any(row.source.endswith(('expert.json', 'legend.json')) for row in rows)}
    families: dict[str, list[Puzzle]] = defaultdict(list)
    for puzzle in puzzles:
        for text in puzzle.rules:
            family = recurring_family(normalize_rule(text, blind=True,
                                                      atom_symbols=puzzle.atom_symbols))
            if family and puzzle not in families[family]:
                families[family].append(puzzle)
    return {"rules": repeated["rules"],
            "templates": {key: rows for key, rows in repeated["templates"].items()
                          if any(count > 3 for count in Counter(row.source for row in rows).values())},
            "families": {key: rows for key, rows in families.items()
                         if any(row.identifier not in FAMILY_OWNERS[key] for row in rows)},
            "quality": quality,
            "number_sets": repeated["number_sets"], "qa": repeated["qa"],
            "tier_questions": tier_questions,
            "atom_sets": atom_sets, "missing_atoms": missing_atoms}


def report(puzzles: list[Puzzle]) -> None:
    repeated = collisions(puzzles)
    bad = violations(puzzles)
    print("source | puzzles | rules | repeated rules | repeated templates | repeated number sets | repeated questions | repeated answers | missing atoms")
    print("--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---:")
    for source in sorted({p.source for p in puzzles}):
        rows = [p for p in puzzles if p.source == source]
        ids = {p.identifier for p in rows}
        def count(kind: str) -> int:
            return sum(len([p for p in owners if p.source == source]) for owners in repeated[kind].values())
        print(f"{source} | {len(rows)} | {sum(len(p.rules) for p in rows)} | {count('rules')} | "
              f"{count('templates')} | {count('number_sets')} | {count('questions')} | "
              f"{count('answers')} | {sum(not row.atom_field for row in rows)}")
    print("\nviolations:", ", ".join(f"{name}={len(rows)}" for name, rows in bad.items()))
    print("\nmode | atom set | puzzles")
    print("--- | --- | ---:")
    for source in sorted({p.source for p in puzzles}):
        rows = [p for p in puzzles if p.source == source]
        if not source.startswith("docs/assets/data/challenge/") or len(rows) != 12:
            continue
        for atom_set, count in sorted(Counter(row.atoms for row in rows).items(),
                                      key=lambda item: (-item[1], item[0])):
            print(f"{source.rsplit('/', 1)[-1]} | {', '.join(atom_set) or '(missing)'} | {count}")
    for name in ("rules", "templates", "families", "number_sets", "qa"):
        for key, rows in list(bad[name].items())[:30]:
            print(f"{name}: {key}: {', '.join(row.identifier for row in rows)}")
        if len(bad[name]) > 30:
            print(f"  ... {len(bad[name]) - 30} more {name} groups")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="fail on any uniqueness violation")
    args = parser.parse_args()
    puzzles = load_puzzles()
    report(puzzles)
    if args.strict and any(violations(puzzles).values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
