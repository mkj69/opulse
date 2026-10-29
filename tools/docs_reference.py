"""Generate the CLI and configuration reference pages from the code.

    python tools/docs_reference.py

docs/reference/cli.md comes from the argparse definitions of every command and
docs/reference/configuration.md from the settings dataclasses (names, types
and defaults), so both pages always match the installed version.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import fields, is_dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from opulse.cli import main as cli_main
from opulse.config import Settings


def relative_default(value):
    """Represent path defaults from the repository root in generated pages."""
    if isinstance(value, Path):
        return Path(os.path.relpath(value, ROOT)) if value.is_absolute() else value
    if isinstance(value, list):
        return [relative_default(item) for item in value]
    if isinstance(value, tuple):
        return tuple(relative_default(item) for item in value)
    if isinstance(value, dict):
        return {key: relative_default(item) for key, item in value.items()}
    return value

DESCRIPTIONS = {
    "preset": "Selects a named world and its generation defaults, including the numeric, typed, and action presets.",
    "semantics.mode": "`exact`: overflow and division by zero give NaN. `legacy`: reproduce old datasets "
                      "(symmetric folding, zero divisor treated as 1). `modular`: reduce integer results modulo `semantics.modulus`.",
    "semantics.bound": "Largest absolute value B of a base-operation result. `null`: no bound (exact mode only).",
    "semantics.max_string_length": "Largest number of characters a registered string atom can return before its result becomes NaN.",
    "semantics.max_list_length": "Largest number of elements a registered list atom can return before its result becomes NaN.",
    "semantics.modulus": "Integer modulus of at least 2 in modular mode. `null` in other modes.",
    "symbols.left_operand": "Name of the first parameter in definitions.",
    "symbols.right_operand": "Name of the second parameter in definitions.",
    "symbols.operand_names": "All parameter names, in order; their number is the largest arity. Empty: "
                             "`left_operand`, `right_operand`, then `c d e f g h`. When set, its first two "
                             "names are the left and right operands.",
    "symbols.argument_separator": "Separates the arguments of an operator with three or more arguments, "
                                  "written in call form `⊕(a, b, c)`.",
    "symbols.left_paren": "Opening bracket.",
    "symbols.right_paren": "Closing bracket.",
    "symbols.equals": "Sign between the left-hand side and the body of a definition.",
    "symbols.nan": "Spelling of the undefined value.",
    "symbols.inf": "Spelling of positive infinity (legacy data only).",
    "symbols.neg_inf": "Spelling of negative infinity (legacy data only).",
    "numerals.max_base": "Largest numeral base used for random bases.",
    "numerals.digits": "Digit alphabet for numerals in bases above 10.",
    "operators.naming": "Generated name style. `shape_index` joins a shape and an index; `legacy` uses random symbol strings.",
    "operators.shape_sets": "Named shape sets used in `shape_index` mode: `shapes` and `suits`.",
    "operators.shape_chars": "Additional shape glyphs used in `shape_index` mode.",
    "operators.index_chars": "Ordered index alphabet. A zero first alphabet with ten characters writes decimal indices.",
    "operators.definition_layout": "`compact` uses one line. `piecewise` puts each branch on a line when long.",
    "operators.piecewise_min_length": "Minimum compact definition length for piecewise rendering.",
    "operators.definedness": "Adds the `defined` atom to the starting operator set so branch conditions can test whether a value is defined.",
    "operators.symbol_min_len": "Shortest generated operator symbol in `legacy` mode.",
    "operators.symbol_max_len": "Longest generated operator symbol in `legacy` mode.",
    "operators.symbol_sets": "Named character sets for `legacy` symbols; see the table below.",
    "operators.symbol_chars": "More characters for `legacy` symbols, listed directly, e.g. `\"♪♫\"`.",
    "operators.symbol_blocks": "Advanced `legacy` mode: raw Unicode ranges (`start-end`, hex), e.g. `2200-22FF`. "
                               "Symbols and non-ASCII letters are accepted.",
    "operators.symbol_ascii": "Extra ASCII characters allowed in `legacy` symbols.",
    "operators.exclude_confusable": "Drop legacy glyphs that look like ASCII arithmetic, comparisons or bars.",
    "operators.max_if_branches": "Most branches in a branch definition.",
    "operators.partial_probability": "Probability that a branch definition has no `else` "
                                     "(undefined outside its regions).",
    "operators.reject_dead_branches": "Reject definitions in which z3 proves a branch unreachable or always NaN.",
    "operators.reject_degenerate": "Reject subexpressions that use a parameter yet take one value wherever "
                                   "defined, such as `a - a` or `a % a` (proved with z3).",
    "operators.min_defined_share": "Total definitions must be defined on at least this share of inputs from "
                                   "the expression value range (0 disables).",
    "operators.undefined_branch_check": "Also reject branches whose body z3 proves always NaN (costlier; "
                                        "consider turning it off for very large runs).",
    "operators.dead_branch_budget": "Deterministic effort of that check (encoding nodes; z3 gets a proportional "
                                    "resource limit). Undecided branches are accepted.",
    "operators.degenerate_budget": "Deterministic effort of the degenerate subexpression check (encoding nodes; "
                                   "z3 gets a proportional resource limit). Undecided suspects are accepted.",
    "operators.safety_timeout_ms": "Wall clock safety limit per solver check during generation. Reaching it stops "
                                   "the run with an error; it never decides a check. Raise it on slow machines.",
    "operators.arity_weights": "Relative number of new operators per arity, e.g. `{1: 0.25, 2: 0.5, 3: 0.25}`; "
                               "unary operators are prefix or postfix with equal chance, arity 3 and more is "
                               "written in call form. The default draws exactly as before (no call-form "
                               "operators).",
    "operators.allow_simple": "Permits generated definitions with one unconditional body.",
    "operators.allow_branches": "Permits generated definitions with conditional branches.",
    "operators.max_substitution_depth": "Limits the depth of sampled simple and branch bodies; `null` uses `expressions.max_depth`.",
    "operators.max_arity": "Limits generated operator arity; `null` retains every arity with a positive weight in `operators.arity_weights`.",
    "operators.max_condition_comparisons": "Limits comparisons in each branch condition; `null` uses the default region sampler.",
    "operators.condition_atoms": "Names unary or binary starting atoms applied to parameters in branch conditions; an empty list uses the parameters directly.",
    "operators.condition_min": "Smallest threshold in branch conditions.",
    "operators.condition_max": "Largest threshold in branch conditions.",
    "recursion.style": "Selects the `bounded_mod`, `direct`, `peano`, `bits`, or `primitive` recursion template when `recursion.styles` is `null`.",
    "recursion.enabled": "Permits recursive definitions and generated layers above zero.",
    "recursion.styles": "Samples recursive definitions from these templates; `null` uses `recursion.style`.",
    "recursion.max_recursive_calls": "Sets the maximum number of recursive result slots in a binary callee to one or two.",
    "recursion.modulus_min": "Smallest modulus m of `bounded_mod` (unfolds at most m - 1 times).",
    "recursion.modulus_max": "Largest modulus m of `bounded_mod`.",
    "recursion.direct_bound": "Largest absolute control value allowed by `direct`, `peano`, `bits`, and `primitive` recursive definitions.",
    "recursion.search_enabled": "Allows simple definitions to search for the first index equal to a sampled expression.",
    "recursion.search_bound": "Largest index examined by generated bounded searches, from zero through at most 32.",
    "recursion.constant_min": "Smallest constant in the base case.",
    "recursion.constant_max": "Largest constant in the base case.",
    "recursion.step_down": "Symbol of the postfix predecessor atom used for decreasing `peano` recursion.",
    "recursion.step_up": "Symbol of the postfix successor atom used for increasing `peano` recursion.",
    "recursion.nonnegative": "Omits the negative input branch from generated `bounded_mod`, `direct`, `peano`, and `bits` recursive definitions.",
    "expressions.variables": "Variable names used in sampled expressions with variables.",
    "expressions.value_min": "Smallest sampled number.",
    "expressions.value_max": "Largest sampled number.",
    "expressions.max_depth": "Largest expression depth.",
    "expressions.type_weights": "Relative weights of binary, prefix, postfix applications and atoms; an "
                                "optional `call` weight for operators with three or more arguments (default: "
                                "the `binary` weight).",
    "expressions.atom_weights": "Relative weights of variables and numbers among atoms.",
    "expressions.numeral_base": "Base of numerals in expressions.",
    "expressions.random_numeral_base": "Draw a random base (2..max_base) for every numeral.",
    "expressions.result_base": "Base in which results are written.",
    "expressions.random_result_base": "Draw a random base for every result.",
    "expressions.cot_base": "Base of numbers in evaluation steps.",
    "solver.fallback_range": "Inclusive integer input range checked by the reference interpreter when a solver analysis cannot encode an operator.",
    "solver.rlimit": "Deterministic z3 resource limit per solver question; a question it cannot decide within the "
                     "limit is reported as unknown, the same way on every machine.",
    "solver.max_nodes": "Largest formula, in encoding nodes, that the z3 encoder builds before giving up on a question.",
    "interest.dedup": "Reject a candidate whose value table on the probe grid equals an existing operator's, "
                      "also after permuting arguments or negating arguments or the result.",
    "interest.selection": "`off`, `best` or `sample`: draw `pool` accepted candidates per operator and keep "
                          "the highest scoring one, or one drawn with weight exp(score / temperature).",
    "interest.pool": "Accepted candidates drawn per operator when `selection` is on.",
    "interest.temperature": "Temperature of `selection: sample`.",
    "interest.weights": "Weights of the score components `novelty`, `regularity`, `reuse`, "
                        "`non_degeneracy` and `compression`; unnamed components keep weight 1.",
    "interest.probe_ints": "Integer probe values, closed under negation; the probe grid is their product "
                           "over the integer arguments.",
    "interest.max_probe_points": "Largest probe grid; high arities use fewer, evenly spread values.",
    "interest.regularity_range": "Monotonicity, periodicity and fixed points are read on [-R, R] "
                                 "(monotonicity also on the probe values).",
    "interest.max_period": "Largest period looked for.",
    "interest.solver_timeout_ms": "z3 time limit per question when `opulse interest --solver` confirms "
                                  "regularities.",
}


EXPRESSIVENESS_SWITCHES = """## Expressiveness switches

These settings control numeric definitions written by `opulse operators`. A CLI flag with the same meaning overrides its YAML key for that run. The default values keep the existing generation behavior.

| Form | YAML key | CLI flag | Default | Effect |
| --- | --- | --- | --- | --- |
| Simple definitions | `operators.allow_simple` | `--no-simple` | `true` | Permit definitions with one unconditional body. |
| Substitution | `operators.max_substitution_depth` | `--max-substitution-depth` | `null` | Maximum depth of sampled simple or branch bodies. `null` uses `expressions.max_depth`. |
| Branch definitions | `operators.allow_branches` | `--no-branches` | `true` | Permit conditional definitions. |
| Branch count | `operators.max_if_branches` | `--max-if-branches` | `10` | Maximum bodies in one branch definition. |
| Condition complexity | `operators.max_condition_comparisons` | `--max-condition-comparisons` | `null` | Maximum comparisons in each condition of a branch definition. `null` keeps the original region sampling. |
| Condition thresholds | `operators.condition_min`, `operators.condition_max` | config only | `0`, `100` | Inclusive range of thresholds in branch conditions. |
| Condition atoms | `operators.condition_atoms` | `--condition-atoms` | `[]` | Atom names allowed in branch conditions. An empty list uses raw parameters. Each named atom must be in the starting set. Binary atoms receive the parameter and the constant 2. |
| Arity | `operators.max_arity` | `--max-arity` | `null` | Largest arity of a generated operator. `null` keeps every arity that `operators.arity_weights` gives a positive weight. |
| Recursion | `recursion.enabled` | `--no-recursion` | `true` | Permit recursive definitions and layers above zero. |
| Recursion template | `recursion.style` | `--recursion-style` | `bounded_mod` | Template used when `recursion.styles` is `null`. |
| Recursion templates | `recursion.styles` | `--recursion-styles` | `null` | List of templates sampled for recursive definitions: `bounded_mod`, `direct`, `peano`, `bits`, `primitive`. |
| Recursion calls | `recursion.max_recursive_calls` | `--max-recursive-calls` | `2` | Maximum recursive result slots in a binary callee of a generated recursive definition. |
| Remainder bound | `recursion.modulus_min`, `recursion.modulus_max` | `--recursion-modulus-min`, `--recursion-modulus-max` | `3`, `9` | Inclusive modulus range for `bounded_mod`; unfolding is at most modulus minus 1. |
| Direct bound | `recursion.direct_bound` | `--recursion-direct-bound` | `8` | Maximum unfolding depth for `direct`, `peano`, `bits`, and `primitive`. |

```yaml
operators:
  allow_branches: false
  max_substitution_depth: 1
recursion:
  enabled: false
```

This example generates simple definitions with bodies sampled at depth one and keeps all generated operators on layer zero.
"""


def cli_page() -> str:
    parser = argparse.ArgumentParser(prog="opulse")
    parser.add_argument("-v", "--verbose", action="store_true", help="show debug logs")
    parser.add_argument("--plugin", action="append", default=[], metavar="MODULE",
                        help="import a module that registers atoms; repeatable")
    commands = parser.add_subparsers(dest="command", required=True)
    modules = [m for m in vars(cli_main).values() if hasattr(m, "register") and m.__name__.startswith("opulse.cli.")]
    for module in modules:
        module.register(commands)
    lines = ["# Command line reference", "",
             "Generated from the command definitions by `tools/docs_reference.py`.", "",
             "Every command is run as `opulse <command> [options]`. Commands that read settings take",
             "`--config` (default `configs/default.yaml`).", ""]
    lines += ["## Global options", "", "```text", parser.format_help().rstrip(), "```", ""]
    lines += ["| Command | Purpose |", "| --- | --- |"]
    for name, sub in commands.choices.items():
        help_text = next((a.help for a in commands._choices_actions if a.dest == name), "")
        lines.append(f"| [`{name}`](#{name}) | {help_text} |")
    for name, sub in commands.choices.items():
        lines += ["", f"## {name}", "", "```text", sub.format_help().replace("usage: opulse", "opulse").rstrip(),
                  "```"]
        for action in sub._actions:  # nested commands, e.g. `opulse bench build`
            if isinstance(action, argparse._SubParsersAction):
                for child_name, child in action.choices.items():
                    lines += ["", f"### {name} {child_name}", "", "```text",
                              child.format_help().replace("usage: opulse", "opulse").rstrip(), "```"]
    return "\n".join(lines) + "\n"


def config_page() -> str:
    defaults = Settings()
    keys = [f"{section.name}.{item.name}" if is_dataclass(getattr(defaults, section.name))
            else section.name
            for section in fields(Settings)
            for item in (fields(getattr(defaults, section.name))
                         if is_dataclass(getattr(defaults, section.name)) else (None,))]
    missing = [key for key in keys if not isinstance(DESCRIPTIONS.get(key), str)
               or not DESCRIPTIONS[key].strip()]
    if missing:
        raise ValueError(f"describe these settings in DESCRIPTIONS: {', '.join(missing)}")
    lines = ["# Configuration reference", "",
             "Generated from `opulse.config` by `tools/docs_reference.py`. A configuration is one YAML file;",
             "every key is optional and omitted keys take the defaults below.", "",
             "```yaml", (ROOT / "configs" / "default.yaml").read_text(encoding="utf-8").rstrip(), "```", ""]
    for section in fields(Settings):
        lines += [f"## `{section.name}`", "", "| Key | Type | Default | Meaning |", "| --- | --- | --- | --- |"]
        value = getattr(defaults, section.name)
        if not is_dataclass(value):
            kind = str(section.type).replace("|", "\\|")
            lines += [f"| `{section.name}` | `{kind}` | `{relative_default(value)!r}` | {DESCRIPTIONS.get(section.name, '')} |", ""]
            continue
        for item in fields(value):
            default = getattr(value, item.name)
            if isinstance(default, tuple):
                default = list(default)
            kind = str(item.type).replace("|", "\\|")
            meaning = DESCRIPTIONS.get(f"{section.name}.{item.name}", "")
            lines.append(f"| `{item.name}` | `{kind}` | `{relative_default(default)!r}` | {meaning} |")
        lines.append("")
        if section.name == "operators":
            from opulse.generation.symbols import NAMED_SETS

            lines += ["### Named symbol sets", "", "| Name | Characters |", "| --- | --- |"]
            lines += [f"| `{name}` | {' '.join(chars)} |" for name, chars in NAMED_SETS.items()]
            lines.append("")
    return "\n".join(lines) + "\n" + EXPRESSIVENESS_SWITCHES


def chinese_cli_page(previous: str) -> str:
    """Refresh command coverage and defaults while retaining translated descriptions."""
    descriptions = {}
    purposes = {}
    heading = None
    for line in previous.splitlines():
        if line.startswith(("## ", "### ")):
            heading = line.split(" ", 1)[1].split(" { #", 1)[0].strip("`")
        elif heading and line.startswith("| `-"):
            cells = line.strip("| ").split(" | ")
            descriptions[(heading, cells[0])] = cells[-1]
        elif line.startswith("| [`"):
            match = re.match(r"\| \[`([^`]+)`\]\([^)]+\) \| (.*) \|", line)
            if match:
                purposes[match[1]] = match[2]

    parser = argparse.ArgumentParser(prog="opulse")
    parser.add_argument("-v", "--verbose", action="store_true", help="show debug logs")
    parser.add_argument("--plugin", action="append", default=[], metavar="MODULE",
                        help="import a module that registers atoms; repeatable")
    commands = parser.add_subparsers(dest="command")
    modules = [m for m in vars(cli_main).values() if hasattr(m, "register") and m.__name__.startswith("opulse.cli.")]
    for module in modules:
        module.register(commands)

    lines = ["# 命令行参考", "", "命令格式为 `opulse <命令> [参数]`。需要配置的命令使用 `--config` 读取 YAML 文件。", "",
             "## 全局参数", "", "| 参数 | 说明 |", "| --- | --- |",
             "| `-h`, `--help` | 显示帮助。 |",
             "| `-v`, `--verbose` | 显示调试日志。 |",
             "| `--plugin MODULE` | 导入注册原子操作的模块，可重复使用。 |", ""]
    lines += ["| 命令 | 用途 |", "| --- | --- |"]
    for name in commands.choices:
        purpose = purposes.get(name, next((a.help for a in commands._choices_actions if a.dest == name), ""))
        lines.append(f"| [`{name}`](#{name}) | {purpose} |")

    def section(name, sub, level):
        lines.extend(["", f"{'#' * level} {name}", "", "| 参数 | 默认值 | 说明 |", "| --- | --- | --- |"])
        for action in sub._actions:
            if not action.option_strings:
                continue
            option = ", ".join(f"`{value}`" for value in action.option_strings)
            default = str(relative_default(action.default)) if isinstance(action.default, Path) else relative_default(action.default)
            meaning = descriptions.get((name, option), action.help or "参见命令帮助。")
            lines.append(f"| {option} | `{default!r}` | {meaning} |")
        for action in sub._actions:
            if isinstance(action, argparse._SubParsersAction):
                for child_name, child in action.choices.items():
                    section(f"{name} {child_name}", child, 3)

    for name, sub in commands.choices.items():
        section(name, sub, 2)
    return "\n".join(lines) + "\n"


def chinese_config_page(english: str, previous: str) -> str:
    """Keep translated setting meanings aligned with generated keys and defaults."""
    meanings = {}
    section = None
    for line in previous.splitlines():
        match = re.match(r"## `([^`]+)`", line)
        if match:
            section = match[1]
        elif section and line.startswith("| `"):
            cells = line.strip("| ").split(" | ")
            if len(cells) >= 4:
                meanings[(section, cells[0])] = cells[3]

    lines = []
    section = None
    for line in english.splitlines():
        match = re.match(r"## `([^`]+)`", line)
        if match:
            section = match[1]
        if section and line.startswith("| `"):
            cells = line.strip("| ").split(" | ")
            if len(cells) >= 4:
                meaning = meanings.get((section, cells[0]), cells[3])
                line = "| " + " | ".join([*cells[:3], meaning]) + " |"
        lines.append(line)
    lines[0] = "# 配置参考"
    return "\n".join(lines) + "\n"


def main() -> int:
    cli = cli_page()
    configuration = config_page()
    out = ROOT / "docs" / "reference"
    out.mkdir(parents=True, exist_ok=True)
    (out / "cli.md").write_text(cli, encoding="utf-8")
    (out / "configuration.md").write_text(configuration, encoding="utf-8")
    zh = ROOT / "docs_zh" / "reference"
    if zh.parent.is_dir():
        zh.mkdir(parents=True, exist_ok=True)
        previous_cli = (zh / "cli.md").read_text(encoding="utf-8") if (zh / "cli.md").exists() else ""
        previous_config = ((zh / "configuration.md").read_text(encoding="utf-8")
                           if (zh / "configuration.md").exists() else "")
        (zh / "cli.md").write_text(chinese_cli_page(previous_cli), encoding="utf-8")
        (zh / "configuration.md").write_text(
            chinese_config_page(configuration, previous_config), encoding="utf-8")
    print("wrote CLI and configuration references")
    return 0


if __name__ == "__main__":
    sys.exit(main())
