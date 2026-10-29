"""Browser showcases built from seeded, generated operator sets.

Every world supplies a :class:`WorldSpec`: how to grow its operators, which input values to
try, how to encode values for the browser, and the text of its atom panel. One exporter does
the rest for every world, so all showcases share their naming, sentences, example choice and
file layout:

* operators keep their generated shapes and receive short indices in display order;
* each operator gets a sentence in English and Chinese from
  :class:`opulse.worlds.present.Describer`;
* examples are chosen from many candidate inputs so that the first three already differ in
  the case taken, the recursion depth, whether the result is defined, and the input size;
* every example value comes from the reference interpreter, and every derivation from the
  reducer; the derivations go to ``<world>/steps/<operator index>.json``, one list of steps
  per example, loaded when a reader opens one.
"""

from __future__ import annotations

import itertools
import json
import random
import re
import shutil
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from opulse.config import Settings
from opulse.core.operator import BRANCH, RECURSIVE, SIMPLE, Operator
from opulse.core.primitives import CUSTOM, atom_records, rule_for
from opulse.core.registry import OperatorRegistry
from opulse.core.semantics import NAN, base_operation_name
from opulse.definition.parser import DefinitionParser
from opulse.expression.nodes import Call, Number
from opulse.expression.render import ExpressionRenderer
from opulse.generation.pipeline import OperatorFactory, layer_plan
from opulse.runtime.python_backend import PythonRuntime
from opulse.trace.reducer import Reducer
from opulse.verify import Oracle
from opulse.worlds.present import Describer, alias, operator_names, zh_spacing
from opulse.worlds._atomic_export import staged_export

WORLD_IDS = ("successor", "integer", "clock", "bits", "strings", "lists",
             "logic", "perm", "rel", "grid", "pitch")
DIMENSIONS = ("number", "text", "structure", "logic", "order", "knowledge", "vision", "sound", "action")
KINDS = {SIMPLE: "composition", BRANCH: "branching", RECURSIVE: "recursion"}


@dataclass
class WorldSpec:
    world: str
    title: str
    title_zh: str
    dimension: str
    build: Callable[[], tuple]  # () -> (settings, registry, generated operators in growth order)
    values: Callable[[str], Sequence]  # value type -> candidate inputs
    encode: Callable[[object, str | None], dict]  # (value, value type) -> browser value
    atom_zh: dict[str, str]  # atom name -> one Chinese sentence
    atom_examples: dict[str, tuple] = field(default_factory=dict)  # atom name -> worked inputs
    domain: tuple = ()  # ((English, Chinese), ...) what the values are
    settings: Callable[[Settings], list] | None = None  # -> [(key, value, English, Chinese)]
    why: tuple = ("", "")
    seed: int = 0
    value_text: Callable | None = None  # (value, type) -> text or (English, Chinese) text
    operator_extra: Callable | None = None  # (operator, row, tools) -> None
    step_extra: Callable | None = None  # (trace step, record, tools) -> None
    context: Callable | None = None  # (tools) -> dict merged into the world data
    extra_inputs: Callable | None = None  # (operator, tools) -> extra candidate tuples
    order: Callable | None = None  # (generated) -> featured operators, or None to choose


# ------------------------------------------------------------------ values

def encode(value, kind: str | None = None) -> dict:
    if value is NAN:
        return {"t": "nan"}
    if isinstance(value, bool):
        return {"t": "bool", "v": value}
    if isinstance(value, int):
        return {"t": "int", "v": value}
    if isinstance(value, str):
        return {"t": "str", "v": value}
    if isinstance(value, (list, tuple)):
        return {"t": "list", "v": [encode(item) for item in value]}
    raise TypeError(value)


def short_text(value, kind: str | None = None) -> str:
    """A value as a step note shows it: short, with large values summarised."""
    if value is NAN:
        return "NaN"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return '"' + value + '"'
    if kind == "grid" or (isinstance(value, tuple) and value and isinstance(value[0], tuple)
                          and kind != "melody"):
        return f"a {len(value)}×{len(value[0])} grid"
    if kind == "melody":
        return f"a melody of {len(value)} notes"
    if isinstance(value, tuple):
        return "[" + ", ".join(map(str, value)) + "]"
    return str(value)


def short_text_zh(value, kind: str | None = None) -> str:
    if value is NAN:
        return "NaN"
    if isinstance(value, bool):
        return "真" if value else "假"
    if kind == "grid" or (isinstance(value, tuple) and value and isinstance(value[0], tuple)
                          and kind != "melody"):
        return f"一个 {len(value)}×{len(value[0])} 网格"
    if kind == "melody":
        return f"一段 {len(value)} 个音的旋律"
    return short_text(value, kind)


def _size(value) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return abs(value)
    if isinstance(value, str):
        return len(value)
    if isinstance(value, tuple) and value and isinstance(value[0], tuple):
        return len(value) * len(value[0])
    if isinstance(value, tuple):
        return len(value)
    return 0


def _bucket(size: int) -> int:
    return 0 if size == 0 else 1 if size <= 2 else 2 if size <= 9 else 3 if size <= 30 else 4


TRIVIAL = (0, 1, -1, "", (), False, True)


def _trivial(value) -> bool:
    return any(value == item and type(value) is type(item) for item in TRIVIAL)


# ------------------------------------------------------------------ tools


@dataclass
class Tools:
    spec: WorldSpec
    settings: Settings
    registry: OperatorRegistry
    names: dict
    oracle: Oracle
    reducer: Reducer
    renderer: ExpressionRenderer
    parser: DefinitionParser
    describer: Describer

    def show(self, text: str) -> str:
        return alias(text, self.names)


def _value_types(registry, op: Operator) -> tuple[str, ...]:
    return tuple(op.parameter_types)


def _candidates(spec: WorldSpec, op: Operator, tools: Tools, limit: int = 400) -> list[tuple]:
    pools = [list(spec.values(kind)) for kind in op.parameter_types]
    extra = list(spec.extra_inputs(op, tools)) if spec.extra_inputs else []
    product = list(itertools.product(*pools))
    random.Random(len(op.definition)).shuffle(product)
    out, seen = [], set()
    for args in (*extra, *product):
        key = repr(args)
        if key not in seen:
            seen.add(key)
            out.append(args)
        if len(out) >= limit:
            break
    return out


def _signature(op: Operator, trace) -> tuple:
    own = [step for step in trace.steps if step.operator.func_id == op.func_id and step.kind == "expand"]
    branch = own[0].branch_index if own else None
    return branch, min(len(own), 4)


def _inert_atoms(trace) -> int:
    return sum(step.kind == "eval" and step.operator.definition is None
               and step.output is not NAN and step.before.args
               and type(step.output) is type(step.before.args[0].value)
               and step.output == step.before.args[0].value
               for step in trace.steps)


def choose_examples(op: Operator, tools: Tools, count: int) -> list[dict]:
    """Pick ``count`` inputs whose first three already show different behaviours."""
    oracle = tools.oracle
    light = Reducer(tools.registry, tools.reducer.runtime, tools.parser,
                    expand=lambda other: other.func_id == op.func_id, max_steps=60)
    rows = []
    for args in _candidates(tools.spec, op, tools):
        try:
            value = oracle.evaluate(op, args).value
            outline = light.reduce(Call(op, tuple(Number(arg) for arg in args)))
        except (RecursionError, OverflowError, ValueError, TypeError):
            continue
        branch, depth = _signature(op, outline)
        rows.append({"args": args, "value": value, "branch": branch, "depth": depth,
                     "nan": value is NAN, "sizes": tuple(_bucket(_size(arg)) for arg in args),
                     "trivial": sum(_trivial(arg) for arg in args), "out": repr(value)})
    has_defined = any(not row["nan"] for row in rows)
    chosen = []
    seen = {"branch": set(), "depth": set(), "nan": set(), "sizes": set(), "out": set(), "first": set()}
    while len(chosen) < count:
        ranked = []
        for row in rows:
            if row.get("used"):
                continue
            if row["nan"] and has_defined and (not chosen or
                    (len(chosen) < 3 and sum(item["nan"] for item in chosen) >= 1)):
                continue
            score = 0.0
            score += 4 * (row["branch"] not in seen["branch"])
            score += 3 * (row["depth"] not in seen["depth"])
            score += 2.5 * (row["out"] not in seen["out"])
            score += 1.5 * (row["sizes"] not in seen["sizes"])
            score += 1.0 * (repr(row["args"][0]) not in seen["first"])
            if row["nan"]:
                score += 1.5 if (True not in seen["nan"] and len(chosen) >= 2) else -6
            score -= 1.2 * row["trivial"]
            score -= 0.02 * sum(_size(arg) for arg in row["args"])
            ranked.append((score, row))
        ranked.sort(key=lambda item: item[0], reverse=True)
        best = None
        for _, row in ranked:
            if "trace" not in row:
                tree = Call(op, tuple(Number(arg) for arg in row["args"]))
                try:
                    trace = tools.reducer.reduce(tree)
                except (RecursionError, OverflowError, ValueError, TypeError):
                    row["invalid"] = True
                    continue
                if trace.truncated or len(trace.steps) > 90 or not _same(trace.value, row["value"]):
                    row["invalid"] = True
                    continue
                row["trace"], row["tree"] = trace, tree
                row["inert_atoms"] = _inert_atoms(trace)
            if row.get("invalid"):
                continue
            if best is None or row["inert_atoms"] < best["inert_atoms"]:
                best = row
            if row["inert_atoms"] == 0:
                break
        if best is None:
            if not chosen:
                raise RuntimeError(f"no example for {op.symbol}")
            break  # an operator on two truth values has only a few distinct inputs
        best["used"] = True
        chosen.append(best)
        for key in ("branch", "depth", "sizes", "out"):
            seen[key].add(best[key])
        seen["nan"].add(best["nan"])
        seen["first"].add(repr(best["args"][0]))
    return chosen


def _same(left, right) -> bool:
    return left is right or left == right


# ------------------------------------------------------------------ featured operators


def _featured(generated: list[Operator], tools: Tools) -> list[Operator]:
    """Five operators: the most interesting substitution, branch and recursion, then the next two.

    Interest is scored by :mod:`opulse.generation.interest`. An operator whose sentence is only a
    summary, or that leans on many helpers, ranks lower, because the reader should be able to
    follow a featured operator from its sentence alone.
    """
    from opulse.generation.interest import score_registry
    from opulse.worlds.metrics import fingerprint

    prints = [fingerprint(op, tools.oracle, tools.spec.world) for op in generated]
    scores = score_registry(tools.registry, tools.settings)
    for op in generated:
        op._interest = scores.get(op.func_id)

    def rank(op: Operator) -> float:
        description = tools.describer.describe(op)
        helpers = sum(1 for kind, symbol in description.mentions
                      if kind == "op" and symbol in tools.names and symbol != op.symbol)
        return ((op._interest or {}).get("score", 0.0)
                - 0.08 * max(helpers - 1, 0) - 0.3 * (description.reading == "summary")
                - 0.15 * (len(set(prints[generated.index(op)][1])) <= 2) + 0.05 * (description.reading == "repetition"))

    ranked = sorted(generated, key=lambda op: (-rank(op), generated.index(op)))
    chosen: list[Operator] = []
    seen = set()
    for kind in (SIMPLE, BRANCH, RECURSIVE):
        best = next((op for op in ranked if op.definition_type == kind), None)
        if best is not None:
            chosen.append(best)
            seen.add(prints[generated.index(best)])
    for op in ranked:
        if len(chosen) >= 5:
            break
        mark = prints[generated.index(op)]
        if op not in chosen and mark not in seen:
            chosen.append(op)
            seen.add(mark)
    return chosen


# ------------------------------------------------------------------ export


def _notes(step, tools: Tools, kinds: dict) -> tuple[str, str]:
    name = tools.names.get(step.operator.symbol, step.operator.symbol)
    focus = tools.show(tools.renderer.full(step.before))
    if step.kind == "expand":
        condition = tools.show(step.condition) if step.condition else ""
        for code, sign in (("==", "="), ("!=", "≠"), ("<=", "≤"), (">=", "≥")):
            condition = condition.replace(" " + code + " ", " " + sign + " ")
        index = (step.branch_index or 0) + 1
        if condition:
            return (f"Unfold {name}: case {index} applies because {condition}.",
                    zh_spacing(f"展开 {name}：{condition} 成立，用第 {index} 种情形。"))
        return f"Unfold {name}.", zh_spacing(f"展开 {name}。")
    if step.kind == "undefined":
        return (f"No case of {name} applies to {focus}, so the result is NaN.",
                zh_spacing(f"{focus} 不满足 {name} 的任何情形，结果为 NaN。"))
    kind = kinds.get(step.operator.func_id)
    value = step.output
    return (f"Compute {focus}: {short_text(value, kind)}.",
            zh_spacing(f"计算 {focus}，得 {short_text_zh(value, kind)}。"))


def _atom_panel(spec: WorldSpec, tools: Tools) -> list[dict]:
    atoms = []
    for op in tools.registry:
        if op.definition is not None:
            continue
        name = base_operation_name(op.symbol, op.n_ary, op.unary_position)
        custom = CUSTOM.get(name)
        kinds = tuple(custom.parameter_types) if custom and custom.parameter_types else ("int",) * op.n_ary
        result = custom.result_type if custom and custom.result_type else "int"
        args = spec.atom_examples.get(name)
        if args is None:
            pools = [list(spec.values(kind)) for kind in kinds]
            args = next((candidate for candidate in itertools.product(*pools)
                         if not any(_trivial(item) for item in candidate)
                         and tools.oracle.evaluate(op, candidate).value is not NAN),
                        tuple(pool[0] for pool in pools))
        value = tools.oracle.evaluate(op, args).value
        expression = tools.renderer.full(Call(op, tuple(Number(arg) for arg in args)))
        zh = spec.atom_zh.get(name)
        if zh is None:
            raise KeyError(f"the {spec.world} world has no Chinese sentence for atom {name!r}")
        atoms.append({"symbol": op.symbol, "name": name, "arity": op.n_ary,
                      "signature": " × ".join(kinds) + " → " + result,
                      "rule": rule_for(name), "plain": rule_for(name),
                      "plain_zh": zh_spacing(zh),
                      "params": [{"name": n, "type": t} for n, t in
                                 zip(tools.settings.symbols.operands(op.n_ary), kinds)],
                      "result_type": result,
                      "example": {"expression": expression,
                                  "inputs": [spec.encode(arg, kind) for arg, kind in zip(args, kinds)],
                                  "output": spec.encode(value, result)}})
    shared = Path(__file__).resolve().parents[3] / "docs/assets/data/atoms" / f"{spec.world}.json"
    if shared.exists():
        published = json.loads(shared.read_text(encoding="utf-8"))
        records = published if isinstance(published, list) else published.get("atoms", [])
        by_symbol = {(item["symbol"], item["arity"]): item for item in records}
        for atom in atoms:
            key = (atom["symbol"], atom["arity"])
            if key in by_symbol:
                atom.update({key: value for key, value in by_symbol[key].items()
                             if key in {"name", "arity", "signature", "plain", "plain_zh", "example"}})
    return atoms


def _reader_plain(world: str, plain: str, kind: str, uses: list[str]) -> str:
    """Keep direct bounded repetitions readable without hiding their limit."""
    if (world == "bits" and kind == "recursion" and not uses
            and plain.startswith("Recurse on b (for b from 0 to 31): when b = 0 the result is a;")
            and plain.endswith("then OR r with b bit by bit.")):
        return "Starting from a, OR in b and its successive right shifts until b reaches zero (b from 0 to 31)."
    if world != "grid" or kind != "recursion" or uses or len(plain.split()) <= 22:
        return plain
    match = re.fullmatch(r"Start with (.+?)\. Repeat (.+?) times \(for .+?; other values give NaN\): (.+)\.", plain)
    if match is None:
        return plain
    start, count, step = match.groups()
    short = f"Start with {start}; repeat {count} times: {step} (counts beyond the bound give NaN)."
    return short if len(short.split()) <= 22 else plain


def export_spec(spec: WorldSpec, out_path: str | Path, seed: int | None = None,
                root: str | Path | None = None, steps_dir: Path | None = None) -> dict:
    """Write one seed of one world: its data file and its lazily loaded derivation files.

    Derivations go under ``root`` (the directory of ``out_path`` by default).
    """
    out_path = Path(out_path)
    root = Path(root) if root is not None else out_path.parent
    seed = spec.seed if seed is None else seed
    if steps_dir is None:
        with staged_export(root / spec.world / "steps" / str(seed), out_path) as (staged, staged_json):
            return export_spec(spec, staged_json, seed, root, staged)
    settings, registry, generated = spec.build(seed)
    semantics = settings.semantics.build()
    parser = DefinitionParser(settings.symbols, registry)
    oracle = Oracle(registry, settings.symbols, semantics)
    runtime = PythonRuntime(registry, semantics)
    # Helpers two unfoldings deep are computed in one step, which keeps derivations readable.
    reducer = Reducer(registry, runtime, parser, max_steps=91, max_depth=2)
    renderer = ExpressionRenderer(settings.symbols)
    atom_symbols = [op.symbol for op in registry if op.definition is None]
    provisional = operator_names(generated, settings, atom_symbols, seed)
    describer = Describer(registry, provisional, parser, spec.value_text)
    tools = Tools(spec, settings, registry, provisional, oracle, reducer, renderer, parser, describer)
    featured = spec.order(generated) if spec.order else _featured(generated, tools)
    ordered = featured + [op for op in generated if op not in featured]
    names = operator_names(ordered, settings, atom_symbols, seed)
    tools.names = names
    tools.describer = describer = Describer(registry, names, parser, spec.value_text)
    kinds = {op.func_id: op.result_type for op in registry}
    steps_dir = steps_dir if steps_dir is not None else root / spec.world / "steps" / str(seed)
    steps_dir.mkdir(parents=True, exist_ok=True)
    for stale in steps_dir.glob("*.json"):
        stale.unlink()
    operators = []
    for index, op in enumerate(ordered):
        description = describer.describe(op)
        interest = getattr(op, "_interest", None)
        if interest is not None:
            interest = {**interest, "nearest": names.get(interest.get("nearest"), interest.get("nearest"))}
        uses = sorted({names[symbol] for kind, symbol in description.mentions
                       if kind == "op" and symbol in names and symbol != op.symbol})
        row = {"name": names[op.symbol], "definition": tools.show(op.definition),
               "plain": _reader_plain(spec.world, description.en, KINDS[op.definition_type], uses),
               "plain_zh": description.zh, "reading": description.reading,
               "params": [{"name": name, "type": kind}
                          for name, kind in zip(settings.symbols.operands(op.n_ary), op.parameter_types)],
               "result_type": op.result_type, "layer": op.recursive_layer,
               "kind": KINDS[op.definition_type], "featured": index < len(featured),
               "interest": interest,
               "uses": uses,
               "examples": []}
        count = 10 if index < len(featured) else 3
        detail = []
        for choice in choose_examples(op, tools, count):
            args, value, trace = choice["args"], choice["value"], choice["trace"]
            row["examples"].append({
                "expression": tools.show(renderer.full(choice["tree"])),
                "inputs": [spec.encode(arg, kind) for arg, kind in zip(args, op.parameter_types)],
                "output": spec.encode(value, op.result_type),
                "case": None if choice["branch"] is None else choice["branch"] + 1,
                "depth": choice["depth"],
            })
            steps = []
            for step in trace.steps:
                note, note_zh = _notes(step, tools, kinds)
                kind = kinds.get(step.operator.func_id)
                record = {"kind": step.kind,
                          "expression": tools.show(renderer.full(step.expression_after)),
                          "focus": tools.show(renderer.full(step.before)),
                          "value": spec.encode(step.output, kind) if step.output is not None else None,
                          "note": note, "note_zh": note_zh,
                          "gate": names.get(step.operator.symbol, step.operator.symbol),
                          "branch": step.branch_index}
                if spec.step_extra:
                    spec.step_extra(step, record, tools)
                steps.append(record)
            detail.append(steps)
        if spec.operator_extra:
            spec.operator_extra(op, row, tools)
        (steps_dir / f"{index}.json").write_text(json.dumps(detail, ensure_ascii=False, separators=(",", ":")),
                                                 encoding="utf-8")
        operators.append(row)
    domain = [{"en": en, "zh": zh_spacing(zh)} for en, zh in spec.domain]
    rows = spec.settings(settings) if spec.settings else []
    from opulse.worlds.metrics import measure

    data = {"world": spec.world, "seed": seed, "steps": f"{spec.world}/steps/{seed}/",
            "title": spec.title, "title_zh": spec.title_zh,
            "dimension": spec.dimension, "atoms": _atom_panel(spec, tools), "domain": domain,
            "settings": [{"key": key, "value": value, "en": en, "zh": zh_spacing(zh)}
                         for key, value, en, zh in rows],
            "why": {"en": spec.why[0], "zh": zh_spacing(spec.why[1])},
            "operators": operators}
    from opulse.worlds.curation import curate

    data["curated"], data["curation_rejected"] = curate(ordered, operators, spec, oracle, registry, names, tools)
    data["curation_target"] = 24
    data["curation_not_selected"] = len(operators) - len(data["curated"]) - sum(data["curation_rejected"].values())
    if spec.context:
        data.update(spec.context(tools))
    data["metrics"] = measure(spec.world, registry, generated, oracle, parser)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _write(out_path, data)
    return data


def _write(path: Path, data: dict) -> None:
    public = {key: value for key, value in data.items() if key != "metrics"}
    public["metrics"] = {key: value for key, value in data["metrics"].items() if not key.startswith("_")}
    path.write_text(json.dumps(public, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


SEEDS = 3


def export_world(world_name: str, directory: str | Path, seeds: int = SEEDS) -> list[dict]:
    """Write ``seeds`` independently grown operator sets of one world.

    The first goes to ``<world>.json``, the others to ``<world>/seed-<seed>.json``. Every file
    lists all seeds with their measured variety, including how many behaviours of each seed
    occur in no other seed.
    """
    from opulse.worlds.metrics import add_novelty

    directory = Path(directory)
    spec = world_spec(world_name)
    numbers = [spec.seed + 101 * index for index in range(seeds)]
    folder = directory / world_name
    paths = [directory / f"{world_name}.json"] + [folder / f"seed-{n}.json" for n in numbers[1:]]
    with staged_export(folder, paths[0]) as (staged, staged_main):
        if folder.exists():
            shutil.copytree(folder, staged, dirs_exist_ok=True)
        if (staged / "steps").exists():
            shutil.rmtree(staged / "steps")
        for stale in staged.glob("seed-*.json"):
            stale.unlink()
        staged_paths = [staged_main] + [staged / f"seed-{n}.json" for n in numbers[1:]]
        results = [export_spec(spec, path, seed, directory, staged / "steps" / str(seed))
                   for path, seed in zip(staged_paths, numbers)]
        metrics = [result["metrics"] for result in results]
        add_novelty(metrics)
        listing = [{"seed": seed, "file": str(path.relative_to(directory)), "metrics": result["metrics"]}
                   for seed, path, result in zip(numbers, paths, results)]
        for path, result in zip(staged_paths, results):
            result["seeds"] = listing
            _write(path, result)
    return results


# ------------------------------------------------------------------ the numeric and text worlds


GROWTH = (40, 35, 25)
FORMS = (0.40, 0.30, 0.30)


def grow(world: str, settings: Settings, registry: OperatorRegistry, seed: int,
         counts=GROWTH, proportions=FORMS, attempts: int = 120) -> list[Operator]:
    """Grow layered operators, keeping only ones whose behaviour is new.

    A candidate is measured on the world's fixed probes (:mod:`opulse.worlds.metrics`). It is
    rejected when it gives one output on every probe, when a non boolean operator gives at
    most two, or when an accepted operator already has the same outputs. If ``attempts``
    candidates in a row fail, the first varied duplicate seen is accepted instead, so a world
    with few possible behaviours (two truth values) still fills its layers.
    """
    from opulse.generation.pipeline import GenerationError
    from opulse.worlds.metrics import fingerprint

    factory = OperatorFactory(settings, registry, random.Random(seed), max_attempts=300)
    seen: set = set()
    for layer, count in enumerate(counts):
        for kind in layer_plan(count, layer, proportions, factory.rng):
            fallback = None
            chosen = None
            for _ in range(attempts):
                try:
                    operator = factory.generate(kind, layer)
                except GenerationError:
                    break
                factory.oracle.include(operator)
                mark = fingerprint(operator, factory.oracle, world)
                outputs = set(mark[1])
                varied = len(outputs) > 1 and (operator.result_type == "bool" or len(outputs) > 2)
                swapped = None
                if len(mark[0]) == 2 and mark[0][0] == mark[0][1]:
                    swapped = (mark[0], _swap_outputs(world, operator, mark[1]))
                if varied and mark not in seen and swapped not in seen:
                    chosen = operator
                    break
                if varied and fallback is None:
                    fallback = (operator, mark)
                factory.runtime.unload(operator)
                factory.oracle.forget(operator)
            if chosen is None and fallback is not None:
                chosen, mark = fallback
            if chosen is None:
                continue  # this form has no candidate here; the layer stays a little smaller
            factory.add(chosen)
            seen.add(mark)
    return [op for op in registry if op.definition]


def _swap_outputs(world: str, operator: Operator, outputs: tuple) -> tuple:
    """The probe outputs of ``operator`` with its two inputs exchanged, read from ``outputs``."""
    from opulse.worlds.metrics import probes

    pool = list(probes(world, operator.parameter_types[0]))
    points = list(itertools.islice(itertools.product(pool, pool), len(outputs)))
    where = {point: index for index, point in enumerate(points)}
    return tuple(outputs[where[(b, a)]] if (b, a) in where else "?" for a, b in points)


def _grow(world: str, seed: int):
    from opulse.core.presets import PRESETS as TYPED_PRESETS
    from opulse.presets import PRESETS as NUMERIC_PRESETS

    names = TYPED_PRESETS[world] if world in TYPED_PRESETS else NUMERIC_PRESETS[world]["atoms"]
    Settings.from_dict({"preset": world})  # registers the atoms
    registry = OperatorRegistry(Operator.from_dict(row) for row in atom_records(names, seed=seed))
    settings = Settings.from_dict({
        "preset": world,
        "operators": {"max_if_branches": 3, "min_defined_share": 0.5},
        "expressions": {"max_depth": 2},
    })
    return settings, registry, grow(world, settings, registry, seed)


def _pool(world: str):
    def values(kind: str):
        if kind == "str":
            return ("hello", "Abc", "", "racecar", "Opulse", "b", "xY", "data", "aba", "B", "ab", "a",
                    "Tea", "level", "Zz9")
        if kind == "list[int]":
            return ((3, 1, 4, 1, 5), (), (7,), (2, 9), (-4, 0, 6), (10, 20, 30, 40), (1, 2), (2, 3),
                    (5, 5, 5), (8, -3, 6, 0, 2, 9), (1,), (12, 7))
        if kind == "bool":
            return (True, False)
        if world in ("strings", "lists"):
            return (2, 0, 5, -3, 1, 8, -7, 4, 9, 3, -1, 6)
        if world == "clock":
            return (11, 5, 14, 7, 23, 3, 9, -4, 0, 18, 6, 31, 2, 8, 13)
        if world == "bits":
            return (13, 6, 31, 10, 0, 21, 7, 16, 44, 3, 63, 5, 2, 25, 12)
        if world == "successor":
            return (3, 7, 0, 12, 5, 2, 9, 15, 1, 4, 20, 6, 11)
        return (7, 12, -5, 23, 3, -18, 41, 0, 9, 64, -2, 15, 100, 1, -37, 28, 5, 77)
    return values


def _literal_inputs(op: Operator, tools: Tools):
    """Inputs equal to a literal tested in a condition, so that branch can be shown."""
    from opulse.definition import ast

    definition = tools.parser.parse(op.definition)
    found = []

    def visit(node):
        if isinstance(node, ast.Truth):
            visit(node.expr)
        elif isinstance(node, ast.Apply):
            for arg in node.args:
                visit(arg)
        elif isinstance(node, (ast.And, ast.Or)):
            visit(node.left)
            visit(node.right)
        elif isinstance(node, ast.Not):
            visit(node.operand)
        elif isinstance(node, ast.Compare):
            visit(node.left)
            visit(node.right)
        elif isinstance(node, ast.Literal):
            found.append(node.value)

    for branch in definition.branches:
        if branch.condition is not None:
            visit(branch.condition)
    out = []
    for value in found:
        for position, kind in enumerate(op.parameter_types):
            pools = [list(tools.spec.values(k))[:4] for k in op.parameter_types]
            if _type_matches(value, kind):
                pools[position] = [value]
                out.extend(itertools.product(*pools))
    return out


def _type_matches(value, kind: str) -> bool:
    from opulse.core.types import type_of

    try:
        return str(type_of(value)) == kind or (kind.startswith("perm[") and type(value).__name__ == "Permutation")
    except (TypeError, ValueError):
        return False


_INT_ZH = {
    "add": "a + b 是整数加法。", "sub": "a - b 是整数减法。", "mul": "a * b 是整数乘法。",
    "div": "a / b 是向零取整的除法，b = 0 时结果为 NaN。",
    "mod": "a % b 是余数 a - b * (a / b)，符号与 a 相同，b = 0 时结果为 NaN。",
    "neg": "- a 是 a 的相反数。",
    "reverse": "a @ 把 |a| 的十进制数字倒过来写，再保留 a 的符号。",
    "triangle": "# a 是带符号三角数 sign(a) * |a| * (|a| + 1) / 2。",
    "popcount": "a $ 是 |a| 的二进制里 1 的个数。",
    "digitsum": "& a 是 |a| 的各位数字之和，再乘上 a 的符号。",
    "natural_succ": "a ↑ 是非负整数 a 加一，负数输入得 NaN。",
    "natural_pred": "a ↓ 是 max(0, a - 1)，负数输入得 NaN。",
    "is_zero": "a ○ 在 a 为零时得 1，否则得 0，负数输入得 NaN。",
    "bit_and": "a ∧ b 是两个非负整数的按位与。",
    "bit_or": "a ∨ b 是两个非负整数的按位或。",
    "bit_xor": "a ⊻ b 是两个非负整数的按位异或。",
    "shift_left": "a ⇐ b 把非负整数 a 左移 b 位，b 大于 31 时得 NaN。",
    "shift_right": "a ⇒ b 把非负整数 a 右移 b 位。",
    "bit_count": "a ♯ 是非负整数 a 的二进制里 1 的个数。",
    "str_concat": "a ⊕ b 把字符串 b 接在 a 后面。",
    "str_length": "a ℓ 是字符串 a 的字符个数。",
    "str_reverse": "a ↶ 把字符串 a 倒过来。",
    "str_first": "a ⌑ 是 a 的第一个字符，空字符串得空字符串。",
    "str_drop": "a ⇥ 去掉 a 的第一个字符，空字符串保持为空。",
    "str_upper": "a ⇧ 把 a 中的小写字母改成大写。",
    "str_lower": "a ⇩ 把 a 中的大写字母改成小写。",
    "str_equal": "a ≡ b 在两个字符串完全相同时为真。",
    "list_cons": "a ⊲ b 把整数 a 放到列表 b 的最前面。",
    "list_head": "a ⌃ 是列表 a 的第一个元素，空列表得 NaN。",
    "list_tail": "a ⌄ 去掉列表 a 的第一个元素，空列表保持为空。",
    "list_length": "a ℒ 是列表 a 的元素个数。",
    "list_append": "a ⊞ b 把列表 b 接在 a 后面。",
    "list_sum": "a Σ 是列表 a 所有元素之和。",
    "list_at": "a ⊙ b 是列表 a 中下标为 b 的元素，下标从零数，越界得 NaN。",
    "list_equal": "a ≍ b 在两个列表元素和顺序都相同时为真。",
}


def _numeric_settings(world: str):
    def rows(settings: Settings):
        recursion = settings.recursion
        out = [("preset", world, "The preset that selects these atoms and defaults.",
                "选择这些原子和默认设置的预设。")]
        if settings.semantics.mode == "modular":
            out.append(("semantics.modulus", settings.semantics.modulus,
                        "Every atom result is reduced modulo this number.", "每个原子的结果都对这个数取模。"))
        out.append(("recursion.style", recursion.style,
                    "The template of recursive definitions.", "递归定义使用的模板。"))
        if recursion.style == "bounded_mod":
            out.append(("recursion.modulus_min / modulus_max", f"{recursion.modulus_min} / {recursion.modulus_max}",
                        ("A recursive call reduces its counter modulo a number drawn from this range, "
                        "so it unfolds fewer times than that number."),
                        "递归计数先对这个范围里抽到的数取模，所以展开次数小于这个数。"))
        else:
            out.append(("recursion.direct_bound", recursion.direct_bound,
                        "A recursive call unfolds at most this many times; larger counters give NaN.",
                        "递归最多展开这么多次，更大的计数得 NaN。"))
        out.append(("expressions.value_min / value_max",
                    f"{settings.expressions.value_min} / {settings.expressions.value_max}",
                    "The range of numbers in generated expressions and branch thresholds.",
                    "生成算式和分支阈值所用的数值范围。"))
        return out
    return rows


def _typed_settings(world: str, extra=()):
    def rows(settings: Settings):
        recursion = settings.recursion
        out = [("preset", world, "The preset that selects these atoms.", "选择这些原子的预设。")]
        out.append(("recursion.direct_bound", recursion.direct_bound,
                    "A recursive call repeats its step at most this many times; larger counts give NaN.",
                    "递归最多重复这么多步，更大的次数得 NaN。"))
        out.append(("operators.max_if_branches", settings.operators.max_if_branches,
                    "The largest number of cases in a branch definition.", "分支定义最多的情形数。"))
        out.extend(extra)
        return out
    return rows


WHY = (("These atoms are one example. Atoms are chosen by the user: any function with a rule can be "
       "registered and the same three composition forms grow operators from it."),
       "这些原子只是一个例子。原子由用户自己选：任何写得出规则的函数都能注册，同样三种组合方式会从它长出新运算符。")


def _core_spec(world: str) -> WorldSpec:
    seeds = {"successor": 31, "integer": 30, "clock": 57, "bits": 43, "strings": 22, "lists": 64}
    titles = {"successor": ("Successor", "后继", "number"), "integer": ("Integers", "整数", "number"),
              "clock": ("Clock", "时钟", "number"), "bits": ("Bits", "二进制位", "number"),
              "strings": ("Strings", "字符串", "text"), "lists": ("Lists", "列表", "structure")}
    domains = {
        "successor": (("Values are nonnegative integers. A negative input to an atom gives NaN.",
                       "取值是非负整数，原子遇到负数输入得 NaN。"),),
        "integer": (("Values are integers within ±2147483647; a result outside that bound is NaN.",
                     "取值是 ±2147483647 以内的整数，超出这个界的结果为 NaN。"),),
        "clock": (("Values are integers, and each atom result is reduced modulo 12, so results lie in 0 to 11.",
                   "取值是整数，每个原子结果都对 12 取模，所以结果落在 0 到 11。"),),
        "bits": (("Values are nonnegative integers read as bit patterns; the lamps show the lowest eight bits.",
                  "取值是看作二进制位的非负整数，灯显示最低 8 位。"),),
        "strings": (("Values are strings and integers. Strings may be empty; integers count characters and steps.",
                     "取值是字符串和整数。字符串可以为空，整数用来数字符和步数。"),),
        "lists": (("Values are lists of integers and integers. Lists may be empty; an index counts from zero.",
                   "取值是整数列表和整数。列表可以为空，下标从零数起。"),),
    }
    examples = {"successor": {"natural_succ": (4,), "natural_pred": (0,), "is_zero": (0,)},
                "integer": {"add": (7, 12), "sub": (5, 23), "mul": (-3, 7), "div": (-7, 2), "mod": (-7, 2),
                            "neg": (15,), "reverse": (120,), "triangle": (4,), "popcount": (13,),
                            "digitsum": (-123,)},
                "clock": {"add": (11, 3), "sub": (2, 5), "mul": (5, 7), "div": (23, 2), "mod": (14, 5),
                          "neg": (5,), "reverse": (19,), "triangle": (6,), "popcount": (7,), "digitsum": (58,)},
                "bits": {"bit_and": (12, 10), "bit_or": (12, 10), "bit_xor": (12, 10), "shift_left": (5, 2),
                         "shift_right": (44, 2), "bit_count": (13,)},
                "strings": {"add": (2, 5), "sub": (9, 4), "mod": (7, 3), "neg": (4,),
                            "str_concat": ("data", "base"), "str_length": ("hello",),
                            "str_reverse": ("Opulse",), "str_first": ("Tea",), "str_drop": ("Tea",),
                            "str_upper": ("xY",), "str_lower": ("ABc",), "str_equal": ("ab", "ab")},
                "lists": {"add": (2, 5), "sub": (9, 4), "mod": (7, 3), "neg": (4,),
                          "list_cons": (9, (2, 3)), "list_head": ((7, 8, 9),), "list_tail": ((7, 8, 9),),
                          "list_length": ((3, 1, 4),), "list_append": ((1, 2), (3,)), "list_sum": ((3, 1, 4),),
                          "list_at": ((10, 20, 30), 2), "list_equal": ((1, 2), (1, 2))}}
    title, title_zh, dimension = titles[world]
    seed = seeds[world]
    return WorldSpec(world, title, title_zh, dimension, build=lambda seed=seed: _grow(world, seed),
                     values=_pool(world), encode=encode, atom_zh=_INT_ZH, atom_examples=examples[world],
                     domain=domains[world],
                     settings=(_numeric_settings(world) if world in ("successor", "integer", "clock", "bits")
                               else _typed_settings(world)),
                     why=WHY, seed=seed, extra_inputs=_literal_inputs,
                     context=(lambda tools: {"modulus": tools.settings.semantics.modulus})
                     if world == "clock" else None)


def world_spec(world: str) -> WorldSpec:
    if world in ("successor", "integer", "clock", "bits", "strings", "lists"):
        return _core_spec(world)
    if world not in WORLD_IDS:
        raise ValueError(f"unknown world {world!r}")
    import importlib

    return importlib.import_module(f"opulse.worlds.{world}").showcase_spec()


def export_world_showcase(world_name: str, out_path: str | Path) -> dict:
    """Write one world's showcase data (see the module docstring)."""
    return export_spec(world_spec(world_name), out_path)
