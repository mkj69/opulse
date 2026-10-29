# Numeric preset worlds

A preset selects starting atoms and default settings for generating operators. Choose `successor`, `integer`, `clock`, or `bits` with one option:

```bash
opulse operators --preset successor --out outputs/successor.jsonl --seed 17
```

This command grows successor world operators from its three atoms using the preset layer counts.

| Preset | Starting atoms | Input values sampled by default |
| --- | --- | --- |
| `successor` | successor, predecessor, comparison with zero | 0 through 12 |
| `integer` | the ten shipped integer atoms | 0 through 100 |
| `bits` | bitwise AND, OR, XOR, left shift, right shift, popcount | 0 through 31 |
| `clock` | the ten shipped integer atoms | 0 through 11 |

The clock preset uses modular arithmetic with modulus 12. Set `semantics.modulus` in a config to use another clock size. For example, a modulus of 24 makes `23 + 2` equal `1`.

The successor and bits atoms give an undefined result for negative inputs. The successor predecessor stops at zero. Left shifts with counts above 31 give an undefined result. The custom bit atoms have no z3 encoding, so solver analyses mark definitions that use them as not expressible. Generation, evaluation, traces, and benchmark checks use the reference interpreter.

## Example operators

```text
◇₃ a = { (a ↑) ↑ }
```

For a natural number, this successor world operator adds two.

The integer example comes from `opulse operators --preset integer --out outputs/integer.jsonl --seed 17`:

```text
●₁ a = { ((& a) $) - (& (- a)) }
```

This integer world operator subtracts the digit sum of the negated input from the popcount of the digit sum of the input.

The bits example comes from `opulse operators --preset bits --out outputs/bits.jsonl --seed 17`:

```text
♦₅ a = { a ∨ 2 }
```

This bits world operator returns the bitwise OR of its input and 2.

## Override settings

Put the preset name in a YAML config and provide only the settings you want to change:

```yaml
preset: bits
expressions:
  value_max: 15
operators:
  condition_max: 15
```

This config keeps the bits atom set and samples expression inputs up to 15.

```bash
opulse operators --preset bits --out outputs/bits_default.jsonl --layers 12 6 --seed 17
cat > my_bits.yaml <<'YAML'
preset: bits
expressions:
  value_max: 15
operators:
  condition_max: 15
YAML
opulse operators --config my_bits.yaml --out outputs/bits.jsonl --layers 12 6 --seed 17
```

This command overrides the preset layer counts with 12 operators in layer zero and 6 in layer one.

Use the same config for `expressions`, `verify`, and `bench` so each command registers the preset atoms and applies its settings. To replace the starting atoms, pass `--initial` to `operators`.

## Regenerate a batch

`tools/preset_batches.py` writes checked operator, expression, task and corpus files under `outputs/presets` by default.

```bash
PYTHONPATH=src python tools/preset_batches.py --seed 17 --world successor
PYTHONPATH=src python tools/preset_batches.py --seed 17 --world integer
PYTHONPATH=src python tools/preset_batches.py --seed 17 --world bits
```

The successor command builds a small batch from natural number atoms.
The integer command builds a small batch from arithmetic atoms.
The bits command builds a small batch from bitwise atoms.
Each batch has checked answers.

```bash
PYTHONPATH=src python tools/preset_batches.py --seed 17 --world successor --expressions 20000 --tasks 2000 --limit 0 --out full_batches
PYTHONPATH=src python tools/preset_batches.py --seed 17 --world integer --expressions 20000 --tasks 2000 --limit 0 --out full_batches
PYTHONPATH=src python tools/preset_batches.py --seed 17 --world bits --expressions 20000 --tasks 2000 --limit 0 --out full_batches
```

These commands write larger batches for the three worlds to `full_batches`.
