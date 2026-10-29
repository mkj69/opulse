```python
op = world["□₃₆"]
print(op.definition)
print(op.kind, op.layer, op.position)
print([callee.symbol for callee in op.callees])
print(op.evaluate(3, 4), op(10, 2))
print(op.result(3, 4))
```

```text
a □₃₆ b = { b, if a % 3 == 0; (((a % 3) - 1) □₃₆ b) - a, if a % 3 > 0; (((a % 3) + 1) □₃₆ b) - a, if a % 3 < 0 }
recursive 1 binary
['+', '-', '%']
4 -8
CallResult(value=4, base_ops=1, calls=1)
```
