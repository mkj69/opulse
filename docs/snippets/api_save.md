```python
path = world.save("my_world")
print(sorted(p.name for p in path.iterdir()))
again = opulse.World.load(path)
print(again.fingerprint == world.fingerprint)
```

```text
['config.yaml', 'operators.jsonl', 'world.json']
True
```
