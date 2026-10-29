"""Typed settings for every generator, loaded from one YAML file.

The new layout groups keys by the component that reads them::

    semantics:   {mode, bound}
    symbols:     {left_operand, right_operand, operand_names, argument_separator,
                  left_paren, right_paren, equals, nan, inf, neg_inf}
    numerals:    {max_base, digits}
    operators:   {naming, shape_sets, shape_chars, index_chars, definition_layout, piecewise_min_length,
                  symbol_min_len, symbol_max_len, symbol_sets, symbol_chars, symbol_blocks, symbol_ascii,
                  exclude_confusable, arity_weights,
                  max_if_branches, condition_min, condition_max}
    recursion:   {style, modulus_min, modulus_max, direct_bound, constant_min, constant_max}
    expressions: {variables, value_min, value_max, max_depth, type_weights, atom_weights,
                  numeral_base, random_numeral_base, result_base, random_result_base, cot_base}
    interest:    {dedup, selection, pool, temperature, weights, probe_ints, max_probe_points,
                  regularity_range, max_period, solver_timeout_ms}

Legacy flat configs (``config/generate_operator.yaml`` in the old tree) are
also accepted; see :func:`_from_legacy`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SemanticsSettings:
    """Numeric mode (docs/reference/semantics.md section 2)."""

    mode: str = "exact"          # exact | legacy | modular
    bound: int | None = 2**31 - 1  # null: no bound (exact mode only)
    max_string_length: int = 256
    max_list_length: int = 256
    modulus: int | None = None

    def build(self):
        from opulse.core.semantics import Semantics

        return Semantics(self.mode, self.bound, self.max_string_length, self.max_list_length, self.modulus)


# Parameter names after ``a`` and ``b`` when ``symbols.operand_names`` is not set.
DEFAULT_EXTRA_OPERANDS = ("c", "d", "e", "f", "g", "h")


@dataclass(frozen=True)
class Symbols:
    left_operand: str = "a"
    right_operand: str = "b"
    left_paren: str = "("
    right_paren: str = ")"
    equals: str = "="
    nan: str = "NaN"
    inf: str = "Inf"
    neg_inf: str = "-Inf"
    # Parameter names of operators, in order. Empty: left_operand, right_operand, then c, d, e,
    # f, g, h. When set, its first two names are the left and right operands; the number of
    # names is the largest arity an operator can have.
    operand_names: tuple[str, ...] = ()
    # Separates the arguments of an operator with three or more arguments, which is written
    # in call form: ``⊕(a, b, c)``.
    argument_separator: str = ","

    def __post_init__(self) -> None:
        names = tuple(self.operand_names)
        object.__setattr__(self, "operand_names", names)
        if names:
            if len(names) < 2:
                raise ValueError("symbols.operand_names needs at least two names")
            for attr, default, given in (("left_operand", "a", names[0]), ("right_operand", "b", names[1])):
                current = getattr(self, attr)
                if current == default:
                    object.__setattr__(self, attr, given)
                elif current != given:
                    raise ValueError(f"symbols.{attr} {current!r} differs from operand_names "
                                     f"{names[:2]}; set one of them")
        params = self.parameter_names
        for name in names:  # what the tokenizer reads as a name: a letter, then letters or digits
            if not (name[:1].isalpha() and all(c.isalpha() or c.isdigit() for c in name)) \
                    or name in ("if", "else", "and", "or", "not", "search") or name == self.nan:
                raise ValueError(f"symbols.operand_names: {name!r} must be a word (a letter, then letters "
                                 "or digits) other than a keyword or the NaN spelling")
        if len(set(params)) != len(params):
            raise ValueError(f"operand names must be distinct, got {params}")
        sep = self.argument_separator
        if not sep or any(ch.isspace() or ch.isalnum() or ch in "{};=<>!" for ch in sep) \
                or sep in (self.left_paren, self.right_paren):
            raise ValueError(f"symbols.argument_separator {sep!r} must be punctuation other than "
                             "brackets and { } ; = < > !")

    @property
    def parameter_names(self) -> tuple[str, ...]:
        """Every parameter name, in order (its length is the largest arity)."""
        if self.operand_names:
            return self.operand_names
        first = (self.left_operand, self.right_operand)
        return first + tuple(name for name in DEFAULT_EXTRA_OPERANDS if name not in first)

    @property
    def max_arity(self) -> int:
        return len(self.parameter_names)

    def paren(self, text: str) -> str:
        return f"{self.left_paren}{text}{self.right_paren}"

    def call(self, symbol: str, args) -> str:
        """Call form of an application with three or more arguments: ``⊕(a, b, c)``."""
        return f"{symbol}{self.left_paren}{(self.argument_separator + ' ').join(args)}{self.right_paren}"

    def operands(self, n_ary: int) -> tuple[str, ...]:
        if n_ary == 1:
            return (self.left_operand,)
        if n_ary == 2:
            return (self.left_operand, self.right_operand)
        names = self.parameter_names
        if n_ary > len(names):
            raise ValueError(f"{n_ary} parameters need {n_ary} names, but symbols.operand_names "
                             f"gives {len(names)}")
        return names[:n_ary]


@dataclass(frozen=True)
class Numerals:
    max_base: int = 16
    digits: str = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


DEFAULT_ARITY_WEIGHTS = {1: 0.5, 2: 0.5}


@dataclass(frozen=True)
class OperatorSettings:
    naming: str = "shape_index"  # shape_index | legacy
    shape_sets: tuple[str, ...] = ("shapes", "suits")
    shape_chars: str = ""
    index_chars: str = "₀₁₂₃₄₅₆₇₈₉"
    definition_layout: str = "compact"  # compact | piecewise
    piecewise_min_length: int = 120
    definedness: bool = False
    symbol_min_len: int = 1
    symbol_max_len: int = 3
    # Legacy mode: named character sets that random symbols are drawn from (opulse.generation.symbols.NAMED_SETS:
    # circled, squared, logic, sets, calculus, math, arrows, shapes, suits, greek).
    symbol_sets: tuple[str, ...] = ("math", "arrows", "shapes")
    # Further characters, listed directly, e.g. "⊕⊗★".
    symbol_chars: str = ""
    # Advanced: raw Unicode ranges (inclusive "start-end" hex), e.g. "2200-22FF" for all math operators.
    symbol_blocks: tuple[str, ...] = ()
    # Extra ASCII characters allowed inside random symbols. Empty by default:
    # mixing "+-*/%" into new symbols makes them read like built-in arithmetic.
    symbol_ascii: str = ""
    # Drop characters that look like ASCII arithmetic, comparisons or bars (see generation.symbols).
    exclude_confusable: bool = True
    # Relative number of new operators per arity, e.g. {1: 0.25, 2: 0.5, 3: 0.25}. Arity 1 is
    # split evenly between prefix and postfix; arity 3 and more is written in call form. The
    # default draws exactly as earlier releases did (binary or unary with probability 1/2 each).
    arity_weights: dict[int, float] = field(default_factory=lambda: dict(DEFAULT_ARITY_WEIGHTS))
    allow_simple: bool = True
    allow_branches: bool = True
    max_substitution_depth: int | None = None  # None uses expressions.max_depth
    max_arity: int | None = None  # None keeps every arity in arity_weights
    max_if_branches: int = 10
    max_condition_comparisons: int | None = None  # None keeps the original rectangular regions
    condition_atoms: tuple[str, ...] = ()  # atom names applied to branch condition variables
    # Probability that a branch definition has no ``else`` and is undefined outside its regions.
    partial_probability: float = 0.0
    # Reject branch definitions with a branch that z3 proves unreachable.
    reject_dead_branches: bool = True
    # Reject subexpressions that use a parameter yet take one value wherever defined (a - a,
    # a % a); proved with z3. They are the main source of NaN (as divisors).
    reject_degenerate: bool = True
    # Total definitions must be defined on at least this share of inputs from the expression
    # value range (0 disables; intentionally partial definitions are exempt).
    min_defined_share: float = 0.95
    # Also reject branches whose body z3 proves always NaN. Costlier: it encodes whole bodies,
    # which grow deep in large operator sets; turn it off for very large runs.
    undefined_branch_check: bool = True
    # Effort of that check (encoding nodes; z3 gets a proportional deterministic resource limit).
    # Deterministic, so a seed always yields the same operators; undecided branches are accepted.
    dead_branch_budget: int = 600
    degenerate_budget: int = 200
    safety_timeout_ms: int = 30_000
    condition_min: int = 0
    condition_max: int = 100


@dataclass(frozen=True)
class RecursionSettings:
    # Template A (bounded_mod): the loop variable is reduced modulo m, so a recursive
    # operator unfolds at most m-1 times. Template B (direct): recurse on v-1 / v+1 for
    # |v| <= direct_bound, undefined beyond (docs/reference/semantics.md section 4.1).
    # Template D (primitive): the full primitive-recursion schema h(x, n) = g(x, n - 1, h(x, n - 1))
    # with the counter bounded like template B.
    style: str = "bounded_mod"  # "bounded_mod" | "direct" | "peano" (direct, stepping with ⁻ / ⁺) | "primitive"
    enabled: bool = True
    styles: tuple[str, ...] | None = None  # None uses style; otherwise sample from these templates
    max_recursive_calls: int = 2  # recursive result may occupy one or two callee slots
    modulus_min: int = 3
    modulus_max: int = 9
    direct_bound: int = 8
    search_enabled: bool = False
    search_bound: int = 8
    constant_min: int = -100
    constant_max: int = 100
    step_down: str = "⁻"
    step_up: str = "⁺"
    nonnegative: bool = False


@dataclass(frozen=True)
class ExpressionSettings:
    variables: tuple[str, ...] = ("a", "b")
    value_min: int = 0
    value_max: int = 100
    max_depth: int = 3
    type_weights: dict[str, float] = field(
        default_factory=lambda: {"binary": 0.7, "unary_prefix": 0.2, "unary_postfix": 0.1, "atom": 0.1}
    )
    atom_weights: dict[str, float] = field(default_factory=lambda: {"variable": 0.8, "number": 0.2})
    numeral_base: int = 10
    random_numeral_base: bool = False
    result_base: int = 10
    random_result_base: bool = False
    cot_base: int = 10


@dataclass(frozen=True)
class SolverSettings:
    fallback_range: tuple[int, int] | None = None
    rlimit: int = 5_000_000
    max_nodes: int = 300

    def __post_init__(self) -> None:
        if self.rlimit <= 0 or self.max_nodes <= 0:
            raise ValueError("solver.rlimit and solver.max_nodes must be positive")


INTEREST_COMPONENTS = ("novelty", "regularity", "reuse", "non_degeneracy", "compression")


@dataclass(frozen=True)
class InterestSettings:
    """Behavioural deduplication and interestingness scores (opulse.generation.interest).

    Everything is off by default; a default run computes none of it.
    """

    dedup: bool = False  # reject candidates whose value table repeats an existing operator's
    selection: str = "off"  # off | sample | best: choose each operator from a pool of candidates
    pool: int = 4  # accepted candidates drawn per operator when selection is on
    temperature: float = 0.1  # sample: candidate weight exp(score / temperature)
    weights: dict[str, float] = field(default_factory=lambda: dict.fromkeys(INTEREST_COMPONENTS, 1.0))
    # Integer probes, closed under negation; they reach the default condition and value range.
    probe_ints: tuple[int, ...] = (0, 1, 2, 3, 5, 7, 10, 17, 31, 50, 64, 83, 100,
                                   -1, -2, -3, -5, -7, -10, -17, -31, -50, -64, -83, -100)
    max_probe_points: int = 729  # cap on the probe grid; high arities use fewer values per argument
    regularity_range: int = 12  # monotonicity, periodicity and fixed points are read on [-R, R]
    max_period: int = 8
    solver_timeout_ms: int = 1000  # per solver question when regularities are confirmed

    def __post_init__(self) -> None:
        if self.selection not in ("off", "sample", "best"):
            raise ValueError("interest.selection must be off, sample or best")
        if self.pool < 1:
            raise ValueError("interest.pool must be at least 1")
        if self.temperature <= 0:
            raise ValueError("interest.temperature must be positive")
        unknown = set(self.weights) - set(INTEREST_COMPONENTS)
        if unknown:
            raise ValueError(f"interest.weights: unknown components {sorted(unknown)}")
        if any(w < 0 for w in self.weights.values()) or not any(self.weights.values()):
            raise ValueError("interest.weights must be non-negative with at least one positive weight")
        if sorted(self.probe_ints) != sorted(-v for v in self.probe_ints) or len(set(self.probe_ints)) < 3:
            raise ValueError("interest.probe_ints needs three or more distinct values, closed under negation")
        if self.max_probe_points < 8 or self.regularity_range < 2 or self.max_period < 2:
            raise ValueError("interest needs max_probe_points >= 8, regularity_range >= 2, max_period >= 2")

    @property
    def enabled(self) -> bool:
        return self.dedup or self.selection != "off"


@dataclass(frozen=True)
class Settings:
    preset: str | None = None
    semantics: SemanticsSettings = field(default_factory=SemanticsSettings)
    symbols: Symbols = field(default_factory=Symbols)
    numerals: Numerals = field(default_factory=Numerals)
    operators: OperatorSettings = field(default_factory=OperatorSettings)
    recursion: RecursionSettings = field(default_factory=RecursionSettings)
    expressions: ExpressionSettings = field(default_factory=ExpressionSettings)
    solver: SolverSettings = field(default_factory=SolverSettings)
    interest: InterestSettings = field(default_factory=InterestSettings)

    @classmethod
    def load(cls, path: str | Path, preset: str | None = None) -> Settings:
        import yaml  # imported here so that modules needing only Symbols do not require PyYAML

        with open(path, encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
        if "other_symbols_atoms" in raw or "expr_max_depth" in raw:
            raw = _from_legacy(raw)
        if preset is not None:
            raw["preset"] = preset
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Settings:
        raw = dict(raw)
        preset = raw.pop("preset", None)
        if preset is not None:
            from opulse.presets import PRESETS as NUMERIC_PRESETS, register_preset as register_numeric_preset
            from opulse.core.presets import PRESETS as TYPED_PRESETS, register_preset as register_typed_preset

            if preset in NUMERIC_PRESETS:
                register_numeric_preset(preset)
                defaults = NUMERIC_PRESETS[preset]["settings"]
            elif preset in TYPED_PRESETS:
                register_typed_preset(preset)
                defaults = {}
            else:
                raise ValueError(f"unknown preset {preset!r}")
            raw = {section: {**defaults.get(section, {}), **raw.get(section, {})}
                   for section in set(defaults) | set(raw)}
        sections = {
            "semantics": SemanticsSettings,
            "symbols": Symbols,
            "numerals": Numerals,
            "operators": OperatorSettings,
            "recursion": RecursionSettings,
            "expressions": ExpressionSettings,
            "solver": SolverSettings,
            "interest": InterestSettings,
        }
        unknown = set(raw) - set(sections)
        if unknown:
            raise ValueError(f"unknown config sections: {sorted(unknown)}")
        return cls(preset=preset, **{name: _build(section, raw.get(name, {})) for name, section in sections.items()})


def _build(section_cls, values: dict[str, Any]):
    known = {f.name for f in fields(section_cls)}
    unknown = set(values) - known
    if unknown:
        raise ValueError(f"unknown keys for {section_cls.__name__}: {sorted(unknown)}")
    for key in ("variables", "symbol_blocks", "symbol_sets", "shape_sets", "operand_names",
                "fallback_range", "condition_atoms", "styles", "probe_ints"):  # YAML lists -> hashable tuples
        if key in values:
            values = {**values, key: None if values[key] is None else tuple(values[key])}
    if section_cls is InterestSettings and "weights" in values:  # unnamed components keep weight 1
        values = {**values, "weights": {**dict.fromkeys(INTEREST_COMPONENTS, 1.0),
                                        **{k: float(w) for k, w in dict(values["weights"]).items()}}}
    if "arity_weights" in values:
        values = {**values, "arity_weights": normalize_arity_weights(values["arity_weights"])}
    return section_cls(**values)


def normalize_arity_weights(weights: dict) -> dict[int, float]:
    """Integer arities (YAML may give "3") with non-negative weights, at least one positive."""
    out = {}
    for key, weight in dict(weights).items():
        arity = int(key)
        if arity < 1:
            raise ValueError(f"operators.arity_weights: arity {key!r} must be 1 or more")
        if weight < 0:
            raise ValueError(f"operators.arity_weights: weight of arity {arity} is negative")
        out[arity] = float(weight)
    if not any(out.values()):
        raise ValueError("operators.arity_weights needs a positive weight")
    return out


# Settings added after a release: left out of the provenance hash while they keep their default,
# so records of an unchanged configuration stay byte-identical.
LATER_DEFAULTS = {
    ("symbols", "operand_names"): (),
    ("symbols", "argument_separator"): ",",
    ("operators", "arity_weights"): DEFAULT_ARITY_WEIGHTS,
    ("recursion", "search_enabled"): False,
    ("recursion", "search_bound"): 8,
    # Names: configs written before shape and index names meant the legacy symbols.
    ("operators", "naming"): "legacy",
    ("operators", "shape_sets"): ("shapes", "suits"),
    ("operators", "shape_chars"): "",
    ("operators", "index_chars"): "₀₁₂₃₄₅₆₇₈₉",
    ("operators", "definition_layout"): "compact",
    ("operators", "piecewise_min_length"): 120,
    ("operators", "definedness"): False,
    ("operators", "allow_simple"): True,
    ("operators", "allow_branches"): True,
    ("operators", "max_substitution_depth"): None,
    ("operators", "max_arity"): None,
    ("operators", "max_condition_comparisons"): None,
    ("operators", "condition_atoms"): (),
    ("recursion", "enabled"): True,
    ("recursion", "styles"): None,
    ("recursion", "max_recursive_calls"): 2,
    ("recursion", "step_down"): "⁻",
    ("recursion", "step_up"): "⁺",
    ("recursion", "nonnegative"): False,
    ("preset", None): None,
    ("semantics", "max_string_length"): 256,
    ("semantics", "max_list_length"): 256,
    ("semantics", "modulus"): None,
    ("operators", "degenerate_budget"): 200,
    ("operators", "safety_timeout_ms"): 30_000,
    # A whole later section is dropped while every key keeps its default.
    ("solver", None): {"fallback_range": None, "rlimit": 5_000_000, "max_nodes": 300},
    ("interest", None): asdict(InterestSettings()),
}


def stable_dict(settings: Settings) -> dict:
    """``asdict(settings)`` without later-added keys that still have their defaults."""
    from dataclasses import asdict

    data = asdict(settings)
    for (section, key), default in LATER_DEFAULTS.items():
        if key is None:
            if data.get(section) == default:
                del data[section]
        elif data[section].get(key) == default:
            del data[section][key]
    return data


def _from_legacy(raw: dict[str, Any]) -> dict[str, Any]:
    """Translate the old flat key layout into the sectioned one."""
    other = raw.get("other_symbols_atoms", {})
    variable_atoms = {k: v for item in raw.get("variable_atoms", []) for k, v in item.items()}
    expr_range = raw.get("expr_numeric_range", {})
    cond_range = raw.get("condition_numeric_range", {})
    variables = raw.get("expr_variables", ["a", "b"])
    if isinstance(variables, str):
        variables = [v.strip() for v in variables.split(",")]
    type_weights = dict(raw.get("expr_type_weights", {}))
    if "atoms" in type_weights:
        type_weights["atom"] = type_weights.pop("atoms")

    converted: dict[str, Any] = {
        # Legacy configs describe data made by the legacy arithmetic.
        "semantics": {"mode": "legacy", "bound": 2**31 - 1},
        "symbols": {
            "left_operand": variable_atoms.get("left_operand", "a"),
            "right_operand": variable_atoms.get("right_operand", "b"),
            "left_paren": other.get("left_parenthesis", "("),
            "right_paren": other.get("right_parenthesis", ")"),
            "equals": other.get("equals_sign", "="),
            "nan": other.get("nan_symbol", "NaN"),
            "inf": other.get("inf_symbol", "Inf"),
            "neg_inf": other.get("neg_inf_symbol", "-Inf"),
        },
        "numerals": {
            "max_base": raw.get("max_base", 16),
            "digits": raw.get("custom_digits", Numerals.digits),
        },
        "operators": {
            "symbol_min_len": raw.get("operator_symbol_min_len", 1),
            "naming": "legacy",
            "symbol_max_len": raw.get("operator_symbol_max_len", 3),
            # The legacy generator mixed the basic ASCII operators into new symbols.
            "symbol_ascii": "".join(raw.get("basic_operator_symbols", [])),
            # The legacy symbol pool: whole Unicode blocks.
            "symbol_sets": [],
            "symbol_blocks": ["2200-22FF", "2A00-2AFF", "2190-21FF"],
            "exclude_confusable": False,
            "max_if_branches": raw.get("max_if_branches", 10),
            "condition_min": cond_range.get("min_value", 0),
            "condition_max": cond_range.get("max_value", 100),
        },
        "expressions": {
            "variables": variables,
            "value_min": expr_range.get("min_value", 0),
            "value_max": expr_range.get("max_value", 100),
            "max_depth": raw.get("expr_max_depth", 3),
            "type_weights": type_weights or ExpressionSettings().type_weights,
            "atom_weights": raw.get("expr_atom_type_weights", ExpressionSettings().atom_weights),
        },
    }
    expressions = converted["expressions"]
    if "random_base" in raw:
        expressions["random_numeral_base"] = raw["random_base"]["flag"]
        expressions["numeral_base"] = raw["random_base"]["base"]
    if "result_base" in raw:
        expressions["random_result_base"] = raw["result_base"]["random_flag"]
        expressions["result_base"] = raw["result_base"]["base"]
    if "longer_result_compute" in raw:
        expressions["cot_base"] = raw["longer_result_compute"]["base"]
    return converted
