```bash
python tools/docs_granularity.py --operators-only
opulse explain --operators outputs/docs_granularity/operators.jsonl --operator "△₁"
```

```text
△₁  (branch, layer 0)
a △₁ b = { (▲₁ (& 3)) / ((a + 18) $), if a < 88 and b < 35; & ((- 1) + (- b)), if a >= 100 and b < 35; (■₁ (▲₁ b)) + (79 * (17 * a)), if a < 88 and b >= 35 and b < 60; ((& 9) - (■₁ b)) + (& (a $)), if a >= 88 and a < 100 and b >= 60 and b < 67; & ((b □₁) + (a + b)), if a >= 88 and a < 100 and b >= 92; (■₁ (- b)) / ((▲₁ b) + (- 25)), else }

formula
  branch 1, if a < 88 and b < 35: (▲₁ (& 3)) / ((a + 18) $)
    inlined:    ((& 3) * (& 3)) / ((a + 18) $)   [proved equal by z3]
    SymPy form: 9 / ((18 + a) $)   [proved equal by z3]
  branch 2, if a >= 100 and b < 35: & ((- 1) + (- b))
    SymPy form: & ((- 1) - b)   [proved equal by z3]
  branch 3, if a < 88 and b >= 35 and b < 60: (■₁ (▲₁ b)) + (79 * (17 * a))
    inlined:    ((# (b * b)) * (& (b * b))) + (79 * (17 * a))   [proved equal by z3]
    SymPy form: (1343 * a) + ((# (b * b)) * (& (b * b)))   [proved equal by z3]
  branch 4, if a >= 88 and a < 100 and b >= 60 and b < 67: ((& 9) - (■₁ b)) + (& (a $))
    inlined:    ((& 9) - ((# b) * (& b))) + (& (a $))   [proved equal by z3]
    SymPy form: (9 + (& (a $))) - ((# b) * (& b))   [proved equal by z3]
  branch 5, if a >= 88 and a < 100 and b >= 92: & ((b □₁) + (a + b))
    inlined:    & ((((# b) * (& b)) % (- 3)) + (a + b))   [proved equal by z3]
  branch 6, else: (■₁ (- b)) / ((▲₁ b) + (- 25))
    inlined:    ((# (- b)) * (& (- b))) / ((b * b) + (- 25))   [proved equal by z3]
    SymPy form: ((# (- b)) * (& (- b))) / ((b * b) - 25)   [proved equal by z3]

behaviour, a in [4, 103], b in [4, 103]
  a = 4 .. 87
    b = 4 .. 34      branch 1                 5 values in [1, 9]
    b = 35 .. 59     branch 3                 2100 values in [7514622, 97083577]
    b = 60 .. 103    branch 6                 10 values in [0, 9]
  a = 88 .. 99
    b = 4 .. 59      branch 6                 12 values in [-4, 11]
    b = 60 .. 66     branch 4                 35 values in [-26521, -10965]
    b = 67 .. 91     branch 6                 6 values in [3, 8]
    b = 92 .. 103    branch 5                 15 values in [2, 19]
  a = 100 .. 103
    b = 4 .. 34      branch 2                 11 values in [-11, -1]
    b = 35 .. 103    branch 6                 10 values in [0, 9]

uses
  a △₁ b  (branch, layer 0)
    ■₁ a  (simple, layer 0)
      # a  (base)
      & a  (base)
      a * b  (base)
    a □₁  (simple, layer 0)
      ■₁ a  (simple, layer 0) (above)
      a % b  (base)
      - a  (base)
    ▲₁ a  (simple, layer 0)
    a $  (base)
    a + b  (base)
    a - b  (base)
    a / b  (base)
```
