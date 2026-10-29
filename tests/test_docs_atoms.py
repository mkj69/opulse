"""The published layer-0 glossary covers the rules users can see and copy."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs/assets"
WORLDS = ASSETS / "data/worlds"
ATOMS = ASSETS / "data/atoms"


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def symbols_in(text: str, known: set[str]) -> set[str]:
    symbols = set()
    for symbol in known:
        if symbol == "- (unary)":
            if re.search(r"(^|[({;=\n])\s*-\s*(?=[a-zA-Z(&#])", text):
                symbols.add(symbol)
        elif symbol == "-":
            if re.search(r"[a-zA-Z0-9)]\s+-\s+[a-zA-Z0-9(]", text):
                symbols.add(symbol)
        elif symbol in {"+", "*", "/", "%"}:
            if re.search(r"[a-zA-Z0-9)]\s*" + re.escape(symbol) + r"\s*[a-zA-Z0-9(-]", text):
                symbols.add(symbol)
        elif re.search(re.escape(symbol) + r"(?![₀-₉])", text):
            symbols.add(symbol)
    return symbols


def test_generated_catalogues_match_world_source():
    result = subprocess.run(["python3", "tools/docs_atoms.py", "--check"], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    for path in WORLDS.glob("*.json"):
        if path.stem == "index":
            continue
        world = read(path)
        catalogue = read(ATOMS / path.name)
        for atom in world["atoms"]:
            key = "- (unary)" if atom["symbol"] == "-" and len(atom["params"]) == 1 else atom["symbol"]
            entry = catalogue[key]
            assert set(entry) == {"name", "arity", "signature", "plain", "plain_zh", "example"}
            assert entry["arity"] == len(atom["params"])
            assert entry["plain"] == atom["plain"]
            assert entry["plain_zh"] == atom["plain_zh"]


def test_every_atom_in_published_rules_has_a_definition():
    catalogues = {path.stem: read(path) for path in ATOMS.glob("*.json")}
    expected = {path.stem: {"- (unary)" if atom["symbol"] == "-" and len(atom["params"]) == 1
                             else atom["symbol"] for atom in read(path)["atoms"]}
                for path in WORLDS.glob("*.json") if path.stem != "index"}
    for path in (ASSETS / "data/challenge").glob("*.json"):
        for puzzle in read(path)["challenges"]:
            for rule in puzzle.get("rules", []):
                world = rule["symbol"].split(" ", 1)[0] if path.stem == "translate" else "integer"
                assert symbols_in(rule["text"], expected[world]) <= set(catalogues[world]), (path, puzzle["id"], rule)
            prompt_texts = [puzzle.get(key, "") for key in
                            ("question", "statement", "left", "right", "reference", "text", "skeleton")]
            prompt_texts += [step.get("expr", "") for step in puzzle.get("steps", [])
                             if isinstance(step, dict)] if isinstance(puzzle.get("steps"), list) else []
            prompt_texts += [branch.get("text", "") for branch in puzzle.get("branches", [])]
            prompt_texts += [entry.get("expr", "") for entry in puzzle.get("items", [])]
            prompt_texts += [puzzle.get("edit", {}).get(key, "") for key in ("before", "after")]
            prompt_texts += [puzzle.get("rule", {}).get("text", "")]
            prompt_texts += puzzle.get("atoms", []) + puzzle.get("allowed", [])
            prompt_texts = [value for value in prompt_texts if isinstance(value, str)]
            worlds = (puzzle["source_world"], puzzle["target_world"]) if path.stem == "translate" else ("integer",)
            for world in worlds:
                assert symbols_in("\n".join(prompt_texts), expected[world]) <= set(catalogues[world]), (path, puzzle["id"])
            if path.stem in {"challenges", "expert", "master", "legend"}:
                for rule in puzzle.get("rules", []):
                    assert symbols_in(rule["text"], expected["integer"]) <= set(catalogues["integer"])
                assert symbols_in(puzzle["variant"]["after"], expected["integer"]) <= set(catalogues["integer"])
    for path in WORLDS.glob("*/challenge.json"):
        world = path.parent.name
        for puzzle in read(path)["challenges"]:
            texts = [rule["text"] for rule in puzzle.get("rules", [])]
            if puzzle.get("reference_definition"):
                texts.append(puzzle["reference_definition"]["text"])
            if puzzle.get("variant"):
                texts.append(puzzle["variant"]["after"])
            assert symbols_in("\n".join(texts), expected[world]) <= set(catalogues[world]), (path, puzzle["id"])
    for path in WORLDS.glob("*.json"):
        if path.stem == "index":
            continue
        world = read(path)
        texts = [operator.get("definition", "") for operator in world["operators"]]
        assert symbols_in("\n".join(texts), expected[path.stem]) <= set(catalogues[path.stem]), path
    for path in (ASSETS / "data/scales").glob("*/*.json"):
        example = read(path)
        if "header" not in example:
            continue
        world = example["header"]["world"]
        texts = [operator.get("definition", "") or "" for operator in example["operators"]]
        texts.append(example["header"]["expression"])
        assert symbols_in("\n".join(texts), expected[world]) <= set(catalogues[world]), path


def test_widgets_load_shared_legend_and_chinese_build_keeps_localizations():
    config = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    assert "assets/js/atoms-legend.js" in config
    assert "assets/css/atoms-legend.css" in config
    files = ["challenge.js", "challenge-modes.js", "home-scales.js", "scales-tour.js",
             "scales-solve.js", "granularity.js", "granularity-anim.js", "opulse-vis.js",
             "worlds/challenge.js"]
    for name in files:
        source = (ASSETS / "js" / name).read_text(encoding="utf-8")
        assert "OpulseAtoms.legend" in source, name
    assert "What these atoms do" in (ASSETS / "js/worlds/core.js").read_text(encoding="utf-8")
    if (ROOT / "docs_zh").is_dir():
        for name in ["challenge.js", "home-scales.js", "scales-tour.js", "scales-solve.js",
                     "granularity.js", "granularity-anim.js", "opulse-vis.js"]:
            source = (ROOT / "docs_zh/snippets/localized_assets/js" / name).read_text(encoding="utf-8")
            assert "OpulseAtoms.legend" in source, name


def test_copied_prompts_include_localized_atom_definitions():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js unavailable")
    script = r"""
const assert = require('node:assert/strict');
const path = require('node:path');
const root = process.argv[1];
const atoms = require(path.join(root, 'docs/assets/js/atoms-legend.js'));
const {computePrompt} = require(path.join(root, 'docs/assets/js/challenge.js'));
const {promptFor, atomTexts, atomWorld} = require(path.join(root, 'docs/assets/js/challenge-modes.js'));
const compute = require(path.join(root, 'docs/assets/data/challenge/challenges.json')).challenges[0];
const puzzle = require(path.join(root, 'docs/assets/data/challenge/wrongstep.json')).challenges[0];
const expert = require(path.join(root, 'docs/assets/data/challenge/expert.json')).challenges.find(x => x.id === 'expert-03');
for (const mode of ['wrongstep','hole','equiv','laws','deadbranch','ripple','induce','translate','shorten','describe','target']) {
  const item = require(path.join(root, 'docs/assets/data/challenge', mode + '.json')).challenges[0];
  assert(Array.isArray(atomTexts(mode, item)), mode);
  assert(atomWorld(mode, item), mode);
}
Promise.all(['en','zh'].map(async lang => {
  const def = await atoms.promptLines('integer', ['# a', '& a', 'a @', '- (a + b)'], lang);
  assert(def.includes('# 4 = 10') && def.includes('& (-123) = -6'));
  assert(def.includes(lang === 'zh' ? '原子操作：' : 'Atoms used:'));
  assert(!def.includes(lang === 'zh' ? 'is integer addition' : '整数加法'));
  assert(computePrompt(compute, 0, lang, def).includes(def));
  assert(promptFor('wrongstep', puzzle, lang, def).includes(def));
  if (lang === 'zh') {
    assert(promptFor('wrongstep', puzzle, lang, def).includes('找出推导中第一处错误'));
    assert(!promptFor('wrongstep', puzzle, lang, def).includes('Find the first wrong step'));
  }
  const expertLines = await atoms.promptLines('integer', expert.rules.map(rule => rule.text), lang);
  for (const symbol of ['#', '$', '@', '&']) assert(expertLines.includes('- ' + symbol + ': '));
})).catch(error => { console.error(error); process.exitCode = 1; });
"""
    result = subprocess.run([node, "-e", script, str(ROOT)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
