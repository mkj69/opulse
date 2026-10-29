"""Character spans of subexpressions in rendered text.

The span of a subtree is found by rendering the whole expression once more with that subtree
replaced by a placeholder: the text before the placeholder fixes the start, and the subtree's
own rendering (without the brackets its parent adds) fixes the length. The result is checked
against the real rendering, so a span always covers exactly the text of its subexpression,
and that text parses back to the subexpression.
"""

from __future__ import annotations

from opulse.expression.nodes import Call, Node, Variable
from opulse.expression.render import ExpressionRenderer

PLACEHOLDER = ""  # a private-use character that never occurs in rendered expressions


def replace_at(node: Node, path: tuple[int, ...], new: Node) -> Node:
    if not path:
        return new
    head, *rest = path
    args = list(node.args)
    args[head] = replace_at(args[head], tuple(rest), new)
    return Call(node.operator, tuple(args))


def subtree(node: Node, path: tuple[int, ...]) -> Node:
    for index in path:
        node = node.args[index]
    return node


def full_span(renderer: ExpressionRenderer, expression: Node, path: tuple[int, ...],
              text: str | None = None) -> tuple[int, int]:
    """``(start, end)`` of the subtree at ``path`` in ``renderer.full(expression)``."""
    text = renderer.full(expression) if text is None else text
    core = renderer.full(subtree(expression, path))
    if not path:
        if core != text:
            raise ValueError("the rendering is not compositional")
        return 0, len(text)
    marked = renderer.full(replace_at(expression, path, Variable(PLACEHOLDER)))
    before, _, after = marked.partition(PLACEHOLDER)
    context = text[len(before): len(text) - len(after)]
    if not text.startswith(before) or not text.endswith(after) or core not in context:
        raise ValueError("the rendering is not compositional")
    start = len(before) + context.index(core)
    return start, start + len(core)
