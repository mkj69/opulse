"""Evaluate hand-written definitions and one expression, for the documentation playground.

The playground page (docs/guide/playground.md) runs this module in the browser under Pyodide.
It only connects existing parts of the library: the definition parser, the code generator and
:class:`~opulse.runtime.PythonRuntime`, the reference interpreter (:class:`~opulse.verify.Oracle`),
the step-by-step :class:`~opulse.trace.Reducer` and :func:`~opulse.analysis.graph.dependency_graph`.
Its import closure is the standard library plus those modules; ``tools/build_playground.py``
packages exactly that closure and a test checks the package against ``src/``.

Input format:

* ``definitions``: one definition per line, for example ``a ⊕ b = { (a * a) + b }``. A
  definition may continue on following lines until its braces close. Lines starting with ``//``
  are comments. Definitions may appear in any order; an operator may call itself, but two
  operators may not call each other in a cycle.
* ``expression``: one closed expression over the built-in atoms and the defined operators,
  written in the definition grammar (all binary operators share one level and group to the left).

:func:`run` returns a JSON-compatible dict: the value with its counts, every reduction step with
the focused subexpression located in the rendered text, the branch chosen at each unfolding and
why, the cause of every NaN, and the dependency graph of the operators involved.

The page also configures the world the definitions live in. :func:`atom_table` lists the atoms
of a starting set with a validation message per row (switched off, new symbol, edited rule,
custom Python atoms); :func:`setting_values` and :func:`settings_for` read the config settings
the page exposes; :func:`grow` grows an operator set with the CLI's generation pipeline, its z3
checks off; :func:`export` writes the config file, plugin module and commands that rebuild the
same world with ``opulse operators``.
"""

from __future__ import annotations

import ast as python_ast
import importlib
import inspect
import itertools
import json
import re
from dataclasses import dataclass

from opulse.analysis.graph import dependency_graph, topological_layers
from opulse.config import Symbols
from opulse.core.operator import BINARY, BRANCH, PREFIX, RECURSIVE, SIMPLE, Operator
from opulse.core.primitives import (
    BUILT_IN_RULES,
    CUSTOM,
    atom_records,
    register_primitive,
    rule_for,
    unregister_primitive,
)
from opulse.core.registry import OperatorRegistry
from opulse.core.semantics import NAN, Semantics, base_operation_name
from opulse.core.types import literal, same_value
from opulse.definition import ast
from opulse.definition.ast import render_condition, render_definition
from opulse.definition.codegen import compile_definition, registry_resolver
from opulse.definition.interpreter import COMPARISONS, EngineError
from opulse.definition.parser import DefinitionParser
from opulse.definition.syntax import (
    BINARY_ROLE,
    Notation,
    SyntaxProblem,
    _Parser,
    parse_definition,
    parse_expression,
    tokenize,
)
from opulse.expression.nodes import (
    Call,
    Node,
    Number,
    from_ast,
    has_variable,
    literal_form,
)
from opulse.expression.render import ExpressionRenderer
from opulse.runtime import PythonRuntime
from opulse.trace.reducer import Reducer, _substitute_condition
from opulse.verify import Oracle

MAX_STEPS = 600  # reduction steps computed; a longer trace is reported as truncated
MAX_DEPTH = 100  # nested calls the reference interpreter follows before it stops
MAX_STEP_TEXT = 300_000  # characters of rendered steps returned; later steps are counted only

KIND_ATOM = "atom"
_KINDS = {SIMPLE: "simple", BRANCH: "branch", RECURSIVE: "recursive"}


class PlaygroundError(ValueError):
    """A problem in the user's input, with the place it was found."""

    def __init__(self, message: str, where: str, line: int | None = None, column: int = 0,
                 length: int = 1) -> None:
        super().__init__(message)
        self.message = message
        self.where = where  # "definitions" | "expression" | "atoms"
        self.line = line  # 1-based line in the definitions text
        self.column = column  # 0-based column on that line (or in the expression)
        self.length = max(1, length)

    def to_dict(self) -> dict:
        return {"message": self.message, "where": self.where, "line": self.line,
                "column": self.column, "length": self.length}


# ------------------------------------------------------------------------------- atoms
#
# One playground world is: a starting atom set (a named world), atoms switched off, atoms with a
# new symbol or rule text, custom atoms written as Python functions, and the settings that the
# CLI reads from a config file. ``config`` holds everything except the world and custom atoms:
#
#     {"off": ["mul"], "symbols": {"add": "⊞"}, "rules": {"add": "a ⊞ b is a + b."},
#      "settings": {"semantics": {"bound": 1000}, "recursion": {"direct_bound": 5}}}
#
# Registration changes module state (CUSTOM and BASE_OPERATIONS). Each call of
# :func:`prepare_atoms` first undoes what the previous call changed, so a page state never sees
# the atoms or symbols of an earlier one.

# Characters the definition grammar uses for itself; an atom symbol may not contain them.
SYNTAX_CHARS = "(){}[];,=<>!_\"'"
# Atoms whose symbol other parts of the library write directly (a negative number is "- n").
FIXED_SYMBOLS = {"neg": "negative numbers are written with it"}
# The settings a playground world exposes, by config section; every other key keeps its default.
SETTING_KEYS = {
    "semantics": ("mode", "bound", "max_string_length", "max_list_length"),
    "recursion": ("enabled", "style", "direct_bound", "modulus_min", "modulus_max"),
    "operators": ("naming", "shape_sets", "shape_chars", "index_chars"),
}
# Generation in the browser has no z3, so it skips the two solver checks. The exported config
# writes the same switches, so the CLI grows the same set from the same seed.
BROWSER_GENERATION = {"reject_dead_branches": False, "reject_degenerate": False}
TYPED_WORLDS = ("strings", "lists")
# Generation defaults of starting sets that are not presets: the atomic set has no + - %, so its
# recursion steps with ⁻ and ⁺ (the peano template).
DOMAIN_SETTINGS = {"atomic": {"recursion": {"style": "peano"}}}
MAX_GROWN = 40  # operators one Grow request may add

_PLAYGROUND_CUSTOM: set[str] = set()
_RENAMED: list[tuple[str, object]] = []  # (atom, its CUSTOM entry before the rename)
_SAVED_BASE: dict = {}  # BASE_OPERATIONS before the first rename


def atom_registry(names=None) -> OperatorRegistry:
    """The selected atoms as base operators; the default retains all shipped atoms."""
    return OperatorRegistry(Operator.from_dict(row) for row in atom_records(names or BUILT_IN_RULES))


def available_worlds() -> list[str]:
    """Starting atom sets available to the browser package."""
    from opulse.core.presets import PRESETS as typed
    from opulse.core.semantics import DOMAINS
    from opulse.presets import PRESETS as numeric
    names = list(dict.fromkeys((*numeric, *DOMAINS, *typed)))
    try:
        importlib.import_module("opulse.worlds.action")
    except ModuleNotFoundError:
        pass
    else:
        names.append("action")
    return names


def _world_atoms(world: str | None) -> list[str]:
    if world is None or world == "":
        return list(BUILT_IN_RULES)
    from opulse.core.presets import PRESETS as typed
    from opulse.core.presets import register_preset as register_typed
    from opulse.core.semantics import DOMAINS
    from opulse.presets import PRESETS as numeric
    from opulse.presets import register_preset as register_numeric
    if world in numeric:
        register_numeric(world)
        return list(numeric[world]["atoms"])
    if world in DOMAINS:
        return list(DOMAINS[world])
    if world in typed:
        register_typed(world)
        return list(typed[world])
    if world == "action":
        try:
            module = importlib.import_module("opulse.worlds.action")
        except ModuleNotFoundError:
            raise PlaygroundError("World 'action' is unavailable in this package.", "atoms") from None
        return list(module.register_action_atoms())
    raise PlaygroundError(f"World {world!r} is unavailable in this package.", "atoms")


def parse_types(text, arity: int) -> tuple[tuple[str, ...], str]:
    """``"str, int -> str"`` as (parameter types, result type); an empty text means integers."""
    from opulse.core.types import parse_type

    text = str(text or "").strip().replace("→", "->")
    if not text:
        return ("int",) * arity, "int"
    if "->" not in text:
        raise ValueError("write the types as inputs -> result, for example str, int -> str")
    inputs, result = (part.strip() for part in text.rsplit("->", 1))
    parameters = tuple(part.strip() for part in re.split(r",(?![^\[]*\])", inputs) if part.strip())
    if len(parameters) != arity:
        raise ValueError(f"the types name {len(parameters)} inputs, but the arity is {arity}")
    for kind in (*parameters, result):
        try:
            parse_type(kind)
        except ValueError:
            raise ValueError(f"unknown type {kind!r}; use int, bool, str or list[int]") from None
    return parameters, result


def _compile_atom(spec: dict, index: int):
    code = str(spec.get("code", ""))
    try:
        tree = python_ast.parse(code)
    except SyntaxError as exc:
        raise PlaygroundError(f"Atom {index}: {exc.msg}.", "atoms", index, (exc.offset or 1) - 1) from None
    if len(tree.body) != 1 or not isinstance(tree.body[0], python_ast.FunctionDef):
        raise PlaygroundError(f"Atom {index}: write one Python function definition.", "atoms", index)
    name = tree.body[0].name
    if name != spec.get("name"):
        raise PlaygroundError(f"Atom {index}: the function name must be {spec.get('name')!r}.", "atoms", index)
    try:
        arity = int(spec.get("arity", 1))
    except (TypeError, ValueError):
        raise PlaygroundError(f"Atom {index}: arity must be 1 or 2.", "atoms", index) from None
    if arity not in (1, 2):
        raise PlaygroundError(f"Atom {index}: arity must be 1 or 2.", "atoms", index)
    try:
        namespace = {}
        exec(compile(tree, f"<playground atom {index}>", "exec"), namespace)  # noqa: S102
        function = namespace[name]
        inspect.signature(function).bind(*([0] * arity))
        if len(inspect.signature(function).parameters) != arity:
            raise TypeError("the function parameters must match its arity")
    except (TypeError, ValueError, NameError) as exc:
        raise PlaygroundError(f"Atom {index}: {exc}", "atoms", index) from None
    return function, arity


def _restore() -> None:
    """Undo the renames and custom atoms of the previous playground state."""
    from opulse.core.semantics import BASE_OPERATIONS

    if _RENAMED:
        BASE_OPERATIONS.clear()
        BASE_OPERATIONS.update(_SAVED_BASE)
        for name, entry in _RENAMED:
            if entry is not None:
                CUSTOM[name] = entry
        _RENAMED.clear()
        _SAVED_BASE.clear()
    for name in _PLAYGROUND_CUSTOM:
        unregister_primitive(name)
    _PLAYGROUND_CUSTOM.clear()


def _key_of(name: str) -> tuple:
    from opulse.core.semantics import BASE_OPERATIONS

    return next(key for key, owner in BASE_OPERATIONS.items() if owner == name)


def _rename(name: str, symbol: str) -> None:
    from dataclasses import replace

    from opulse.core.semantics import BASE_OPERATIONS

    key = _key_of(name)
    if not _RENAMED:  # a new symbol may displace an atom of another world loaded earlier
        _SAVED_BASE.update(BASE_OPERATIONS)
    _RENAMED.append((name, CUSTOM.get(name)))
    del BASE_OPERATIONS[key]
    BASE_OPERATIONS[(symbol, key[1], key[2])] = name
    if name in CUSTOM:
        CUSTOM[name] = replace(CUSTOM[name], symbol=symbol)


def _role(n_ary: int, position) -> str:
    return BINARY_ROLE if n_ary == BINARY else (position if n_ary == 1 else "call")


def symbol_problem(symbol: str, n_ary: int, position, others, index_chars: str = "") -> str | None:
    """Why ``symbol`` cannot name an atom next to ``others``, or None.

    ``others`` lists (name, symbol, n_ary, position) of the other atoms that are on. A symbol may
    not contain spaces, digits (a digit would read as a number) or the grammar's own characters,
    may not be a keyword or variable, may not repeat another atom's symbol in the same role, and
    must keep the whole alphabet uniquely decodable, so that a run of symbols splits one way.
    """
    from opulse.core.primitives import _uniquely_decodable
    from opulse.definition.syntax import KEYWORDS, role_of

    if not symbol:
        return "Write a symbol."
    if any(char.isspace() for char in symbol):
        return "A symbol has no spaces."
    if any(char.isdigit() or char.isnumeric() for char in symbol):
        return "A symbol has no digits; 1, ³ and ₂ all read as digits."
    reserved = [char for char in dict.fromkeys(symbol) if char in SYNTAX_CHARS]
    if reserved:
        return f"A symbol may not contain {' '.join(reserved)}; the grammar uses these characters."
    clash = [char for char in dict.fromkeys(symbol) if char in index_chars]
    if clash:
        return (f"{''.join(clash)} is an index character of generated operator names "
                "(operators.index_chars).")
    if symbol in KEYWORDS or symbol in ("a", "b", "NaN", "true", "false"):
        return f"{symbol} is a keyword or variable of the definition grammar."
    role = _role(n_ary, position)
    for name, other, other_n, other_position in others:
        if other == symbol and _role(other_n, other_position) == role:
            return f"{symbol} is already the symbol of {name}."
    notation = Notation(Symbols())
    notation.roles = {}
    for _, other, other_n, other_position in others:
        notation.roles.setdefault(other, set()).add(role_of(other_n, other_position))
    notation.roles.setdefault(symbol, set()).add(role_of(n_ary, position))
    try:
        notation.check_symbol(symbol)
        tokens = tokenize(symbol, notation, allow_unknown=False)
    except ValueError as exc:
        if "more than one way" in str(exc):
            return f"{symbol} makes adjacent symbols ambiguous: it also reads as a run of other symbols."
        return f"{symbol} cannot be read as one operator: {_friendly(str(exc))}"
    if len(tokens) != 2 or tokens[0].kind != "op" or tokens[0].text != symbol:
        return f"{symbol} cannot be read as one operator."
    alphabet = {other for _, other, _, _ in others}
    if not _uniquely_decodable(alphabet | {symbol}):
        partner = next((other for other in sorted(alphabet) if not _uniquely_decodable({other, symbol})), None)
        return (f"{symbol} makes adjacent symbols ambiguous" +
                (f" with {partner}." if partner else ".") + " Choose a symbol that no other symbol starts or ends with.")
    return None


def _rule_text(name: str, overrides: dict) -> str:
    return overrides.get(name) or rule_for(name)


def _settings_index(config: dict | None) -> str:
    operators = ((config or {}).get("settings") or {}).get("operators") or {}
    return str(operators.get("index_chars", "₀₁₂₃₄₅₆₇₈₉"))


def _custom_row(spec, index: int) -> tuple[dict, str | None]:
    """A custom atom's table row, and the reason it cannot be registered (or None)."""
    spec = spec if isinstance(spec, dict) else {}
    try:
        arity = int(spec.get("arity", 1))
    except (TypeError, ValueError):
        arity = 1
    position = spec.get("position", "postfix") if arity == 1 else None
    row = {"name": str(spec.get("name", "")), "symbol": str(spec.get("symbol", "")), "n_ary": arity,
           "position": position, "rule": str(spec.get("rule", "")), "source": "custom", "custom": index - 1}
    problem = None
    try:
        parameters, result = parse_types(spec.get("types", ""), arity)
        row["types"] = _types_text(parameters, result)
    except ValueError as exc:
        row["types"] = str(spec.get("types", ""))
        problem = f"Types: {exc}."
    if problem is None and not row["name"].isidentifier():
        problem = "The name must be a Python identifier, for example cube."
    if problem is None and not row["rule"].strip():
        problem = "Write a rule: one sentence that says how to compute the atom."
    if problem is None:
        try:
            _compile_atom(spec, index)
        except PlaygroundError as exc:
            problem = exc.message.split(": ", 1)[-1]
    return row, problem


def _types_text(parameters, result) -> str:
    return f"{', '.join(parameters)} → {result}"


def atom_table(world: str | None = None, custom_atoms: list | None = None, config: dict | None = None) -> list[dict]:
    """Every atom of a playground world with its current symbol, rule and validation message.

    Rows: name, symbol, default_symbol, n_ary, shape, types, rule, default_rule, on, source
    ("built in", "world" or "custom"), custom (index into ``custom_atoms`` or None) and error.
    Registering nothing permanently: the state before the call is restored afterwards.
    """
    config = config or {}
    off = set(config.get("off") or ())
    symbols = dict(config.get("symbols") or {})
    rules = dict(config.get("rules") or {})
    index_chars = _settings_index(config)
    _restore()
    rows: list[dict] = []
    for name in _world_atoms(world):
        symbol, n_ary, position = _key_of(name)
        primitive = CUSTOM.get(name)
        types = _types_text(primitive.parameter_types, primitive.result_type) if primitive else \
            _types_text(("int",) * n_ary, "int")
        rows.append({"name": name, "symbol": symbols.get(name, symbol), "default_symbol": symbol,
                     "n_ary": n_ary, "position": position, "types": types,
                     "rule": _rule_text(name, rules), "default_rule": rule_for(name), "on": name not in off,
                     "source": "built in" if name in BUILT_IN_RULES else "world", "custom": None, "error": None})
    known = {row["name"] for row in rows} | set(BUILT_IN_RULES) | set(CUSTOM)
    for index, spec in enumerate(custom_atoms or [], start=1):
        row, problem = _custom_row(spec, index)
        if problem is None and row["name"] in known:
            problem = f"The name {row['name']} is already used by another atom."
        known.add(row["name"])
        row.update(default_symbol=row["symbol"], default_rule=row["rule"], on=row["name"] not in off,
                   error=problem)
        rows.append(row)
    for row in rows:
        row["shape"] = "binary" if row["n_ary"] == BINARY else (row["position"] if row["n_ary"] == 1 else "call")
        fixed = FIXED_SYMBOLS.get(row["name"])
        if fixed and row["symbol"] != row["default_symbol"]:
            row["error"] = f"The symbol of {row['name']} cannot change: {fixed}."
        if row["error"] or not row["on"]:
            continue
        # A world atom is checked against the world; a custom atom against everything, so that a
        # clash between the two is reported on the custom row.
        others = [(o["name"], o["symbol"], o["n_ary"], o["position"]) for o in rows
                  if o is not row and o["on"] and not (o["source"] == "custom" and (o["error"] or row["custom"] is None))]
        row["error"] = symbol_problem(row["symbol"], row["n_ary"], row["position"], others, index_chars)
        if row["error"] is None and row["custom"] is not None:
            row["error"] = _loaded_clash(row, {o["name"] for o in rows})
    return rows


def _loaded_clash(row: dict, names: set) -> str | None:
    """An atom of another world loaded earlier in this page that already owns the symbol."""
    from opulse.core.semantics import BASE_OPERATIONS

    key = (row["symbol"], row["n_ary"], row["position"] if row["n_ary"] == 1 else None)
    owner = BASE_OPERATIONS.get(key)
    if owner is not None and owner not in names:
        return f"{row['symbol']} already denotes the atom {owner} of another world; choose another symbol."
    return None


def prepare_atoms(world: str | None = None, custom_atoms: list[dict] | None = None,
                  config: dict | None = None) -> list[str]:
    """Register the atoms of one playground state and return the names of those that are on."""
    rows = atom_table(world, custom_atoms, config)
    bad = next((row for row in rows if row["on"] and row["error"]), None)
    if bad is not None:
        line = bad["custom"] + 1 if bad["custom"] is not None else None
        raise PlaygroundError(f"Atom {bad['name'] or line}: {bad['error']}", "atoms", line)
    for row in rows:
        if row["custom"] is None or not row["on"]:
            continue
        spec = custom_atoms[row["custom"]]
        function, arity = _compile_atom(spec, row["custom"] + 1)
        parameters, result = parse_types(spec.get("types", ""), arity)
        try:
            register_primitive(row["name"], row["symbol"], function, rule=row["rule"], n_ary=arity,
                               position=row["position"], parameter_types=parameters, result_type=result)
        except ValueError as exc:
            raise PlaygroundError(f"Atom {row['custom'] + 1}: {exc}", "atoms", row["custom"] + 1) from None
        _PLAYGROUND_CUSTOM.add(row["name"])
    for row in rows:
        if row["custom"] is None and row["on"] and row["symbol"] != row["default_symbol"]:
            _rename(row["name"], row["symbol"])
    return [row["name"] for row in rows if row["on"]]


def atoms(world: str | None = None, custom_atoms: list[dict] | None = None, config: dict | None = None) -> list[dict]:
    """Symbol, shape and rule of atoms active in one playground state."""
    names = prepare_atoms(world, custom_atoms, config)
    rules = dict((config or {}).get("rules") or {})
    rows = []
    for operator in atom_registry(names):
        name = base_operation_name(operator.symbol, operator.n_ary, operator.unary_position)
        rows.append({"name": name, "symbol": operator.symbol, "shape": _shape(operator),
                     "rule": _rule_text(name, rules)})
    return rows


# ---------------------------------------------------------------------------- settings


def world_settings(world: str | None, config: dict | None = None) -> dict:
    """The config sections of a world: its preset defaults with the playground's settings on top."""
    from opulse.presets import PRESETS

    base = PRESETS[world]["settings"] if world in PRESETS else DOMAIN_SETTINGS.get(world or "", {})
    chosen = (config or {}).get("settings") or {}
    sections = {}
    for section in sorted(set(base) | set(chosen)):
        values = {**base.get(section, {}), **{key: value for key, value in (chosen.get(section) or {}).items()}}
        if values:
            sections[section] = values
    return sections


def settings_for(world: str | None, config: dict | None = None, browser: bool = True):
    """:class:`~opulse.config.Settings` of a playground world (no PyYAML needed)."""
    from opulse.config import Settings

    sections = world_settings(world, config)
    _check_settings(sections)
    if browser:
        sections["operators"] = {**sections.get("operators", {}), **BROWSER_GENERATION}
    try:
        return Settings.from_dict(sections)
    except (TypeError, ValueError) as exc:
        raise PlaygroundError(f"Settings: {exc}", "settings") from None


_CHOICES = {("semantics", "mode"): ("exact", "legacy", "modular"),
            ("recursion", "style"): ("bounded_mod", "direct", "peano", "bits", "primitive"),
            ("operators", "naming"): ("shape_index", "legacy")}
_LIMITS = {("semantics", "max_string_length"): 0, ("semantics", "max_list_length"): 0,
           ("recursion", "direct_bound"): 0, ("recursion", "modulus_min"): 2, ("recursion", "modulus_max"): 2}


def _check_settings(sections: dict) -> None:
    """Type and range checks of the exposed settings, with the config key in each message."""
    def fail(key, text):
        raise PlaygroundError(f"Settings: {key} {text}.", "settings")

    for (section, name), choices in _CHOICES.items():
        value = sections.get(section, {}).get(name)
        if value is not None and value not in choices:
            fail(f"{section}.{name}", f"must be one of {', '.join(choices)}")
    for (section, name), low in _LIMITS.items():
        value = sections.get(section, {}).get(name)
        if value is not None and (type(value) is not int or value < low):
            fail(f"{section}.{name}", f"must be a whole number of at least {low}")
    bound = sections.get("semantics", {}).get("bound", 1)
    if bound is not None and (type(bound) is not int or bound < 1):
        fail("semantics.bound", "must be a positive whole number, or empty for no bound")
    recursion = sections.get("recursion", {})
    if recursion.get("modulus_min", 3) > recursion.get("modulus_max", 9):
        fail("recursion.modulus_min", "must not exceed recursion.modulus_max")
    enabled = recursion.get("enabled", True)
    if type(enabled) is not bool:
        fail("recursion.enabled", "must be true or false")
    operators = sections.get("operators", {})
    shape_sets = operators.get("shape_sets", ("shapes",))
    if not isinstance(shape_sets, (list, tuple)) or not all(isinstance(item, str) for item in shape_sets):
        fail("operators.shape_sets", "must be a list of set names")
    for name in ("shape_chars", "index_chars"):
        if not isinstance(operators.get(name, ""), str):
            fail(f"operators.{name}", "must be text")
    index = operators.get("index_chars")
    if index is not None and (len(set(index)) < 2 or len(set(index)) != len(index) or
                              not all(char.isalnum() for char in index)):
        fail("operators.index_chars", "needs at least two distinct letters or digits")


def world_semantics(world: str | None, config: dict | None = None) -> Semantics:
    """The value bound, mode and length limits that evaluation uses."""
    return settings_for(world, config).semantics.build()


def setting_values(world: str | None = None, config: dict | None = None) -> dict:
    """Current value of every exposed setting, by section, for the settings panel."""
    from dataclasses import asdict

    settings = asdict(settings_for(world, config, browser=False))
    return {section: {key: settings[section][key] for key in keys} for section, keys in SETTING_KEYS.items()}


def _shape(operator) -> str:
    return "binary" if operator.n_ary == BINARY else operator.unary_position


# -------------------------------------------------------------------------- workspace


@dataclass
class _Source:
    text: str  # the definition, possibly spanning several lines joined by "\n"
    line: int  # 1-based line of its first character
    offsets: list[int]  # start offset (in ``text``) of each of its lines


class Workspace:
    """The atoms plus the user's definitions, compiled and ready to evaluate expressions."""

    def __init__(self, definitions: str, symbols: Symbols | None = None, semantics: Semantics | None = None,
                 max_steps: int = MAX_STEPS, max_depth: int = MAX_DEPTH, atom_names=None,
                 rules: dict | None = None) -> None:
        symbols = symbols or Symbols()
        self.rules = dict(rules or {})  # rule texts edited in the playground, by atom name
        semantics = semantics or Semantics()
        self.symbols = symbols
        self.semantics = semantics
        self.registry = atom_registry(atom_names)
        self.runtime = PythonRuntime(self.registry, semantics)
        self.defined: list[Operator] = []
        self._sources: dict[str, _Source] = {}
        self._build(_split_definitions(definitions))
        self.parser = DefinitionParser(symbols, self.registry)
        self.oracle = Oracle(self.registry, symbols, semantics)
        self.oracle.interpreter.max_depth = max_depth
        self.max_depth = max_depth
        self.reducer = Reducer(self.registry, self.runtime, self.parser, max_steps=max_steps)
        self.renderer = ExpressionRenderer(symbols)

    # ------------------------------------------------------------------ building
    def _build(self, sources: list[_Source]) -> None:
        base = Notation.from_registry(self.registry, self.symbols)
        shapes: dict[tuple, int] = {}  # (symbol, n_ary, position) -> index into sources
        lhs_of: list[ast.Apply] = []
        for index, source in enumerate(sources):
            lhs = self._lhs(source, base)
            key = (lhs.symbol, lhs.n_ary, lhs.unary_position)
            column = source.text.find(lhs.symbol)
            if key in shapes:
                raise self._error(source, f"{_describe(key)} is defined twice, on lines "
                                          f"{sources[shapes[key]].line} and {source.line}.", column, len(lhs.symbol))
            if self.registry.find(*key) is not None:
                name = base_operation_name(*key)
                raise self._error(source, f"{_describe(key)} is the built in atom {name}; "
                                          "choose another symbol.", column, len(lhs.symbol))
            shapes[key] = index
            lhs_of.append(lhs)

        notation = base
        for lhs in lhs_of:
            notation = notation.with_role(lhs.symbol, BINARY_ROLE if lhs.n_ary == BINARY else lhs.unary_position)
        parsed = [self._parse(source, notation) for source in sources]

        calls: list[set[int]] = []  # indices of other definitions each one calls
        for index, (source, definition) in enumerate(zip(sources, parsed)):
            used = set()
            for application in _applications(definition):
                key = (application.symbol, application.n_ary, application.unary_position)
                if key in shapes:
                    used.add(shapes[key])
                elif self.registry.find(*key) is None:
                    column = _find_symbol(source.text, application.symbol)
                    raise self._error(source, f"{_describe(key)} is used but not defined.", column,
                                      len(application.symbol))
            used.discard(index)
            calls.append(used)

        for index in _topological(sources, calls, lhs_of):
            definition, source = parsed[index], sources[index]
            kind = RECURSIVE if _calls_itself(definition, lhs_of[index]) else (
                BRANCH if any(branch.condition is not None for branch in definition.branches) else SIMPLE)
            operator = Operator(func_id=f"user{index + 1}", symbol=lhs_of[index].symbol,
                                n_ary=lhs_of[index].n_ary, unary_position=lhs_of[index].unary_position,
                                definition=render_definition(definition, self.symbols), definition_type=kind)
            try:
                code = compile_definition(definition, operator.func_id,
                                          registry_resolver(self.registry, operator))
            except ValueError as exc:  # a variable that is not a parameter
                name = re.findall(r"'(\w+)'", str(exc))
                column = _find_word(source.text, name[0], source.text.find("=")) if name else 0
                raise self._error(source, _unbound_message(exc, definition), column,
                                  len(name[0]) if name else 1) from None
            operator.op_compute_func, operator.op_count_func = code.compute, code.count
            operator.dependencies = list(code.dependencies)
            operator.recursive_layer = self.registry.recursive_layer_of(operator)
            operator.id = len(self.registry) + 1
            self.registry.add(operator)
            self.runtime.load(operator)
            self.defined.append(operator)
            self._sources[operator.func_id] = source

    def _lhs(self, source: _Source, notation: Notation) -> ast.Apply:
        try:
            parser = _Parser(tokenize(source.text, notation), notation, expression_mode=False)
            return parser.lhs()
        except SyntaxProblem as exc:
            equals = source.text.find(self.symbols.equals)
            raise self._error(source, _friendly(str(exc)), *_located(exc, 0, max(1, equals))) from None

    def _parse(self, source: _Source, notation: Notation) -> ast.Definition:
        try:
            return parse_definition(source.text, notation)
        except SyntaxProblem as exc:
            raise self._error(source, _friendly(str(exc)), *_located(exc, len(source.text), 1)) from None
        except ValueError as exc:
            raise self._error(source, str(exc), 0, len(source.text)) from None

    def _error(self, source: _Source, message: str, column: int, length: int = 1) -> PlaygroundError:
        line = 0
        for k, start in enumerate(source.offsets):
            if column >= start:
                line = k
        start = source.offsets[line]
        end = source.offsets[line + 1] - 1 if line + 1 < len(source.offsets) else len(source.text)
        length = max(1, min(length, end - column)) if column < end else 1
        return PlaygroundError(message, "definitions", source.line + line, column - start, length)

    # ---------------------------------------------------------------- evaluation
    def parse(self, expression: str) -> Node:
        text = expression
        if not text.strip():
            raise PlaygroundError("Write an expression to evaluate, for example 3 + 4.", "expression", None, 0,
                                  1)
        notation = self.parser.notation
        try:
            tokens = tokenize(text, notation, allow_unknown=False)
            node = parse_expression(text, notation, expression_mode=False)
        except SyntaxProblem as exc:
            raise PlaygroundError(_friendly(str(exc)), "expression", None,
                                  *_located(exc, len(text), 1)) from None
        variable = next((t for t in tokens if t.kind == "var"), None)
        if variable is not None:
            raise PlaygroundError(f"The expression uses the variable {variable.text}. Variables belong in "
                                  "definitions; write a number in its place.", "expression", None,
                                  variable.pos, len(variable.text))
        try:
            tree = from_ast(node, self.registry)
        except LookupError:
            application = next(a for a in ast.iter_applications(node)
                               if self.registry.find(a.symbol, a.n_ary, a.unary_position) is None)
            key = (application.symbol, application.n_ary, application.unary_position)
            raise PlaygroundError(f"{_describe(key)} is not an atom and has no definition.", "expression",
                                  None, _find_symbol(text, application.symbol), len(application.symbol)) from None
        assert not has_variable(tree)
        return literal_form(tree, self.registry)

    def evaluate(self, expression: str) -> dict:
        tree = self.parse(expression)
        try:
            reference = self.oracle.evaluate_expr(_to_ast(tree), {})
        except (EngineError, RecursionError):
            raise PlaygroundError(f"The evaluation nested more than {self.max_depth} calls, so it was stopped. "
                                  "Check that every recursive call moves toward a base case.",
                                  "expression", None, 0, len(expression)) from None
        result = {
            "value": _value(reference.value),
            "base_ops": reference.base_ops,
            "calls": reference.calls,
            "expression": self.renderer.full(tree),
        }
        try:
            trace = self.reducer.reduce(tree)
        except RecursionError:
            trace = None
        if trace is None:
            result.update(steps=[], step_count=0, truncated=True, agrees=None)
        else:
            steps, budget = [], MAX_STEP_TEXT
            for step in trace.steps:
                row = self._step(step)
                budget -= len(row["before"]) + len(row["after"])
                if budget < 0:
                    break
                steps.append(row)
            final = trace.value if not trace.truncated else None
            result.update(
                steps=steps, step_count=len(trace.steps), truncated=trace.truncated,
                result=self.renderer.full(trace.result),
                agrees=None if trace.truncated else same_value(final, reference.value),
            )
        used = {op.func_id for op in _operators_in(tree)}
        for step in trace.steps if trace is not None else ():
            used.add(step.operator.func_id)
        result["graph"] = self.graph(used)
        return result

    # ------------------------------------------------------------------- steps
    def _step(self, step) -> dict:
        before, focus = _render_marked(step.expression_before, step.path, self.symbols)
        after, new = _render_marked(step.expression_after, step.path, self.symbols)
        op = step.operator
        row = {
            "index": step.index + 1,
            "kind": step.kind,
            "symbol": op.symbol,
            "shape": _shape(op),
            "operator_kind": _KINDS.get(op.definition_type, KIND_ATOM),
            "atom": base_operation_name(op.symbol, op.n_ary, op.unary_position) if op.definition is None else None,
            "inputs": [_value(v) for v in step.inputs],
            "parameters": [],
            "before": before, "focus": focus,
            "after": after, "new": new,
            "replacement": self.renderer.full(step.after),
            "output": _value(step.output) if step.output is not None else None,
            "depth": step.depth,
            "branches": None, "branch_index": None, "branch_count": None,
            "reason": step.reason, "nan_cause": None,
        }
        if op.definition is not None:
            definition = self.reducer._definition(op)
            env = dict(zip(definition.parameters, step.inputs))
            row["parameters"] = [{"name": k, "value": _value(v)} for k, v in env.items()]
            row["branch_count"] = len(definition.branches)
            row["branch_index"] = None if step.branch_index is None else step.branch_index + 1
            row["branches"] = self._branches(definition, env, step.branch_index)
        if step.kind == "eval" and isinstance(step.after, Number) and step.after.value is NAN:
            row["nan_cause"] = self._nan_cause(step)
        if step.kind == "undefined":
            row["nan_cause"] = step.reason
        return row

    def _branches(self, definition: ast.Definition, env: dict, chosen: int | None) -> list[dict]:
        """Each branch tried, in order, up to the chosen one (all of them when none holds)."""
        rows = []
        for index, branch in enumerate(definition.branches):
            body = ast.render_expr(branch.expr, self.symbols)
            if branch.condition is None:
                rows.append({"index": index + 1, "condition": None, "else": branch.is_else, "truth": True,
                             "body": body, "comparisons": []})
                break
            comparisons: list[dict] = []
            truth = self._truth(branch.condition, env, comparisons)
            rows.append({
                "index": index + 1,
                "condition": render_condition(branch.condition, self.symbols),
                "substituted": render_condition(_substitute_condition(branch.condition, env), self.symbols),
                "truth": None if truth is NAN else bool(truth),
                "body": body, "comparisons": comparisons, "else": False,
            })
            if truth is NAN or (chosen is not None and index == chosen):
                break
        return rows

    def _truth(self, node: ast.Condition, env: dict, seen: list):
        """The same evaluation order as Reducer._truth, recording each comparison it evaluates."""
        if isinstance(node, ast.Truth):  # a Boolean value used as a condition (typed worlds)
            value = self.reducer._value(node.expr, env)
            seen.append({"text": render_condition(_substitute_condition(node, env), self.symbols),
                         "left": _value(value), "op": "", "right": "",
                         "truth": None if value is NAN else bool(value)})
            return value
        if isinstance(node, ast.Compare):
            left, right = self.reducer._value(node.left, env), self.reducer._value(node.right, env)
            truth = NAN if left is NAN or right is NAN else COMPARISONS[node.op](left, right)
            seen.append({"text": render_condition(_substitute_condition(node, env), self.symbols),
                         "left": _value(left), "op": node.op, "right": _value(right),
                         "truth": None if truth is NAN else bool(truth)})
            return truth
        if isinstance(node, ast.Not):
            inner = self._truth(node.operand, env, seen)
            return inner if inner is NAN else not inner
        left = self._truth(node.left, env, seen)
        if left is NAN:
            return NAN
        if isinstance(node, ast.And) and not left:
            return False
        if isinstance(node, ast.Or) and left:
            return True
        return self._truth(node.right, env, seen)

    def _nan_cause(self, step) -> str:
        if any(v is NAN for v in step.inputs):
            return "nan_input"
        name = base_operation_name(step.operator.symbol, step.operator.n_ary, step.operator.unary_position)
        if name in ("div", "mod") and step.inputs[1] == 0:
            return "division_by_zero"
        return "bound"

    # ------------------------------------------------------------------- graph
    def graph(self, used: set[str] = frozenset()) -> dict:
        """Defined operators and the atoms they call, grouped into dependency columns."""
        full = dependency_graph(self.registry)
        keep = {op.func_id for op in self.defined}
        for op in self.defined:
            keep.update(op.dependencies)
        keep.update(used)
        nodes = [n for n in full["nodes"] if n["func_id"] in keep]
        edges = [e for e in full["edges"] if e["source"] in keep and e["target"] in keep]
        layers = topological_layers({"nodes": nodes, "edges": edges})
        column = {key: i for i, layer in enumerate(layers) for key in layer}
        out_nodes = []
        for n in nodes:
            op = self.registry.get(n["func_id"])
            source = self._sources.get(op.func_id)
            out_nodes.append({
                "id": n["func_id"], "symbol": n["symbol"], "shape": _shape(op),
                "kind": _KINDS.get(n["definition_type"], KIND_ATOM), "layer": n["recursive_layer"],
                "column": column[n["func_id"]], "used": n["func_id"] in used,
                "line": source.line if source else None,
                "definition": n["definition"],
                "rule": _rule_text(base_operation_name(op.symbol, op.n_ary, op.unary_position), self.rules)
                if op.definition is None else None,
            })
        return {"nodes": out_nodes, "edges": edges}

    def summary(self) -> list[dict]:
        return [{"symbol": op.symbol, "shape": _shape(op), "kind": _KINDS[op.definition_type],
                 "layer": op.recursive_layer, "line": self._sources[op.func_id].line,
                 "definition": op.definition} for op in self.defined]


# ------------------------------------------------------------------------- front door

_CACHE: dict[str, Workspace] = {}


def run(definitions: str, expression: str, custom_atoms: list[dict] | None = None,
        world: str | None = None, config: dict | None = None) -> dict:
    """Everything the playground shows for one input; errors are returned, not raised."""
    try:
        names = prepare_atoms(world, custom_atoms, config)
        key = json.dumps([definitions, world, custom_atoms, config], sort_keys=True, ensure_ascii=False)
        workspace = _CACHE.get(key)
        if workspace is None:
            workspace = Workspace(definitions, semantics=world_semantics(world, config), atom_names=names,
                                  rules=(config or {}).get("rules"))
            _CACHE.clear()
            _CACHE[key] = workspace
    except PlaygroundError as exc:
        return {"ok": False, "error": exc.to_dict()}
    except RecursionError:
        return {"ok": False, "error": PlaygroundError("A definition is nested too deeply to read.",
                                                      "definitions", 1, 0, 1).to_dict()}
    out = {"ok": True, "operators": workspace.summary()}
    try:
        out.update(workspace.evaluate(expression))
    except PlaygroundError as exc:
        out.update(ok=False, error=exc.to_dict(), graph=workspace.graph())
    except Exception as exc:
        if not custom_atoms:
            raise
        out.update(ok=False, error=PlaygroundError(f"An atom failed: {exc}", "atoms").to_dict(),
                   graph=workspace.graph())
    return out


def run_json(definitions: str, expression: str, custom_atoms_json: str = "[]",
             world: str = "", config_json: str = "{}") -> str:
    try:
        custom_atoms = json.loads(custom_atoms_json)
        config = json.loads(config_json)
    except json.JSONDecodeError as exc:
        return json.dumps({"ok": False, "error": PlaygroundError(str(exc), "atoms").to_dict()})
    return json.dumps(run(definitions, expression, custom_atoms, world, config), ensure_ascii=False)


def _challenge_value(value):
    """Keep integer answers as JSON numbers and the interpreter's NaN as a string."""
    return "NaN" if value is NAN else value


def check_equivalent(definitions: str, symbol: str, candidate: str, domain: list[int]) -> dict:
    """Compare a replacement definition at every integer tuple in an inclusive range."""
    if (not isinstance(domain, list) or len(domain) != 2
            or any(type(x) is not int for x in domain) or domain[0] > domain[1]):
        return {"equivalent": False, "proof": "range", "counterexample": None,
                "parse_error": "Domain must be an inclusive [low, high] integer range."}
    try:
        original = Workspace(definitions)
        matches = [op for op in original.defined if op.symbol == symbol]
        if len(matches) != 1:
            raise PlaygroundError(f"Expected one definition for {symbol}.", "definitions")
        operator = matches[0]
        parsed = parse_definition(candidate, original.parser.notation)
        lhs = parsed.lhs
        if (lhs.symbol, lhs.n_ary, lhs.unary_position) != (
                operator.symbol, operator.n_ary, operator.unary_position):
            raise PlaygroundError("The candidate must define the same operator and arity.", "definitions")
        sources = _split_definitions(definitions)
        index = int(operator.func_id.removeprefix("user")) - 1
        sources[index] = _Source(candidate, 1, [0])
        replacement = Workspace("\n".join(source.text for source in sources))
        other = next(op for op in replacement.defined if op.symbol == symbol)
    except (PlaygroundError, SyntaxProblem, ValueError, RecursionError) as exc:
        return {"equivalent": False, "proof": "range", "counterexample": None,
                "parse_error": exc.message if isinstance(exc, PlaygroundError) else str(exc)}

    for inputs in itertools.product(range(domain[0], domain[1] + 1), repeat=operator.n_ary):
        values = []
        for workspace, op in ((original, operator), (replacement, other)):
            expression = op.apply_str(*(str(x) if x >= 0 else f"(- {-x})" for x in inputs))
            try:
                tree = workspace.parse(expression)
                values.append(workspace.oracle.evaluate_expr(_to_ast(tree), {}).value)
            except (EngineError, RecursionError):
                return {"equivalent": False, "proof": "range", "counterexample": None,
                        "parse_error": "Evaluation exceeded the interpreter's recursion limit."}
        if not same_value(*values):
            return {"equivalent": False, "proof": "range", "counterexample": {
                "inputs": list(inputs), "expected": _challenge_value(values[0]),
                "got": _challenge_value(values[1])}, "parse_error": None}
    return {"equivalent": True, "proof": "range", "counterexample": None, "parse_error": None}


def check_equivalent_json(definitions: str, symbol: str, candidate: str, domain_json: str) -> str:
    return json.dumps(check_equivalent(definitions, symbol, candidate, json.loads(domain_json)), ensure_ascii=False)


def challenge_steps(definitions: str, candidate: str, inputs: list[list[int]]) -> dict:
    """Faster-family cost for a replacement rule on the stated input tuples.

    Each counted step is a reference-interpreter base operation evaluation.
    Definition expansions shown by the trace are separate display rows.
    The candidate replaces its original rule, as in check_equivalent.
    """
    empty = {"total": None, "per_input": [], "parse_error": None}
    try:
        if (not isinstance(inputs, list) or not inputs or
                any(not isinstance(point, list) or not all(type(x) is int for x in point)
                    for point in inputs)):
            raise ValueError("Inputs must be a nonempty list of integer tuples.")
        original = Workspace(definitions, semantics=Semantics(bound=None))
        parsed = parse_definition(candidate, original.parser.notation)
        key = (parsed.lhs.symbol, parsed.lhs.n_ary, parsed.lhs.unary_position)
        matches = [op for op in original.defined
                   if (op.symbol, op.n_ary, op.unary_position) == key]
        if len(matches) != 1:
            raise ValueError("The candidate must replace one listed operator with the same arity.")
        sources = _split_definitions(definitions)
        index = int(matches[0].func_id.removeprefix("user")) - 1
        sources[index] = _Source(candidate, 1, [0])
        replacement = Workspace("\n".join(source.text for source in sources),
                                semantics=Semantics(bound=None))
        operator = next(op for op in replacement.defined
                        if (op.symbol, op.n_ary, op.unary_position) == key)
        if any(len(point) != operator.n_ary for point in inputs):
            raise ValueError("Input arity differs from the definition.")
        per_input = [{"inputs": point,
                      "steps": replacement.oracle.evaluate(operator, tuple(point)).base_ops}
                     for point in inputs]
        return {"total": sum(row["steps"] for row in per_input),
                "per_input": per_input, "parse_error": None}
    except (PlaygroundError, SyntaxProblem, ValueError, EngineError, RecursionError) as exc:
        return {**empty, "parse_error": exc.message if isinstance(exc, PlaygroundError) else str(exc)}


def challenge_steps_json(definitions: str, candidate: str, inputs_json: str) -> str:
    try:
        inputs = json.loads(inputs_json)
    except json.JSONDecodeError as exc:
        return json.dumps({"total": None, "per_input": [], "parse_error": str(exc)})
    return json.dumps(challenge_steps(definitions, candidate, inputs), ensure_ascii=False)


def check_playground_guess_json(definitions: str, symbol: str, candidate: str, domain_json: str,
                                world: str = "", custom_atoms_json: str = "[]", config_json: str = "{}") -> str:
    """Check a hidden definition on an inclusive integer range or finite typed input sets."""
    result = {"equivalent": False, "proof": "range", "counterexample": None, "parse_error": None}
    try:
        domain = json.loads(domain_json)
        custom_atoms = json.loads(custom_atoms_json)
        config = json.loads(config_json)
        names = prepare_atoms(world, custom_atoms, config)
        semantics = world_semantics(world, config)
        original = Workspace(definitions, semantics=semantics, atom_names=names)
        matches = [op for op in original.defined if op.symbol == symbol]
        if len(matches) != 1:
            raise PlaygroundError(f"Expected one definition for {symbol}.", "definitions")
        operator = matches[0]
        parsed = parse_definition(candidate, original.parser.notation)
        lhs = parsed.lhs
        if (lhs.symbol, lhs.n_ary, lhs.unary_position) != (
                operator.symbol, operator.n_ary, operator.unary_position):
            raise PlaygroundError("The candidate must define the same operator and arity.", "definitions")
        sources = _split_definitions(definitions)
        index = int(operator.func_id.removeprefix("user")) - 1
        sources[index] = _Source(candidate, 1, [0])
        replacement = Workspace("\n".join(source.text for source in sources), semantics=semantics,
                                atom_names=names)
        other = next(op for op in replacement.defined if op.symbol == symbol)
        if (isinstance(domain, list) and len(domain) == 2
                and all(type(x) is int for x in domain) and domain[0] <= domain[1]):
            cases = itertools.product(range(domain[0], domain[1] + 1), repeat=operator.n_ary)
        elif (isinstance(domain, dict) and isinstance(domain.get("values"), list)
              and len(domain["values"]) == operator.n_ary
              and all(isinstance(values, list) and values for values in domain["values"])):
            cases = itertools.product(*domain["values"])
            result["proof"] = "values"
        elif (isinstance(domain, dict) and isinstance(domain.get("literals"), list)
              and len(domain["literals"]) == operator.n_ary
              and all(isinstance(values, list) and values and all(isinstance(x, str) for x in values)
                      for values in domain["literals"])):
            cases = itertools.product(*domain["literals"])
            result["proof"] = "values"
        else:
            raise ValueError("Domain must be an inclusive integer range or one nonempty value set per input.")
        for inputs in cases:
            values = []
            for workspace, op in ((original, operator), (replacement, other)):
                args = list(inputs) if isinstance(domain, dict) and "literals" in domain else [
                    str(x) if type(x) is int and x >= 0 else f"(- {-x})"
                    if type(x) is int else literal(x) for x in inputs]
                expression = op.apply_str(*args)
                tree = workspace.parse(expression)
                values.append(workspace.oracle.evaluate_expr(_to_ast(tree), {}).value)
            if not same_value(*values):
                result["counterexample"] = {"inputs": list(inputs),
                                            "expected": _challenge_value(values[0]),
                                            "got": _challenge_value(values[1])}
                break
        else:
            result["equivalent"] = True
    except (PlaygroundError, SyntaxProblem, ValueError, RecursionError) as exc:
        result["parse_error"] = exc.message if isinstance(exc, PlaygroundError) else str(exc)
    return json.dumps(result, ensure_ascii=False)


def size(definition: str) -> int:
    """Count applications in every branch body and condition, as simplify does."""
    base = Notation.from_registry(atom_registry(), Symbols())
    lhs = _Parser(tokenize(definition, base), base, expression_mode=False).lhs()
    notation = base.with_role(lhs.symbol, BINARY_ROLE if lhs.n_ary == BINARY else lhs.unary_position)
    parsed = parse_definition(definition, notation)
    return sum(sum(1 for _ in ast.iter_applications(node))
               for branch in parsed.branches
               for node in (branch.expr, branch.condition) if node is not None)


def atoms_json(world: str = "", custom_atoms_json: str = "[]", config_json: str = "{}") -> str:
    return json.dumps(atoms(world, json.loads(custom_atoms_json), json.loads(config_json)), ensure_ascii=False)


def worlds_json() -> str:
    return json.dumps(available_worlds())


# -------------------------------------------------------------------------------- grow


def _proportions(world: str | None) -> tuple[float, float, float]:
    from opulse.presets import PRESETS

    return tuple(PRESETS.get(world or "", {}).get("proportions", (0.4, 0.4, 0.2)))


def _layers(layers) -> list[int]:
    if isinstance(layers, str):
        layers = layers.replace(",", " ").split()
    try:
        counts = [int(count) for count in layers]
    except (TypeError, ValueError):
        raise PlaygroundError("Layers: write whole numbers, for example 6 6.", "grow") from None
    if not counts or len(counts) > 4 or any(count < 0 for count in counts) or not any(counts):
        raise PlaygroundError("Layers: give one to four counts, for example 6 6.", "grow")
    if sum(counts) > MAX_GROWN:
        raise PlaygroundError(f"Layers: the browser grows at most {MAX_GROWN} operators at once.", "grow")
    return counts


def grow(world: str | None = None, custom_atoms: list | None = None, config: dict | None = None,
         layers=(6, 6), seed: int = 1) -> dict:
    """Grow an operator set from the playground's atoms, the way ``opulse operators`` does.

    The steps are those of the CLI with ``--initial`` (a starting set written by
    :func:`~opulse.core.primitives.write_initial_set`) and ``--seed``: the same registry, the
    same random stream and :func:`~opulse.generation.pipeline.build_layers`. The z3 checks are
    off (:data:`BROWSER_GENERATION`); the exported config switches them off too, so the CLI
    then writes the same definitions. Returns the definitions in dependency order and an
    expression that evaluates to a defined value, or ``{"ok": False, "error": ...}``.
    """
    import random

    from opulse.generation.pipeline import OperatorFactory, build_layers

    try:
        counts = _layers(layers)
        try:
            seed = int(seed)
        except (TypeError, ValueError):
            raise PlaygroundError("Seed: write a whole number.", "grow") from None
        names = prepare_atoms(world, custom_atoms, config)
        settings = settings_for(world, config)
        registry = OperatorRegistry(Operator.from_dict(row) for row in atom_records(names, 0))
        rng = random.Random(seed + len(registry))
        try:
            factory = OperatorFactory(settings, registry, rng)
            build_layers(factory, counts, _proportions(world))
        except (ValueError, RuntimeError) as exc:
            raise PlaygroundError(f"Generation stopped: {exc}", "grow") from None
    except PlaygroundError as exc:
        return {"ok": False, "error": exc.to_dict()}
    defined = [op for op in registry.topological_order() if op.definition is not None]
    text = "\n".join(op.definition for op in defined)
    return {"ok": True, "definitions": text, "expression": _sample_expression(defined, text, world, custom_atoms, config),
            "count": len(defined), "layers": counts, "seed": seed,
            "stats": factory.stats.summary()}


def _sample_expression(defined: list, text: str, world, custom_atoms, config) -> str:
    """A call of the highest operator whose value is defined and takes a few steps."""
    import random

    from opulse.generation.typed import sample_value

    rng = random.Random(0)
    workspace = Workspace(text, semantics=world_semantics(world, config),
                          atom_names=prepare_atoms(world, custom_atoms, config))
    fallback = None
    for op in sorted(defined, key=lambda op: (-op.recursive_layer, defined.index(op))):
        for attempt in range(8):
            args = [sample_value(kind, rng) if kind != "int" else rng.choice((2, 3, 5, 7, 9, 12))
                    for kind in op.parameter_types]
            expression = op.apply_str(*(literal(arg) for arg in args))
            fallback = fallback or expression
            try:
                result = workspace.evaluate(expression)
            except PlaygroundError:
                continue
            if result["value"] != "NaN" and 2 <= result["step_count"] <= 200:
                return expression
    return fallback or ""


def grow_json(world: str = "", custom_atoms_json: str = "[]", config_json: str = "{}",
              layers: str = "6 6", seed: str = "1") -> str:
    return json.dumps(grow(world, json.loads(custom_atoms_json), json.loads(config_json), layers, seed),
                      ensure_ascii=False)


# ------------------------------------------------------------------------------ export


def _yaml_scalar(value) -> str:
    if value is None:
        return "null"
    if value is True or value is False:
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_yaml_scalar(item) for item in value) + "]"
    return json.dumps(str(value), ensure_ascii=False)  # a JSON string is a YAML double-quoted scalar


def to_yaml(sections: dict, comments: dict | None = None) -> str:
    """Two-level config sections as YAML (the playground has no PyYAML)."""
    comments = comments or {}
    lines = []
    for section, values in sections.items():
        lines.append(f"{section}:")
        for key, value in values.items():
            note = comments.get((section, key))
            lines.append(f"  {key}: {_yaml_scalar(value)}" + (f"  # {note}" if note else ""))
    return "\n".join(lines) + "\n"


def export_sections(world: str | None, config: dict | None = None) -> dict:
    """The config file of a playground world: every exposed setting plus the world's own defaults."""
    sections = world_settings(world, config)
    values = setting_values(world, config)
    for section, keys in SETTING_KEYS.items():
        sections[section] = {**{key: values[section][key] for key in keys}, **sections.get(section, {})}
        sections[section] = {key: list(v) if isinstance(v, tuple) else v for key, v in sections[section].items()}
    sections["operators"] = {**sections["operators"], **BROWSER_GENERATION}
    order = ("semantics", "operators", "recursion", "expressions")
    return {name: sections[name] for name in (*order, *sorted(set(sections) - set(order))) if name in sections}


def _indent(code: str) -> str:
    return code.strip("\n") + "\n"


def plugin_code(world: str | None, custom_atoms: list | None = None, config: dict | None = None,
                file_name: str = "world_atoms.py") -> str:
    """A plugin module that registers the playground's atoms for the CLI.

    It registers the world's atoms, the custom atoms, the new symbols and rule texts, and as a
    script writes the starting operator set (``ATOMS``) for ``opulse operators --initial``.
    """
    from opulse.core.presets import PRESETS as typed
    from opulse.presets import PRESETS as numeric

    rows = atom_table(world, custom_atoms, config)
    on = [row for row in rows if row["on"]]
    out = ['"""Atoms of a world exported from the Opulse playground.',
           "",
           f"    python {file_name} initial.jsonl      # write the starting operator set",
           f"    opulse --plugin {file_name} operators --config world.yaml --initial initial.jsonl ...",
           '"""', "", "from opulse.core.primitives import BUILT_IN_RULES, CUSTOM, register_primitive, write_initial_set",
           "from opulse.core.semantics import BASE_OPERATIONS", ""]
    if world in numeric:
        out += ["from opulse.presets import register_preset", "", f"register_preset({world!r})", ""]
    elif world in typed:
        out += ["from opulse.core.presets import register_preset", "", f"register_preset({world!r})", ""]
    customs = [row for row in on if row["custom"] is not None]
    for row in customs:
        spec = custom_atoms[row["custom"]]
        parameters, result = parse_types(spec.get("types", ""), row["n_ary"])
        out += [_indent(str(spec["code"])), ""]
        extra = f", position={row['position']!r}" if row["n_ary"] == 1 else ", position=None"
        if (parameters, result) != (("int",) * row["n_ary"], "int"):
            extra += f", parameter_types={parameters!r}, result_type={result!r}"
        out += [(f"register_primitive({row['name']!r}, {row['symbol']!r}, {row['name']}, "
                f"rule={row['rule']!r}, n_ary={row['n_ary']}{extra})"), ""]
    renamed = [row for row in on if row["custom"] is None and row["symbol"] != row["default_symbol"]]
    edited = [row for row in on if row["custom"] is None and row["rule"] != row["default_rule"]]
    if renamed or edited:
        out += ["", "def rename(name, symbol):",
                '    """Write an atom with another symbol; its computation stays the same."""',
                "    from dataclasses import replace",
                "",
                "    key = next(key for key, owner in BASE_OPERATIONS.items() if owner == name)",
                "    del BASE_OPERATIONS[key]",
                "    BASE_OPERATIONS[(symbol, key[1], key[2])] = name",
                "    if name in CUSTOM:",
                "        CUSTOM[name] = replace(CUSTOM[name], symbol=symbol)",
                "",
                "",
                "def set_rule(name, rule):",
                '    """Change the sentence that prompts show for an atom."""',
                "    from dataclasses import replace",
                "",
                "    if name in CUSTOM:",
                "        CUSTOM[name] = replace(CUSTOM[name], rule=rule)",
                "    else:",
                "        BUILT_IN_RULES[name] = rule",
                "", ""]
        out += [f"rename({row['name']!r}, {row['symbol']!r})" for row in renamed]
        out += [f"set_rule({row['name']!r}, {row['rule']!r})" for row in edited]
        out.append("")
    out += ["ATOMS = [" + ", ".join(repr(row["name"]) for row in on) + "]", "",
            'if __name__ == "__main__":', "    import sys", "",
            '    write_initial_set(sys.argv[1] if len(sys.argv) > 1 else "initial.jsonl", ATOMS)', ""]
    return "\n".join(out)


def export(world: str | None = None, custom_atoms: list | None = None, config: dict | None = None,
           layers=(6, 6), seed: int = 1) -> dict:
    """Config file, plugin module and commands that rebuild the playground world with the CLI."""
    try:
        counts = _layers(layers)
        sections = export_sections(world, config)
        settings_for(world, config)  # reports invalid settings
        prepare_atoms(world, custom_atoms, config)  # reports invalid atoms
    except PlaygroundError as exc:
        return {"ok": False, "error": exc.to_dict()}
    comments = {("operators", key): "the playground has no z3; true runs the solver checks"
                for key in BROWSER_GENERATION}
    simple, branch, recursive = _proportions(world)
    commands = ("python world_atoms.py initial.jsonl\n"
                "opulse --plugin world_atoms.py operators --config world.yaml --initial initial.jsonl \\\n"
                f"    --layers {' '.join(map(str, counts))} --proportions {simple} {branch} {recursive} "
                f"--seed {int(seed)} --out operators.jsonl\n")
    return {"ok": True, "yaml": to_yaml(sections, comments), "json": sections,
            "plugin": plugin_code(world, custom_atoms, config), "commands": commands}


def export_json(world: str = "", custom_atoms_json: str = "[]", config_json: str = "{}",
                layers: str = "6 6", seed: str = "1") -> str:
    return json.dumps(export(world, json.loads(custom_atoms_json), json.loads(config_json), layers, seed),
                      ensure_ascii=False)


def table_json(world: str = "", custom_atoms_json: str = "[]", config_json: str = "{}") -> str:
    """The atom table and the setting values of one playground state."""
    config = json.loads(config_json)
    try:
        rows = atom_table(world, json.loads(custom_atoms_json), config)
    except PlaygroundError as exc:
        return json.dumps({"ok": False, "error": exc.to_dict()}, ensure_ascii=False)
    try:
        values, problem = setting_values(world, config), None
    except PlaygroundError as exc:
        values, problem = setting_values(world, {}), exc.to_dict()
    return json.dumps({"ok": True, "atoms": rows, "settings": values, "settings_error": problem,
                       "proportions": _proportions(world)}, ensure_ascii=False)


# ------------------------------------------------------------------------- rendering


def _render_marked(node: Node, path: tuple[int, ...], symbols: Symbols) -> tuple[str, list[int]]:
    """``ExpressionRenderer.full`` text of ``node`` and the ``[start, end)`` span of the subtree at ``path``."""
    renderer = ExpressionRenderer(symbols)
    span = [0, 0]

    def render(current: Node, parent, here: tuple[int, ...], offset: int) -> str:
        # ``offset`` is where this subtree's text starts, including an opening bracket.
        if isinstance(current, Call):
            op = current.operator
            bracket = parent is not None
            cursor = offset + (len(symbols.left_paren) if bracket else 0)
            if op.n_ary == BINARY:
                left = render(current.args[0], op, here + (0,), cursor)
                right = render(current.args[1], op, here + (1,), cursor + len(left) + len(op.symbol) + 2)
                text = op.apply_str(left, right)
            else:
                start = cursor + (len(op.symbol) + 1 if op.unary_position == PREFIX else 0)
                text = op.apply_str(render(current.args[0], op, here + (0,), start))
            full = symbols.paren(text) if bracket else text
        else:
            full = renderer._render(current, parent, None, minimal=False)
        if here == path:
            span[0], span[1] = offset, offset + len(full)
        return full

    text = render(node, None, (), 0)
    return text, span


def _to_ast(node: Node) -> ast.Expr:
    if isinstance(node, Number):
        if node.value is NAN:
            return ast.NaN()
        return ast.negate(node.value) if isinstance(node.value, int) and not isinstance(node.value, bool) \
            else ast.Literal(node.value)
    op = node.operator
    return ast.Apply(op.symbol, tuple(_to_ast(arg) for arg in node.args), op.unary_position)


def _operators_in(node: Node):
    if isinstance(node, Call):
        yield node.operator
        for arg in node.args:
            yield from _operators_in(arg)


def _value(value) -> str:
    return "NaN" if value is NAN else literal(value)


# ------------------------------------------------------------------------- input text


def _split_definitions(text: str) -> list[_Source]:
    """Group lines into definitions: a definition ends on the line where its braces close."""
    sources: list[_Source] = []
    current: list[str] = []
    first = 0
    depth = 0
    for number, line in enumerate(text.split("\n"), start=1):
        stripped = line.strip()
        if not current and (not stripped or stripped.startswith("//")):
            continue
        if not current:
            first = number
        current.append(line)
        depth += line.count("{") - line.count("}")
        if depth <= 0 and "{" in "".join(current):
            sources.append(_source(current, first))
            current, depth = [], 0
    if current:
        sources.append(_source(current, first))
    return sources


def _source(lines: list[str], first: int) -> _Source:
    offsets, position = [], 0
    for line in lines:
        offsets.append(position)
        position += len(line) + 1
    return _Source("\n".join(lines), first, offsets)


def _applications(definition: ast.Definition):
    for branch in definition.branches:
        yield from ast.iter_applications(branch.expr)
        if branch.condition is not None:
            yield from ast.iter_applications(branch.condition)


def _calls_itself(definition: ast.Definition, lhs: ast.Apply) -> bool:
    key = (lhs.symbol, lhs.n_ary, lhs.unary_position)
    return any((a.symbol, a.n_ary, a.unary_position) == key for a in _applications(definition))


def _topological(sources: list[_Source], calls: list[set[int]], lhs_of: list[ast.Apply]) -> list[int]:
    order: list[int] = []
    state: dict[int, int] = {}  # 1 visiting, 2 done

    def visit(index: int, chain: list[int]) -> None:
        if state.get(index) == 2:
            return
        if state.get(index) == 1:
            cycle = chain[chain.index(index):] + [index]
            names = " calls ".join(lhs_of[i].symbol for i in cycle)
            source = sources[index]
            raise PlaygroundError(
                f"The definitions form a cycle: {names}. An operator may call itself, "
                "but operators may not call each other in a cycle.", "definitions", source.line, 0,
                len(source.text.split("\n")[0]))
        state[index] = 1
        for callee in sorted(calls[index]):
            visit(callee, chain + [index])
        state[index] = 2
        order.append(index)

    for index in range(len(sources)):
        visit(index, [])
    return order


def _describe(key: tuple) -> str:
    symbol, n_ary, position = key
    shape = "binary operator" if n_ary == BINARY else f"{position} operator"
    return f"The {shape} {symbol}"


_TOKEN_NAMES = {"'rparen'": "')'", "'lparen'": "'('", "'end'": "the end", "'eq'": "'='", "'cmp'": "a comparison",
                "'punct'": "punctuation", "'kw'": "a keyword", "'op'": "an operator"}


def _friendly(message: str) -> str:
    text = re.sub(r" at \d+", "", message)
    text = re.sub(r"operator run '(.*)' is not made of known symbols",
                  r"'\1' is not an atom or a defined operator, and it does not split into such symbols", text)
    text = re.sub(r"unknown word '(.*)'", r"unknown word '\1'; the only variables are a and b", text)
    for raw, nice in _TOKEN_NAMES.items():
        text = text.replace(raw, nice)
    text = text.replace("found 'end'", "found the end")
    return text[0].upper() + text[1:] + ("" if text.endswith(".") else ".")


def _located(exc: SyntaxProblem, default: int, length: int) -> tuple[int, int]:
    found = re.findall(r" at (\d+)", str(exc))
    if not found:
        return default, length
    position = int(found[-1])
    run = re.search(r"(?:run|word) '([^']*)'", str(exc))
    return position, len(run.group(1)) if run else 1


def _find_symbol(text: str, symbol: str) -> int:
    start = text.find("=") + 1 if "=" in text and "{" in text else 0
    found = text.find(symbol, start)
    return max(found, 0)


def _find_word(text: str, word: str, start: int) -> int:
    match = re.search(rf"(?<![A-Za-z0-9]){re.escape(word)}(?![A-Za-z0-9])", text[max(0, start):])
    return match.start() + max(0, start) if match else 0


def _unbound_message(exc: Exception, definition: ast.Definition) -> str:
    names = re.findall(r"'(\w+)'", str(exc))
    params = ", ".join(definition.parameters)
    which = names[0] if names else "?"
    return f"The variable {which} is not a parameter of this definition; its parameters are {params}."


__all__ = ["PlaygroundError", "Workspace", "atom_registry", "atom_table", "atoms", "atoms_json", "export",
           "export_json", "grow", "grow_json", "run", "run_json", "symbol_problem", "table_json"]
