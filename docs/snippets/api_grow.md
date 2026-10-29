```python
import opulse

world = opulse.World.grow(layers=[20, 10, 5], seed=1)
print(world)
print(world.summary()["layers"])
```

```text
<World 35 operators (L0:20 L1:10 L2:5) over 10 atoms, seed=1>
{0: {'simple': 11, 'branch': 9}, 1: {'recursive': 2, 'simple': 4, 'branch': 4}, 2: {'recursive': 1, 'simple': 2, 'branch': 2}}
```
