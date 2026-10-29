```bash
python tools/docs_granularity.py
opulse trace --operators outputs/docs_granularity/operators.jsonl --expression "15 ☆₁ ((3 ○₁) ★₁ (& 47))" --known-layers 3 --open 1
```

```text
15 ☆₁ ((3 ○₁) ★₁ (& 47))
= 15 ☆₁ (0 ★₁ (& 47))   [eval ○₁]
    3 ○₁
    = 3 ●₁   [expand ○₁, branch 2: 3 < 69]
    = 0      [eval ●₁]
= 15 ☆₁ (0 ★₁ 11)       [atom &]
= 15 ☆₁ 0               [eval ★₁]
    0 ★₁ 11
    = (0 ★₁ (11 % 6 - 1)) ●₁   [expand ★₁, branch 2: 11 % 6 > 0]
    = (0 ★₁ (5 - 1)) ●₁        [atom %]
    = (0 ★₁ 4) ●₁              [atom -]
    = 0 ●₁                     [eval ★₁]
    = 0                        [eval ●₁]
= 67                    [eval ☆₁]
    15 ☆₁ 0
    = (15 * 15) ★₁ 0   [expand ☆₁]
    = 225 ★₁ 0         [atom *]
    = 67               [eval ★₁]
```
