---
description: An essay on compiling Opulse operators into residual networks with hand set weights and joining separately compiled networks by copying their weights.
---

# Compile and Stitch

<div class="stv-page"></div>

<p class="stv-byline"><em>Ma Kaijing · October 24, 2026</em></p>

A programmer who calls a library function does not need to know how it was written. The function
has a fixed interface, and any code that respects the interface can use it. Large programs are built
this way, one tested part at a time.

A trained neural network gives no such guarantee. It can spread what it knows across millions of
weights without marking where one piece ends and the next begins. That makes it hard to isolate one
piece, test it alone, and connect it to another model.

Could knowledge in a network be built like software? Suppose two concepts are each built as a
separate network, neither aware of the other. Can the two networks be snapped together, with no
weight changed, so that the joined network computes the combined concept exactly? Testing whether the parts fit and
how their joint behaves under weight noise shows what this kind of interface requires.

Composition of this kind is a first step toward modular knowledge, whose parts could be added,
replaced, edited and inspected one at a time. This essay tests that step in networks built by hand.

To ask this precisely we need concepts small enough to check completely. Opulse defines new
concepts as short definitions over a few integer operations. Here are two:

* `a ◆₁ = { (a % 5) * 3 }` takes the remainder modulo 5 and triples it.
* `a ▲₂ b = { a - b, if a > b; b - a, else }` is the distance between two numbers.

Together they give `(a ◆₁) ▲₂ b`. For `a = 12` and `b = 3`, `12 ◆₁` is 6, and the distance from 6
to 3 is 3.

So we build the networks by hand, writing every weight so that the meaning of every coordinate is
known. With real weight matrices, we then test three things: whether separately built parts join, what
joining costs in size, and how errors behave at the joint.

!!! abstract "What we found"

    * **Compiled parts snap together exactly.** The stitched network, assembled by copying the separately compiled weights of `◆₁` and `▲₂` and
      wiring one slot, is exact on all 256 inputs. All 1280 slot checks agree with the Opulse reference interpreter.
    * **For three composites, stitching yields the blocks of a whole compile.** Outputs are identical and the blocks match value for value; only slot coordinates and the
      arrangement of blocks across layers differ.
    * **A stitched part keeps its general tables.** With one argument fixed at 7, the whole compile's
      widest layer is 50 times narrower: 150 hidden units against 7500.
    * **Errors grow at the joint.** At weight noise σ = 0.05, compiled `◆₁` alone is correct on all of its inputs
      and `▲₂` alone scores 0.9998, but the stitched pair
      scores 0.703. A noise free
      cleanup layer at the joint restores 0.983.
    * **The compiler covers more than two examples.** All 36 generated operators compile, and every checked slot passes the verifier. Of their 1240 outputs, 142 lose an in range answer because an intermediate
      value left the range; none is a wrong integer.

Every result and the data behind every figure come from `tools/stitch_visuals.py`, which reruns the
whole experiment on a CPU.

## An operator becomes a lookup table

The compiler turns each operation into a block of lookup units, and each value into a named place
in one vector. That vector is the **residual stream**, which every layer reads and adds to. Each
value gets its own **slot**, a fixed range of coordinates, so no value ever overwrites another.

The compiler walks a definition once and emits one block per operation. `◆₁` has two operations,
`% 5` and `* 3`, so its network has two layers with one block each. Each block of `◆₁` is a lookup table with one hidden unit per input token. When the input slot
holds an exact one hot token, exactly one unit fires and writes the answer.

??? note "How it works: tokens, slots and lookup units"

    The inputs are the integers 0 to 15. Every integer value the network stores is a token from a fixed vocabulary: the integers from −16 to 31, plus `NaN` for an undefined value and `OOV` for a defined
    integer outside that range. That makes 50 tokens. A value in an integer slot is stored one hot, as 50 coordinates of which exactly
    one is 1.

    There is a single stream position and no attention. Each layer is a small MLP that adds its output
    to the stream: `x + down(relu(up(x)))`.

    In a lookup block, the unit for token `t` has weight 2 on coordinate `t` and bias −1. If the slot
    holds `t`, the unit computes `2·1 − 1 = 1`. If it holds any other token, the unit computes `−1`,
    which the ReLU turns into 0. The unit's single output weight writes a 1 into the coordinate of the
    answer token. So every unit has a margin of 1 on either side of the ReLU, and exactly one unit per
    block fires.

Because each unit stands for one input value, the weights of `◆₁` can be read as its table.

<div class="stv" data-stv="operator" data-src="../assets/data/stitch/operator.json" markdown="0">
<p class="stv-title">Figure 1. An operator as weights</p>
<p class="stv-lede">The compiled network of <code>a ◆₁</code>. Left: its table on the inputs 0 to 15. Right: the five columns are the input slot, the 50 hidden units of layer 1, the slot <code>a % 5</code>, the 50 units of layer 2 and the output slot. Each faint wire is one nonzero input or output weight read from the network; the biases are not drawn. Hover or tap a row or an input token to light the unit that fires.</p>
<p class="stv-static">The interactive figure needs JavaScript. Its data is in docs/assets/data/stitch/operator.json.</p>
</div>

Layer 1 sends every integer token to its remainder and passes `NaN` and `OOV` through, so its 50
output wires converge on a handful of tokens.
Layer 2 triples the remainders. Of the network's 30100 parameters, 300 are nonzero: per layer, 50 input
weights, 50 biases and 50 output weights.

Two more kinds of block cover the rest. An operation on two slots becomes a **binary table**, with
one unit per pair of input tokens. A definition with branches becomes a **select chain**, which
computes the condition and copies the value of the branch it picks. `▲₂` uses both: its first layer
computes `a > b`, `a - b` and `b - a`, and its second picks one.

??? note "How it works: binary tables, branches and recursion"

    A binary table has 2500 units, one per pair of tokens, each with weight 2 on two coordinates and
    bias −3.

    In a select chain, the condition `a > b` is itself a binary table that writes one of four tokens
    (`F`, `T`, `NaN`, `OOV`) into a small slot. A select block then copies the value of the branch
    whose condition holds: 50 units pass a value when the condition is `T`, 50 when it is `F`, and two
    more write `NaN` or `OOV` when the condition itself is undefined or unknown. For `▲₂` the first
    layer holds three binary tables (`a > b`, `a - b`, `b - a`, 7500 units in all) and the second this
    select block of 102 units.

    Calls of other operators are compiled inline, and a recursive call is unrolled as far as the
    arguments that can actually reach it.

For each input, the verifier checks every computed slot on the path that input takes against the Opulse
reference interpreter. On the inputs 0 to 15, `◆₁` passes 32 slot checks. On all pairs of those inputs, `▲₂` passes 768.
None fails. The interpreter never looks at the
network, but it is not a fully independent witness: the compiler used the same interpreter to fill
its tables, so a mistake in the semantics themselves would pass.

??? note "How it works: the verifier"

    The verifier runs each input through the network and asks the interpreter what each slot should
    hold: the value of the subexpression, condition or call the compiler recorded for it. A slot is
    excused only when its branch is not taken for that input; Figure 2 shows one.

## Two parts, one stream

Stitching copies two compiled networks into one stream and connects them through one shared slot.
For `◆₁` and `▲₂`, the result is exact.

`◆₁` and `▲₂` are compiled separately but with the same vocabulary, so their slots already use one
code. Stitching copies both sets of layers, unchanged, into one wider residual stream and runs them in
order. The only new decision is the wiring, made by hand: `▲₂`'s input slot `a` is placed on the
same coordinates as `◆₁`'s output slot.

No weight value changes and no copy layer is added: `▲₂` reads where `◆₁` wrote. The experiment
tests composition through a shared code and a chosen wire. It does not test whether such an
interface could be discovered.

Figure 2 follows one input through the stitched network, slot by slot.

<div class="stv" data-stv="flow" data-src="../assets/data/stitch/flow.json" markdown="0">
<p class="stv-title">Figure 2. Slots in the residual stream</p>
<p class="stv-lede">The stitched network <code>(a ◆₁) ▲₂ b</code>: eight slots, four layers, residual width 354. Rows are slots in stream order; columns are the stream after each layer. The verifier checks the computed slots: ✓ marks a match with the interpreter, ○ marks a branch value this input does not use, which is not checked. Pick inputs and press Run.</p>
<p class="stv-static">The interactive figure needs JavaScript. Its data is in docs/assets/data/stitch/flow.json.</p>
</div>

The stitched network gives the exact answer on all 256 inputs. Across them the verifier makes 1280
slot checks, all correct. Another 256 slot values go unchecked, because for each input one of `x - b` and `b - x`, where `x`
is the output of `◆₁`, lies on the branch not taken. Every slot holds an exact one hot vector, which is stronger
than having the right argmax.

## The same blocks as a whole compile

For three composites, stitching produces exactly the blocks that compiling the composite in one
piece produces.

The stitched expression `(a ◆₁) ▲₂ b` can also be written as one operator,
`a ★₃ b = { (a ◆₁) ▲₂ b }`, and compiled whole.
Identical outputs would show that the two networks compute the same function. Comparing their
blocks asks whether they use the same machinery.

For `★₃`, `⬢₄ = (a ◆₁) ▲₂ (b ◆₁)` and `⬟₅ = ((a ◆₁) ▲₂ b) ◆₁`, the whole and stitched networks give
identical outputs. Cutting every block out of the weight matrices gives the same collection in
both, with every value equal.

What differs is placement. The slots sit at other coordinates, and stitched `⬢₄` runs its two copies
of `◆₁` one after the other, in 6 layers where the whole compile needs 4. A second pass, `compact`,
merges layers that do not depend on each other and brings stitched `⬢₄` back to 4.

??? note "How it works: comparing blocks and compacting layers"

    A block is cut out of the assembled weight matrices as its hidden units together with the
    coordinates of the slots it reads and writes. Two networks match when these collections are equal,
    value for value, wherever the blocks sit. `compact` reads only the weight matrices: it finds layers
    that do not depend on each other and merges them.

## What stitching costs

A part compiled on its own cannot use facts that hold only where it is used. That can cost a great
deal of size.

The fourth composite fixes one argument: `a ⬡₆ = { (a ◆₁) ▲₂ 7 }`. The whole compile knows that `b`
is 7, so each binary table of `▲₂` collapses into a unary one with 50 units instead of 2500. In the stitched network, `b` stays an input slot that is fed 7, so `▲₂` keeps its full binary
tables.

Figure 3 compares the layer widths of the two networks when `b` is fixed at 7.

<div class="stv" data-stv="whole" data-start="⬡₆" data-src="../assets/data/stitch/whole_vs_stitched.json" markdown="0">
<p class="stv-title">Figure 3. Whole versus stitched</p>
<p class="stv-lede">Each row is a layer; bar length is hidden units on one scale shared by both networks. Choose a composite.</p>
<p class="stv-static">The interactive figure needs JavaScript. Its data is in docs/assets/data/stitch/whole_vs_stitched.json.</p>
</div>

Both networks are exact on all 16 inputs, but the whole one is far smaller. Its widest layer has 150
units against 7500 for the stitch, 50 times narrower. The whole network has 1156 nonzero parameters, against 30706 in the
stitched one.

A module compiled alone must be correct for every value another module could write into its slot.
The compiler also drops unreachable branches and shares repeated subexpressions. Across a stitch it
can do neither, though these four composites do not measure what that costs.

If trained networks face the same trade, one would expect cheaper specialised circuits wherever the
context is fixed, rather than reused general ones. That is a hypothesis about trained models, and this experiment does not test it.

## Where approximate parts break

Under weight noise, two parts that are each almost always right can fail together far more often
than their scores suggest. The loss happens at the wire.

Hand set weights are exact by construction, so we also trained each part by gradient descent. Both trained parts reach 100% on their tables, and the stitched pair is correct on all 256 inputs. But the slots they write are only approximately one hot. The next part reads magnitudes, so once the weights are
disturbed, the joined network can fail even when the first part's output
has the right argmax.

??? note "How it works: the trained parts"

    For each operator, one MLP layer with the same input and output slots as the compiled part was
    trained on its full table until every input combination decoded to the right token: 64 hidden
    units for `◆₁`, 512 for `▲₂`. In the stitched pair, the largest deviation from an exact one hot
    vector is 0.026.

To see how small errors combine, we add Gaussian noise with standard deviation σ to every nonzero
weight and bias, and compare the stitched pair with the product of the parts' separate scores. The product is a rough reference: what one would expect if the parts' errors were independent and the wire passed values
through cleanly. Neither assumption is tested here.

??? note "How it works: the noise protocol"

    Each setting is repeated 50 times with fixed seeds. `◆₁` alone is scored on its 16 inputs. `▲₂`
    alone is scored on the 256 pairs it receives inside the stitched network, with exact one hot
    inputs. σ is absolute. The trained curves perturb one trained pair; they do not vary the training
    run.

    These numbers agree in shape with the table in the
    [compiled models guide](../guide/compiled-models.md), which uses 5 trials and scores `▲₂` on its
    own 256 inputs, so its values differ slightly (0.682 instead of 0.703 for the stitched pair at
    σ = 0.05).

With compiled parts at σ = 0.05, `◆₁` alone is correct on all of its inputs, `▲₂` alone scores 0.9998, and the
product is 0.9998. The stitched network scores 0.703. Figure 4 follows the gap as the
noise grows.

<div class="stv" data-stv="noise" data-src="../assets/data/stitch/noise.json" markdown="0">
<p class="stv-title">Figure 4. How errors compose</p>
<p class="stv-lede">Accuracy against weight noise σ, compiled parts (left) and trained parts (right). Touch or hover a chart to see values. σ is absolute, and the two kinds of weights have different scales, so compare curves within a panel. The trained curves perturb one trained pair; they do not vary the training run.</p>
<p class="stv-static">The interactive figure needs JavaScript. Its data is in docs/assets/data/stitch/noise.json.</p>
</div>

At low noise, the stitched network falls far below the product. The gap hides inside the word "correct". A part is scored by the argmax of its output slot, but the
next part reads magnitudes. At σ = 0.05 the argmax of `◆₁`'s output was right every time, yet 61% of
its peak values fell outside 0.9 to 1.1, and the lookup units downstream amplify such deviations.

Splitting the noise locates the loss. A noisy `◆₁` feeding a clean `▲₂` already drops to 0.705. A
clean `◆₁` feeding a noisy `▲₂` stays at 0.9998. The damage is done at the wire.

??? note "How it works: why small deviations are amplified"

    At σ = 0.05, the largest coordinate of `◆₁`'s output ranged from 0.488 to 1.619 across trials and
    inputs, and 61% of those peaks fell outside 0.9 to 1.1. A lookup unit reads its inputs with weight
    2, so an input of 0.75 instead of 1 lowers its preactivation from 1 to 0.5. The next unit, which
    needs two inputs near 1 to clear its bias, may not fire at all.

    Off peak coordinates can also wake or silence lookup units. They were not measured separately, so
    the peak sizes above illustrate the mechanism; they do not account for all of the loss.

## Cleaning the joint

A noise free layer that rounds the values at the wire recovers most of the measured loss. The
rounding has limits of its own.

A **snap layer** at the wire sends each coordinate of the slot that is clearly low to exactly 0 and
each one that is clearly high to exactly 1. With the
snap layer itself kept free of noise, the compiled pair at σ = 0.05 recovers from 0.703 to 0.983.

??? note "How it works: the snap layer"

    Each coordinate passes through `relu(4x − 1.5) − relu(4x − 2.5)`, which gives exactly 0 below
    0.375 and exactly 1 above 0.625. A slot comes out exact when its correct coordinate is above 0.625
    and every other coordinate is below 0.375. In the main curve the snap layer receives no noise.

The fix has two limits. First, the rounding condition fails more often as σ grows: at σ = 0.1 the
snapped pair scores 0.813 against a product of 0.958.

Second, the snap layer is itself made of weights. When its nonzero weights and biases receive the same noise as the parts, the pair scores 0.761 at σ = 0.05. At σ = 0.1 it scores 0.482, slightly below no snap at all
(0.497). Cleanup pays only when it is more precise than what it cleans.

At σ = 0.05, trained parts show the same pattern at their own scale: their product is 0.980, the
stitched pair scores 0.880, and the snapped pair returns to 0.980.

??? note "How it works: trained parts under noise"

    Trained weights are much smaller than compiled ones: root mean square 0.10 and 0.11, against 1.41
    and 2.12. The same σ is therefore a larger relative disturbance. At σ = 0.05 the trained parts
    score 1.000 and 0.980 alone.

    The trained `▲₂` tolerates a noisy input better than the compiled one: a noisy trained `◆₁`
    feeding a clean trained `▲₂` still scores 1.000 at σ = 0.05. Near the floor the order flips. At
    σ = 0.2 the trained stitched pair scores 0.023 against a product of 0.013, and by σ = 0.3 every
    trained curve except `◆₁` alone (0.101) is below 0.03.

## Thirty six operators

The compiler is not limited to two hand picked operators. In these tests, a value that leaves the
range sometimes costs an answer, but no output is ever a wrong integer or a wrong `NaN`.

A generated set of 36 operators (19 simple, 14 with branches, 3 recursive) all compile and pass
verification on the inputs 0 to 7, with integer tokens from −16 to 15. The largest network, for the
recursive `♤₇₉`, has 241 layers and 1263 blocks.

<div class="stv" data-stv="generated" data-src="../assets/data/stitch/generated.json" markdown="0">
<p class="stv-title">Figure 5. Thirty six generated operators</p>
<p class="stv-lede">One card per operator, grouped by kind and sorted by depth. The thin bar is depth on a log scale. The thicker bar splits the outputs (8 per unary operator, 64 per binary one) into exact values, correct <code>OOV</code> for answers outside the range, and <code>OOV</code> where an intermediate value left the range. None is a wrong integer. Tap or hover a card to see its definition and counts.</p>
<p class="stv-static">The interactive figure needs JavaScript. Its data is in docs/assets/data/stitch/generated.json.</p>
</div>

Of the 1240 outputs, 810 give the correct integer or `NaN`. Another 288 are `OOV`, correctly, because
the answer itself lies outside −16 to 15. The remaining 142 are `OOV` although the answer is in
range: those answers are lost. None of the 33846 checked slot values is wrong.

The checks cover only the paths that inputs take. Another 143322 slot values, 81% of all, lie on
branches or calls that their inputs do not reach and were not checked.

??? note "How it works: when an `OOV` counts as correct"

    The verifier accepts an `OOV` slot only when a value it depends on is already `OOV` or when its
    exact value is itself out of range. So each lost answer goes back to an intermediate value outside
    the range.

## A test bed with known answers

Compiled networks give interpretability methods a test bed with known answers. Methods are usually
judged on models whose mechanism no one knows; here every slot has a stated meaning, and the
interpreter gives the value it should hold.

Take the slot named `a % 5`, which holds the remainder after layer 1. A probe, which decodes a value from activations, may also decode the remainder from the input slot,
because the input determines it. So decoding alone cannot show whether the network reads the `a % 5` slot.

Patching, which replaces an activation with the one
from another input, tests the slot's causal role: after a patch, the output should be exactly what
the interpreter predicts for the patched value. A circuit discovery method could likewise be scored on whether it recovers the compiled network's
recorded blocks and the effects of slot interventions.

??? note "How it works: tracing with nnsight"

    The networks are ordinary `torch.nn.Module` objects, and nnsight 0.7.0 traces them. In the stitched
    network, after the first layer, the slot `a % 5` holds 0 for the input (5, 9), as it should.

Stitching adds a second use. A trained part can put every argmax in the right place and still write magnitudes the next part
does not expect, and that error compounds across the wire. Whether trained models normalise or
clean values between the components they compose is a question this setup can pose precisely,
because the answer for the compiled case is known.

## Proposed experiments { #two-follow-up-experiments }

Two experiments ask whether a compiled module works inside a pretrained model, and whether
training finds a similar mechanism. Neither experiment has been run. The existing base code is in
[the compiler](https://github.com/mkj69/opulse/tree/HEAD/src/opulse/compile) and
[the compile examples](https://github.com/mkj69/opulse/tree/HEAD/examples/compile).

**A. Write a new concept into a pretrained model without training the module.** Insert the compiled `◆₁`
network into the residual stream of a real model such as Qwen2.5 0.5B, through a read adapter and a
write adapter that are the only fitted parts. Then ask whether the model answers `5 ◆₁ =`
correctly, and whether it uses `◆₁` inside longer expressions such as `(5 ◆₁) + 2`. Controls decide
what any result means: the model without the module, a blank module, a module with shuffled input or
output mappings, and inputs the adapters were not tuned on.

??? note "How it works: adapters and outcomes"

    The read adapter maps the model's residual stream at the operand position to the one hot input
    slot. The write adapter maps the output slot back into the residual stream, for example along the
    directions the model itself uses to score the answer tokens.

    How the results would be read:

    * If the model answers both kinds of question on held out prompts and every control fails, that is
      evidence that this module works inside a trained residual stream through these adapters, and that
      later layers read its output. It would not yet show that a concept can be added in general.
    * If it answers `5 ◆₁ =` but fails inside longer expressions, the write adapter may have put the
      value where the unembedding reads answers but not where later layers read intermediate values.
      Varying where the value is written can test this.
    * If it fails even on `5 ◆₁ =`, the adapters are the first suspect. Reading an operand out of a
      trained stream may itself be the hard part, or the inserted vectors may be off distribution and get
      overwritten. The layer and scale of insertion are the next things to vary.

**B. Does gradient descent find the compiled solution?** Train a small transformer from scratch on
Opulse data for the same operators, and compare it with the compiled network slot by slot and layer
by layer.

In [Constructing an LLM-Computer](https://www.percepta.ai/blog/constructing-llm-computer)
(March 2026), the Percepta Research Team describe their compiler from code to weights and report that they "analytically compiled a WebAssembly VM into a transformer". A construction like
theirs, or like the networks here, shows that suitable weights exist. Whether training finds them is
a separate question, and it is the one experiment B asks.

??? note "How it works: comparisons and outcomes"

    Probes for every compiled slot value at every layer; activation patching, scored against the
    interpreter's predicted outputs; centred kernel alignment (CKA), a similarity score between the two
    networks' activations; and an alignment of their layers.

    How the results would be read:

    * If the intermediate values can be decoded and changing them moves outputs as the interpreter
      predicts, training may have found a similar computation, and layer alignment would strengthen the
      case. Compiled networks could then serve as reference mechanisms for trained ones.
    * If the values are present but at other layers, or merged and spread across directions, training
      may use the same variables with another schedule or encoding. The slot structure would then be a
      useful coordinate system, though not a literal description.
    * If the outputs are right but probes and patches find no causally relevant intermediate values, the
      model may compute the composite another way, perhaps closer to one memorised table. The methods
      may also miss values that are there, so probe strength and the validity of each intervention need
      their own controls.
    * Mixed results, such as some slots found and others not, or a model that fails on part of the
      table, are likely and would be reported slot by slot.

## Limits

* **MLP only.** Every network is a stack of MLP layers at a single stream position. There is no
  attention, nothing moves between token positions, and the inputs arrive already stored one hot in
  their slots.
* **Small ranges.** The main vocabulary has 50 tokens, and a binary table's width grows with its square.
  Values outside the range become `OOV`: the network never gives a wrong integer, but it stops
  knowing the value.
* **Dense weights.** The stitched `★₃` network stores 5460718 parameters, of which 30706 are
  nonzero.
* **Simple training and noise.** The trained blocks are single layers fitted to complete tables, not
  models trained on text. Gaussian weight noise is a crude stand in for a real model's errors.
* **Supported forms.** Integer operators with simple, branch and recursive definitions. Search,
  strings, lists and bool valued conditions are not compiled.

## What this shows

In these hand compiled networks, separately built concepts do snap together. Two concepts compiled apart combine
into an exact composite by copying weights and choosing one wire, and for three composites the
result holds the same blocks a whole compile would build.

The conditions are strict. Here the parts had to share a code at the interface, and the values
crossing it had to be exact enough that the reader's thresholds were not disturbed. Errors small enough to leave every argmax of `◆₁` intact were enough to break the joint.

The experiment does not show that trained models are modular, that an interface can be found
without being chosen by hand, or that any of this survives attention and real data. For interpretability, it offers a reference mechanism: every slot has a stated meaning, and the
interpreter predicts every value an input uses. Methods can be scored against it. Whether trained
models contain comparable interfaces remains open.

## How to run

Torch is needed. Everything runs on a CPU. On one machine the last command below took 6 minutes,
two of them for the 241 layer network, and used up to 64 GB of memory because the weights are
stored densely.

```bash
python -m opulse.compile --n 16 --trained --json results.json   # the tables of the guide
opulse operators --out ops.jsonl --layers 20 10 6 --seed 3
python examples/compile/verify_generated.py ops.jsonl --n 8      # the 36 generated operators
python tools/stitch_visuals.py                                   # every result and figure on this page
```

In code, a stitch is one call:

```python
from opulse.compile import Compiler, Vocab
from opulse.compile.demo import operator_set
from opulse.compile.network import build_network, stitch

ops = operator_set()
by_symbol = {op.symbol: op for op in ops.registry if op.definition is not None}
compiler = Compiler(ops.oracle, Vocab(-16, 31))
f = build_network(compiler.compile(by_symbol["◆₁"]))
g = build_network(compiler.compile(by_symbol["▲₂"]))
joined = stitch([("f", f), ("g", g)], {"g.in0_a": f"f.{f.output}"}, f"g.{g.output}")
joined.run([(5, 9), (12, 3)])   # [9, 3]
```

The [compiled models guide](../guide/compiled-models.md) documents the compiler, the verifier and
the full tables.

## Acknowledgements

<!-- acknowledgements list -->

## Citation

Please cite this post as:

Ma Kaijing. "Compile and Stitch." Blog post, 2026. https://mkj69.github.io/opulse/stitching/

```bibtex
@misc{ma2026stitch,
  author       = {Ma, Kaijing},
  title        = {Compile and Stitch},
  year         = {2026},
  howpublished = {\url{https://mkj69.github.io/opulse/stitching/}},
  note         = {Blog post}
}
```
