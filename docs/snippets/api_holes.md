```python
for hole in world.holes(2, depth=2, unique_only=True, seed=0, timeout_ms=500, domain=50):
    print(hole.text, " x =", hole.solutions)
```

```text
(50 □₃₆ x) □₁₁ = -63  x = [30]
(# 32) ♥₁₂ x = -169  x = [18]
```
