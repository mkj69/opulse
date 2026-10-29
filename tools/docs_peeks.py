"""Generate the Experiment ideas peek records from fixed seed Opulse CLI runs.

Run ``.venv/bin/python tools/docs_peeks.py`` at the repository root. Work files live in
``outputs/peeks``; the compact, checked JSON snippets live in ``docs/snippets/peeks``.

Two peeks (``same-tree-other-world`` and ``world-variety``) need ``opulse skeleton`` and
``--world-mix``. When this checkout lacks them, the committed snippets are kept. To
regenerate only those two from another source tree that has them, run
``.venv/bin/python tools/docs_peeks.py --worlds-src PATH/TO/src``.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from collections import Counter
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from docs_evidence import display  # noqa: E402

from opulse.bench.check import base_registry, prompt_registry  # noqa: E402
from opulse.bench.context import closure  # noqa: E402
from opulse.cli.operators import DEFAULT_CONFIG  # noqa: E402
from opulse.config import Settings  # noqa: E402
from opulse.core.registry import OperatorRegistry  # noqa: E402
from opulse.core.semantics import NAN  # noqa: E402
from opulse.definition.parser import DefinitionParser  # noqa: E402
from opulse.expression.nodes import from_ast, from_dict  # noqa: E402
from opulse.runtime import PythonRuntime  # noqa: E402
from opulse.trace import Reducer  # noqa: E402

WORK = ROOT / "outputs" / "peeks"
SNIPPETS = ROOT / "docs" / "snippets" / "peeks"
ZH_SNIPPETS = ROOT / "docs_zh" / "snippets" / "peeks"
zh_peeks: dict[str, dict] = {}
SETTINGS = Settings.load(DEFAULT_CONFIG)
ANCHORS = (
    "failure-predictor", "distractors", "probes-and-patches", "edit-propagation",
    "transfer", "weights-or-context", "process-reward", "derivation-tokens",
    "long-tail", "breadth-or-depth", "prerequisite-order", "spacing",
    "contrast-reward", "applied-rules-per-parameter", "read-only-rules",
    "manipulate-rules", "precompute", "depth-vs-layers", "corrected-mistakes",
    "delayed-generalization",
    "auto-curriculum", "same-tree-other-world", "world-variety", "step-checker-new-world",
    "write-concept", "compiled-solution",
)
WORLD_ANCHORS = ("same-tree-other-world", "world-variety")

# Display text only. Commands, expressions, field names and values stay identical
# across the English and Chinese pages.
NOTES_ZH = {
    "failure-predictor": "这些生成题展示定义数、依赖层数和参考改写次数。模型实验还需从中挑选性质匹配的题组。",
    "distractors": "每道生成题都统计题面中的定义。检索器是另设的实验组。",
    "probes-and-patches": "这组题提供探针和激活替换所需的参考答案。这里没有模型激活。",
    "edit-propagation": "修改规则前后的值由参考解释器计算。题面修改和参数修改是实验条件。",
    "transfer": "定义类型的计数来自整个生成的运算符库。图中是规则库样例，不是迁移结果。",
    "weights-or-context": "同一道算式配有两条定义和两个参考答案。出现次数由外部采样器设置。",
    "process-reward": "两种题目格式共用一个参考答案。奖励方式由训练器设置，这里没有展示。",
    "derivation-tokens": "计数基于英文推导文本。按空格切分的 token 数只是近似值。",
    "breadth-or-depth": "两组各 12 条记录，都取自保存的 800 条记录。每组只展示一道样例题。",
    "prerequisite-order": "三种顺序使用同一套保存的记录 ID。排序由外部程序完成。",
    "spacing": "三种练习安排重复使用同三条记录，最后一次都在第 12 步。",
    "applied-rules-per-parameter": "算式是真实生成的应用样例。出现次数和无关数据占比是尚未执行的训练条件。",
    "read-only-rules": "A/B 组的训练出现次数是实验设定。A 组样例和 B 组题面都有生成的参考答案。",
    "manipulate-rules": "正向计算和比较的值来自解释器。逆向题是生成的填空题，其他提问形式尚未执行。",
    "precompute": "绑定值由解释器计算。提问位置是题面设计，这里没有查询模型。",
    "depth-vs-layers": "组合深度来自计算题。模型层数和探针属于后续评测条件。",
    "corrected-mistakes": "错误原子结果比正确值大 1，逐步检查器会拒绝它。撤回后的续写是训练样例设计。",
    "delayed-generalization": "网格答案由解释器给出。输入对划分是训练条件，这里没有检查点或模型结果。",
    "auto-curriculum": "两道题只在一个结构维度上不同。样例没有学习者的作答记录，因此无法计算成功率。",
    "same-tree-other-world": "这对样例记录的对应等级为 G1，表示已确认签名一致；两边的值表不同。这只是数据示例，不能说明迁移效果。",
    "world-variety": "一次加权生成里的两道题，来自同一个骨架、两个世界。这里只有数据，没有训练。",
    "step-checker-new-world": "精确步骤检查器给样例步骤判定。这里只展示整数世界，未列出核对错误步骤所需的定义；其他世界需等待世界预设。",
    "write-concept": "这里只展示解释器答案，没有参数注入结果。题目算式是数据样例，不是注入脚本实际使用的题面。",
    "compiled-solution": "表中答案来自解释器，每四行留出一行作测试。样例没有编译槽位标签，也没有训练后的网络。",
}

LABELS_ZH = {
    "task and counterfactual": "原题与反事实题", "dependency chain": "依赖链",
    "plain mix library sample": "仅代入规则库样例", "mixed library sample": "混合规则库样例",
    "steps format": "逐步格式", "free format": "自由格式",
    "known layer 0": "已知第 0 层", "full derivation": "完整推导",
    "uniform": "均匀", "zipf:1.5": "zipf:1.5",
    "2 operators, 6 records each": "2 个运算符，各 6 条记录",
    "4 operators, 3 records each": "4 个运算符，各 3 条记录",
    "layer order": "按层排序", "shuffled order": "打乱顺序", "reverse order": "逆序",
    "massed": "集中练习", "even": "等间隔练习", "growing": "递增间隔练习",
    "contrast member A": "对照题 A", "contrast member B": "对照题 B",
    "small load, test prompt": "小规则库测试题面",
    "small load with junk, test prompt": "含无关数据的测试题面",
    "A application sample": "A 组应用样例", "B test without context": "B 组无定义测试题",
    "B test with context": "B 组有定义测试题",
    "four questions from one rule": "同一规则的四种提问",
    "question after bindings": "绑定后提问", "question before bindings": "提问后给绑定",
    "wrong rewrite and correction": "错误改写与改正", "finite pair split": "有限输入对划分",
    "easier cell": "较易的格", "one axis harder": "仅一个结构维度更难",
    "strings instance": "字符串世界实例", "lists instance": "列表世界实例",
    "strings task": "字符串世界题目", "lists task": "列表世界题目",
    "exact step labels": "精确的步骤判定",
    "direct prompt": "直接提问", "inside a longer expression": "放进更长的算式",
    "operand table and split": "操作数表与划分",
}

TAGS_ZH = {
    "task input": "题目输入", "prompt control": "题面对照",
    "test prompt": "测试题面", "question examples": "提问样例",
    "unrun prompt": "题面设计", "injected error": "注入错误",
    "integer world": "整数世界", "grade G1": "等级 G1",
}


def label_zh(label: str) -> str:
    if label in LABELS_ZH:
        return LABELS_ZH[label]
    patterns = (
        (r"(\d+) needed definitions", lambda m: f"需要 {m[1]} 条定义"),
        (r"requested (\d+) distractors", lambda m: f"要求 {m[1]} 条干扰定义"),
        (r"swapped definition (\d+)", lambda m: f"替换定义 {m[1]}"),
        (r"generator cap (\d+)", lambda m: f"生成深度上限 {m[1]}"),
    )
    for pattern, render in patterns:
        match = re.fullmatch(pattern, label)
        if match:
            return render(match)
    raise ValueError(f"Missing Chinese label: {label}")


def run(args: list[str], out: Path | None = None) -> str:
    """Run a real CLI or example entry point, with a fresh output file."""
    if out is not None:
        out.unlink(missing_ok=True)
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    result = subprocess.run([sys.executable, *args], cwd=ROOT, env=env,
                            text=True, capture_output=True, check=True)
    return result.stdout


def run_with(src: Path, args: list[str], out: Path | None = None) -> str:
    """Run the CLI of another source tree; used only for the two world peeks."""
    if out is not None and out.is_file():
        out.unlink()
    env = dict(os.environ, PYTHONPATH=str(src))
    result = subprocess.run([sys.executable, "-m", "opulse.cli.main", *args], cwd=WORK,
                            env=env, text=True, capture_output=True, check=True)
    return result.stdout


def world_peeks(src: Path) -> None:
    """Peeks for the Across worlds cards: one skeleton in two worlds, and a weighted mix."""
    import shutil

    work = WORK / "worlds"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    run_with(src, ["operators", "--preset", "strings", "--out", "worlds/source.jsonl",
                   "--layers", "2", "--proportions", "1", "0", "0", "--seed", "7"])
    run_with(src, ["skeleton", "extract", "--operators", "worlds/source.jsonl",
                   "--out", "worlds/skeletons.json"])
    for world in ("strings", "lists"):
        run_with(src, ["operators", "--preset", world, "--out", f"worlds/{world}_atoms.jsonl",
                       "--layers", "0", "--seed", "1"])
    (work / "type_maps.json").write_text('{"lists": {"str": "list[int]"}}\n', encoding="utf-8")
    match_args = ["skeleton", "match", "--skeletons", "worlds/skeletons.json",
                  "--world", "strings=worlds/strings_atoms.jsonl", "--world", "lists=worlds/lists_atoms.jsonl",
                  "--type-maps", "worlds/type_maps.json", "--out-dir", "worlds/matched",
                  "--seed", "3", "--attempts", "50"]
    run_with(src, match_args)
    report = json.loads((work / "matched" / "match.json").read_text(encoding="utf-8"))
    comparison = report["comparisons"]["lists"][0]
    assert comparison["structural_hash_equal"] and comparison["grade"] == "G1"
    instances = rows(work / "matched" / "instances.jsonl")
    first = instances[0]["skeleton_id"]
    pair = {}
    for world in ("strings", "lists"):
        defined = [r for r in rows(work / "matched" / f"{world}.jsonl") if r["definition"]]
        record = next(i for i in instances if i["world"] == world and i["skeleton_id"] == first)
        op = next(r for r in defined if r["func_id"] == record["func_id"])
        pair[world] = (op, record)
    match_records = []
    for world in ("strings", "lists"):
        op, record = pair[world]
        probe = record["probe"]
        match_records.append({
            "label": f"{world} instance", "tag": "grade G1",
            "operators": [op["definition"]],
            "fields": {"world": world, "skeleton_id": first[:8],
                       "undefined_rate": probe["nan_rate"],
                       "unfolded_length": probe["unfolded_length"]}})
    match_records[1]["fields"]["value_tables_differ"] = str(comparison["value_tables_differ"]).lower()
    save("same-tree-other-world",
         "opulse skeleton match --skeletons skeletons.json --world strings=strings_atoms.jsonl "
         "--world lists=lists_atoms.jsonl --type-maps type_maps.json --out-dir matched --seed 3 --attempts 50",
         match_records,
         "This data illustration pairs one skeleton across two worlds. Grade G1 confirms matching signatures; the value tables differ. It shows no transfer result.")

    mix_args = ["bench", "build", "--world", "strings=worlds/matched/strings.jsonl",
                "--world", "lists=worlds/matched/lists.jsonl", "--world-mix", "strings:0.5,lists:0.5",
                "--count", "4", "--out", "worlds/mix.jsonl", "--max-answer-share", "1", "--seed", "0"]
    run_with(src, mix_args)
    tasks = rows(work / "mix.jsonl")
    by_skeleton = defaultdict(dict)
    for task in tasks:
        by_skeleton[task["skeleton_ids"][0]].setdefault(task["world"], task)
    shared = next(group for group in by_skeleton.values() if len(group) == 2)
    mix_records = []
    for world in ("strings", "lists"):
        task = shared[world]
        mix_records.append({
            "label": f"{world} task", "operators": task["definitions"],
            "expression": task["expression"], "answer": task["answer"],
            "fields": {"world": world, "skeleton_id": task["skeleton_ids"][0][:8],
                       "unfolded_length": task["axes"]["unfolded_length"]}})
    save("world-variety",
         "opulse bench build --world strings=strings.jsonl --world lists=lists.jsonl "
         "--world-mix strings:0.5,lists:0.5 --count 4 --out mixed_tasks.jsonl --max-answer-share 1 --seed 0",
         mix_records,
         "Two tasks from one weighted build: one skeleton in two worlds. This is data only; nothing was trained.")


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def cli_text(*args: str) -> str:
    return "opulse " + " ".join(args)


def bench(name: str, ops: Path, *, count: int = 1, seed: int = 0,
          family: str = "compute", extra: tuple[str, ...] = ()) -> list[dict]:
    out = WORK / f"{name}.jsonl"
    run(["-m", "opulse.cli.main", "bench", "build", "--operators", str(ops),
         "--out", str(out), "--family", family, "--count", str(count),
         "--seed", str(seed), *extra], out)
    result = rows(out)
    assert len(result) == count
    return result


def expressions(name: str, ops: Path, *, count: int = 1, seed: int = 0,
                extra: tuple[str, ...] = ()) -> list[dict]:
    out = WORK / f"{name}.jsonl"
    run(["-m", "opulse.cli.main", "expressions", "--operators", str(ops),
         "--out", str(out), "--count", str(count), "--seed", str(seed), *extra], out)
    result = rows(out)
    assert len(result) == count
    return result


def answer(value: object) -> int | str:
    return "NaN" if value is None or value is NAN else int(value)


def trace_for(expression: str, registry: OperatorRegistry, *, known_layers: int = 0):
    parser = DefinitionParser(SETTINGS.symbols, registry)
    node = from_ast(parser.parse_expr(expression, expression_mode=True), registry)
    reducer = Reducer(registry, PythonRuntime(registry, SETTINGS.semantics.build()), parser,
                      expand=lambda op: op.definition is not None and (op.recursive_layer or 0) >= known_layers)
    trace = reducer.reduce(node)
    assert not trace.truncated, expression
    return trace


def task_record(task: dict, ops: Path, *, label: str | None = None,
                fields: tuple[str, ...] = (), show_definitions: bool = True) -> dict:
    assert len(task["definitions"]) <= 3 or not show_definitions
    registry = OperatorRegistry.from_jsonl(ops)
    if task["family"] == "contrast":
        registry = prompt_registry(task["definitions"], base_registry(registry),
                                   SETTINGS.symbols, SETTINGS.semantics.build()).registry
    expr = task["expression"]
    if task["family"] == "hole":
        evaluation = re.sub(r"\bx\b", str(task["answer"]), expr)
        trace = trace_for(evaluation, registry)
    else:
        trace = trace_for(expr, registry)
        assert answer(trace.value) == answer(task["answer"]), task["id"]
    record = {
        "operators": [display(d, ops) for d in task["definitions"]] if show_definitions else [],
        "expression": display(expr, ops),
        "answer": answer(task["answer"]),
        "steps": len(trace.steps),
    }
    if label:
        record = {"label": label, **record}
    if fields:
        record["fields"] = {key: task["axes"][key] for key in fields}
    return record


def expression_record(row: dict, ops: Path, *, label: str | None = None,
                      known_layers: int = 0, fields: tuple[str, ...] = ()) -> dict:
    registry = OperatorRegistry.from_jsonl(ops)
    tree = from_dict(row["tree"], registry)
    definitions = [op.definition for op in closure(registry, tree)]
    assert len(definitions) <= 3, row["expression_plain"]
    trace = trace_for(row["expression_plain"], registry, known_layers=known_layers)
    assert answer(trace.value) == answer(row["result"])
    record = {
        "operators": [display(d, ops) for d in definitions],
        "expression": display(row["expression_plain"], ops),
        "answer": answer(row["result"]),
        "steps": len(trace.steps),
    }
    if label:
        record = {"label": label, **record}
    if fields:
        record["fields"] = {key: row[key] for key in fields}
    return record


def compact_expression(corpus: list[dict], ops: Path) -> dict:
    registry = OperatorRegistry.from_jsonl(ops)
    return next(row for row in corpus
                if 1 <= len(closure(registry, from_dict(row["tree"], registry))) <= 3)


def command_for(kind: str, *, count: int = 1, extra: tuple[str, ...] = (),
                family: str = "compute", library: str = "ops.jsonl") -> str:
    if kind == "bench":
        return cli_text("bench build --operators", library, "--out tasks.jsonl --family", family,
                        "--count", str(count), "--seed 0", *extra)
    return cli_text("expressions --operators", library, "--out pool.jsonl --count", str(count),
                    "--seed 0", *extra)


def short_trace(expression: str, ops: Path, *, known_layers: int = 0, limit: int = 4) -> list[str]:
    trace = trace_for(expression, OperatorRegistry.from_jsonl(ops), known_layers=known_layers)
    result = []
    for step in trace.steps[:limit]:
        args = ", ".join(map(str, step.inputs))
        result.append(display(f"{step.operator.symbol}({args}) → {step.output if step.output is not None else 'expand'}", ops))
    return result


def save(anchor: str, command: str, records: list[dict], note: str | None = None) -> None:
    assert anchor in ANCHORS
    assert 1 <= len(records) <= 4
    zh_peeks[anchor] = {
        "note": NOTES_ZH.get(anchor, ""),
        "records": [
            {"label": label_zh(record["label"]) if record.get("label") else "",
             "tag": TAGS_ZH[record["tag"]] if record.get("tag") else ""}
            for record in records
        ],
    }
    for record in records:
        assert len(record.get("operators", [])) <= 3
        assert len(record.get("fields", {})) <= 5
        assert len(record.get("lines", [])) <= 8
        if "steps" in record:
            assert isinstance(record["steps"], int) and record["steps"] >= 0
    payload = {"anchor": anchor, "command": command, "records": records}
    if note:
        payload["note"] = note
    english = {key: value for key, value in payload.items() if not key.endswith("_zh")}
    english["records"] = [{key: value for key, value in record.items()
                           if not key.endswith("_zh")} for record in records]
    chinese = {**payload, "note_zh": zh_peeks[anchor]["note"]}
    chinese["records"] = [
        {**record, "label_zh": zh_peeks[anchor]["records"][i]["label"],
         "tag_zh": zh_peeks[anchor]["records"][i]["tag"]}
        for i, record in enumerate(records)
    ]
    outputs = [(SNIPPETS, english)]
    if ZH_SNIPPETS.parents[1].is_dir():
        outputs.append((ZH_SNIPPETS, chinese))
    for directory, content in outputs:
        data = json.dumps(content, ensure_ascii=False, separators=(",", ":")) + "\n"
        assert len(data.encode("utf-8")) < 6144, (anchor, len(data))
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"{anchor}.json").write_text(data, encoding="utf-8")
    print(f"{anchor}: {len(records)} record(s), {len(data.encode('utf-8'))} bytes")


def main() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    SNIPPETS.mkdir(parents=True, exist_ok=True)
    ops = WORK / "ops.jsonl"
    small = WORK / "small_ops.jsonl"
    plain = WORK / "plain_ops.jsonl"
    edit_ops = WORK / "edit_ops.jsonl"
    for path, layers, extra in ((ops, (20, 20), ()), (small, (4, 4, 4, 4), ()),
                                (plain, (20, 20), ("--proportions", "1", "0", "0")),
                                (edit_ops, (8, 8), ())):
        run(["-m", "opulse.cli.main", "operators", "--out", str(path), "--layers",
             *(str(n) for n in layers), "--seed", "3" if path == edit_ops else "1",
             "--check-variety", *extra], path)

    short = ("--min-definitions", "1", "--max-definitions", "2", "--max-depth", "2")
    one = ("--min-definitions", "1", "--max-definitions", "1", "--max-depth", "2")
    # Evaluation cards.
    failure_records = []
    for needed in (1, 2, 4):
        extra = ("--min-definitions", str(needed), "--max-definitions", str(needed), "--max-depth", "2")
        task = bench(f"failure_{needed}", ops, extra=extra)[0]
        rec = task_record(task, ops, label=f"{needed} needed definitions",
                          fields=("definitions_needed", "max_layer", "applications"),
                          show_definitions=needed <= 3)
        rec["command"] = command_for("bench", extra=extra)
        if needed > 3:
            rec["fields"]["definitions_shown"] = len(task["definitions"])
        failure_records.append(rec)
    save("failure-predictor", failure_records[0]["command"], failure_records,
         "These generated cells expose definition count, dependency layer and reference rewrites. Matching cells for a model study is a separate selection step.")

    distractor_records = []
    for requested in (0, 8, 32):
        extra = (*one, "--distractors", str(requested))
        task = bench(f"distractors_{requested}", ops, extra=extra)[0]
        record = task_record(task, ops, label=f"requested {requested} distractors", fields=("distractors",), show_definitions=False)
        record["fields"]["definitions_shown"] = len(task["definitions"])
        record["command"] = command_for("bench", extra=extra)
        distractor_records.append(record)
    save("distractors", distractor_records[0]["command"], distractor_records,
         "Definitions are counted in each generated prompt. A retriever is a separate experimental arm.")

    t = bench("probes", ops, extra=("--context", "full", "--naming", "symbols", "--min-definitions", "2", "--max-definitions", "2", "--max-depth", "2"))[0]
    probe = task_record(t, ops, label="task and counterfactual", fields=("definitions_needed", "max_layer"))
    probe["tag"] = "task input"
    probe["command"] = command_for("bench", extra=("--context", "full", "--naming", "symbols", "--min-definitions", "2", "--max-definitions", "2", "--max-depth", "2"))
    old_expr = t["expression"]
    changed_expr = re.sub(r"\d+", lambda m: str(int(m.group()) + 1), old_expr, count=1)
    changed_answer = answer(trace_for(changed_expr, OperatorRegistry.from_jsonl(ops)).value)
    probe["lines"] = [f"original: {display(old_expr, ops)} → {probe['answer']}",
                      f"one argument changed: {display(changed_expr, ops)} → {changed_answer}",
                      "probe target: subexpression or reduction step", "patch sites: aligned source spans"]
    save("probes-and-patches", probe["command"], [probe],
         "The pair gives reference answers for an activation probe and patch task. No model activations are shown.")

    edit_out = WORK / "edits.jsonl"
    edit_stdout = run(["examples/edit_propagation.py", str(edit_ops), "--out", str(edit_out)], edit_out)
    edited_old = re.search(r"^edited\s+(.+)$", edit_stdout, re.M).group(1)
    edited_new = re.search(r"^\s+into\s+(.+)$", edit_stdout, re.M).group(1)
    edit_registry = OperatorRegistry.from_jsonl(edit_ops)
    edit_parser = DefinitionParser(SETTINGS.symbols, edit_registry)

    def edit_expression(record: dict, index: int) -> str:
        op = next(o for o in edit_registry if o.definition == record["operator"])
        inputs = record["inputs"][index]
        if op.n_ary == 2:
            return f"{inputs[0]} {op.symbol} {inputs[1]}"
        return f"{op.symbol} {inputs[0]}" if op.unary_position == "prefix" else f"{inputs[0]} {op.symbol}"

    edit_changes = []
    for distance in sorted({r["distance"] for r in rows(edit_out)}):
        selected = next(((r, i, edit_expression(r, i)) for r in rows(edit_out)
                         if r["distance"] == distance
                         for i, (a, b) in enumerate(zip(r["before"], r["after"]))
                         if a is not None and b is not None and a != b), None)
        if selected:
            edit_changes.append(selected)
    raw = rows(edit_ops)
    edited_path = WORK / "edited_ops.jsonl"
    edited_path.write_text("".join(json.dumps({**r, "definition": edited_new} if r["definition"] == edited_old else r,
                                              ensure_ascii=False) + "\n" for r in raw), encoding="utf-8")
    edit_lines = ["old: " + display(edited_old, edit_ops), "new: " + display(edited_new, edit_ops)]
    edit_lines.extend(f"distance {r['distance']}: {display(expr, edit_ops)}: {r['before'][i]} → {r['after'][i]}"
                      for r, i, expr in edit_changes[:3])
    save("edit-propagation", "python examples/edit_propagation.py ops.jsonl --out edits.jsonl",
         [{"label": "dependency chain", "lines": edit_lines,
           "fields": {"changed_distances": len(edit_changes)}}],
         "Reference interpreter values before and after one rule edit. The context and weight edit arms are experiment designs.")

    mixed_task = bench("transfer_mixed", ops, extra=short)[0]
    plain_task = bench("transfer_plain", plain, extra=short)[0]
    transfer_records = []
    for label, library, task, extra in (("plain mix library sample", plain, plain_task, ("--proportions", "1", "0", "0")),
                                       ("mixed library sample", ops, mixed_task, ())):
        rec = task_record(task, library, label=label)
        rec["fields"] = dict(Counter(r["definition_type"] for r in rows(library) if r["definition"]))
        rec["command"] = cli_text("operators --out ops.jsonl --layers 20 20 --seed 1 --check-variety", *extra)
        transfer_records.append(rec)
    save("transfer", transfer_records[0]["command"], transfer_records,
         "Accepted definition kinds count the whole generated library. These are library samples, not transfer results.")

    swapped = bench("context_swap", ops, count=2, family="contrast", extra=short)
    assert swapped[0]["expression"] == swapped[1]["expression"]
    save("weights-or-context", command_for("bench", count=2, family="contrast", extra=short),
         [{**task_record(task, ops, label=f"swapped definition {index}", fields=("definitions_needed",)),
           "tag": "prompt control"} for index, task in enumerate(swapped, 1)],
         "The same expression has two supplied definitions and two reference answers. Exposure levels come from an external sampler.")

    steps_task = bench("reward_steps", ops, extra=(*short, "--format", "steps"))[0]
    export_path = WORK / "reward.jsonl"
    run(["-m", "opulse.cli.main", "bench", "export", "--tasks", str(WORK / "reward_steps.jsonl"),
         "--operators", str(ops), "--out", str(export_path)], export_path)
    assert rows(export_path)
    outcome_task = bench("reward_outcome", ops, extra=short)[0]
    assert outcome_task["expression"] == steps_task["expression"]
    reward_record = task_record(steps_task, ops, label="steps format", fields=("definitions_needed",))
    reward_record["fields"]["format"] = steps_task["format"]
    reward_record["command"] = command_for("bench", extra=(*short, "--format", "steps"))
    reward_record["lines"] = short_trace(steps_task["expression"], ops, limit=4)
    outcome_record = task_record(outcome_task, ops, label="free format", fields=("definitions_needed",))
    outcome_record["fields"]["format"] = outcome_task["format"]
    outcome_record["command"] = command_for("bench", extra=short)
    save("process-reward", cli_text("bench build --operators ops.jsonl --out tasks.jsonl --family compute --format steps --context full --min-definitions 1 --max-definitions 2 --count 1 --seed 0"),
         [outcome_record, reward_record],
         "The two task formats share a reference answer. Reward modes are trainer settings and are not shown here.")

    # Expression corpus cards. A low layer cap keeps the displayed dependency closure short.
    expr_common = ("--max-layer", "0")
    coarse_rows = expressions("cot_coarse", ops, count=100, extra=(*expr_common, "--cot", "en", "--cot-known-layers", "1"))
    detailed_rows = expressions("cot_full", ops, count=100, extra=(*expr_common, "--cot", "en"))
    coarse, detailed = next((a, b) for a, b in zip(coarse_rows, detailed_rows)
                            if a["expression_plain"] == b["expression_plain"]
                            and 1 <= len(closure(OperatorRegistry.from_jsonl(ops),
                                                 from_dict(a["tree"], OperatorRegistry.from_jsonl(ops)))) <= 3
                            and len(trace_for(a["expression_plain"], OperatorRegistry.from_jsonl(ops), known_layers=1).steps)
                            != len(trace_for(b["expression_plain"], OperatorRegistry.from_jsonl(ops)).steps))
    assert coarse["expression_plain"] == detailed["expression_plain"]
    trace_records = []
    for label, row, known, extra in (("known layer 0", coarse, 1, ("--cot-known-layers", "1")),
                                     ("full derivation", detailed, 0, ())):
        rec = expression_record(row, ops, label=label, known_layers=known)
        rec["command"] = command_for("expressions", count=100, extra=(*expr_common, "--cot", "en", *extra))
        rec["lines"] = short_trace(row["expression_plain"], ops, known_layers=known, limit=4)
        rec["fields"] = {"trace_characters": len(row["cot"]),
                         "whitespace_tokens": len(row["cot"].split())}
        trace_records.append(rec)
    save("derivation-tokens", trace_records[0]["command"], trace_records,
         "Counts use the serialized English derivation text. Whitespace tokens are a tokenizer independent proxy.")

    uniform = expressions("frequency_uniform", ops, count=100, extra=(*expr_common, "--operator-frequency", "uniform"))
    zipf = expressions("frequency_zipf", ops, count=100, extra=(*expr_common, "--operator-frequency", "zipf:1.5", "--frequency-seed", "1"))
    registry = OperatorRegistry.from_jsonl(ops)
    eligible = lambda row: 1 <= len(closure(registry, from_dict(row["tree"], registry))) <= 3
    shared = next(op for op, n in Counter(x for row in uniform if eligible(row)
                                         for x in row["defined_operators"]).most_common()
                  if any(op in row["defined_operators"] and eligible(row) for row in zipf))
    freq_records = []
    for label, corpus in (("uniform", uniform), ("zipf:1.5", zipf)):
        row = next(r for r in corpus if shared in r["defined_operators"] and 1 <= len(closure(OperatorRegistry.from_jsonl(ops), from_dict(r["tree"], OperatorRegistry.from_jsonl(ops)))) <= 3)
        counts = Counter(op for item in corpus for op in item["defined_operators"])
        symbol = next(r["symbol"] for r in rows(ops) if r["func_id"] == shared)
        record = expression_record(row, ops, label=label)
        record["fields"] = {"operator": display(symbol, ops), "usage_in_100_records": counts[shared]}
        record["command"] = command_for("expressions", count=100,
                                        extra=(*expr_common, "--operator-frequency", label,
                                               *(("--frequency-seed", "1") if label != "uniform" else ())))
        freq_records.append(record)
    save("long-tail", freq_records[0]["command"], freq_records)

    # The short-closure, single-operator filter leaves too few repeats in 400 records
    # for the documented 2 x 6 and 4 x 3 comparison with this generated library.
    breadth_pool_count = 800
    pool = expressions("breadth_pool", ops, count=breadth_pool_count, extra=("--max-layer", "0", "--cot", "none"))
    grouped = defaultdict(list)
    for row in pool:
        if len(row["defined_operators"]) == 1 and eligible(row):
            grouped[row["defined_operators"][0]].append(row)
    narrow_ids = [key for key, items in grouped.items() if len(items) >= 6][:2]
    broad_ids = [key for key, items in grouped.items() if len(items) >= 3][:4]
    assert len(narrow_ids) == 2 and len(broad_ids) == 4, (
        "breadth pool must supply two operators with six records and four with three")
    breadth_records = []
    for label, ids, each in (("2 operators, 6 records each", narrow_ids, 6),
                              ("4 operators, 3 records each", broad_ids, 3)):
        selected = [row for key in ids for row in grouped[key][:each]]
        rec = expression_record(selected[0], ops, label=label)
        rec["fields"] = {"distinct_operators": len(ids), "records_per_operator": each,
                         "total_records": len(selected)}
        breadth_records.append(rec)
    save("breadth-or-depth", command_for("expressions", count=breadth_pool_count, extra=("--max-layer", "0", "--cot", "none")), breadth_records,
         f"Both 12 record cells are selected from one saved {breadth_pool_count} record pool. The displayed expression is one sample per cell.")

    layered = []
    for layer in (0, 3):
        layered.append(compact_expression(expressions(f"order_{layer}", small, count=100,
                                                      extra=("--max-layer", str(layer))), small))
    later_corpus = rows(WORK / "order_3.jsonl")
    small_registry = OperatorRegistry.from_jsonl(small)
    layered[1] = next(r for r in later_corpus
                      if r["highest_layer"] == 2
                      and 1 <= len(closure(small_registry, from_dict(r["tree"], small_registry))) <= 3)
    order_pool = later_corpus
    by_layer = {layer: next(r for r in order_pool if r["highest_layer"] == layer)
                for layer in (0, 1, 2)}
    ids = [f"r{by_layer[layer]['id']}" for layer in (0, 1, 2)]
    save("prerequisite-order", command_for("expressions", count=100, extra=("--max-layer", "3"), library="small_ops.jsonl"),
         [{"label": name, "lines": [" → ".join(ids[index] for index in order)],
           "fields": {"records": 3, "layers": "0, 1, 2"}}
          for name, order in (("layer order", (0, 1, 2)), ("shuffled order", (1, 0, 2)),
                              ("reverse order", (2, 1, 0)))],
         "All three schedules reuse the same saved record IDs from a four layer library. Ordering is an external serialization step.")

    spacing_pool = expressions("spacing", ops, count=100, extra=(*expr_common, "--cot", "none"))
    spacing_ids = [f"r{row['id']}" for row in spacing_pool[:3]]
    save("spacing", cli_text("expressions --operators ops.jsonl --out pool.jsonl --count 100 --seed 0 --max-layer 0 --cot none"),
         [{"label": name, "lines": [f"t{at}: {', '.join(spacing_ids)}" for at in times],
           "fields": {"exposures_per_record": 4, "last_exposure": 12}}
          for name, times in (("massed", (1, 2, 3, 12)), ("even", (1, 4, 8, 12)),
                              ("growing", (1, 3, 7, 12)))],
         "The same three saved record IDs recur in each external schedule. Every schedule ends at step 12.")

    pair = bench("contrast", ops, count=2, family="contrast", extra=short)
    assert pair[0]["expression"] == pair[1]["expression"]
    save("contrast-reward", cli_text("bench build --operators ops.jsonl --out tasks.jsonl --family contrast --count 2 --seed 0 --min-definitions 1 --max-definitions 2 --max-depth 2"),
         [task_record(pair[0], ops, label="contrast member A", fields=("definitions_needed",)),
          task_record(pair[1], ops, label="contrast member B", fields=("definitions_needed",))])

    # Training designs use real application or benchmark records as their inspectable unit.
    app = compact_expression(expressions("applications", ops, count=100, extra=(*expr_common, "--cot", "none")), ops)
    save("applied-rules-per-parameter", cli_text("expressions --operators ops.jsonl --out tasks.jsonl --count 100 --seed 0 --max-layer 0 --cot none"),
         [{**expression_record(app, ops, label="small load, test prompt"), "tag": "test prompt",
           "fields": {"library_operators": 40, "target_exposures_per_operator": 100, "junk_share": 0}},
          {**expression_record(app, ops, label="small load with junk, test prompt"), "tag": "test prompt",
           "fields": {"evaluated_operators": 40, "target_exposures_per_operator": 100, "junk_share": "7/8 target"}}],
         "The expression is one real application sample. Load cell exposures and junk share specify unrun training arms.")

    read_a = bench("read_A", ops, extra=(*short, "--context", "none", "--max-layer", "0"))[0]
    read_none = bench("read_none", ops, extra=(*short, "--context", "none"))[0]
    read_full = bench("read_full", ops, extra=(*short, "--context", "full"))[0]
    assert read_none["expression"] == read_full["expression"]
    read_records = []
    for label, task, context, shown, extra in (("A application sample", read_a, "none", False, ("--max-layer", "0")),
                                                ("B test without context", read_none, "none", False, ()),
                                                ("B test with context", read_full, "full", True, ())):
        rec = task_record(task, ops, label=label, fields=("definitions_needed",), show_definitions=shown)
        rec["tag"] = "test prompt"
        rec["fields"].update({"A_rules": 20, "B_rules": 20,
                              "A_training": "definitions + applications", "B_training": "definitions only"})
        rec["command"] = command_for("bench", extra=(*short, "--context", context, *extra))
        read_records.append(rec)
    save("read-only-rules", read_records[0]["command"], read_records,
         "A/B training exposure labels describe the proposed split. The A sample and paired B benchmark prompts have generated reference answers.")

    hole = bench("hole", ops, family="hole", extra=one)[0]
    hole_op = next(d for d in hole["definitions"] if any(r["symbol"] in d for r in rows(ops) if r["definition"]))
    hole_symbol = next(r["symbol"] for r in rows(ops) if r["definition"] == hole_op)
    hole_meta = next(r for r in rows(ops) if r["symbol"] == hole_symbol)
    if hole_meta["n_ary"] == 1:
        forward_expr = f"{hole_symbol} 85" if hole_meta["unary_position"] == "prefix" else f"85 {hole_symbol}"
        second_expr = f"{hole_symbol} 86" if hole_meta["unary_position"] == "prefix" else f"86 {hole_symbol}"
    else:
        forward_expr, second_expr = f"85 {hole_symbol} 2", f"86 {hole_symbol} 2"
    forward_value = answer(trace_for(forward_expr, OperatorRegistry.from_jsonl(ops)).value)
    second_value = answer(trace_for(second_expr, OperatorRegistry.from_jsonl(ops)).value)
    save("manipulate-rules", cli_text("bench build --operators ops.jsonl --out tasks.jsonl --family hole --count 1 --seed 0 --min-definitions 1 --max-definitions 1 --max-depth 2"),
         [{"label": "four questions from one rule", "operators": [display(hole_op, ops)],
           "lines": [f"forward: {display(forward_expr, ops)} = {forward_value}",
                     f"parity: {forward_value} is {'even' if isinstance(forward_value, int) and forward_value % 2 == 0 else 'odd'}",
                     f"compare: {forward_value} {'=' if forward_value == second_value else '<' if forward_value < second_value else '>'} {second_value} ({display(second_expr, ops)})",
                     f"inverse: {display(forward_expr.replace('85', 'x', 1), ops)} = {forward_value}, x ∈ {{85,86}} → 85",
                     f"inverse hole: {display(hole['expression'], ops)} = {hole['answer']}",
                     f"written intermediate: {display(forward_expr, ops)} = {forward_value}"],
           "tag": "question examples", "fields": {"inverse_reverse_steps": hole["axes"]["reverse_steps"]}}],
         "Forward and comparison values use the interpreter. The inverse is a generated hole task; the other question forms are unrun prompts.")

    binary = next(r for r in rows(ops) if r["definition"] and r["n_ary"] == 2 and r["recursive_layer"] == 0)
    symbol = binary["symbol"]
    first_expr = f"3 {symbol} 5"
    first_value = answer(trace_for(first_expr, OperatorRegistry.from_jsonl(ops)).value)
    second_expr = f"{first_value} {symbol} 2"
    second_value = answer(trace_for(second_expr, OperatorRegistry.from_jsonl(ops)).value)
    third_expr = f"4 {symbol} 1"
    third_value = answer(trace_for(third_expr, OperatorRegistry.from_jsonl(ops)).value)
    prefix = [f"a = {display(first_expr, ops)} → {first_value}",
              f"b = a {display(symbol, ops)} 2 → {second_value}",
              f"c = {display(third_expr, ops)} → {third_value}"]
    save("precompute", cli_text("operators --out ops.jsonl --layers 20 20 --seed 1 --check-variety"),
         [{"label": "question after bindings", "operators": [display(binary["definition"], ops)],
           "tag": "unrun prompt", "lines": [*prefix, f"question: b? → {second_value}"]},
          {"label": "question before bindings", "operators": [display(binary["definition"], ops)],
           "tag": "unrun prompt", "lines": [f"question: b?", *prefix, f"answer: {second_value}"]}],
         "Binding values are interpreter results. Question positions are proposed prompt formats; no model was queried.")

    shallow = bench("depth_1", ops, extra=(*short, "--max-depth", "1"))[0]
    deep = bench("depth_3", ops, extra=(*short, "--max-depth", "3"))[0]
    depth_records = []
    for cap, task in ((1, shallow), (3, deep)):
        rec = task_record(task, ops, label=f"generator cap {cap}")
        rec["fields"] = {"generator_max_depth": cap, "measured_expression_depth": task["axes"]["expression_depth"]}
        rec["command"] = command_for("bench", extra=(*short, "--max-depth", str(cap)))
        depth_records.append(rec)
    save("depth-vs-layers", depth_records[0]["command"], depth_records,
         "Composition depth comes from compute tasks; model layer counts and probes belong to the external evaluation.")

    from docs_evidence import _replace, _step_tools  # noqa: E402
    from opulse.cli.bench import step_checker_for  # noqa: E402
    from opulse.expression.nodes import Number  # noqa: E402
    from opulse.verify.steps import _changed_path  # noqa: E402

    corrected_task = bench("corrected_steps", ops, extra=(*short, "--format", "steps"))[0]
    _, start, clean_trace, renderer = _step_tools(ops, None)(corrected_task)
    clean_nodes = [step.expression_after for step in clean_trace.steps]
    wrong_index = next(i for i, node in enumerate(clean_nodes)
                       if isinstance(_changed_path(start if i == 0 else clean_nodes[i - 1], node)[-1][1], Number))
    previous = start if wrong_index == 0 else clean_nodes[wrong_index - 1]
    target = _changed_path(previous, clean_nodes[wrong_index])[-1][1]
    wrong_node = _replace(clean_nodes[wrong_index], target, Number(target.value + 1))
    wrong_lines = [renderer.full(node) for node in clean_nodes[:wrong_index]] + [renderer.full(wrong_node)]
    response = "\n".join("= " + line for line in wrong_lines) + f"\nAnswer: {corrected_task['answer_text']}"
    verdict = step_checker_for(ops, DEFAULT_CONFIG)(corrected_task, response)
    assert verdict["first_error"] is not None
    context = [f"= {display(line, ops)}" for line in wrong_lines[max(0, wrong_index - 1):]]
    context += [f"checker: first wrong line {verdict['first_error'] + 1}",
                "↩ retract", f"= {display(renderer.full(clean_nodes[wrong_index]), ops)}"]
    save("corrected-mistakes", command_for("bench", extra=(*short, "--format", "steps")),
         [{"label": "wrong rewrite and correction", "tag": "injected error",
           "expression": display(corrected_task["expression"], ops), "answer": answer(corrected_task["answer"]),
           "lines": context, "fields": {"injected_line": wrong_index + 1,
                                          "checker_first_error": verdict["first_error"] + 1}}],
         "The incorrect base result adds one, as in docs_evidence.py derive --wrong-line. The step checker rejects it; the retraction is an unrun training example.")

    composed = next(r for r in rows(ops) if r["definition"] and r["n_ary"] == 2
                    and r["recursive_layer"] == 1)
    grid_lines = []
    for a in range(5):
        for b in range(5):
            expr = f"{a} {composed['symbol']} {b}"
            value = answer(trace_for(expr, OperatorRegistry.from_jsonl(ops)).value)
            grid_lines.append((a, b, value))
    train_pairs = grid_lines[::2]
    held_pairs = grid_lines[1::2]
    fmt = lambda items: ", ".join(f"({a},{b})" for a, b, _ in items)
    save("delayed-generalization", cli_text("operators --out ops.jsonl --layers 20 20 --seed 1 --check-variety"),
         [{"label": "finite pair split", "operators": [display(composed["definition"], ops)],
           "lines": ["inputs: 0..4 × 0..4", "train: " + fmt(train_pairs),
                     "held out: " + fmt(held_pairs),
                     f"reference: (0,0)→{grid_lines[0][2]}, (0,1)→{grid_lines[1][2]}"],
           "fields": {"train_pairs": len(train_pairs), "held_out_pairs": len(held_pairs),
                      "split": "alternating pair index"}}],
         "The interpreter supplies all grid answers. The split is a proposed training input; no checkpoints or model outcomes are shown.")


    # Automatic curriculum: two neighboring difficulty cells.
    pool = bench("curriculum_pool", ops, count=40,
                 extra=("--min-definitions", "1", "--max-definitions", "2", "--max-depth", "2"))
    cell_keys = ("definitions_needed", "max_layer", "expression_depth", "recursive_definitions",
                 "branch_definitions")

    def cell(task: dict) -> tuple:
        return tuple(task["axes"][key] for key in cell_keys)

    easy, hard = next((a, b) for a in pool for b in pool
                      if a["axes"]["definitions_needed"] == 1 and b["axes"]["definitions_needed"] == 2
                      and len(b["definitions"]) <= 3
                      and all(cell(a)[i] == cell(b)[i] for i in range(1, len(cell_keys))))
    curriculum_records = []
    for label, task in (("easier cell", easy), ("one axis harder", hard)):
        rec = task_record(task, ops, label=label, fields=cell_keys[:3])
        curriculum_records.append(rec)
    save("auto-curriculum", command_for("bench", count=40, extra=("--min-definitions", "1",
                                                                  "--max-definitions", "2", "--max-depth", "2")),
         curriculum_records,
         "The two tasks differ on one structural axis. A cell's success rate would come from a learner's graded answers; no learner is shown.")

    # A step checker for a new material: exact labels on each line (integer world only).
    step_pool = bench("checker_steps", ops, count=12, extra=(*short, "--format", "steps"))
    checker = step_checker_for(ops, DEFAULT_CONFIG)
    for step_task in step_pool:
        _, step_start, step_trace, step_renderer = _step_tools(ops, None)(step_task)
        nodes = [step.expression_after for step in step_trace.steps]
        numeric = [i for i, node in enumerate(nodes)
                   if isinstance(_changed_path(step_start if i == 0 else nodes[i - 1], node)[-1][1], Number)]
        if len(numeric) >= 2 and numeric[1] <= 3:
            break
    else:
        raise AssertionError("no steps task with two numeric rewrites")
    bad = numeric[1]
    before = step_start if bad == 0 else nodes[bad - 1]
    target = _changed_path(before, nodes[bad])[-1][1]
    bad_node = _replace(nodes[bad], target, Number(target.value + 1))
    clean_lines = [step_renderer.full(node) for node in nodes]
    clean_response = "\n".join("= " + line for line in clean_lines) + f"\nAnswer: {step_task['answer_text']}"
    assert checker(step_task, clean_response)["first_error"] is None
    bad_lines = clean_lines[:bad] + [step_renderer.full(bad_node)]
    bad_response = "\n".join("= " + line for line in bad_lines) + f"\nAnswer: {step_task['answer_text']}"
    bad_verdict = checker(step_task, bad_response)
    assert bad_verdict["first_error"] == bad, bad_verdict
    shown = [f"= {display(line, ops)}   ✓" for line in bad_lines[:bad]]
    shown.append(f"= {display(bad_lines[bad], ops)}   ✗ first wrong step")
    save("step-checker-new-world", command_for("bench", count=12, extra=(*short, "--format", "steps")),
         [{"label": "exact step labels", "tag": "integer world",
           "expression": display(step_task["expression"], ops), "answer": answer(step_task["answer"]),
           "lines": shown, "fields": {"first_wrong_line": bad + 1}}],
         "The exact step checker labels the shown steps. This integer example omits the definitions needed to audit the wrong step; other worlds need presets.")

    # Inside the weights: reference answers for the handwired operator a ◆₁ = { (a % 3) + 1 }.
    raw = "⧫"
    handwired = prompt_registry([f"a {raw} = {{ (a % 3) + 1 }}"], base_registry(OperatorRegistry.from_jsonl(ops)),
                                SETTINGS.symbols, SETTINGS.semantics.build()).registry
    shape = lambda text: text.replace(raw, "◆₁")
    direct = f"5 {raw}"
    longer = f"(5 {raw}) + 1"
    direct_value = answer(trace_for(direct, handwired).value)
    longer_value = answer(trace_for(longer, handwired).value)
    assert (direct_value, longer_value) == (3, 4)
    definition = shape(f"a {raw} = {{ (a % 3) + 1 }}")
    save("write-concept", "",
         [{"label": "direct prompt", "operators": [definition], "expression": shape(direct),
           "answer": direct_value, "steps": len(trace_for(direct, handwired).steps)},
          {"label": "inside a longer expression", "operators": [definition], "expression": shape(longer),
           "answer": longer_value, "steps": len(trace_for(longer, handwired).steps)}],
         "These are interpreter answers, not injection results. The expressions illustrate the data and differ from the prompts used by the injection script.")

    table = [(a, answer(trace_for(f"{a} {raw}", handwired).value)) for a in range(8)]
    train_rows = [f"{a} ◆₁ → {v}" for a, v in table if a % 4 != 3]
    held_rows = [f"{a} ◆₁ → {v}" for a, v in table if a % 4 == 3]
    save("compiled-solution", "",
         [{"label": "operand table and split", "operators": [definition],
           "lines": ["train: " + ", ".join(train_rows), "held out: " + ", ".join(held_rows)],
           "fields": {"train_rows": len(train_rows), "held_out_rows": len(held_rows),
                      "split": "every fourth row"}}],
         "The interpreter gives every answer; every fourth row is held out. This peek has no compiled slot labels or trained network.")

    if importlib.util.find_spec("opulse.skeleton") is not None:
        world_peeks(ROOT / "src")
    else:
        print("same-tree-other-world, world-variety: kept (needs opulse skeleton and --world-mix)")

    actual = {p.stem for p in SNIPPETS.glob("*.json")}
    assert actual == set(ANCHORS), (set(ANCHORS) - actual, actual - set(ANCHORS))
    for path in SNIPPETS.glob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(payload["command"], str) and 1 <= len(payload["records"]) <= 4
        assert path.stat().st_size < 6144


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--worlds-src":
        WORK.mkdir(parents=True, exist_ok=True)
        world_peeks(Path(sys.argv[2]).resolve())
    else:
        main()
