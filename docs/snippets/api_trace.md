```python
trace = op.trace(2, 2)
print(len(trace), "steps, value", trace.value)
print("\n= ".join(trace.lines()[:6]))
```

```text
9 steps, value -1
2 □₃₆ 2
= (2 % 3 - 1) □₃₆ 2 - 2
= (2 - 1) □₃₆ 2 - 2
= 1 □₃₆ 2 - 2
= ((1 % 3 - 1) □₃₆ 2 - 1) - 2
= ((1 - 1) □₃₆ 2 - 1) - 2
```
