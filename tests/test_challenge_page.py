"""The small challenge page uses checked, shareable puzzle records."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import requires_zh_site
from opulse.playground import check_equivalent, run

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs/assets/data/challenge/challenges.json"
EXPERT = ROOT / "docs/assets/data/challenge/expert.json"
LEGEND = ROOT / "docs/assets/data/challenge/legend.json"


def test_page_is_in_the_english_nav_and_assets_are_registered():
    english = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    assert english.index("- Tour:") < english.index("- Challenge:") < english.index("- Worlds:")
    assert "assets/js/challenge.js" in english
    assert "assets/js/challenge-modes.js" in english
    assert "assets/css/challenge.css" in english
    assert "# Learn this tiny world" in (ROOT / "docs/challenge.md").read_text(encoding="utf-8")


@requires_zh_site
def test_chinese_page_mirrors_the_english_assets():
    chinese = (ROOT / "mkdocs.zh.yml").read_text(encoding="utf-8")
    assert chinese.index("- 导览:") < chinese.index("- 挑战:") < chinese.index("- 世界:")
    assert "# 学会这个小世界" in (ROOT / "docs_zh/challenge.md").read_text(encoding="utf-8")
    assert (ROOT / "docs/assets/js/challenge.js").read_bytes() == (
        ROOT / "docs_zh/snippets/localized_assets/js/challenge.js"
    ).read_bytes()
    assert EXPERT.read_bytes() == (ROOT / "docs_zh/assets/data/challenge/expert.json").read_bytes()
    assert LEGEND.read_bytes() == (ROOT / "docs_zh/assets/data/challenge/legend.json").read_bytes()
    assert (ROOT / "docs/assets/css/challenge.css").read_bytes() == (
        ROOT / "docs_zh/assets/css/challenge.css"
    ).read_bytes()
    assert (ROOT / "docs/assets/js/challenge-answer.js").read_bytes() == (
        ROOT / "docs_zh/assets/js/challenge-answer.js"
    ).read_bytes()
    assert (ROOT / "docs/assets/js/scales-core.js").read_bytes() == (
        ROOT / "docs_zh/assets/js/scales-core.js"
    ).read_bytes()


def test_picker_and_large_step_controls_exist():
    script = (ROOT / "docs/assets/js/challenge.js").read_text(encoding="utf-8")
    modes = (ROOT / "docs/assets/js/challenge-modes.js").read_text(encoding="utf-8")
    style = (ROOT / "docs/assets/css/challenge.css").read_text(encoding="utf-8")
    assert 'load("challenges.json")' in modes
    assert 'load("expert.json")' in modes
    assert 'load("legend.json")' in modes
    assert 'catch(function () { return data; })' in modes
    for marker in ("challenge-picker-toggle", "challenge-tile", "aria-current",
                   "challenge-header-nav", "challenge-rule-search", "challenge-rule-group",
                   "challenge-step-modes", "challenge-step-view", "OpulseStepView.render"):
        assert marker in script
    assert "50" in script
    assert "max-height: 22rem" in style
    assert "challenge-tile-legend" in style
    assert "example.fullPage(offset, size)" in script
    assert 'whyLabel: "Why this one"' in script
    assert 'whyLabel: "这题的看点"' in script
    assert 'lang === "zh" ? "why_zh" : "why"' in script


def test_grouped_mode_wiring_and_renderers():
    script = (ROOT / "docs/assets/js/challenge-modes.js").read_text(encoding="utf-8")
    groups = {
        "compute": ("compute", "wrongstep"),
        "invert": ("hole",),
        "decide": ("equiv", "laws", "deadbranch", "ripple"),
        "describe": ("describe",),
        "induce": ("induce", "translate"),
        "create": ("shorten", "target"),
    }
    assert [script.index(f'id: "{group}"') for group in groups] == sorted(
        script.index(f'id: "{group}"') for group in groups
    )
    for group, names in groups.items():
        assert f'id: "{group}"' in script
        assert 'modes: [' + ', '.join(f'"{name}"' for name in names) + ']' in script
    for label in ("Follow the rules", "Find the wrong step", "Find the unknown", "Same or different?",
                  "True or false law", "Find the dead end", "Trace the ripple", "Guess the rule",
                  "Cross-world analogy", "Simplify the definition", "依规演算", "查找错步", "逆求未知",
                  "判定等价", "定律真伪", "找出死路", "连锁追踪", "归纳规则", "跨界类比", "精简定义",
                  "Name it or write it", "转述规则", "Hit the target", "凑出目标"):
        assert label in script
    for marker in ("challenge-group-tab", "challenge-mode-chip", "renderTask", "fillReveal",
                   'method: "HEAD"', "OpulseCheck.ready", "OpulseWorlds.renderValue",
                   'searchParams.set("mode"', "challenge-scan-cell"):
        assert marker in script
    assert 'api.renderValue = async function' in (ROOT / "docs/assets/js/worlds/core.js").read_text(encoding="utf-8")


def test_temporary_mode_fixtures_have_checked_shape():
    # Existing fixture group fields remain intact; the UI maps each mode to its new group.
    for mode, group in (("wrongstep", "execute"), ("hole", "reason"), ("equiv", "reason"),
                        ("ripple", "reason"), ("laws", "reason"), ("deadbranch", "reason"),
                        ("describe", "describe"), ("induce", "induce"), ("translate", "induce"),
                        ("shorten", "create"), ("target", "create")):
        data = json.loads((ROOT / f"docs/assets/data/challenge/{mode}.json").read_text(encoding="utf-8"))
        assert data["schema"] == "opulse.challenge-mode/1"
        assert (data["mode"], data["group"]) == (mode, group)
        assert len(data["challenges"]) >= 2
        assert len({item["id"] for item in data["challenges"]}) == len(data["challenges"])
        assert all(item["verified"] and item["why"] and item["why_zh"] for item in data["challenges"])


def test_describe_and_target_fixtures_use_the_interpreter():
    describe = json.loads((ROOT / "docs/assets/data/challenge/describe.json").read_text(encoding="utf-8"))
    assert len(describe["challenges"]) == 12
    assert {item["direction"] for item in describe["challenges"]} == {"name", "write"}
    for item in describe["challenges"]:
        definitions = "\n".join([*(rule["text"] for rule in item["rules"]), item["reference"]])
        assert item["arity"] == 2 and item["verified"]
        assert run(definitions, f"2 {item['symbol']} 3")["ok"], item["id"]
        if item["direction"] == "name":
            assert item["rule"]["text"] == item["reference"]
            assert len(item["options"]) == len(item["option_notes"]) == 4
            assert 0 <= item["answer_index"] < 4
        else:
            assert check_equivalent(definitions, item["symbol"], item["reference"],
                                    item["domain"])["equivalent"], item["id"]
    target = json.loads((ROOT / "docs/assets/data/challenge/target.json").read_text(encoding="utf-8"))
    for item in target["challenges"]:
        assert 4 <= len(item["numbers"]) <= 6
        assert item["solutions_count"] >= 1 and item["size_limit"] >= 1
        assert run("\n".join(rule["text"] for rule in item["rules"]), item["solution"])["value"] == str(item["target"])


def test_mode_prompts_use_plain_domains_and_world_columns():
    script = (ROOT / "docs/assets/js/challenge-modes.js").read_text(encoding="utf-8")
    style = (ROOT / "docs/assets/css/challenge.css").read_text(encoding="utf-8")
    assert 'item.question + " = " + item.target' in script
    assert '"Find x between "' in script
    assert '" always equal to "' in script
    assert '"Same: " + (item.proof === "z3"' in script
    assert '"Line " + (item.wrong_index + 1) + " is wrong: it should be "' in script
    assert '" steps; the budget is " + item.budget_steps' in (
        ROOT / "docs/assets/js/challenge-answer.js"
    ).read_text(encoding="utf-8")
    assert "challenge-translation-rules" in script and "challenge-translation-atom" in script
    assert "repeat(6, minmax(0, 1fr))" in style
    assert "challenge-encoded-value" in style
    if (ROOT / "docs_zh").is_dir():
        assert (ROOT / "docs_zh/assets/js/challenge-modes.js").read_bytes() == (
            ROOT / "docs/assets/js/challenge-modes.js"
        ).read_bytes()


def test_legend_trace_references_and_chunks_resolve():
    data = json.loads(LEGEND.read_text(encoding="utf-8"))
    assert data["schema"] == "opulse.challenge/1"
    assert len(data["challenges"]) == 3
    for item in data["challenges"]:
        assert item["level"] == "legend"
        assert item["set"]["operators"] == 1000
        assert len(item["rules"]) > 600
        assert item["rules"][item["variant"]["rule_index"]]["text"] == item["variant"]["before"]
        assert 0 < item["variant"]["affected_rules"] <= len(item["rules"])
        for record in (item, item["variant"]):
            assert len(record["coarse_steps"]) == record["coarse_step_count"] + 1
            assert record["coarse_steps"][0] == {"expr": item["question"], "rule": None}
            assert record["coarse_steps"][-1]["expr"] == str(record["answer"])
            ref = record["steps_ref"]
            assert ref["format"] == "opulse.scale-example/1"
            assert ref["count"] == record["step_count"]
            assert ref["path"].startswith("legend/" + item["id"] + "/")
            bases = [ROOT / "docs/assets/data/challenge"]
            if (ROOT / "docs_zh").is_dir():
                bases.append(ROOT / "docs_zh/assets/data/challenge")
            for base in bases:
                directory = base / ref["path"]
                index = json.loads((directory / "index.json").read_text(encoding="utf-8"))
                assert index["schema"] == ref["format"]
                assert index["header"]["verification"]["full_trace_steps"] == ref["count"]
                assert index["chunks"][-1]["file"] == "root.json"
                assert all((directory / chunk["file"]).is_file() for chunk in index["chunks"])
                root = json.loads((directory / "root.json").read_text(encoding="utf-8"))
                assert root["nodes"][0]["full"] == ref["count"]


def test_big_challenge_schema_and_answers():
    data = json.loads(EXPERT.read_text(encoding="utf-8"))
    assert data["schema"] == "opulse.challenge/1"
    assert {item["level"] for item in data["challenges"]} == {"expert", "master"}
    assert all(item["id"].startswith(item["level"] + "-") for item in data["challenges"])
    assert len({item["id"] for item in data["challenges"]}) == len(data["challenges"])
    for item in data["challenges"]:
        source = item["set"]
        assert source["name"] == ("int10" if item["level"] == "expert" else "int100")
        assert source["operators"] in (10, 100)
        assert isinstance(source["seed"], int) and source["seed"] > 0
        assert source["command"].startswith("python -m opulse.cli.main operators ")
        assert item["rules"] and all(set(rule) >= {"symbol", "text", "hint", "layer"}
                                     for rule in item["rules"])
        assert [rule["layer"] for rule in item["rules"]] == sorted(rule["layer"] for rule in item["rules"])
        variant = item["variant"]
        changed = variant["rule_index"]
        assert item["rules"][changed]["text"] == variant["before"] != variant["after"]
        for version, record in ((0, item), (1, variant)):
            steps = record["steps"]
            coarse = record["coarse_steps"]
            assert len(steps) == record["step_count"] + 1
            assert len(coarse) == record["coarse_step_count"] + 1
            for trace in (steps, coarse):
                assert trace[0] == {"expr": item["question"], "rule": None}
                assert trace[-1]["expr"] == str(record["answer"])
                assert all(set(step) >= {"expr", "rule"} for step in trace)
            if record["step_count"] <= 100:
                lines = [rule["text"] for rule in item["rules"]]
                if version:
                    lines[changed] = variant["after"]
                result = run("\n".join(lines), item["question"])
                assert result["ok"] and result["agrees"] is True, item["id"]
                assert result["value"] == str(record["answer"])


def test_challenge_schema_and_interpreter_answers():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    assert data["schema"] == "opulse.challenge/1"
    assert len(data["challenges"]) >= 3
    ids = [item["id"] for item in data["challenges"]]
    assert len(ids) == len(set(ids))
    for item in data["challenges"]:
        assert item["id"] and isinstance(item["question"], str)
        rules = item["rules"]
        assert 2 <= len(rules) <= 4
        assert all(set(rule) >= {"symbol", "text", "hint"} for rule in rules)
        variant = item["variant"]
        changed = variant["rule_index"]
        assert 0 <= changed < len(rules)
        assert rules[changed]["text"] == variant["before"]
        assert variant["after"] != variant["before"]
        for version, expected, steps in (
            (0, item["answer"], item["steps"]),
            (1, variant["answer"], variant["steps"]),
        ):
            lines = [rule["text"] for rule in rules]
            if version:
                lines[changed] = variant["after"]
            result = run("\n".join(lines), item["question"])
            assert result["ok"] and result["agrees"] is True, (item["id"], result.get("error"))
            assert result["value"] == str(expected), item["id"]
            assert steps[0] == {"expr": item["question"], "rule": None}
            assert steps[-1]["expr"] == str(expected)
            assert all(set(step) >= {"expr", "rule"} for step in steps)
            for step in steps:
                checked = run("\n".join(lines), step["expr"])
                assert checked["ok"] and checked["value"] == str(expected), (item["id"], step)


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is unavailable")
def test_share_parser_selects_exact_puzzle_and_version():
    script = ROOT / "docs/assets/js/challenge.js"
    probe = """
const {parseShare} = require(process.argv[1]);
const items = [{id:'first'}, {id:'second'}];
const assert = require('node:assert/strict');
assert.deepEqual(parseShare('?mode=hole&c=second&v=1', items), {mode:'hole', index:1, variant:1});
assert.deepEqual(parseShare('?mode=equiv&c=unknown&v=2', items), {mode:'equiv', index:0, variant:0});
assert.deepEqual(parseShare('?c=first&v=0', items), {mode:'compute', index:0, variant:0});
"""
    subprocess.run(["node", "-e", probe, str(script)], check=True, capture_output=True, text=True)


def _node():
    return shutil.which("node")


def test_machine_answer_formats_and_grading():
    answer = ROOT / "docs/assets/js/challenge-answer.js"
    modes = ROOT / "docs/assets/js/challenge-modes.js"
    expected = {
        "wrongstep": "Wrong step: <line number>", "hole": "x = <integer>",
        "equiv": "Counterexample: a = <int>, b = <int>",
        "laws": "Verdict: holds", "deadbranch": "Dead branch: <branch number>",
        "ripple": "Changes: <comma-separated item numbers>", "induce": "Outputs: <v1>; <v2>",
        "translate": "Option: <number>", "shorten": "Rule: <definition line>",
        "describe": "Option: <n>", "target": "Expression: <expression>",
    }
    assert 'Answer: <integer or NaN>' in (ROOT / "docs/assets/js/challenge.js").read_text()
    assert 'assets/js/challenge-answer.js' in (ROOT / "mkdocs.yml").read_text()
    assert 'challenge-model-answer' in (ROOT / "docs/assets/css/challenge.css").read_text()
    if _node():
        probe = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = process.argv[1], {parseAnswer,gradeAnswer,targetTokens} = require(process.argv[2]);
const {promptFor} = require(process.argv[3]);
const {computePrompt} = require(path.join(root, 'docs/assets/js/challenge.js'));
const expected = JSON.parse(process.argv[4]);
const get = mode => JSON.parse(fs.readFileSync(path.join(root, 'docs/assets/data/challenge', mode + '.json'))).challenges[0];
const modes = Object.keys(expected);
const compute = JSON.parse(fs.readFileSync(path.join(root, 'docs/assets/data/challenge/challenges.json'))).challenges[0];
assert(computePrompt(compute, 0, 'en').endsWith('Answer format:\nAnswer: <integer or NaN>\nPut nothing else on the Answer line.'));
assert(computePrompt(compute, 1, 'en').includes(compute.variant.after));
assert(computePrompt(compute, 1, 'zh').includes('Answer: <integer or NaN>'));
for (const mode of modes) {
  const prompt = promptFor(mode, get(mode), 'en');
  assert(prompt.includes('Answer format:\n') && prompt.includes(expected[mode]), mode);
  assert(prompt.includes('Rules:\n'), mode);
  assert(prompt.endsWith('Use only the applicable format lines; put nothing else on those lines.'), mode);
  assert(promptFor(mode, get(mode), 'zh').includes('回答格式：'), mode);
}
const wrongstep = get('wrongstep');
assert(promptFor('wrongstep', wrongstep, 'en').includes('7. ' + wrongstep.steps[6].expr));
assert(promptFor('ripple', get('ripple'), 'en').includes('6. 5 ♣₁ (- 2)'));
assert(promptFor('translate', get('translate'), 'en').includes('4. '));
assert.deepEqual(parseAnswer('compute', {}, 'noise\nANSWER: 2\nAnswer: NaN').value, 'NaN');
assert.equal(parseAnswer('compute', {}, 'Answer: 2\nAnswer: nonsense').ok, false);
assert.match(parseAnswer('compute', {}, 'It is 2').error, /No 'Answer:' line/);
assert.equal(parseAnswer('hole', get('hole'), 'x = -2\nX = 1').value, 1);
assert.equal(parseAnswer('hole', get('hole'), 'x: 1').ok, false);
assert.equal(parseAnswer('wrongstep', get('wrongstep'), 'Wrong step: 7').value, 7);
assert.equal(parseAnswer('deadbranch', get('deadbranch'), 'Dead branch: 2').value, 2);
assert.deepEqual(parseAnswer('ripple', get('ripple'), 'Changes: none').value, []);
assert.deepEqual(parseAnswer('ripple', get('ripple'), 'Changes: 1, 2, 5, 6').value, [1,2,5,6]);
assert.equal(parseAnswer('ripple', get('ripple'), 'Changes: 1, 1').ok, false);
assert.equal(parseAnswer('translate', get('translate'), 'OPTION: 4').value, 4);
assert.deepEqual(parseAnswer('induce', get('induce'), 'Outputs: 8; 13; 19\nRule: a ★ b = { (a ♧ b) * 2 }').value.outputs, [8,13,19]);
assert.equal(parseAnswer('induce', get('induce'), 'Outputs: 10, 6').ok, false);
assert.equal(parseAnswer('shorten', get('shorten'), 'Rule: ⋆(a, b, c) = { a * (b + c) }').ok, true);
assert.equal(parseAnswer('describe', get('describe'), 'Option: 1').value, 1);
assert.equal(parseAnswer('target', get('target'), 'Expression: (7 - 3) ◇ (4 + 2)').value, '(7 - 3) ◇ (4 + 2)');
const different = JSON.parse(fs.readFileSync(path.join(root,'docs/assets/data/challenge/equiv.json'))).challenges[1];
assert.deepEqual(parseAnswer('equiv', different, 'Verdict: different\nCounterexample: a = 4, b = -1').value.inputs,[4,-1]);
assert.equal(parseAnswer('equiv', different, 'Verdict: different\nVerdict: same').value.verdict,'same');
assert.equal(parseAnswer('equiv', different, 'Verdict: different\nCounterexample: 4,3').ok,false);
const law = JSON.parse(fs.readFileSync(path.join(root,'docs/assets/data/challenge/laws.json'))).challenges[2];
assert.deepEqual(parseAnswer('laws', law, 'Verdict: fails\nCounterexample: a = 4, b = 5').value.inputs,[4,5]);
assert.equal(parseAnswer('laws', law, 'Verdict: fails\nCounterexample: b = 5, a = 4').ok,false);
const grade = async (mode,item,text) => await gradeAnswer(mode,item,parseAnswer(mode,item,text));
(async () => {
  assert((await grade('compute',{answer:0},'Answer: 0')).correct);
  assert(!(await grade('compute',{answer:0},'Answer: 1')).correct);
  assert((await grade('hole',get('hole'),'x = 1')).correct);
  assert((await grade('wrongstep',wrongstep,'Wrong step: ' + (wrongstep.wrong_index + 1))).correct);
  assert((await grade('deadbranch',get('deadbranch'),'Dead branch: 2')).correct);
  assert((await grade('ripple',get('ripple'),'Changes: 6, 5, 2, 1')).correct);
  assert(!(await grade('ripple',get('ripple'),'Changes: none')).correct);
  assert((await grade('translate',get('translate'),'Option: 4')).correct);
  const named = get('describe');
  assert((await grade('describe',named,'Option: ' + (named.answer_index + 1))).correct);
  assert(!(await grade('describe',named,'Option: ' + ((named.answer_index + 1) % named.options.length + 1))).correct);
  assert((await grade('equiv',get('equiv'),'Verdict: same')).correct);
  assert((await grade('equiv',different,'Verdict: different\nCounterexample: a = 4, b = -1')).correct);
  assert(!(await grade('equiv',different,'Verdict: different\nCounterexample: a = 100, b = 3')).correct);
  assert(!(await grade('equiv',different,'Verdict: different\nCounterexample: a = 4, b = 0')).correct);
  assert((await grade('laws',law,'Verdict: fails\nCounterexample: a = 4, b = 5')).correct);
  assert(!(await grade('laws',law,'Verdict: fails\nCounterexample: a = 3, b = 3')).correct);
  assert((await grade('induce',get('induce'),'Outputs: 8; 13; 19')).correct);
  assert(!(await grade('induce',get('induce'),'Outputs: 8; 13; 20')).correct);
  global.OpulseCheck = {equivalent: async () => ({equivalent:false}), steps: async () => ({total:24,parse_error:null})};
  assert(!(await grade('induce',get('induce'),'Outputs: 8; 13; 19\nRule: wrong')).correct);
  global.OpulseCheck.equivalent = async () => ({equivalent:true});
  const describeWrite = JSON.parse(fs.readFileSync(path.join(root,'docs/assets/data/challenge/describe.json'))).challenges[1];
  assert((await grade('describe',describeWrite,'Rule: ' + describeWrite.reference)).correct);
  assert((await grade('induce',get('induce'),'Outputs: 8; 13; 19\nRule: good')).correct);
  const short = get('shorten');
  let checkedInputs;
  global.OpulseCheck.steps = async (_, definition, inputs) => {checkedInputs = inputs; return {total:24,parse_error:null};};
  assert.equal((await grade('shorten',short,'Rule: good')).detail, 'Same results, 24 steps (budget 24): solved');
  assert.deepEqual(checkedInputs, short.inputs);
  global.OpulseCheck.steps = async () => ({total:32,parse_error:null});
  assert.equal((await grade('shorten',short,'Rule: long')).detail, 'Same results, but 32 steps; the budget is 24');
  global.OpulseCheck.equivalent = async () => ({equivalent:false,counterexample:{inputs:[2,1],got:5,expected:7}});
  assert.equal((await grade('shorten',short,'Rule: wrong')).detail, 'Differs at a = 2, b = 1: yours gives 5, the rule gives 7');
  assert(promptFor('shorten',short,'en').includes('24 total steps'));
  assert(promptFor('shorten',short,'en').includes('(0, 0), (5, 5)'));
  global.OpulseCheck.evaluate = async (_, expression) => ({value: expression.includes('✧') ? 6 : 7});
  assert((await grade('equiv',different,'Verdict: different\nCounterexample: a = 4, b = -1')).correct);
  global.OpulseCheck.evaluate = async () => ({value: 6});
  assert(!(await grade('equiv',different,'Verdict: different\nCounterexample: a = 4, b = -1')).correct);
  assert(!(await grade('laws',law,'Verdict: fails\nCounterexample: a = 4, b = 5')).correct);
  const target = get('target');
  assert(targetTokens({numbers:[-2,3,4,7],allowed:['+']}, '-2 + 3').ok);
  assert.equal((await grade('target',target,'Expression: 7 + 7')).detail, 'Uses 7 twice');
  assert(!(await grade('target',target,'Expression: 7 / 3')).correct);
  global.OpulseCheck.evaluate = async () => ({value: target.target});
  assert.equal((await grade('target',target,'Expression: ' + target.solution)).detail, 'Reached ' + target.target + ': solved');
  global.OpulseCheck.evaluate = async () => ({value: 22});
  assert.equal((await grade('target',target,'Expression: ' + target.solution)).detail, 'Gives 22');
})().catch(error => {console.error(error); process.exitCode = 1;});
"""
        subprocess.run([_node(), "-e", probe, str(ROOT), str(answer), str(modes), json.dumps(expected)],
                       check=True, capture_output=True, text=True)
    else:
        # Keep this Python format mirror in sync with challenge-answer.js when Node is unavailable.
        def parse_mirror(mode, item, text):
            label = {"wrongstep": "Wrong step", "hole": "x", "equiv": "Verdict", "laws": "Verdict",
                     "deadbranch": "Dead branch", "ripple": "Changes", "induce": "Outputs",
                     "translate": "Option", "shorten": "Rule", "compute": "Answer",
                     "describe": "Option", "target": "Expression"}[mode]
            marker = "=" if mode == "hole" else ":"
            lines = re.findall(rf"^\s*{label}\s*{marker}\s*(.*?)\s*$", text, re.I | re.M)
            return lines[-1] if lines else None

        examples = {"compute": "Answer: NaN", "wrongstep": "Wrong step: 7", "hole": "x = 1",
                    "equiv": "Verdict: same", "laws": "Verdict: holds", "deadbranch": "Dead branch: 2",
                    "ripple": "Changes: none", "induce": "Outputs: 8; 13; 19", "translate": "Option: 4",
                    "shorten": "Rule: ⋆(a, b, c) = { a * (b + c) }",
                    "describe": "Option: 1", "target": "Expression: (7 - 3) ◇ (4 + 2)"}
        for mode, text in examples.items():
            expected_value = "1" if mode == "hole" else text.split(":", 1)[-1].strip()
            assert parse_mirror(mode, None, "irrelevant\n" + text) == expected_value
        source = modes.read_text()
        for format_text in expected.values():
            assert format_text.split(":", 1)[0] in source
