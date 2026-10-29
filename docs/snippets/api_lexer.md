```python
from pygments import highlight
from pygments.formatters import HtmlFormatter

html = highlight(op.definition, world.lexer(), HtmlFormatter())
for token, text in world.lexer().get_tokens("a ■₄₁ (2 + NaN)"):
    if text.strip():
        print(f"{text:6} {token}")
```

```text
a      Token.Name.Variable
■₄₁    Token.Name.Function
(      Token.Punctuation
2      Token.Literal.Number.Integer
+      Token.Operator
NaN    Token.Keyword.Constant
)      Token.Punctuation
```
