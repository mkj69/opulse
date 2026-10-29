```python
expr = world.expression("2 * 3 ■₄₁ 4 + 1")
print(expr.text, "=", expr.value)
print(expr.full_text)
print(expr.trace().value == expr.value)
free = world.expression("a ■₄₁ b")
print(free.variables, free.evaluate(a=6, b=4))
```

```text
2 * 3 ■₄₁ 4 + 1 = 40
2 * ((3 ■₄₁ 4) + 1)
True
('a', 'b') 19
```
