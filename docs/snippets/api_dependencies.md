```python
print([dep.symbol for dep in world.dependencies(op, transitive=True)])
print([caller.symbol for caller in op.callers])
graph = world.graph(focus=op)
print(graph)
```

```text
['+', '-', '%']
['♣₄₉']
<Graph 4 operators, 4 edges>
```
