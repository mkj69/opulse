# Compiled models

`opulse.compile` turns an operator definition into a small residual network whose weights are set by hand, not trained. Networks compiled separately can be joined into one network by copying their weights, and the joined network computes the composition of the operators. Every network is checked slot by slot against the reference interpreter. The package needs numpy for compiling and torch for building, joining and checking networks.

## What the compiler builds

Inputs range over the integers `0 .. n-1`. Every value the network stores lives in its own **slot**, a named range of coordinates in the residual stream that holds one one-hot token. An integer slot has a token for each integer from `lo` to `hi` and two more tokens:

| Token | Meaning |
| --- | --- |
| `NaN` | the value is undefined, as in the [semantics](../reference/semantics.md) |
| `OOV` | the value is a defined integer outside `lo .. hi`, so the network no longer knows it |

A condition slot holds `F`, `T`, `NaN` (the comparison saw an undefined value) or `OOV`.

Each layer computes `x + down(relu(up(x)))` at a single stream position. There is no attention. The compiler produces three kinds of blocks, and every block reads some slots and writes one new slot:

| Block | Built for | Hidden units |
| --- | --- | --- |
| unary table | a base operation or comparison with one slot argument (the other argument, if any, is a constant) | one per input token |
| binary table | a base operation, comparison, `and` or `or` with two slot arguments | one per pair of input tokens |
| select | one branch of a definition: the branch value if the condition holds, the rest of the chain otherwise | at most two per output token, plus two |

A hidden unit that tests k coordinates has weight 2 on each and bias `1 - 2k`. It is 1 when all k coordinates are set and at most `-1` otherwise.

Other forms are handled at compile time:

* Constant subexpressions fold with the reference interpreter.
* A call of a defined operator is compiled inline. Its parameters become the argument slots.
* A recursive call is unrolled. Each inlined call is compiled only for the argument tokens that can reach it on an evaluated path, so the unrolling stops when no argument reaches a deeper call. A branch that no reaching argument takes is left out. The slots that this leaves behind hold values that are never read, and the verifier marks them "don't care".
* Equal subexpressions with equal argument slots share one block.

Blocks go into the first layer after all the slots they read are written. Blocks in the same layer share one MLP.

## Compile, run, check

```python
import itertools

from opulse.compile import Compiler, Vocab
from opulse.compile.demo import operator_set
from opulse.compile.network import build_network
from opulse.compile.verify import verify

ops = operator_set(["a ◆₁ = { (a % 5) * 3 }",
                    "a ▲₂ b = { a - b, if a > b; b - a, else }"])
triangle = next(op for op in ops.registry if op.symbol == "▲₂")
network = build_network(Compiler(ops.oracle, Vocab(-16, 31)).compile(triangle))

rows = list(itertools.product(range(16), repeat=2))
report = verify(network, ops.oracle, rows, lambda row: ops.oracle.evaluate(triangle, row).value)
print(report.exact, network.stats())
print(network.slot_map)  # slot name -> (start, stop) in the residual stream
```

`operator_set` adds definition texts to the base operations and returns the registry, a parser and an oracle. Any `OperatorRegistry` with an `Oracle` works the same way. `network.run(rows)` returns the output values. `network.decode(x, slot)` reads one slot of a residual stream.

The whole experiment on this page runs with:

```bash
python -m opulse.compile --n 16 --trained --json results.json
python examples/compile/verify_generated.py ops.jsonl --n 8
```

## Stitching

`stitch(parts, wiring, output)` joins finished networks. It reads only their weight matrices. Each part keeps its weights unchanged. They are copied into a wider residual stream, and a wired input slot of a later part takes the coordinates of the slot it is wired to, so no copy layer is needed. The layers of the parts run one after the other.

```python
from opulse.compile.network import compact, stitch

compiler = Compiler(ops.oracle, Vocab(-16, 31))
diamond = next(op for op in ops.registry if op.symbol == "◆₁")
f = build_network(compiler.compile(diamond))    # a ◆₁
g = build_network(compiler.compile(triangle))   # a ▲₂ b
joined = stitch([("f", f), ("g", g)], {"g.in0_a": f"f.{f.output}"}, f"g.{g.output}")
joined.inputs                                     # ['f.in0_a', 'g.in1_b']
packed = compact(joined)
```

`compact` moves every layer to the first position after the layers that write what it reads, again using only the weight matrices, and joins layers that land at the same position. `stitch(..., snap=True)` puts one extra layer in front of each wired input. It computes `relu(4x - 1.5) - relu(4x - 2.5)` on every coordinate, which is exactly 0 below 0.375 and exactly 1 above 0.625. An approximate one-hot vector becomes an exact one when its largest coordinate is above 0.625 and all others are below 0.375.

## What is verified

`verify` runs the network on every input row. For every slot, it computes the exact value the slot stands for with the reference interpreter alone: the subexpression, condition, rest of a branch chain or call recorded for that slot, evaluated on the reference values of the slots it was bound to. Then it compares the tokens. A slot may differ from its reference value in only two ways, both counted:

* it holds `OOV`, and the block that wrote it read an `OOV` token or a don't care constant;
* it lies in a branch or inlined call that its parameter values do not reach.

All other differences are failures. The output is also compared with a separate reference function, by default the interpreter applied to the operator. The check also confirms that every slot holds an exact one-hot vector.

### Separate operators and stitched compositions

Domain `0 .. 15`, slot values `-16 .. 31`, so an integer slot has 50 tokens.

| Operator | Definition | Layers | Max hidden | Non-zero weights | Exact outputs | Slot checks failed |
| --- | --- | --- | --- | --- | --- | --- |
| `◆₁` | `(a % 5) * 3` | 2 | 50 | 300 | 16 of 16 | 0 of 32 |
| `▲₂` | `a - b` if `a > b`, else `b - a` | 2 | 7500 | 30406 | 256 of 256 | 0 of 768 |
| `★₃` | `(a ◆₁) ▲₂ b` | 4 | 7500 | 30706 | 256 of 256 | 0 of 1280 |
| `⬢₄` | `(a ◆₁) ▲₂ (b ◆₁)` | 4 | 7500 | 31006 | 256 of 256 | 0 of 1792 |
| `⬟₅` | `((a ◆₁) ▲₂ b) ◆₁` | 6 | 7500 | 31006 | 256 of 256 | 0 of 1792 |
| `⬡₆` | `(a ◆₁) ▲₂ 7` | 4 | 150 | 1156 | 16 of 16 | 0 of 80 |
| `♣₇` | recursive, `a % 6` steps | 20 | 300 | 8141 | 16 of 16 | 0 of 250 |

Each composite was also built by stitching the separately compiled `◆₁` and `▲₂` networks:

| Composite | Form | Layers | Residual width | Exact outputs | Same outputs as whole compile | Same blocks as whole compile |
| --- | --- | --- | --- | --- | --- | --- |
| `★₃` | whole compile | 4 | 354 | 256 of 256 | | |
| `★₃` | stitched | 4 | 354 | 256 of 256 | yes | yes |
| `⬢₄` | whole compile | 4 | 454 | 256 of 256 | | |
| `⬢₄` | stitched | 6 | 454 | 256 of 256 | yes | yes |
| `⬢₄` | stitched, then `compact` | 4 | 454 | 256 of 256 | yes | yes |
| `⬟₅` | whole compile | 6 | 454 | 256 of 256 | | |
| `⬟₅` | stitched | 6 | 454 | 256 of 256 | yes | yes |
| `⬡₆` | whole compile | 4 | 304 | 16 of 16 | | |
| `⬡₆` | stitched, `b` fed 7 | 4 | 354 | 16 of 16 | yes | no |

For `★₃`, `⬢₄` and `⬟₅` the stitched network holds the same multiset of blocks as the whole compile, with every weight equal. Only the slot positions differ. Stitching `⬢₄` places the two `◆₁` copies one after the other, and `compact` puts them back side by side. For `⬡₆` the whole compile knows that `b` is 7 and turns each `▲₂` table into a unary one (max hidden width 150 instead of 7500). A stitched `▲₂` cannot do this.

### A generated operator set

Generated with `opulse operators --layers 20 10 6 --seed 3`, then checked with `examples/compile/verify_generated.py` on the domain `0 .. 7` with slot values `-16 .. 15`:

| Definition kind | Operators | No `OOV` in place of an in-range answer |
| --- | --- | --- |
| simple | 19 | 14 |
| branch | 14 | 9 |
| recursive | 3 | 3 |

Over all 36 operators, 1098 of 1240 outputs equal the reference value clamped to the vocabulary: 810 are the exact integer or `NaN`, and 288 are `OOV` because the answer itself lies outside `-16 .. 15`. The other 142 are `OOV` although the answer is in range, because an intermediate value left `-16 .. 15`. No output and none of the 33846 checked slot values is wrong. The largest network, for the recursive `♤₇₉`, has 241 layers and 1263 blocks.

### Trained blocks

`opulse.compile.trained.train_operator` fits one MLP layer by gradient descent, with the same input and output slots, until it writes the right token for every input token combination. Measured on the domain `0 .. 15`:

| Network | Correct tokens on the domain | Largest distance from one-hot |
| --- | --- | --- |
| trained `◆₁` (64 hidden units) | 16 of 16 | 0.0004 |
| trained `▲₂` (512 hidden units) | 256 of 256 | 0.029 |
| trained `◆₁` stitched to trained `▲₂` | 256 of 256 | 0.026 |
| trained `◆₁` stitched to compiled `▲₂` | 256 of 256 | 0.0001 |
| compiled `◆₁` stitched to trained `▲₂` | 256 of 256 | 0.026 |

A token counts as correct when the largest coordinate of the slot is the right one. Trained slots are close to one-hot vectors but not equal to them, so `verify` reports them as not one-hot.

To see how errors combine, Gaussian noise with standard deviation σ was added to every non-zero weight and bias of both parts (5 seeds, mean fraction of correct tokens). "Product" multiplies the two parts' fractions, each measured alone on exact one-hot inputs. σ is absolute, and compiled and trained weights have different scales, so compare rows of one kind only.

| Parts | σ | `◆₁` alone | `▲₂` alone | Product | Stitched | Stitched with `snap=True` |
| --- | --- | --- | --- | --- | --- | --- |
| compiled | 0.05 | 1.000 | 1.000 | 1.000 | 0.682 | 0.976 |
| compiled | 0.10 | 1.000 | 0.946 | 0.946 | 0.467 | 0.778 |
| compiled | 0.20 | 0.875 | 0.726 | 0.635 | 0.223 | 0.469 |
| trained | 0.05 | 1.000 | 0.988 | 0.988 | 0.883 | 0.988 |
| trained | 0.10 | 0.925 | 0.299 | 0.282 | 0.088 | 0.259 |
| trained | 0.20 | 0.275 | 0.045 | 0.013 | 0.015 | 0.014 |

Without the snap layer, the stitched pair is correct less often than the product of its parts. The second part reads the first part's noisy output, and that deviation adds to its own noise. With the snap layer the stitched pair is correct more often. For the trained parts it is within 0.03 of the product; for the compiled parts it stays below the product.

## Inspecting with nnsight

A compiled network is an ordinary `torch.nn.Module`, so nnsight can wrap it:

```python
from nnsight import NNsight

model = NNsight(network)
with model.trace(network.embed(rows)):
    after_first = model.layers[0].output.save()
start, stop = network.slot_map["s2"]  # one slot; network.slots["s2"].text says what it holds
```

`network.blocks` lists each block with its layer, its hidden unit range and the slot it writes.

## Limits

* **Domain size.** The vocabulary has `hi - lo + 3` tokens. A binary table has one hidden unit per pair of tokens, so its width grows with the square of the vocabulary: 2500 units at 50 tokens. The weight matrices are dense, so `▲₂` above has 3.9 million parameters of which 30406 are non-zero.
* **Values outside `lo .. hi`.** They become `OOV`, and every value computed from them is `OOV` too. The network never gives a wrong integer for them, but an operator whose intermediate values leave the range is exact only on part of the domain. Choose `lo` and `hi` to cover the intermediate values.
* **Supported forms.** Integer operators with simple, branch and recursive definitions; comparisons, `and`, `or`, `not`; calls of defined operators; integer literals and `NaN`. Not supported: `search(...)`, string and list values, bool-valued conditions, and atoms with more than two arguments. Operators with three or more arguments compile in principle but were not tested.
* **Recursion.** Unrolling follows every argument that can reach a call, so the size grows with the number of distinct reachable arguments, not only with the recursion depth. `max_depth` (64 nested calls) and `max_blocks` stop runaway cases with `CompileError`.
* **Stitching.** Stitched depth is the sum of the part depths until `compact` runs. Folding constants, sharing blocks and leaving out unreached branches across a call boundary happen only in a whole compile. Stitched parts must use the same vocabulary.
* **One position.** All values sit in one residual stream position. Nothing is routed between token positions.
