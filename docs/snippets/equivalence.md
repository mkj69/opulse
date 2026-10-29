```text
bound=2147483647:  (a + b) - b  ==  a  ->  refuted  counterexample {'a': 1, 'b': 2147483647}: None vs 1
bound=2147483647:  (a + b) * (a + b)  ==  ((a * a) + (b * b)) + ((2 * a) * b)  ->  refuted  counterexample {'a': 2147483647, 'b': -2147483647}: 0 vs None
bound=None:  (a + b) - b  ==  a  ->  proved
bound=None:  (a + b) * (a + b)  ==  ((a * a) + (b * b)) + ((2 * a) * b)  ->  proved
```
