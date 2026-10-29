"""Historical integer and atomic starting sets, generated without JSONL assets.

The stable identities, precedence and numeral markers preserve existing seeded worlds.
Atom symbols and shapes come from the primitive registry at construction time.
"""

from __future__ import annotations

import json
from pathlib import Path

from opulse.core.operator import Operator
from opulse.core.primitives import atom_records
from opulse.core.registry import OperatorRegistry

STARTING_NAMES = {
    "integer": ("add", "sub", "mul", "div", "mod", "neg", "reverse", "triangle", "popcount", "digitsum"),
    "atomic": ("neg", "succ", "pred", "double", "half", "parity"),
}

# (function identity, precedence) in the historical starting sets.
_IDENTITIES = {'atomic': {'double': ('YOPP5z1oYF', 4),
            'half': ('R26doJldQr', 4),
            'neg': ('0pxTvgPEIa', 4),
            'parity': ('ewR7prNzl2', 4),
            'pred': ('NmH0B4zKPS', 4),
            'succ': ('6nmCEa00cb', 4)},
 'integer': {'add': ('1xW1ZG8bwv', 1),
             'digitsum': ('5ZZT1reNC3', 4),
             'div': ('GjIp03937G', 2),
             'mod': ('ooX1Ek07wh', 3),
             'mul': ('6hLHpcDHtU', 1),
             'neg': ('0pxTvgPEIa', 4),
             'popcount': ('rgFMKPkctM', 5),
             'reverse': ('vmg6514jGu', 5),
             'sub': ('7UumhDVYmZ', 1),
             'triangle': ('aEXLSFKmXm', 6)}}

# Legacy compiled source is retained as operator metadata for exact JSONL exports.
_COMPUTE = {'add': 'def op_{func_id}(a, b):\n'
        '    sum_ab = a + b\n'
        '    if sum_ab > thres:\n'
        '        return sum_ab % thres\n'
        '    elif sum_ab < -thres:\n'
        '        return -(abs(sum_ab) % thres)\n'
        '    return sum_ab\n',
 'digitsum': 'def op_{func_id}(a):\n'
             '    n = abs(a) % thres\n'
             '    result = sum(int(d) for d in str(n))\n'
             '    return result % thres if a > 0 else -(result % thres)\n',
 'div': 'def op_{func_id}(a, b):\n'
        '    if b == 0:\n'
        '        b = 1\n'
        '    result = int(a / b)  # 向零取整\n'
        '    if result > thres:\n'
        '        return result % thres\n'
        '    elif result < -thres:\n'
        '        return -(abs(result) % thres)\n'
        '    return result\n',
 'mod': 'def op_{func_id}(a, b):\n'
        '    if b == 0:\n'
        '        b = 1\n'
        '    result = a - int(a / b) * b  # 保留 a 的符号\n'
        '    if result > thres:\n'
        '        return result % thres\n'
        '    elif result < -thres:\n'
        '        return -(abs(result) % thres)\n'
        '    return result\n',
 'mul': 'def op_{func_id}(a, b):\n'
        '    prod_ab = a * b  \n'
        '    if prod_ab > thres:\n'
        '        return prod_ab % thres\n'
        '    elif prod_ab < -thres:\n'
        '        return -(abs(prod_ab) % thres)\n'
        '    return prod_ab\n',
 'neg': 'def op_{func_id}(a):\n'
        '    neg_a = -a  \n'
        '    if neg_a > thres:\n'
        '        return neg_a % thres\n'
        '    elif neg_a < -thres:\n'
        '        return -(abs(neg_a) % thres)\n'
        '    return neg_a\n',
 'popcount': "def op_{func_id}(a):\n    return bin(a).count('1')\n",
 'reverse': 'def op_{func_id}(a):\n'
            '    str_a = str(abs(a) % thres)  \n'
            '    reversed_a = str_a[::-1]  # Reverse the string representation\n'
            '    result = int(reversed_a) # Convert back to integer\n'
            '    return result % thres if a > 0 else -(result % thres)\n',
 'sub': 'def op_{func_id}(a, b):\n'
        '    diff_ab = a - b  \n'
        '    if diff_ab > thres:\n'
        '        return diff_ab % thres\n'
        '    elif diff_ab < -thres:\n'
        '        return -(abs(diff_ab) % thres)\n'
        '    return diff_ab\n',
 'triangle': 'def op_{func_id}(a):\n'
             '    n = abs(a) % thres\n'
             '    result = n * (n + 1) // 2\n'
             '    return result % thres if a > 0 else -(result % thres)\n'}

# Numeral markers denote bases 2 through 16. They are shared by both sets.
_MARKERS = [(2, '4ODlR07dGR', '≮⫘↔'),
 (3, 'OBoeoEwOM3', '⫏≰'),
 (4, 'RvI9EZk3Pm', '⪩⨒∯'),
 (5, 'Yl4JT0T9eW', '⇑⪆'),
 (6, 'MXf1OUP5ii', '↹⩛'),
 (7, 'dXloO0Kira', '≴∭⊉'),
 (8, '4gIeDH8XbW', '⪪⊹⋣'),
 (9, 'ZJwk9SKawi', '⋋%⋟'),
 (10, 'QLSuuZT3eZ', '⊺⇮'),
 (11, 'ilQi3mCzPa', '⋰*⋻'),
 (12, 'bOONrRIZM9', '⫖↰⪸'),
 (13, 'KHmYSDo95h', '⪎⋱⫍'),
 (14, 'K3QD8kBpfL', '⨗⨭⨅'),
 (15, 'LxqDKtmm8G', '⫶⩼⫲'),
 (16, 'gNCSSZt20n', '∃⊬')]

_FIELDS = ("id", "func_id", "symbol", "n_ary", "unary_position", "recursive_layer",
           "max_path_depth", "max_edge_count", "is_base", "definition", "definition_type",
           "priority", "associativity_direction", "op_compute_func", "op_count_func",
           "dependencies")


def starting_rows(name: str) -> list[dict]:
    """Return the original JSONL records for ``integer`` or ``atomic`` in memory."""
    if name not in STARTING_NAMES:
        raise ValueError(f"unknown starting set {name!r}; choose from {', '.join(STARTING_NAMES)}")
    from opulse.canary import marked

    rows = []
    for atom, generated in zip(STARTING_NAMES[name], atom_records(STARTING_NAMES[name])):
        row = {key: generated[key] for key in _FIELDS}
        func_id, priority = _IDENTITIES[name][atom]
        row["func_id"] = func_id
        row["priority"] = priority
        if name == "integer":
            row["max_edge_count"] = row["n_ary"]
            row["associativity_direction"] = "left" if row["unary_position"] == "postfix" else "right"
        row["op_compute_func"] = _COMPUTE[atom].format(func_id=func_id) if atom in _COMPUTE else None
        row["op_count_func"] = (f"def op_count_{func_id}({'a, b' if row['n_ary'] == 2 else 'a'}):\n"
                                "    return 1\n") if row["op_compute_func"] else None
        rows.append(marked(row))
    for base, func_id, symbol in _MARKERS:
        row = {"id": None, "func_id": func_id, "symbol": symbol, "n_ary": 1,
               "unary_position": "prefix", "recursive_layer": None, "max_path_depth": 1,
               "max_edge_count": 1, "is_base": base, "definition": None, "definition_type": None,
               "priority": None, "associativity_direction": None, "op_compute_func": None,
               "op_count_func": None, "dependencies": None}
        rows.append(marked(row))
    return rows


def starting_registry(name: str = "integer") -> OperatorRegistry:
    """Build a fresh registry with the same entries as the historical starting file."""
    return OperatorRegistry(Operator.from_dict(row) for row in starting_rows(name))


def starting_jsonl(name: str = "integer") -> str:
    """Serialize a built-in starting set with its historical field order."""
    return "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in starting_rows(name))


def export_starting_set(name: str, path: str | Path) -> Path:
    """Write a built-in starting set to a user-selected JSONL file."""
    path = Path(path)
    path.write_text(starting_jsonl(name), encoding="utf-8")
    return path
