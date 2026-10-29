```python
for expr in world.sample_expressions(4, depth=2, frequency="zipf:1.5", seed=0):
    print(expr.text, "=", expr.value, " expansion", expr.record["expansion"])
```

```text
(50 ■₁₇ 30) ★₄₇ = 19  expansion 40
(12 □₁₁) ■₄₁ (18 ●₁₀) = 19  expansion 58
(- 20) ▲₂₄ (61 ★₄₇) = 19  expansion 48
1 ■₁₇ (♤₅₅ 85) = 188  expansion 7
```
