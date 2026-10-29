```text
Operator `%`: `a % b = a - b × trunc(a / b)` uses a quotient truncated toward zero; the remainder has the sign of `a` or is zero; when `b = 0`, the result is NaN. NaN inputs propagate; in exact mode a result outside `[-B, B]` is NaN.
Operator `-`: `- a` negates the integer. NaN inputs propagate; in exact mode a result outside `[-B, B]` is NaN.
Operator `-`: `a - b` is integer subtraction. NaN inputs propagate; in exact mode a result outside `[-B, B]` is NaN.
Operator `&`: `& a` sums the decimal digits of `|a|`, then multiplies by `sgn(a)`. NaN inputs propagate; in exact mode a result outside `[-B, B]` is NaN.
Operator `+`: `a + b` is integer addition. NaN inputs propagate; in exact mode a result outside `[-B, B]` is NaN.
```
