"""Phrases of the controlled English and Chinese definition languages.

Every phrase is a pattern of literal words and typed slots. One table drives both directions:
the realizer picks a phrase whose shape matches a node and fills the slots; the parser tries
every phrase and rebuilds the node. Slot types:

``A``  an atom: a parameter, a decimal literal or the NaN spelling
``N``  a decimal literal
``E``  an English operand: any expression in prefix (function) form; infix forms are excluded
``B``  a Chinese operand: an atom, or any expression inside 「 」
``T``  a top-level expression (adds the infix phrases)
``CMP`` a comparison; ``C`` a nested condition; ``G`` a guard (top-level condition)
``LHS`` the left-hand side in backticks; ``SYM`` an operator symbol in backticks
``WT`` an optional "where" tail that names subexpressions of a long body

A slot written ``{E:1}`` takes argument 1 (0-based) of the node, so a phrase can state the
arguments in another order ("subtracting b from a").

A phrase may start with a slot only when that slot cannot reach the phrase's own category at
the same position (no left recursion): infix phrases take atoms, Chinese phrases take
bracketed operands, comparisons take expressions.
"""

from __future__ import annotations

# (category, pattern, kind). ``kind`` says how slots map to a node:
#   ("atom", name)          application of the named atom, slots are its arguments
#   ("neglit",)             negation of a literal ("negative 5")
#   ("cmp", op)             comparison; ("zero", op) comparison with the literal 0
#   ("and",) ("or",) ("not",) ("group",) ("paren",)
#   ("andlist",) ("orlist",)  "A, B, C and D": a left-nested chain; ("pair",) ("cons",) build its list
#   ("head",) ("single",) ("if", "first"|"later") ("else",) ("always",) ("trail",)
#   ("wt_none",) ("wt",) ("wl_one",) ("wl_more",)

ATOM_SYMBOL = "{SYMBOL}"  # replaced by the atom's registered symbol

EN = [
    # ------------------------------------------------------------ arithmetic
    ("E", "the sum of {E} and {E}", ("atom", "add")),
    ("T", "{A} plus {A}", ("atom", "add")),
    ("E", "the difference of {E} and {E}", ("atom", "sub")),
    ("E", "the result of subtracting {E:1} from {E:0}", ("atom", "sub")),
    ("T", "{A} minus {A}", ("atom", "sub")),
    ("E", "the product of {E} and {E}", ("atom", "mul")),
    ("T", "{A} times {A}", ("atom", "mul")),
    ("E", "the quotient of {E} divided by {E}", ("atom", "div")),
    ("E", "the result of dividing {E} by {E}", ("atom", "div")),
    ("T", "{A} divided by {A}", ("atom", "div")),
    ("E", "the remainder of {E} divided by {E}", ("atom", "mod")),
    ("E", "the remainder when {E} is divided by {E}", ("atom", "mod")),
    ("T", "{A} modulo {A}", ("atom", "mod")),
    ("E", "the negation of {E}", ("atom", "neg")),
    ("E", "the opposite of {E}", ("atom", "neg")),
    ("E", "negative {N}", ("neglit",)),
    ("T", "minus {A}", ("atom", "neg")),
    ("E", "the successor (`{SYMBOL}`) of {E}", ("atom", "succ")),
    ("E", "the predecessor (`{SYMBOL}`) of {E}", ("atom", "pred")),
    ("E", "the double (`{SYMBOL}`) of {E}", ("atom", "double")),
    ("E", "the half (`{SYMBOL}`) of {E}", ("atom", "half")),
    ("E", "the parity (`{SYMBOL}`) of {E}", ("atom", "parity")),
    ("E", "the digit reversal (`{SYMBOL}`) of {E}", ("atom", "reverse")),
    ("E", "the signed triangular number (`{SYMBOL}`) of {E}", ("atom", "triangle")),
    ("E", "the bit count (`{SYMBOL}`) of {E}", ("atom", "popcount")),
    ("E", "the signed digit sum (`{SYMBOL}`) of {E}", ("atom", "digitsum")),
    ("E", "( {T} )", ("paren",)),
    # ------------------------------------------------------------ comparisons
    ("CMP", "{T} is greater than {T}", ("cmp", ">")),
    ("CMP", "{T} exceeds {T}", ("cmp", ">")),
    ("CMP", "{T} is larger than {T}", ("cmp", ">")),
    ("CMP", "{T} is less than {T}", ("cmp", "<")),
    ("CMP", "{T} is smaller than {T}", ("cmp", "<")),
    ("CMP", "{T} is below {T}", ("cmp", "<")),
    ("CMP", "{T} is at least {T}", ("cmp", ">=")),
    ("CMP", "{T} is greater than or equal to {T}", ("cmp", ">=")),
    ("CMP", "{T} is at most {T}", ("cmp", "<=")),
    ("CMP", "{T} is less than or equal to {T}", ("cmp", "<=")),
    ("CMP", "{T} does not exceed {T}", ("cmp", "<=")),
    ("CMP", "{T} equals {T}", ("cmp", "==")),
    ("CMP", "{T} is equal to {T}", ("cmp", "==")),
    ("CMP", "{T} is not equal to {T}", ("cmp", "!=")),
    ("CMP", "{T} differs from {T}", ("cmp", "!=")),
    ("CMP", "{T} does not equal {T}", ("cmp", "!=")),
    ("CMP", "{T} is positive", ("zero", ">")),
    ("CMP", "{T} is negative", ("zero", "<")),
    ("CMP", "{T} is zero", ("zero", "==")),
    ("CMP", "{T} is nonzero", ("zero", "!=")),
    ("CMP", "{T} is nonnegative", ("zero", ">=")),
    ("CMP", "{T} is nonpositive", ("zero", "<=")),
    # ------------------------------------------------------------ logic
    ("C", "both {C} and {C}", ("and",)),
    ("C", "either {C} or {C}", ("or",)),
    ("C", "it is not the case that {C}", ("not",)),
    ("C", "it is false that {C}", ("not",)),
    ("C", "( {G} )", ("group",)),
    ("G", "{C} and {C}", ("and",)),
    ("G", "{C} or {C}", ("or",)),
    ("G", "{C}, {AL}", ("andlist",)),
    ("AL", "{C} and {C}", ("pair",)),
    ("AL", "{C}, {AL}", ("cons",)),
    ("G", "{C}, {OL}", ("orlist",)),
    ("OL", "{C} or {C}", ("pair",)),
    ("OL", "{C}, {OL}", ("cons",)),
    # ------------------------------------------------------------ sentences
    ("S_HEAD", "{LHS} is defined by cases, tried in order:", ("head",)),
    ("S_HEAD", "The cases of {LHS} are checked in order, and the first that applies gives the value:",
     ("head",)),
    ("S_HEAD", "To evaluate {LHS}, go through the cases in order:", ("head",)),
    ("S_SINGLE", "{LHS} is defined as {T}{WT}.", ("single",)),
    ("S_SINGLE", "For all inputs, {LHS} equals {T}{WT}.", ("single",)),
    ("S_SINGLE", "The value of {LHS} is always {T}{WT}.", ("single",)),
    ("S_CASE", "If {G}, the result is {T}{WT}.", ("if", "first")),
    ("S_CASE", "When {G}, the value is {T}{WT}.", ("if", "first")),
    ("S_CASE", "In case {G}, it equals {T}{WT}.", ("if", "first")),
    ("S_CASE", "Otherwise, if {G}, the result is {T}{WT}.", ("if", "later")),
    ("S_CASE", "Else, when {G}, the value is {T}{WT}.", ("if", "later")),
    ("S_CASE", "Failing that, if {G}, it equals {T}{WT}.", ("if", "later")),
    ("S_CASE", "Otherwise, the result is {T}{WT}.", ("else",)),
    ("S_CASE", "In all remaining cases, the value is {T}{WT}.", ("else",)),
    ("S_CASE", "Else, it equals {T}{WT}.", ("else",)),
    ("S_CASE", "Next, unconditionally, the result is {T}{WT}.", ("always",)),
    ("S_CASE", "From here on, unconditionally, it equals {T}{WT}.", ("always",)),
    ("S_TRAIL", "If no case applies, the result is {NAN}.", ("trail",)),
    ("S_TRAIL", "When none of the cases holds, the value is undefined ({NAN}).", ("trail",)),
    ("WT", "", ("wt_none",)),
    ("WT", ", where {WL}", ("wt",)),
    ("WL", "{V} is {T}", ("wl_one",)),
    ("WL", "{V} is {T}, and {WL}", ("wl_more",)),
]

# Generic application of any operator by its symbol (defined operators and registered atoms).
EN_GENERIC_UNARY = ["{SYM} of {E}", "the value of {SYM} at {E}"]
EN_GENERIC_QUALIFIED = ["{QUAL} {SYM} of {E}"]
EN_GENERIC_NARY = ["{SYM} applied to {ARGS}", "the result of {SYM} on {ARGS}"]
EN_QUALIFIERS = {"prefix": "prefix", "postfix": "postfix"}

ZH = [
    ("T", "{B} 与 {B} 之和", ("atom", "add")),
    ("T", "{B} 加 {B}", ("atom", "add")),
    ("T", "{B} 加上 {B}", ("atom", "add")),
    ("T", "{B} 与 {B} 之差", ("atom", "sub")),
    ("T", "{B} 减 {B}", ("atom", "sub")),
    ("T", "从 {B:0} 中减去 {B:1} 的结果", ("atom", "sub")),
    ("T", "{B} 与 {B} 之积", ("atom", "mul")),
    ("T", "{B} 乘 {B}", ("atom", "mul")),
    ("T", "{B} 乘以 {B}", ("atom", "mul")),
    ("T", "{B} 除以 {B} 的商", ("atom", "div")),
    ("T", "用 {B:1} 除 {B:0} 所得的商", ("atom", "div")),
    ("T", "{B} 除以 {B} 的余数", ("atom", "mod")),
    ("T", "{B} 对 {B} 取余的结果", ("atom", "mod")),
    ("T", "{B} 的相反数", ("atom", "neg")),
    ("T", "负 {N}", ("neglit",)),
    ("T", "{B} 取负的结果", ("atom", "neg")),
    ("T", "{B} 的后继（`{SYMBOL}`）", ("atom", "succ")),
    ("T", "{B} 的前驱（`{SYMBOL}`）", ("atom", "pred")),
    ("T", "{B} 的两倍（`{SYMBOL}`）", ("atom", "double")),
    ("T", "{B} 的一半（`{SYMBOL}`）", ("atom", "half")),
    ("T", "{B} 的奇偶位（`{SYMBOL}`）", ("atom", "parity")),
    ("T", "{B} 的数字反转（`{SYMBOL}`）", ("atom", "reverse")),
    ("T", "{B} 的带符号三角数（`{SYMBOL}`）", ("atom", "triangle")),
    ("T", "{B} 的二进制 1 的个数（`{SYMBOL}`）", ("atom", "popcount")),
    ("T", "{B} 的带符号数字和（`{SYMBOL}`）", ("atom", "digitsum")),
    ("B", "「{T}」", ("paren",)),
    ("CMP", "{T} 大于 {T}", ("cmp", ">")),
    ("CMP", "{T} 比 {T} 大", ("cmp", ">")),
    ("CMP", "{T} 小于 {T}", ("cmp", "<")),
    ("CMP", "{T} 比 {T} 小", ("cmp", "<")),
    ("CMP", "{T} 大于或等于 {T}", ("cmp", ">=")),
    ("CMP", "{T} 不小于 {T}", ("cmp", ">=")),
    ("CMP", "{T} 小于或等于 {T}", ("cmp", "<=")),
    ("CMP", "{T} 不大于 {T}", ("cmp", "<=")),
    ("CMP", "{T} 等于 {T}", ("cmp", "==")),
    ("CMP", "{T} 与 {T} 相等", ("cmp", "==")),
    ("CMP", "{T} 不等于 {T}", ("cmp", "!=")),
    ("CMP", "{T} 与 {T} 不相等", ("cmp", "!=")),
    ("CMP", "{T} 为正", ("zero", ">")),
    ("CMP", "{T} 为负", ("zero", "<")),
    ("CMP", "{T} 为零", ("zero", "==")),
    ("CMP", "{T} 不为零", ("zero", "!=")),
    ("CMP", "{T} 非负", ("zero", ">=")),
    ("CMP", "{T} 非正", ("zero", "<=")),
    ("C", "「{G}」", ("group",)),
    ("C", "并非 {C}", ("not",)),
    ("G", "{C} 且 {C}", ("and",)),
    ("G", "{C} 并且 {C}", ("and",)),
    ("G", "{C} 或 {C}", ("or",)),
    ("G", "{C} 或者 {C}", ("or",)),
    ("G", "{C}、{AL}", ("andlist",)),
    ("AL", "{C} 且 {C}", ("pair",)),
    ("AL", "{C}、{AL}", ("cons",)),
    ("G", "{C}、{OL}", ("orlist",)),
    ("OL", "{C} 或 {C}", ("pair",)),
    ("OL", "{C}、{OL}", ("cons",)),
    ("S_HEAD", "{LHS} 分情形定义，按顺序判断：", ("head",)),
    ("S_HEAD", "按顺序检查以下情形，第一个成立的情形给出 {LHS} 的值：", ("head",)),
    ("S_HEAD", "计算 {LHS} 时，依次判断下列情形：", ("head",)),
    ("S_SINGLE", "{LHS} 定义为 {T}{WT}。", ("single",)),
    ("S_SINGLE", "对任意输入，{LHS} 等于 {T}{WT}。", ("single",)),
    ("S_SINGLE", "{LHS} 的值恒为 {T}{WT}。", ("single",)),
    ("S_CASE", "若 {G}，则结果为 {T}{WT}。", ("if", "first")),
    ("S_CASE", "当 {G} 时，值为 {T}{WT}。", ("if", "first")),
    ("S_CASE", "如果 {G}，那么结果是 {T}{WT}。", ("if", "first")),
    ("S_CASE", "否则，若 {G}，则结果为 {T}{WT}。", ("if", "later")),
    ("S_CASE", "否则当 {G} 时，值为 {T}{WT}。", ("if", "later")),
    ("S_CASE", "不然，如果 {G}，那么结果是 {T}{WT}。", ("if", "later")),
    ("S_CASE", "否则，结果为 {T}{WT}。", ("else",)),
    ("S_CASE", "其余情形下，值为 {T}{WT}。", ("else",)),
    ("S_CASE", "接着，无条件地，结果为 {T}{WT}。", ("always",)),
    ("S_TRAIL", "若以上情形都不成立，结果为 {NAN}。", ("trail",)),
    ("S_TRAIL", "没有情形成立时，值为 {NAN}（未定义）。", ("trail",)),
    ("WT", "", ("wt_none",)),
    ("WT", "，其中 {WL}", ("wt",)),
    ("WL", "{V} 为 {T}", ("wl_one",)),
    ("WL", "{V} 为 {T}，{WL}", ("wl_more",)),
]

ZH_GENERIC_UNARY = ["{SYM} 作用于 {B} 的结果", "对 {B} 施加 {SYM} 的结果"]
ZH_GENERIC_QUALIFIED = ["{QUAL} {SYM} 作用于 {B} 的结果"]
ZH_GENERIC_NARY = ["{SYM} 作用于 {ARGS} 的结果", "对 {ARGS} 施加 {SYM} 的结果"]
ZH_QUALIFIERS = {"prefix": "前缀运算", "postfix": "后缀运算"}

# Category inclusion: a slot of the key category also accepts the listed categories.
EN_INCLUDES = {"T": ("E",), "E": ("A",), "G": ("C",), "C": ("CMP",)}
ZH_INCLUDES = {"T": ("B",), "B": ("A",), "G": ("C",), "C": ("CMP",)}

# Names that a long body may introduce for its parts ("where u is ...").
WHERE_NAMES = ("u", "v", "w", "p", "q", "r", "s", "t", "k", "m")

LEXICONS = {
    "en": {"rules": EN, "unary": EN_GENERIC_UNARY, "qualified": EN_GENERIC_QUALIFIED, "nary": EN_GENERIC_NARY,
               "qualifiers": EN_QUALIFIERS, "includes": EN_INCLUDES, "operand": "E", "generic": "E", "separator": ",", "last": "and"},
    "zh": {"rules": ZH, "unary": ZH_GENERIC_UNARY, "qualified": ZH_GENERIC_QUALIFIED, "nary": ZH_GENERIC_NARY,
               "qualifiers": ZH_QUALIFIERS, "includes": ZH_INCLUDES, "operand": "B", "generic": "T", "separator": "、", "last": "与"},
}
