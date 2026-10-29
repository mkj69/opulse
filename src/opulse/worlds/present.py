"""Names and plain sentences for the operators shown in the world showcases.

``operator_names`` keeps each generated operator's shape and assigns a short subscript
in showcase display order. The map is shared by the browser and task exporters.

``Describer`` writes one English and one Chinese sentence per operator from its parsed
definition. Every atom has a verb phrase and a noun phrase in each language (``LEXICON``);
a chain of applications is read inner first ("sum the digits of b, then multiply it by
..."), cases become "if ..., otherwise ..." clauses, and the bounded recursion templates are
read as repetition when every level applies the same step. ``Description.mentions`` lists
every operator symbol, parameter and constant that the sentence names; the showcase tests
check it against the definition, and they check each repetition reading by evaluation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from opulse.core.semantics import base_operation_name
from opulse.definition import ast

SUBSCRIPT_DIGITS = "₀₁₂₃₄₅₆₇₈₉"


def _subscript(number: int) -> str:
    return str(number).translate(str.maketrans("0123456789", SUBSCRIPT_DIGITS))


def operator_names(operators, settings=None, reserved=(), seed: int = 0) -> dict[str, str]:
    """Renumber defined operators 1..N in display order without changing their shapes."""
    names = {}
    for index, op in enumerate(operators, 1):
        match = re.fullmatch(r"(.+?)[₀-₉]+", op.symbol)
        if match is None:
            raise ValueError(f"generated operator has no subscript: {op.symbol}")
        names[op.symbol] = match.group(1) + _subscript(index)
    if len(names) != len(operators) or len(set(names.values())) != len(names):
        raise ValueError("showcase operator names must be unique")
    if set(names.values()) & set(reserved):
        raise ValueError("showcase operator names overlap atom symbols")
    return names


def alias(text: str, names: dict[str, str]) -> str:
    """Replace generated symbols by their display names, longest symbols first."""
    if not names:
        return text
    pattern = re.compile("(?:" + "|".join(re.escape(key) for key in sorted(names, key=len, reverse=True))
                         + ")(?![₀-₉])")
    return pattern.sub(lambda match: names[match.group()], text)


# --------------------------------------------------------------------------- lexicon
# name: (English verb phrase, English noun phrase, Chinese verb phrase, Chinese noun phrase,
#        formula or None, subject index). {0} and {1} are the arguments. A verb phrase is an
# instruction whose subject is argument ``subject``; later steps of a chain call it "it".

@dataclass(frozen=True)
class Entry:
    en_do: str
    en_np: str
    zh_do: str
    zh_np: str
    formula: str | None = None
    subject: int = 0
    en_if: str | None = None   # condition wording for atoms with a truth value
    zh_if: str | None = None


def _e(*args, **kwargs) -> Entry:
    return Entry(*args, **kwargs)


LEXICON: dict[str, Entry] = {
    # integers
    "add": _e("add {1} to {0}", "the sum of {0} and {1}", "把{0}加上{1}", "{0}与{1}之和", "{0} + {1}"),
    "sub": _e("subtract {1} from {0}", "{0} minus {1}", "从{0}中减去{1}", "{0}减{1}的差", "{0} - {1}"),
    "mul": _e("multiply {0} by {1}", "the product of {0} and {1}", "把{0}乘以{1}", "{0}与{1}之积", "{0} * {1}"),
    "div": _e("divide {0} by {1}, rounding toward zero", "{0} divided by {1}, rounded toward zero",
              "把{0}除以{1}并向零取整", "{0}除以{1}向零取整的商", "{0} / {1}"),
    "mod": _e("take the remainder when dividing {0} by {1}",
              "the remainder when dividing {0} by {1}",
              "求{0}除以{1}的余数", "{0}除以{1}的余数", "{0} % {1}"),
    "neg": _e("negate {0}", "the negative of {0}", "把{0}取相反数", "{0}的相反数", "-{0}"),
    "reverse": _e("reverse the digits of {0}", "{0} with its digits reversed", "把{0}的数字倒过来写",
                  "{0}的数字倒写", None),
    "triangle": _e("take the signed triangle number of {0}", "the signed triangle number of {0}",
                   "求{0}的带符号三角数", "{0}的带符号三角数"),
    "popcount": _e("count the one bits of {0}", "the number of one bits in {0}",
                   "数{0}的二进制里有几个 1", "{0}的二进制中 1 的个数"),
    "digitsum": _e("sum the digits of {0}", "the digit sum of {0}", "求{0}的各位数字之和", "{0}的数字和"),
    "succ": _e("add one to {0}", "{0} plus one", "把{0}加一", "{0}加一", "{0} + 1"),
    "pred": _e("subtract one from {0}", "{0} minus one", "把{0}减一", "{0}减一", "{0} - 1"),
    "double": _e("double {0}", "twice {0}", "把{0}翻倍", "{0}的两倍", "2 * {0}"),
    "half": _e("halve {0}, rounding toward zero", "half of {0}", "把{0}减半", "{0}的一半"),
    "parity": _e("take the lowest bit of {0}", "the lowest bit of {0}", "取{0}的最低位", "{0}的最低位"),
    # successor
    "natural_succ": _e("add one to {0}", "{0} plus one", "把{0}加一", "{0}加一"),
    "natural_pred": _e("subtract one from {0}, stopping at zero", "{0} minus one, stopping at zero",
                       "把{0}减一（最小到零）", "{0}减一（最小到零）的值"),
    "is_zero": _e("test whether {0} is zero, giving 1 or 0", "1 if {0} is zero and 0 otherwise",
                  "判断{0}是否为零（是得 1，否得 0）", "{0}是否为零（是为 1，否为 0）"),
    # bits
    "bit_and": _e("AND {0} with {1} bit by bit", "the bitwise AND of {0} and {1}", "把{0}与{1}按位与",
                  "{0}与{1}的按位与"),
    "bit_or": _e("OR {0} with {1} bit by bit", "the bitwise OR of {0} and {1}", "把{0}与{1}按位或",
                 "{0}与{1}的按位或"),
    "bit_xor": _e("XOR {0} with {1} bit by bit", "the bitwise XOR of {0} and {1}", "把{0}与{1}按位异或",
                  "{0}与{1}的按位异或"),
    "shift_left": _e("shift {0} left by {1} bits", "{0} shifted left by {1} bits", "把{0}左移{1}位",
                     "{0}左移{1}位的值"),
    "shift_right": _e("shift {0} right by {1} bits", "{0} shifted right by {1} bits", "把{0}右移{1}位",
                      "{0}右移{1}位的值"),
    "bit_count": _e("count the one bits of {0}", "the number of one bits in {0}",
                    "数{0}的二进制里有几个 1", "{0}的二进制中 1 的个数"),
    # strings
    "str_concat": _e("append {1} to {0}", "{0} followed by {1}", "在{0}后面接上{1}", "{0}后接{1}"),
    "str_length": _e("count the characters of {0}", "the length of {0}", "数{0}有几个字符", "{0}的长度"),
    "str_reverse": _e("reverse {0}", "{0} reversed", "把{0}倒过来", "倒过来的{0}"),
    "str_first": _e("keep only the first character of {0}", "the first character of {0}",
                    "只保留{0}的第一个字符", "{0}的第一个字符"),
    "str_drop": _e("drop the first character of {0}", "{0} without its first character",
                   "去掉{0}的第一个字符", "去掉首字符的{0}"),
    "str_upper": _e("turn {0} into uppercase", "{0} in uppercase", "把{0}转成大写", "大写的{0}"),
    "str_lower": _e("turn {0} into lowercase", "{0} in lowercase", "把{0}转成小写", "小写的{0}"),
    "str_equal": _e("test whether {0} equals {1}", "whether {0} equals {1}", "判断{0}是否等于{1}",
                    "{0}是否等于{1}", en_if="{0} equals {1}", zh_if="{0}等于{1}"),
    # lists
    "list_cons": _e("put {0} at the front of {1}", "{1} with {0} put in front", "把{0}放到{1}最前面",
                    "前面加上{0}的{1}", subject=1),
    "list_head": _e("take the first element of {0}", "the first element of {0}", "取{0}的第一个元素",
                    "{0}的第一个元素"),
    "list_tail": _e("drop the first element of {0}", "{0} without its first element",
                    "去掉{0}的第一个元素", "去掉首元素的{0}"),
    "list_length": _e("count the elements of {0}", "the length of {0}", "数{0}有几个元素", "{0}的长度"),
    "list_append": _e("append {1} to {0}", "{0} followed by {1}", "在{0}后面接上{1}", "{0}后接{1}"),
    "list_sum": _e("add up the elements of {0}", "the sum of the elements of {0}", "把{0}的元素加起来",
                   "{0}的元素和"),
    "list_at": _e("take element {1} of {0}, counting from zero", "element {1} of {0}",
                  "取{0}中下标为{1}的元素", "{0}中下标为{1}的元素"),
    "list_equal": _e("test whether {0} equals {1}", "whether {0} equals {1}", "判断{0}是否等于{1}",
                     "{0}是否等于{1}", en_if="{0} equals {1}", zh_if="{0}等于{1}"),
    # logic
    "logic_and": _e("AND {0} with {1}", "{0} and {1}", "把{0}与{1}做与运算", "{0}与{1}", "{0} ⋀ {1}",
                    en_if="{0} and {1} are both true", zh_if="{0}与{1}都为真"),
    "logic_or": _e("OR {0} with {1}", "{0} or {1}", "把{0}与{1}做或运算", "{0}或{1}", "{0} ⋁ {1}",
                   en_if="{0} or {1} is true", zh_if="{0}与{1}至少一个为真"),
    "logic_not": _e("negate {0}", "not {0}", "对{0}取反", "{0}的否定", "¬{0}",
                    en_if="{0} is false", zh_if="{0}为假"),
    "logic_implies": _e("form {0} implies {1}", "{0} implies {1}", "计算{0}蕴含{1}", "{0}蕴含{1}",
                        "{0} → {1}", en_if="{0} implies {1}", zh_if="{0}蕴含{1}"),
    "logic_xor": _e("XOR {0} with {1}", "{0} differs from {1}", "把{0}与{1}做异或", "{0}与{1}的异或",
                    "{0} ≢ {1}", en_if="{0} and {1} differ", zh_if="{0}与{1}真假不同"),
    "logic_equal": _e("test whether {0} and {1} agree", "whether {0} and {1} agree",
                      "判断{0}与{1}真假是否相同", "{0}与{1}是否同真假", "{0} ⇔ {1}",
                      en_if="{0} and {1} agree", zh_if="{0}与{1}真假相同"),
    # permutations of cards
    "swap": _e("swap cards in {0} using {1} as a position code",
               "{0} with cards swapped using {1} as a position code",
               "按{1}交换{0}中的两张卡片", "按{1}交换两张卡片后的{0}"),
    "rotate_left": _e("rotate {0} one place left", "{0} rotated one place left", "把{0}向左轮转一格",
                      "向左轮转一格的{0}"),
    "rotate_right": _e("rotate {0} one place right", "{0} rotated one place right", "把{0}向右轮转一格",
                       "向右轮转一格的{0}"),
    "perm_reverse": _e("reverse the order of {0}", "{0} with positions reversed", "把{0}的位置顺序倒过来",
                       "位置倒序的{0}"),
    "perm_compose": _e("follow {0} with {1}", "{0} followed by {1}", "在{0}之后接着做{1}", "{0}接着{1}"),
    "perm_inverse": _e("invert {0}", "the inverse of {0}", "求{0}的逆排列", "{0}的逆排列"),
    "perm_apply": _e("find where card {1} goes under {0}", "the position of card {1} under {0}",
                     "求卡片{1}在{0}下去到的位置", "卡片{1}在{0}下的位置"),
    "perm_equal": _e("test whether {0} equals {1}", "whether {0} equals {1}", "判断{0}是否等于{1}",
                     "{0}是否等于{1}", en_if="{0} equals {1}", zh_if="{0}等于{1}"),
    # relations
    "rel_parent": _e("look up the parent of {0}", "the parent of {0}", "查{0}的父母", "{0}的父母"),
    "rel_colleague": _e("look up the colleague of {0}", "the colleague of {0}", "查{0}的同事", "{0}的同事"),
    "rel_neighbour": _e("look up the neighbour of {0}", "the neighbour of {0}", "查{0}的邻居", "{0}的邻居"),
    "rel_equal": _e("test whether {0} equals {1}", "whether {0} equals {1}", "判断{0}是否等于{1}",
                    "{0}是否等于{1}", en_if="{0} equals {1}", zh_if="{0}等于{1}"),
    # grids
    "grid_rotate": _e("rotate {0} 90 degrees clockwise", "{0} rotated 90 degrees clockwise",
                      "把{0}顺时针转 90 度", "顺时针转 90 度的{0}"),
    "grid_reflect_h": _e("mirror {0} left to right", "{0} mirrored left to right", "把{0}左右翻转",
                         "左右翻转的{0}"),
    "grid_reflect_v": _e("flip {0} upside down", "{0} flipped upside down", "把{0}上下翻转", "上下翻转的{0}"),
    "grid_transpose": _e("transpose {0}", "the transpose of {0}", "把{0}转置", "{0}的转置"),
    "grid_wrap_right": _e("wrap {0} right by {1} columns", "{0} wrapped right by {1} columns",
                          "把{0}向右循环移动{1}列", "向右循环移动{1}列的{0}"),
    "grid_wrap_down": _e("wrap {0} down by {1} rows", "{0} wrapped down by {1} rows",
                         "把{0}向下循环移动{1}行", "向下循环移动{1}行的{0}"),
    "grid_shift_right": _e("shift {0} right by {1} columns, filling with 0", "{0} shifted right by {1} columns",
                           "把{0}向右平移{1}列，空位补 0", "向右平移{1}列的{0}"),
    "grid_shift_down": _e("shift {0} down by {1} rows, filling with 0", "{0} shifted down by {1} rows",
                          "把{0}向下平移{1}行，空位补 0", "向下平移{1}行的{0}"),
    "grid_recolour": _e("use {1} as a two digit code to recolour {0}",
                        "{0} recoloured using {1} as a two digit code",
                        "按两位编码{1}给{0}换色", "按编码{1}换色的{0}"),
    "grid_overlay": _e("lay the nonzero cells of {1} over {0}", "{0} with {1} laid over it",
                       "把{1}的非零格盖到{0}上", "盖上{1}的{0}"),
    "grid_crop": _e("crop {0} to the smallest rectangle that holds all its nonzero cells",
                    "{0} cropped to the smallest rectangle that holds all its nonzero cells",
                    "把{0}裁成包含所有非零格的最小矩形", "包含{0}所有非零格的最小矩形"),
    "grid_count": _e("count the cells of colour {1} in {0}", "the number of colour {1} cells in {0}",
                     "数{0}中颜色{1}的格子", "{0}中颜色{1}的格子数"),
    "grid_fill": _e("fill the empty cells of {0} with colour {1}", "{0} with empty cells in colour {1}",
                    "用颜色{1}填满{0}的空格", "空格填成颜色{1}的{0}"),
    "grid_equal": _e("test whether {0} equals {1}", "whether {0} equals {1}", "判断{0}是否等于{1}",
                     "{0}是否等于{1}", en_if="{0} equals {1}", zh_if="{0}等于{1}"),
    # pitch
    "pitch_transpose": _e("transpose {0} by {1} semitones", "{0} moved by {1} semitones",
                          "把{0}移动{1}个半音", "移动{1}个半音的{0}"),
    "pitch_octave_up": _e("raise {0} an octave", "{0} an octave higher", "把{0}升高八度", "升高八度的{0}"),
    "pitch_octave_down": _e("lower {0} an octave", "{0} an octave lower", "把{0}降低八度", "降低八度的{0}"),
    "pitch_interval": _e("measure the semitones from {0} to {1}", "the semitones from {0} to {1}",
                         "求从{0}到{1}的半音数", "从{0}到{1}的半音数"),
    "pitch_invert": _e("mirror {0} around {1}", "{0} mirrored around {1}", "以{1}为轴翻转{0}",
                       "以{1}为轴翻转的{0}"),
    "pitch_retrograde": _e("reverse the notes in {0}", "{0} with its notes in reverse order",
                            "把{0}的音符顺序倒过来", "音符倒序的{0}"),
    "pitch_scale_step": _e("move {0} up one step of C major", "the next C major note above {0}",
                           "把{0}升到 C 大调的下一个音", "{0}之上 C 大调的下一个音"),
    "pitch_major_triad": _e("build a major triad on {0}", "the major triad on {0}", "以{0}为根音搭大三和弦",
                            "以{0}为根音的大三和弦"),
    "pitch_minor_triad": _e("build a minor triad on {0}", "the minor triad on {0}", "以{0}为根音搭小三和弦",
                            "以{0}为根音的小三和弦"),
    "pitch_repeat": _e("repeat {0} {1} times", "{0} repeated {1} times", "把{0}重复{1}遍", "重复{1}遍的{0}"),
    "pitch_concat": _e("append {1} to {0}", "{0} followed by {1}", "在{0}后面接上{1}", "{0}后接{1}"),
    "pitch_melody_equal": _e("test whether {0} equals {1}", "whether {0} equals {1}", "判断{0}是否等于{1}",
                             "{0}是否等于{1}", en_if="{0} equals {1}", zh_if="{0}等于{1}"),
    "pitch_note_equal": _e("test whether {0} is the same note as {1}", "whether {0} is the same note as {1}",
                           "判断{0}与{1}是否同音", "{0}与{1}是否同音",
                           en_if="{0} is the same note as {1}", zh_if="{0}与{1}同音"),
}


def add_lexicon(entries: dict[str, Entry]) -> None:
    """Register phrases for atoms that a world adds outside this module."""
    LEXICON.update(entries)


# --------------------------------------------------------------------------- phrases

_COMPARE = {"==": "=", "!=": "≠", "<=": "≤", ">=": "≥", "<": "<", ">": ">"}
_CJK = r"㐀-鿿（），、。；："


def zh_spacing(text: str) -> str:
    """One space between Chinese text and Latin letters, digits or symbols."""
    text = re.sub(rf"([㐀-鿿])([^\s{_CJK}「」])", r"\1 \2", text)
    text = re.sub(rf"([^\s{_CJK}「」])([㐀-鿿])", r"\1 \2", text)
    return text


@dataclass
class Phrase:
    """A noun: its text in each language and whether it is a formula (no words)."""

    en: str
    zh: str
    formula: bool


@dataclass
class Description:
    en: str
    zh: str
    mentions: set = field(default_factory=set)  # operator symbols, parameters, constants named
    reading: str = "direct"  # direct | repetition | summary
    repetition: dict | None = None  # how a repetition reading is checked


class Describer:
    """Plain sentences for defined operators, read from their parsed definitions."""

    MAX_EN = 240

    def __init__(self, registry, names: dict[str, str], parser, value_text=None) -> None:
        self.registry = registry
        self.names = names
        self._display_renamed = any(symbol != shown for symbol, shown in names.items())
        self.parser = parser
        self.value_text = value_text or (lambda value, kind: None)
        self._holes: dict[str, tuple[str, str]] = {}

    # ---- helpers
    def _operator(self, node: ast.Apply):
        return self.registry.find(node.symbol, node.n_ary, node.unary_position)

    def _entry(self, node: ast.Apply):
        name = base_operation_name(node.symbol, node.n_ary, node.unary_position)
        return LEXICON.get(name) if name else None

    def _show(self, symbol: str) -> str:
        return self.names.get(symbol, symbol)

    def _constant(self, value, kind, lang="en"):
        custom = self.value_text(value, kind)
        if custom:
            return custom[0 if lang == "en" else 1] if isinstance(custom, tuple) else custom
        if isinstance(value, bool):
            return ("true" if value else "false") if lang == "en" else ("真" if value else "假")
        if isinstance(value, str):
            return '"' + value + '"'
        if isinstance(value, tuple) and value and isinstance(value[0], tuple):
            return "[" + ", ".join("[" + ", ".join(map(str, row)) + "]" for row in value) + "]"
        if isinstance(value, tuple):
            return "[" + ", ".join(map(str, value)) + "]"
        return str(value)

    def _formula(self, node, kind=None, lang="en") -> str:
        """The expression as Opulse writes it, with display names."""
        if isinstance(node, ast.Var):
            return node.name
        if isinstance(node, ast.Num):
            return self._constant(node.value, kind, lang)
        if isinstance(node, ast.Literal):
            return self._constant(node.value, kind, lang)
        if isinstance(node, ast.NaN):
            return "NaN"
        types = self._param_types(node)
        parts = [self._formula(arg, kinds, lang) for arg, kinds in zip(node.args, types)]
        parts = [f"({part})" if isinstance(arg, ast.Apply) and not self._is_negative(arg) else part
                 for part, arg in zip(parts, node.args)]
        symbol = self._show(node.symbol)
        if node.n_ary == 2:
            return f"{parts[0]} {symbol} {parts[1]}"
        if node.unary_position == ast.PREFIX:
            return f"{symbol}{parts[0]}" if symbol == "-" else f"{symbol} {parts[0]}"
        return f"{parts[0]} {symbol}"

    @staticmethod
    def _is_negative(node) -> bool:
        return (isinstance(node, ast.Apply) and node.symbol == "-" and node.n_ary == 1
                and isinstance(node.args[0], ast.Num))

    def _param_types(self, node: ast.Apply):
        op = self._operator(node)
        return op.parameter_types if op is not None else (None,) * node.n_ary

    def _record(self, node, mentions: set) -> None:
        if isinstance(node, ast.Var):
            mentions.add(("var", node.name))
        elif isinstance(node, (ast.Num, ast.Literal)):
            mentions.add(("const", repr(node.value)))
        elif isinstance(node, ast.Apply):
            if self._is_negative(node):
                mentions.add(("const", repr(-node.args[0].value)))
                return
            mentions.add(("op", node.symbol))
            for arg in node.args:
                self._record(arg, mentions)

    # ---- nouns
    def noun(self, node, mentions: set, kind=None, depth: int = 0) -> Phrase:
        if isinstance(node, ast.Var) and node.name in self._holes:
            en, zh = self._holes[node.name]
            return Phrase(en, zh, False)
        if isinstance(node, (ast.Var, ast.Num, ast.Literal, ast.NaN)) or self._is_negative(node):
            self._record(node, mentions)
            return Phrase(self._formula(node, kind), self._formula(node, kind, "zh"), True)
        op = self._operator(node)
        types = op.parameter_types if op is not None else (None,) * node.n_ary
        entry = self._entry(node)
        if depth >= 2:
            self._record(node, mentions)
            return Phrase(self._formula(node, kind), self._formula(node, kind, "zh"), True)
        args = [self.noun(arg, mentions, t, depth + 1) for arg, t in zip(node.args, types)]
        mentions.add(("op", node.symbol))
        name = base_operation_name(node.symbol, node.n_ary, node.unary_position)
        if name in ("succ", "natural_succ", "pred", "natural_pred") and isinstance(node.args[0], ast.Num):
            return Phrase(self._formula(node, kind), self._formula(node, kind, "zh"), True)
        if entry is None:  # a generated helper
            name = self._show(node.symbol)
            if all(arg.formula for arg in args):
                return Phrase(self._formula(node, kind), self._formula(node, kind, "zh"), True)
            if node.n_ary == 1:
                return Phrase(f"{name} of {args[0].en}", f"{args[0].zh}经 {name} 的结果", False)
            return Phrase(f"{name} of {args[0].en} and {args[1].en}",
                          f"{args[0].zh}和{args[1].zh}经 {name} 的结果", False)
        if entry.formula and all(arg.formula for arg in args):
            parts = [f"({arg.en})" if isinstance(child, ast.Apply) and not self._is_negative(child) else arg.en
                     for arg, child in zip(args, node.args)]
            parts_zh = [f"({arg.zh})" if isinstance(child, ast.Apply) and not self._is_negative(child) else arg.zh
                        for arg, child in zip(args, node.args)]
            return Phrase(entry.formula.format(*parts), entry.formula.format(*parts_zh), True)
        en = (self._special(node, [arg.en for arg in args], "en", "np")
              or entry.en_np.format(*[arg.en for arg in args]))
        zh = (self._special(node, [self._zh_arg(arg) for arg in args], "zh", "np")
              or entry.zh_np.format(*[self._zh_arg(arg) for arg in args]))
        return Phrase(en, zh, False)

    def _special(self, node, args, lang: str, form: str) -> str | None:
        """Wordings that decode a constant argument (card positions, colour codes)."""
        name = base_operation_name(node.symbol, node.n_ary, node.unary_position)
        if node.n_ary != 2 or not isinstance(node.args[1], ast.Num):
            return None
        code = node.args[1].value
        if name == "swap":
            op = self._operator(node)
            cards = int(op.parameter_types[0][5:-1])
            first, second = divmod(code, cards)
            if not (0 <= first < cards and 0 <= second < cards):
                return None
            if lang == "en":
                return (f"swap the cards at positions {first} and {second} in {args[0]}" if form == "do"
                        else f"{args[0]} with the cards at positions {first} and {second} swapped")
            return (f"交换{args[0]}中位置 {first} 和 {second} 的卡片" if form == "do"
                    else f"交换位置 {first} 和 {second} 后的{args[0]}")
        if name == "grid_recolour" and 0 <= code <= 99:
            source, target = divmod(code, 10)
            if lang == "en":
                return (f"recolour the colour {source} cells of {args[0]} to colour {target}" if form == "do"
                        else f"{args[0]} with colour {source} changed to colour {target}")
            return (f"把{args[0]}中颜色 {source} 的格子改成颜色 {target}" if form == "do"
                    else f"颜色 {source} 改成 {target} 的{args[0]}")
        return None

    @staticmethod
    def _zh_arg(phrase: Phrase) -> str:
        return phrase.zh if phrase.formula or len(phrase.zh) <= 3 else "「" + phrase.zh + "」"

    # ---- chains of verbs
    def chain(self, node, mentions: set, kind=None):
        """(start noun, [(en verb, zh verb, its argument nouns)]) for a chain of applications."""
        if not isinstance(node, ast.Apply) or self._is_negative(node):
            return self.noun(node, mentions, kind), []
        op = self._operator(node)
        types = op.parameter_types if op is not None else (None,) * node.n_ary
        entry = self._entry(node)
        if entry is not None:
            subject = entry.subject
        else:
            result = op.result_type if op is not None else None
            subject = next((i for i, t in enumerate(types) if t == result), 0)
        inner = node.args[subject]
        if isinstance(inner, ast.Apply) and not self._is_negative(inner):
            start, steps = self.chain(inner, mentions, types[subject])
        else:
            start, steps = self.noun(inner, mentions, types[subject]), []
        others = {i: self.noun(arg, mentions, t, 1)
                  for i, (arg, t) in enumerate(zip(node.args, types)) if i != subject}
        mentions.add(("op", node.symbol))
        steps.append((node, entry, subject, others))
        return start, steps

    def _verb(self, node, entry, subject, others, subject_phrase: Phrase, lang: str,
              as_step: bool = False) -> str:
        args = []
        for i in range(node.n_ary):
            phrase = subject_phrase if i == subject else others[i]
            args.append(phrase.en if lang == "en" else self._zh_arg(phrase))
        if entry is not None:
            special = self._special(node, args, lang, "do")
            if special:
                if lang == "en" and subject_phrase.en == "it" and base_operation_name(
                        node.symbol, node.n_ary, node.unary_position) in ("swap", "grid_recolour"):
                    return special.replace(" of it", " in the result").replace(" in it", " in the result")
                return special
            if lang == "en" and subject_phrase.en == "it":
                name = base_operation_name(node.symbol, node.n_ary, node.unary_position)
                if name == "perm_reverse":
                    return "reverse its order"
                if name == "pitch_retrograde":
                    return "reverse its notes"
                if name in ("rel_parent", "rel_colleague", "rel_neighbour"):
                    relation = name.removeprefix("rel_")
                    return f"look up that person's {relation}"
                if name == "digitsum":
                    return "sum its digits"
                if name == "reverse" and self._display_renamed:
                    return "reverse its digits"
                if name == "triangle":
                    return "take its signed triangle number"
                if name in ("popcount", "bit_count"):
                    return "count its one bits"
                if name == "list_cons":
                    return f"prepend {args[0]} to it"
                if name == "list_head":
                    return "take its first element"
                if name == "list_tail":
                    return "drop its first element"
                if name == "list_length":
                    return "count its elements"
                if name == "list_sum":
                    return "add up its elements"
                if name == "list_at":
                    return f"take element {args[1]} from it, counting from zero"
                if name == "str_length":
                    return "count its characters"
                if name == "str_first":
                    return "keep its first character"
                if name == "str_drop":
                    return "drop its first character"
            return (entry.en_do if lang == "en" else entry.zh_do).format(*args)
        name = self._show(node.symbol)
        if node.n_ary == 1:
            if lang == "en":
                return f"apply {name} to {args[0] if args[0] != 'it' else 'the result'}"
            return f"对{args[0]}应用 {name}"
        if lang == "en":
            args = ["the result" if arg == "it" else arg for arg in args]
            simple = all(isinstance(arg, (ast.Var, ast.Num, ast.Literal)) or self._is_negative(arg)
                         for arg in node.args)
            if as_step or not simple:
                for i in range(2):
                    if i != subject and isinstance(node.args[i], ast.Apply) and not self._is_negative(node.args[i]):
                        wording = self._formula(node.args[i]) if "," in args[i] else args[i]
                        args[i] = f"({wording})"
                return f"apply {name} to {args[0]} and {args[1]}"
            for i in range(2):
                complex_arg = isinstance(node.args[i], ast.Apply) and not self._is_negative(node.args[i])
                if i != subject and args[i] != "itself" and (complex_arg or args[i].startswith("the ")):
                    wording = self._formula(node.args[i]) if complex_arg and "," in args[i] else args[i]
                    args[i] = f"({wording})"
            return f"compute {args[0]} {name} {args[1]}"
        if args[0] == args[1]:
            return f"把{args[0]}同时作为两个输入应用 {name}"
        return f"对{args[0]}和{args[1]}应用 {name}"

    def clause(self, node, mentions: set, kind=None, it_en="it", it_zh="结果"):
        """An instruction (English, Chinese) that computes ``node``."""
        start, steps = self.chain(node, mentions, kind)
        if not steps:
            return f"return {start.en}", f"结果为{start.zh}"
        en_parts, zh_parts = [], []
        for position, (child, entry, subject, others) in enumerate(steps):
            subject_phrase = start if position == 0 else Phrase(it_en, it_zh, False)
            repeated = position > 0 and any(
                child.args[i] == child.args[subject] for i in others)
            if repeated:
                others = {i: (Phrase("itself", "结果", False)
                              if child.args[i] == child.args[subject] else phrase)
                          for i, phrase in others.items()}
                subject_phrase = Phrase("the result", "结果", False)
            if (position == len(steps) - 1 and position > 0 and entry is not None
                    and entry.en_do.startswith("test whether ")):
                subject_phrase = Phrase("the result", "结果", False)
            if repeated and entry is not None and entry.en_do == "add {1} to {0}" and subject == 0:
                en_parts.append("add the result to itself")
                zh_parts.append("把结果与自身相加")
            else:
                en_parts.append(self._verb(child, entry, subject, others, subject_phrase, "en",
                                           as_step=len(steps) > 1))
                zh_parts.append(self._verb(child, entry, subject, others, subject_phrase, "zh"))
        if len(steps) == 1:
            return en_parts[0], zh_parts[0]
        zh = "先" + "，再".join(zh_parts[:-1]) + ("，最后" if len(steps) > 2 else "，再") + zh_parts[-1]
        # Adjacent predecessor steps share the same zero bound.
        compact, position = [], 0
        while position < len(steps):
            end = position + 1
            while (end < len(steps) and self._entry(steps[position][0]) is not None
                   and base_operation_name(steps[position][0].symbol, 1, steps[position][0].unary_position)
                   == "natural_pred" and steps[end][0].symbol == steps[position][0].symbol):
                end += 1
            if end > position + 1:
                count = "twice" if end - position == 2 else f"{end - position} times"
                compact.append(en_parts[position].replace(", stopping at zero", f" {count}, stopping at zero"))
            else:
                compact.append(en_parts[position])
            position = end
        en_parts = compact
        if len(en_parts) == 1:
            return en_parts[0], zh
        en = ", ".join(en_parts[:-1]) + ", then " + en_parts[-1]
        return en, zh

    # ---- conditions
    def condition(self, cond, mentions: set):
        if isinstance(cond, ast.And):
            bounds = self._range(cond, mentions)
            if bounds:
                return bounds, bounds
            left, right = self.condition(cond.left, mentions), self.condition(cond.right, mentions)
            return f"{left[0]} and {right[0]}", f"{left[1]}且{right[1]}"
        if isinstance(cond, ast.Or):
            left, right = self.condition(cond.left, mentions), self.condition(cond.right, mentions)
            return f"{left[0]} or {right[0]}", f"{left[1]}或{right[1]}"
        if isinstance(cond, ast.Not):
            inner = self.condition(cond.operand, mentions)
            return f"not ({inner[0]})", f"并非「{inner[1]}」"
        if isinstance(cond, ast.Compare):
            left, right = self.noun(cond.left, mentions), self.noun(cond.right, mentions)
            op = _COMPARE[cond.op]
            if left.formula and right.formula:
                return f"{left.en} {op} {right.en}", f"{left.zh} {op} {right.zh}"
            words = {"=": ("equals", "等于"), "≠": ("differs from", "不等于"), "<": ("is below", "小于"),
                     ">": ("is above", "大于"), "≤": ("is at most", "不大于"), "≥": ("is at least", "不小于")}[op]
            return f"{left.en} {words[0]} {right.en}", f"{self._zh_arg(left)}{words[1]}{self._zh_arg(right)}"
        # Truth
        expr = cond.expr
        if isinstance(expr, ast.Apply):
            entry = self._entry(expr)
            if entry is not None and entry.en_if:
                op = self._operator(expr)
                args = [self.noun(arg, mentions, t, 1) for arg, t in zip(expr.args, op.parameter_types)]
                mentions.add(("op", expr.symbol))
                return (entry.en_if.format(*[a.en for a in args]),
                        entry.zh_if.format(*[self._zh_arg(a) for a in args]))
        phrase = self.noun(expr, mentions, "bool")
        return f"{phrase.en} is true", f"{self._zh_arg(phrase)}为真"

    def _range(self, cond: ast.And, mentions: set) -> str | None:
        """``low ≤ v < high`` for two bounds on one variable."""
        parts = [cond.left, cond.right]
        if not all(isinstance(p, ast.Compare) and isinstance(p.left, ast.Var) for p in parts):
            return None
        if parts[0].left != parts[1].left:
            return None
        lows = [p for p in parts if p.op in (">", ">=")]
        highs = [p for p in parts if p.op in ("<", "<=")]
        if len(lows) != 1 or len(highs) != 1:
            return None
        low, high = lows[0], highs[0]
        if not all(isinstance(p.right, ast.Num) or self._is_negative(p.right) for p in (low, high)):
            return None
        for p in (low, high):
            self._record(p.left, mentions)
            self._record(p.right, mentions)
        var = low.left.name
        low_op = "≤" if low.op == ">=" else "<"
        high_op = "≤" if high.op == "<=" else "<"
        return f"{self._formula(low.right)} {low_op} {var} {high_op} {self._formula(high.right)}"

    # ---- definitions
    def describe(self, operator) -> Description:
        definition = self.parser.parse(operator.definition)
        if operator.definition_type == "recursive_definition":
            result = self._recursive(operator, definition)
            if result is not None:
                return result
        mentions: set = set()
        en, zh = self._cases(definition, mentions)
        description = Description(en, zh, mentions)
        if len(en) > self.MAX_EN:
            description = self._summary(operator, definition)
        return description

    def _cases(self, definition, mentions: set, it_en="it", it_zh="结果"):
        branches = definition.branches
        if len(branches) == 1 and branches[0].condition is None:
            en, zh = self.clause(branches[0].expr, mentions, it_en=it_en, it_zh=it_zh)
            return _sentence(en), _zh_sentence(zh)
        en_parts, zh_parts = [], []
        for branch in branches:
            en, zh = self.clause(branch.expr, mentions, it_en=it_en, it_zh=it_zh)
            if branch.condition is None:
                en_parts.append(f"otherwise {en}")
                zh_parts.append(f"否则{zh}")
            else:
                cen, czh = self.condition(branch.condition, mentions)
                if en_parts:
                    en_parts.append(f"otherwise if {cen}, {en}")
                    zh_parts.append(f"否则若{czh}，{zh}")
                else:
                    en_parts.append(f"if {cen}, {en}")
                    zh_parts.append(f"若{czh}，{zh}")
        if branches[-1].condition is not None:
            en_parts.append("other inputs give NaN")
            zh_parts.append("其他输入得 NaN")
        return _sentence("; ".join(en_parts)), _zh_sentence("；".join(zh_parts))

    def _summary(self, operator, definition) -> Description:
        mentions: set = set()
        for branch in definition.branches:
            self._record(branch.expr, mentions)
            if branch.condition is not None:
                self._record_condition(branch.condition, mentions)
        helpers = [self._show(symbol) for kind, symbol in sorted(mentions)
                   if kind == "op" and symbol in self.names and symbol != operator.symbol]
        atoms = []
        for kind, symbol in sorted(mentions):
            if kind != "op" or symbol in self.names:
                continue
            if any(op.symbol == symbol and op.definition is None for op in self.registry):
                atoms.append(symbol)
        uses_en = _join_en(helpers + atoms)
        uses_zh = "、".join(helpers + atoms)
        n = len(definition.branches)
        tested = sorted({name for kind, name in mentions if kind == "var"})
        if n > 1:
            en = (f"Chooses between {n} cases by testing {_join_en(tested)}; "
                  f"the cases combine {uses_en}.")
            zh = f"按{'、'.join(tested)}的取值在 {n} 种情形中选一种；各情形组合使用 {uses_zh}。"
        else:
            en = f"Combines {uses_en} in one expression."
            zh = f"在一个表达式里组合使用 {uses_zh}。"
        return Description(en, zh_spacing(zh), mentions, reading="summary")

    def _record_condition(self, cond, mentions):
        if isinstance(cond, (ast.And, ast.Or)):
            self._record_condition(cond.left, mentions)
            self._record_condition(cond.right, mentions)
        elif isinstance(cond, ast.Not):
            self._record_condition(cond.operand, mentions)
        elif isinstance(cond, ast.Compare):
            self._record(cond.left, mentions)
            self._record(cond.right, mentions)
        else:
            self._record(cond.expr, mentions)

    # ---- recursion
    def _recursive(self, operator, definition) -> Description | None:
        branches = definition.branches
        if len(branches) not in (2, 3) or any(b.condition is None for b in branches):
            return None
        base, down = branches[0], branches[1]
        up = branches[2] if len(branches) == 3 else None
        if not isinstance(base.condition, ast.Compare) or base.condition.op != "==":
            return None
        control = base.condition.left
        if isinstance(control, ast.Var):
            loop, modulus = control.name, None
        elif (isinstance(control, ast.Apply) and control.symbol == "%" and isinstance(control.args[0], ast.Var)
              and isinstance(control.args[1], ast.Num)):
            loop, modulus = control.args[0].name, control.args[1].value
        else:
            return None
        calls = []

        def find(node):
            if isinstance(node, ast.Apply):
                if node.symbol == operator.symbol and node.n_ary == operator.n_ary:
                    calls.append(node)
                    return
                for arg in node.args:
                    find(arg)

        find(down.expr)
        if not calls or any(call != calls[0] for call in calls):
            return None
        params = definition.parameters
        position = params.index(loop)
        call = calls[0]
        stepped = call.args[position]
        others_same = all(isinstance(arg, ast.Var) and arg.name == params[i]
                          for i, arg in enumerate(call.args) if i != position)
        mentions: set = {("op", operator.symbol), ("var", loop)}
        mentions |= {("var", name) for name in params}  # the other inputs pass through unchanged
        start = self.noun(base.expr, mentions)
        # At the base case the counter is 0, so a base that reads the counter starts from 0. Under
        # a modulus the top call can also stop at once with a nonzero counter, so that case is
        # read level by level instead.
        base_expr = base.expr
        base_reads_loop = self._uses(base_expr, loop)
        if base_reads_loop and modulus is None:
            base_expr = _replace(base_expr, ast.Var(loop), ast.Num(0))
        start_from = self.noun(base_expr, set())
        bound = None
        if isinstance(down.condition, ast.And) and isinstance(down.condition.right, ast.Compare):
            right = down.condition.right
            if isinstance(right.right, ast.Num):
                bound = right.right.value
        loop_free = not self._uses(down.expr, loop, skip=call) and not (base_reads_loop and modulus is not None)
        counting = self._counting(stepped, control, loop, modulus, bound, up is not None, mentions)
        if counting is None or not others_same:
            return None
        if up is not None:
            up_calls = []

            def find_up(node):
                if isinstance(node, ast.Apply):
                    if node.symbol == operator.symbol and node.n_ary == operator.n_ary:
                        up_calls.append(node)
                        return
                    for arg in node.args:
                        find_up(arg)

            find_up(up.expr)
            if not up_calls or any(c != up_calls[0] for c in up_calls):
                return None
            mirrored = _replace(up.expr, up_calls[0], call)
            if mirrored != down.expr:
                return None
        count_en, count_zh, range_en, range_zh = counting
        if loop_free:
            hole = ast.Var("\0it")
            body = _replace(down.expr, call, hole)
            en_step, zh_step = self._step_clause(body, hole, mentions, it_en="the current value")
            en = f"Start with {start_from.en}. Repeat {count_en}{range_en}: {en_step}."
            zh = f"从{self._zh_arg(start_from)}开始，{count_zh}{zh_step}{range_zh}。"
            return Description(_sentence(en), _zh_sentence(zh), mentions, reading="repetition",
                               repetition={"loop": loop, "modulus": modulus, "position": position,
                                           "step": body, "hole": hole.name, "base": base_expr,
                                           "bound": bound, "two_sided": up is not None,
                                           "halving": counting[0] == HALVING_EN.format(loop=loop)})
        # The step also reads the loop variable: say it level by level.
        hole = ast.Var("\0r")
        body = _replace(down.expr, call, hole)
        en_step, zh_step = self._step_clause(body, hole, mentions, it_en="r", it_zh="r")
        next_en = self._formula(stepped)
        self._record(stepped, mentions)
        if up is not None and isinstance(stepped, ast.Apply) and stepped.symbol == "-":
            other = self._formula(ast.Apply("+", stepped.args))
            control_text = self._formula(control)
            next_en_full, next_zh_full = (f"{next_en} (or {other} when {control_text} < 0)",
                                          f"{next_en}（{control_text} < 0 时用 {other}）")
        else:
            next_en_full = next_zh_full = next_en
        counter_en = f", counting with {self._formula(control)}" if modulus is not None else ""
        counter_zh = f"，用{self._formula(control)}计数" if modulus is not None else ""
        en = (f"Recurse on {loop}{counter_en}{range_en}: when {self._formula(control)} = 0 the result is {start.en}; "
              f"otherwise let r be the result for {next_en_full}, then {en_step}.")
        zh = (f"对{loop}递归{counter_zh}{range_zh}：{self._formula(control)} = 0 时结果为{self._zh_arg(start)}；"
              f"否则先求{next_zh_full}的结果 r，再{zh_step}。")
        return Description(_sentence(en), _zh_sentence(zh), mentions, reading="direct")

    def _counting(self, stepped, control, loop, modulus, bound, two_sided, mentions):
        """How many times the step runs, read from the recursive argument."""
        if isinstance(stepped, ast.Apply) and stepped.n_ary == 2 and stepped.symbol in ("-", "⇒"):
            inner, amount = stepped.args
            if not isinstance(amount, ast.Num) or amount.value != 1:
                return None
            if inner != control:
                return None
            if stepped.symbol == "⇒":
                mentions.add(("op", "⇒"))
                return (HALVING_EN.format(loop=loop), f"{loop} 每右移一位（直到变成 0）就做一次：",
                        f" (for {loop} from 0 to {bound})" if bound is not None else "",
                        f"（{loop} 取 0 到 {bound}）" if bound is not None else "")
            mentions.add(("op", "-"))
            mentions.add(("const", "1"))
            if two_sided:
                mentions.add(("op", "+"))  # the negative side steps up by one
            if modulus is not None:
                mentions.add(("op", "%"))
                mentions.add(("const", repr(modulus)))
                return (f"|{loop} % {modulus}| times", f"重复 |{loop} % {modulus}| 次：", "", "")
            if two_sided:
                return (f"|{loop}| times", f"重复 |{loop}| 次：",
                        f" (for {loop} from -{bound} to {bound}; other values give NaN)" if bound is not None else "",
                        f"（{loop} 取 -{bound} 到 {bound}，其余为 NaN）" if bound is not None else "")
            return (f"{loop} times", f"重复 {loop} 次：",
                    f" (for {loop} from 0 to {bound}; other values give NaN)" if bound is not None else "",
                    f"（{loop} 取 0 到 {bound}，其余为 NaN）" if bound is not None else "")
        if (isinstance(stepped, ast.Apply) and stepped.n_ary == 1 and isinstance(stepped.args[0], ast.Var)
                and stepped.args[0].name == loop):
            entry = self._entry(stepped)
            name = base_operation_name(stepped.symbol, 1, stepped.unary_position)
            if name in ("natural_pred", "pred"):
                mentions.add(("op", stepped.symbol))
                return (f"{loop} times", f"重复 {loop} 次：",
                        f" (for {loop} from 0 to {bound}; other values give NaN)" if bound is not None else "",
                        f"（{loop} 取 0 到 {bound}，其余为 NaN）" if bound is not None else "")
            del entry
        return None

    def _step_clause(self, body, hole, mentions, it_en="it", it_zh="结果"):
        if body == hole:
            return f"keep {it_en}", "保持不变"
        self._holes = {hole.name: (it_en, it_zh)}
        try:
            start, steps = self.chain(body, mentions)
        finally:
            self._holes = {}
        mentions.discard(("var", hole.name))
        if start.en != it_en:
            # the running value is not at the start of the chain: name it inside a formula
            text = self._formula(body).replace(hole.name, it_en)
            text_zh = self._formula(body, lang="zh").replace(hole.name, it_zh)
            return f"replace {it_en} by {text}", f"把{it_zh}换成 {text_zh}"
        en_parts, zh_parts = [], []
        for position, (child, entry, subject, others) in enumerate(steps):
            phrase = Phrase(it_en, it_zh, False)
            if base_operation_name(child.symbol, child.n_ary, child.unary_position) == "is_zero":
                en_parts.append(f"apply the zero test to {it_en}")
                zh_parts.append(f"对{it_zh}做零值检测")
            else:
                en_parts.append(self._verb(child, entry, subject, others, phrase, "en", as_step=True))
                zh_parts.append(self._verb(child, entry, subject, others, phrase, "zh"))
        if len(en_parts) == 1:
            return en_parts[0], zh_parts[0]
        return ", then ".join(en_parts), "，再".join(zh_parts)

    def _uses(self, node, name, skip=None) -> bool:
        if node == skip:
            return False
        if isinstance(node, ast.Var):
            return node.name == name
        if isinstance(node, ast.Apply):
            return any(self._uses(arg, name, skip) for arg in node.args)
        return False


HALVING_EN = "once for each right shift of {loop} until it reaches 0"


def _replace(node, old, new):
    if node == old:
        return new
    if isinstance(node, ast.Apply):
        return ast.Apply(node.symbol, tuple(_replace(arg, old, new) for arg in node.args), node.unary_position)
    return node


def _join_en(items: list[str]) -> str:
    items = list(dict.fromkeys(items))
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _sentence(text: str) -> str:
    text = text.strip()
    text = re.sub(r"(?<![\d.-])1 (column|row|bit|semitone|block)s\b", r"1 \1", text)
    text = re.sub(r"(?<![\d.|-])1 times\b", "once", text)
    text = text[0].upper() + text[1:]
    return text if text.endswith(".") else text + "."


def _zh_sentence(text: str) -> str:
    text = zh_spacing(text.strip())
    return text if text.endswith("。") else text + "。"
