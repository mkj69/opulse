```text
opulse corpus --operators operators.jsonl --out corpus --documents train=200,test=50 \
  --split operator --split-ratios train=0.8,test=0.2 \
  --mix definitions=1,values=2,derivations=2 --probe --seed 1 --workers 2
```

prints

```json
{"out": "corpus", "totals": {"documents": 241, "chars": 184217, "bytes": 285632, "tokens_estimate": 74602}, "splits": {"train": 200, "test": 41}}
```
