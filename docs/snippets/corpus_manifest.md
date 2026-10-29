```json
{
  "format": "opulse-corpus/1",
  "seed": 1,
  "config_hash": "11bc655c08071300",
  "operator_sets": {
    "operators.jsonl": {
      "operator_set": "bbf6684c93571251",
      "operators": 61,
      "defined_operators": 36,
      "settings": "a68130efe9973b16",
      "semantics": {
        "mode": "exact",
        "bound": 2147483647
      },
      "opulse": "0.2.0"
    }
  },
  "splits": {
    "test": {
      "operators": 7,
      "operators_mentioned": 22,
      "documents": 41,
      "chars": 33833,
      "bytes": 48035,
      "tokens_estimate": 12179,
      "kinds": {
        "definitions": {
          "requested": 10,
          "written": 1,
          "duplicates_dropped": 139
        },
        "values": {
          "requested": 20,
          "written": 20,
          "duplicates_dropped": 0
        },
        "derivations": {
          "requested": 20,
          "written": 20,
          "duplicates_dropped": 0
        }
      },
      "shards": [
        {
          "path": "test/test-00000.jsonl",
          "documents": 41,
          "chars": 33833,
          "bytes": 48035,
          "tokens_estimate": 12179,
          "sha256": "e9fb82599b87390c649014c534cc25048060486df9eed74a824bd9c66aa052b7"
        }
      ],
      "mentions_of_other_splits": 15
    }
  },
  "totals": {
    "documents": 241,
    "chars": 184217,
    "bytes": 285632,
    "tokens_estimate": 74602
  }
}
```
