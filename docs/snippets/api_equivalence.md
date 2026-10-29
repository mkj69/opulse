```python
print(world.equivalent("a + b", "b + a").status)
verdict = world.equivalent("(a + b) - b", "a")
print(verdict.status, verdict.counterexample)
```

```text
proved
refuted {'a': 1, 'b': 2147483647}
```
