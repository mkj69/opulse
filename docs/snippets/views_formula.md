```latex
a \,\text{◆₁₁} = \begin{cases}
  -2 & \text{if } a \mathbin{\text{\%}} 9 = 0 \\
  \text{\&}\, \left(\left(\left(a \mathbin{\text{\%}} 9\right) - 1\right) \,\text{◆₁₁}\right) & \text{if } a \mathbin{\text{\%}} 9 > 0 \\
  \text{\&}\, \left(\left(\left(a \mathbin{\text{\%}} 9\right) + 1\right) \,\text{◆₁₁}\right) & \text{if } a \mathbin{\text{\%}} 9 < 0 \\
  \mathrm{NaN} & \text{if no case above applies}
\end{cases}
```
