---
description: An essay on Opulse as a controlled laboratory for regularities about training data.
---

# A Laboratory for Data Laws

*Ma Kaijing · October 24, 2026*

Here are two definitions that did not exist before the command that printed them.

```text
◆₁ a = { ((a + a) $) * (# (& 5)) }

a ◆₂ b = { b,                        if a % 9 == 0;
           ◆₁ (((a % 9) - 1) ◆₂ b),  if a % 9 > 0;
           ◆₁ (((a % 9) + 1) ◆₂ b),  if a % 9 < 0 }
```

The atoms are ordinary. `$` counts the 1 bits of a number, `#` gives the triangular number, `&`
sums decimal digits and `%` takes the remainder. Since `# (& 5)` is `# 5`, which is 15, `◆₁` counts
the 1 bits of `2a` and multiplies by 15. The second definition calls itself. For positive `a` it
says: apply `◆₁` to `b` exactly `a % 9` times. The generator paired the definitions with this
question:

```text
What is the value of 43 * (& (31 ◆₂ 50))?
```

Since 31 % 9 is 4, the answer applies `◆₁` four times to 50. Fifty has three 1 bits, so the first
application gives 45. Forty five has four, so the second gives 60. Sixty also has four, so the third
and fourth applications return 60 again. The digit sum of 60 is 6, and 43 · 6 is 258. The reference
derivation takes 39 lines, one rewrite per line, and the interpreter checks every line before
writing it.

Now apply `◆₁` three times instead of four. The answer is still 258.

| times `◆₁` is applied | 0 | 1 | 2 | 3 | **4** | 8 |
| --- | --- | --- | --- | --- | --- | --- |
| value of the inner part | 50 | 45 | 60 | 60 | **60** | 60 |
| final answer | 215 | 387 | 258 | 258 | **258** | 258 |

Sixty is a fixed point of `◆₁`, so every count from two upward lands on the right number. A solver
that miscounts the recursion by one or two earns the same final answer as one that counts
correctly, and no check of the answer can tell them apart. The derivation can. If the solver writes
31 % 9 as 3, Opulse's step checker stops at that line and reports that it "changes the value of a
part from 4 to 3". If it skips from `31 ◆₂ 50` straight to three nested `◆₁`, the checker rejects
that line as a wrong unfolding of `◆₂`.

??? note "Reproduce the opening example"
    ```bash
    opulse operators --out ops12.jsonl --layers 10 6 --seed 12 --check-variety
    opulse bench build --operators ops12.jsonl --out st12.jsonl --format steps \
                       --count 40 --min-definitions 2 --max-definitions 2 --seed 1
    # task compute-000025; in the file, ◆₁ is ∏∆¬ and ◆₂ is ∨∀◆
    python tools/blog_visuals.py   # rebuilds Figure 3, the step checker on the opening question
    python tools/blog_figures.py   # redraws Figures 1, 2, 4, 5 and 6
    ```
    The other numbers in this post come from the linked pages, which show their commands and output.

Generating definitions fresh closes one shortcut and leaves others open. A seeded generator produced
`◆₂` for this post from atoms chosen in advance and gave it a name of arbitrary glyphs (the file spells it `∨∀◆`; this
post relabels generated operators as a shape and a digit). A model trained before this library
existed has never seen this item. It may have met an equivalent function under another name, or
similar computations, and the table shows that a sloppy procedure can still score.

The opening example shows why a final answer alone is a weak measure. Whether a model applies such
definitions correctly depends on its training data: how often it saw
recursion of this shape, whether it practised applying rules it had just read, how long its
training derivations were. Opulse is built to vary those properties one at a time. It
generates new computable concepts from atoms the user chooses and computes the exact value of every
expression and every step. The regularities it looks for are *data laws*: statements of the form
"under these conditions, changing this property of the training data changes learning in this
way". A data law found in Opulse describes learning on Opulse data. It can guide the training of
real models only once it predicts results on tasks outside Opulse, and that requirement shapes
everything below.

The argument runs in order. Questions about training data have no clean answer on natural data,
because the factors of interest move together, intermediate steps have no ground truth and
benchmarks leak. Answering them needs a laboratory that changes one factor at a time and knows the
exact value of every answer and every step. Opulse builds one from atoms, three ways of combining
them and a reference interpreter that acts as referee (Figure 1). Exact steps make derivations
gradable line by line and writable at any granularity, and those two properties support a set of
proposed experiments on training data. The post then traces the older ideas behind the design and
ends with its limits and the questions to answer first.

<figure class="op-blogfig" markdown>
![Overview of Opulse](../assets/blog/fig1.svg#only-light){ .op-fig-d }
![Overview of Opulse](../assets/blog/fig1-dark.svg#only-dark){ .op-fig-d }
![Overview of Opulse](../assets/blog/fig1-m.svg#only-light){ .op-fig-m }
![Overview of Opulse](../assets/blog/fig1-m-dark.svg#only-dark){ .op-fig-m }
<figcaption><b>Figure 1.</b> Opulse in one picture. Concepts grow from user chosen atoms in three ways, and one reference interpreter checks every value and step, so everything Opulse produces can be audited against one written semantics.</figcaption>
</figure>

## Why data questions resist natural data

Pretraining teams face questions like this one: if a rule is rare in the corpus, how much does a
model lose on problems that need it, and does a skewed frequency distribution help or hurt the rare
cases? Frequency does matter. [Kandpal et al.](https://arxiv.org/abs/2211.08411) [1](#ref-1) related question
answering accuracy to the number of pretraining documents relevant to each question and found
correlational and causal evidence for the link. On the web, though, the number of relevant
documents varies together with topic, source and surrounding text, and a frequency comparison on
web data cannot hold those fixed by itself.

That is the first of three recurring problems, **confounding**: on natural data, the factors one
wants to study move together. Longer derivations come from harder topics, rarer concepts from
sparser explanations, deeper compositions from more specialised documents.

The second is **missing ground truth for intermediate steps**. Final answers are often checkable;
the steps in between rarely are. [ProcessBench](https://arxiv.org/abs/2412.06559) [2](#ref-2) contains 3,400
solutions whose earliest wrong step was marked by human experts. Such labels cover the solutions
that were labelled, not every step of every new problem. Labels on written solutions, however
careful, also do not say which intermediate values a trained model represents or uses.

The third is **leakage**. A public benchmark can enter training corpora, and from then on prior
exposure is hard to rule out. [Zhang et al.](https://arxiv.org/abs/2405.00332) [3](#ref-3) wrote GSM1k, a fresh
set of problems matched to GSM8K [4](#ref-4), and observed accuracy drops of up to 8% for some models while
finding little sign of overfitting in many frontier models. Measuring the gap took a new benchmark
written by hand.

The [Physics of Language Models](https://physics.allen-zhu.com/) [5](#ref-5) project argued for another route.
In Part 2.1, [Ye, Xu, Li and Allen-Zhu](https://arxiv.org/abs/2407.20311) [6](#ref-6) explain why they did not
fine tune an existing model on GSM8K: its pretraining data "is a pile of mess", and without control
of that data one cannot tell "whether a model truly learns the reasoning skills or it simply
memorizes problem templates". So they generated grade school problems from random dependency
graphs and trained small models from scratch. Generated data can avoid all three problems, provided
the generator controls each factor, knows the answer to everything it writes, and can make test
rules that no training set contains.

## The idea of a laboratory

A laboratory, in this sense, does three jobs. It computes the correct answer to every question
under a written semantics, so every answer can be audited. It records the properties of every task,
so an experimenter who changes one property of the data can check what else changed in the sample.
And it makes fresh test rules and checks them for overlap with the rules used in training.
Model measurements still vary with seeds, sampled tasks and prompts, and need repetitions and error
bars.

Controlled synthetic data has already yielded regularities of this kind. In the biography experiments
of [Part 3.1](https://arxiv.org/abs/2309.14316) [7](#ref-7), Allen-Zhu and Li changed how many ways each invented
person's facts were written, and found that for knowledge to be reliably extracted by questions, it
"must be sufficiently augmented (e.g., through paraphrasing, sentence shuffling, translations)
during pretraining". In [Part 2.2](https://arxiv.org/abs/2408.16293) [8](#ref-8), pretraining data containing
mistakes followed by corrections gave higher reasoning accuracy than the same amount of error free
data. Each result is a regularity about training data, established in its own setting, that
suggests a choice for real corpora and can be tested there.

These synthetic settings keep their schema or their operations fixed. The biographies share one schema of attributes. The
grade school problems use arithmetic mod 23 over random dependency graphs, so the graph changes and
the operations do not. Grokking experiments such as [Power et al.](https://arxiv.org/abs/2201.02177) [9](#ref-9)
train on the table of a single binary operation. For the questions those papers ask, that is the
right design. But because the operations never change, such datasets cannot isolate what
introducing or changing an operation does: how a model learns a new one, how it composes ones
learned separately, how it updates what was built on a definition that changed.

Opulse generates the operations. Each seed grows a new library of concepts from the chosen atoms,
with a recorded dependency graph, and each structural factor of the data has its own option:

| Factor | What it sets | Option |
| --- | --- | --- |
| atoms | the primitive operations | starting set, `--plugin` |
| composition | plain, branching and recursive definitions | `--proportions`, `recursion.*` |
| depth | definitions a problem needs, depth of dependency | `--min-definitions`, `--max-definitions`, `--max-layer`, `--max-depth` |
| frequency | how often each concept appears | `--operator-frequency uniform` or `zipf:ALPHA` |
| notation | symbols, invented words or English names; numeral base | `--naming`, `expressions.numeral_base` |
| granularity | how much of a derivation is written out | `--cot`, `--cot-depth`, `--cot-known-layers` |

An option can still move things it does not name, so every task records what it actually
contains. In two [runnable checks](../why.md#one-option), writing 50 tasks with
English words in place of symbols kept all 50 answers and 13 of the 14 recorded task features; the
fourteenth is the naming itself. The prompts, and so their token counts, did change. Sampling 2,000
expressions with `zipf:1.5` instead of uniform frequencies raised the Gini coefficient of operator
usage from 0.112 to 0.658, while the minimum, median, 90th percentile and maximum of expression size
and depth stayed the same. Which operators were drawn, and so which answers came up, did change.
Figure 2 summarises the design: one option changes, the other options stay fixed, and the
recorded features show what else moved.

<figure class="op-blogfig" markdown>
![The laboratory design](../assets/blog/fig2.svg#only-light){ .op-fig-d }
![The laboratory design](../assets/blog/fig2-dark.svg#only-dark){ .op-fig-d }
![The laboratory design](../assets/blog/fig2-m.svg#only-light){ .op-fig-m }
![The laboratory design](../assets/blog/fig2-m-dark.svg#only-dark){ .op-fig-m }
<figcaption><b>Figure 2.</b> The laboratory. One option changes while the other options, the semantics and the evaluation stay fixed. Because every task records its features, a sample can be checked for side effects of the change.</figcaption>
</figure>

What remains is to build a generator whose every value is exact.

## How the laboratory is built

Three parts make every value exact: the atoms, three ways of combining them, and a referee that
recomputes everything the generator writes (Figure 1).

### Atoms

Everything starts from atoms, operations computed directly and never unfolded. The shipped integer
set has `+ - * / %`, negation, digit reversal `@`, triangular number `#`, bit count `$` and digit
sum `&`. A second shipped set is deliberately spare: negation, successor, predecessor, doubling,
halving and lowest bit. It has no addition, so the generator must build arithmetic from these
pieces, within the recursion bound. Any integer function can be registered as an atom with a symbol
and a one sentence rule. Generation, evaluation and step checking then use it like a shipped atom,
and the solver analyses use it once it has a z3 [10](#ref-10) encoding ([Atoms](../guide/atoms.md)). The choice of
atoms is the first experimental factor, because it decides what counts as primitive.

### Three ways to combine

Opulse builds definitions from atoms in three ways. **Substitution** passes the result of one
operation to another, and arguments can be chosen, copied or dropped: `a ◆₃ b = { (a + b) * 2 }`.
**Conditional choice** tries branches in order and evaluates only the first whose condition holds:
`a ◇₁ = { a * 41, if a < 21; # a, if a < 83; 4 / a, else }`. **Bounded self reference** lets a
definition call itself on a value that moves toward zero, as `◆₂` does.

The three forms follow McCarthy's trio of composition, conditional expressions and recursive
definition, with recursion confined to templates that always terminate; the section on
[sources](#where-this-comes-from) gives the history.

Each form does a job in the generated definitions. Substitution builds nested applications.
Conditional choice selects a case from the input, and it supplies the base case without which a
self referential definition could not stop. Self reference lets the number of operator applications
grow with the input. Conditional choice adds no expressive power on its own, since a function
defined by cases with primitive recursive conditions is primitive recursive; the recursion
templates need it all the same.

What is left out matters as much. Unbounded search can run forever, so the generator never writes
it. Every recursion follows one of a few templates in which the controlling value walks toward zero
and its size is limited; with the defaults, a recursive operator unfolds at most eight times. With
the shipped atoms, every value is therefore computable, every derivation is finite, and the
generated concepts form a subset of the primitive recursive functions. A registered atom must
itself terminate for those guarantees to carry over. By default operators take one or two arguments;
`operators.arity_weights` adds operators with three or more, written in call form `⊕(a, b, c)`. Values
are integers here, and typed presets add booleans, strings and lists of integers. No operator takes
another operator as an argument ([Scope](../why.md#current-scope)).

### Layers and checks

The generator builds operators from these forms in layers. A recursive operator over a layer k operator starts layer k + 1, so
the layer counts the recursions stacked beneath a concept. Each operator record lists the
operators its definition calls. That graph says which definitions may call which; a particular
input decides which branches are taken and which calls run.

A draft definition survives only if it passes a list of checks. The generator rejects it if a
parameter is unused, if it merely renames another operator, if two branches have the same body, if
its compiled code disagrees with the interpreter on any tested input, or if the solver z3 proves a
branch unreachable or always undefined. With `--check-variety`, it also rejects drafts that are
nearly constant or mostly return an input. `◆₂` passed that check, yet with its first argument fixed
at 31 it returns 60 for every second argument from 1 to 19. Generated concepts can be degenerate on
part of their domain. That is why `bench build --max-answer-share` caps the share of tasks with the
same answer, and why an experiment should measure answer diversity in its own sample. The
[visual tour](../guide/visual-tour.md#growing-an-operator-set) animates a real operator set
growing, with each rejected draft and the reason its check gave.

### The referee

The reference interpreter implements a [written semantics](../reference/semantics.md) directly:
integers, NaN, truncating division and a value bound. Before Opulse writes a dataset record or a
narrated solution step, the interpreter recomputes it. Compiled code, z3 encodings and SMT-LIB exports
are compared with it on boundary and random inputs, and it checks again every counterexample a
solver returns. `opulse bench build` also rebuilds the operators from the prompt text alone and
recomputes each answer, so what the model reads and what it is graded against cannot drift apart. A
test sweep runs these checks in 298 configurations covering notation, operator alphabet, numeric mode,
recursion template, partial definitions and numeral base, and all pass
([Correctness](../about/correctness.md)).

The checks exist because an earlier dataset, the one Opulse was rebuilt from, failed them. Run
through the interpreter, 53 of its recursive operators computed something other than their written
definitions, and through dependencies 449 of its 1,106 operators disagreed with their own
definitions ([Correctness](../about/correctness.md#legacy-data)). A model trained or graded on that
data would have been measured, in part, against answers its prompts did not support, and no accuracy number
would have shown it.

Because the referee knows the exact value after every rewrite, a derivation can be graded line by
line, which is what the next section shows.

## Seeing inside a derivation

The final answer of the opening question concealed a miscounted recursion; the written
derivation exposed it.

The reducer rewrites an expression one step at a time, at the leftmost application whose arguments
are already numbers. A defined operator becomes the body of the branch its arguments select, with the
arguments substituted, and an atom with number arguments becomes its value. In the opening question, lines 1 to 13 unfold the
recursion into four nested calls of `◆₁`, and the remaining lines evaluate them. The
[visual tour](../guide/visual-tour.md#unfold-to-atoms) animates such a reduction one rewrite at a
time.

With `bench build --format steps`, a model writes one rewrite per line, and the checker names the
first wrong line. In Figure 3, the second derivation writes 31 % 9 as 3 and then proceeds
correctly from there. It ends at 258, the right answer, and the checker flags line 2. Rewrites that
keep the value but skip work, such as replacing an application directly by its value, count as
jumps: they are accepted and earn no step credit
([grading rules](../guide/benchmark.md#grading-the-reasoning-not-only-the-answer)). A derivation
that passes shows that its lines follow the rules. It does not show that the model computed its
answer that way.

<figure class="op-blogfig" markdown>
--8<-- "docs/snippets/vis_blog_steps.html"
<figcaption><b>Figure 3.</b> The step checker on the reference derivation of the opening question and on
the same derivation with the recursion count written wrong on line 2. Both end at 258; only the
derivation shows the error.</figcaption>
</figure>

How much of a derivation is written out is a setting. An operator the learner is assumed to know is
computed in one step, and that step is checked like the others. For the opening question:

| Granularity | Option | Lines |
| --- | --- | --- |
| everything unfolded to atoms | default | 39 |
| `◆₁` treated as known | `--cot-known` | 19 |
| only the operators written in the question unfolded | `--cot-depth 1` | 7 |
| nothing unfolded | `--cot-depth 0` | 3 |

Figure 4 shows how the settings nest: one coarse step stands for a block of finer steps, each of
which can be checked.

<figure class="op-blogfig" markdown>
![Derivation granularity as nested blocks](../assets/blog/fig4.svg#only-light){ .op-fig-d }
![Derivation granularity as nested blocks](../assets/blog/fig4-dark.svg#only-dark){ .op-fig-d }
![Derivation granularity as nested blocks](../assets/blog/fig4-m.svg#only-light){ .op-fig-m }
![Derivation granularity as nested blocks](../assets/blog/fig4-m-dark.svg#only-dark){ .op-fig-m }
<figcaption><b>Figure 4.</b> Granularity. One coarse step stands for a block of finer steps, down to atoms; every block is the same computation written at a finer grain.</figcaption>
</figure>

A learner that moves down this table with practice resembles, in its written behaviour, what
[Anderson's ACT theory](https://doi.org/10.1037/0033-295X.89.4.369) [11](#ref-11) calls knowledge compilation. A
skill interpreted step by step becomes one applied directly: composition collapses a sequence of
productions into one, and proceduralization builds facts that were looked up into the procedure
that uses them. The four settings give four correct written views of one computation. Training on
them can test whether data should move down the table as a concept becomes familiar; by
themselves, they say nothing about what a model compiles internally.

Exact values, gradable steps and adjustable granularity are what the experiments in the next
section rely on.


## What can be measured

Exact values and separately controlled factors make experiments on training data possible.
None of the experiments below has been run for this post, and their outcomes are unknown. Each
states the property it changes, what it holds fixed, what it measures, and what a team training a
model would do with either result.

The four proposals that compare training data share one protocol, which enforces the transfer
requirement from the opening. Before training, freeze a named set of external tasks with their prompts, scoring
rules and the smallest effect that would count, for instance short rule application tasks written
in prose and short code execution tasks. Evaluate every arm on those tasks and on fresh Opulse
libraries. Include an arm trained on the same number of tokens of ordinary data and an arm with no
extra training, and repeat across operator seeds and training seeds. A difference that appears only
on Opulse libraries is a fact about Opulse.

Figure 5 groups the five proposals by what they do with a model, and lists for each the regularity
it would reveal and the decision it would inform.

<figure class="op-blogfig" markdown>
![Map of the proposed experiments](../assets/blog/fig5.svg#only-light){ .op-fig-d }
![Map of the proposed experiments](../assets/blog/fig5-dark.svg#only-dark){ .op-fig-d }
![Map of the proposed experiments](../assets/blog/fig5-m.svg#only-light){ .op-fig-m }
![Map of the proposed experiments](../assets/blog/fig5-m-dark.svg#only-dark){ .op-fig-m }
<figcaption><b>Figure 5.</b> Five proposed experiments. Each is tied to a regularity it would reveal and a decision it would inform. Together they cover evaluating existing models, training new ones and looking inside them.</figcaption>
</figure>

### When should a rule live in the weights?

A rule can be trained into a model or supplied in its context each time it is needed. Training pays
once, in examples and compute; supplying the definition adds prompt tokens to every query. Which is
cheaper depends on the accuracy required and on how many queries will follow.
[Ovadia et al.](https://arxiv.org/abs/2312.05934) [12](#ref-12) compared retrieval with unsupervised fine tuning
for factual knowledge and found retrieval ahead. That does not settle the trade for newly defined,
executable rules, partly because on natural data nobody knows how often a model has seen a given
rule.

In Opulse that count can be assigned. Starting from one model, an external sampler gives each
operator 10, 100 or 1,000 training uses. Saved test expressions are then posed without definitions
(`--context none`), which tests the trained rules, and with definitions in the prompt
(`--context full`), with unrelated definitions of the same length as a control. At a fixed accuracy
target and query volume, convert training compute and inference tokens to one stated cost unit and
report where the cheaper option changes. The same choice matters when a rule changes. A second
measurement uses contrast pairs
(`--family contrast`): the same expression under the same symbols, with one definition swapped so
the answer changes. It records how often a model gives the old answer while the new definition is
in front of it. If practice raises that rate, the next comparison is between keeping changeable
rules in context and training on examples in which a supplied rule overrides a practised one. The
[visual tour](../guide/visual-tour.md#test-a-model-in-context) shows a contrast pair.

### Should common concepts subsidise rare ones?

Frequent concepts may help a model learn rare ones.
[Wang, Dang, Lee and Lyu](https://arxiv.org/abs/2604.22951) [13](#ref-13) report that training on power law
distributions of skills outperforms uniform training on compositional tasks such as state tracking.
Their explanation is an asymmetry: frequent compositions are learned first and become stepping
stones for rare ones. Whether that holds when skills form a growing graph of defined concepts, with
branches and recursion, is open.

`--operator-frequency zipf:ALPHA` ranks operators within each kind in random order and draws rank r
with weight proportional to r^-ALPHA, keeping the total share of defined operators as under
`uniform`; rotating `--frequency-seed` keeps any one operator from always being common. Exposure is
the hard part to count. An operator can appear inside the definition of a common one and
run on only some of its inputs. So each operator gets three counts: direct uses in training
expressions, appearances in definitions shown during training, and executions inside derivations
that were part of the training text. The three counts move together through the graph, so a fitted
curve cannot price indirect exposure. Comparing `uniform` with `zipf` arms answers the first
question; whether a gain comes through indirect exposure needs a second test. That test keeps the
same target operators
in every arm, holds their direct uses, their shown definitions and the total tokens fixed, and
varies only how often training derivations execute them inside dependents. A gain would justify
testing a frequent core on the external tasks; a loss would call for a separate test of a minimum
exposure per concept.

### How many derivation tokens is a training example worth?

Written steps cost tokens, and the question is which of them earn their cost.
[Deng, Choi and Shieber](https://arxiv.org/abs/2405.14838) [14](#ref-14) trained models to internalise chain of
thought by removing written steps gradually, and report that a GPT2 Small [15](#ref-15) model solved 9 by 9
multiplication with up to 99% accuracy without intermediate steps. On their tasks, the written
steps could go.

Save one pool of expressions and render every item three ways: answer only, a coarse derivation in
which lower layers are known, and a full derivation. Every step that remains in any rendering is
correct. The arms differ in length, so two comparisons are needed: one at an equal number of
problems, and one at equal tokens, with a declared filler (for example, more answer only problems)
making up the difference in the shorter arms. Results are grouped by the measured length of each
reference derivation. Under the declared filler and budget, this tests, within each length group, whether
full derivations pay for their tokens on Opulse; a policy for real solutions also needs the external
tasks.

### Does an edit reach what was built on it?

When a definition changes, operators above it may change too, though not on every input.
[RippleEdits](https://arxiv.org/abs/2307.12976) [16](#ref-16) built 5,000 factual edits with their expected
consequences and found that established editing methods handle the consequences poorly, while a
simple in context editing baseline did best. In natural knowledge, which facts an edit implies is
itself debatable.

In an Opulse library it can be computed. After one number in a low layer definition changes,
`examples/edit_propagation.py` recomputes each dependent operator on a fixed sample of inputs and
lists its values before and after, with its distance from the edit in the dependency graph. The
test uses two kinds of input at each distance: inputs whose answers change after the edit, and
inputs whose answers do not. Correct answers on both kinds show behaviour consistent with
propagation on those inputs; errors on the unchanged kind show a model that changes too much.
Accuracy on the edited operator itself is reported alongside, with the edit given in context in one
condition and trained into the weights in another. The
[visual tour](../guide/visual-tour.md#edit-one-operator) shows one edit recomputed through its
dependents.

### Can interpretability methods be tested against exact reference values?

An exact label for an intermediate value makes a probe easy to score. It does not show that the
model uses that value. [Hewitt and Liang](https://arxiv.org/abs/1909.03368) [17](#ref-17) introduced control
tasks, pairing word types with random outputs, and found that standard probes lack selectivity: a
probe can score well without the representation encoding the property. [Makelov, Lange and
Nanda](https://arxiv.org/abs/2311.17030) [18](#ref-18) showed that a subspace activation patch can change the
output as if a feature had changed while acting through a different pathway.

Exact reference values are a weaker kind of ground truth than a known mechanism.
[Tracr](https://arxiv.org/abs/2301.05062) [19](#ref-19) compiles programs into transformer weights, so the
mechanism is known by construction. Opulse gives the exact answer and the exact intermediate values
of one reference computation, with the mechanism left to training. A trained model may compute differently.

The opening example shows how to choose inputs in which a reference intermediate value and the
final answer vary independently. Past two applications of `◆₁`, the final answer no longer depends on
the count, so a probe that recovers the count there cannot be reading it off the answer. Pairs in
which an intermediate value changes while the answer stays fixed, and pairs in which the answer
changes while the intermediate value stays fixed, separate the two, provided prompt length and
notation are matched across each pair. A probe at a stated token and layer is compared with equally
small probes on the operand tokens, on the answer, and on shuffled targets. For patching, the
candidate state is swapped between prompts that differ in one reference value, the predicted effect
is checked across several downstream contexts and in reverse, and matched positions elsewhere serve
as controls. Success is evidence that the intervention influences the output as the abstraction
predicts. It does not make the reference value a variable inside the model.

Physics of Language Models shows where such tests can lead. With probes on their grade school
models, [Ye et al.](https://arxiv.org/abs/2407.20311) decoded the necessary parameters before the
model began its solution, and decoded which parameters depend on which before the question appeared,
although fitting the training solutions never required that. These are statements about what a
probe can decode. A future extension of this test asks the analogous question for rules. It starts with a prompt that binds several names to
expressions over new operators and then asks for one: are the dependencies among all bindings
decodable before the question arrives? Whether unused values are also computed is a separate,
stronger question. This prompt format is not part of Opulse yet; it needs a prompt builder and an
alignment of each binding to its tokens.

These questions, and the design behind them, have a history, which the next section traces.

## Where this comes from

The questions are old. What Opulse adds is generated rules with exact semantics and separately
controlled factors. Figure 6 pairs each older idea with the part of Opulse that corresponds to it.

<figure class="op-blogfig" markdown>
![Older ideas and their counterparts in Opulse](../assets/blog/fig6.svg#only-light){ .op-fig-d }
![Older ideas and their counterparts in Opulse](../assets/blog/fig6-dark.svg#only-dark){ .op-fig-d }
![Older ideas and their counterparts in Opulse](../assets/blog/fig6-m.svg#only-light){ .op-fig-m }
![Older ideas and their counterparts in Opulse](../assets/blog/fig6-m-dark.svg#only-dark){ .op-fig-m }
<figcaption><b>Figure 6.</b> Lineage. Each part of Opulse continues an older idea; what Opulse adds is generated rules with exact semantics and separately controlled factors. The paragraphs below give the sources.</figcaption>
</figure>

**Computable functions.** The three forms come from the theory of computable functions. Kleene's construction, as presented
in the [Stanford Encyclopedia of Philosophy](https://plato.stanford.edu/entries/recursive-functions/) [20](#ref-20),
closes a set of initial functions under composition and primitive recursion and then adds unbounded
minimisation. McCarthy, in
[A Basis for a Mathematical Theory of Computation](https://courses.grainger.illinois.edu/cs421/sp2011/project/mccarthy-basis.pdf) [21](#ref-21),
used a trio that reads like a program: composition, conditional expressions and recursive
definition. He showed that with only successor and equality as base functions, this trio reaches
every partial recursive function. Opulse follows McCarthy's trio and confines its recursion to
templates that always terminate.

**Concept discovery.** Lenat's
[AM](https://en.wikisource.org/wiki/An_Artificial_Intelligence_Approach_to_Discovery_in_Mathematics_as_Heuristic_Search) [22](#ref-22)
started in 1976 from 115 elementary concepts of set theory and a few hundred heuristics, defined new
concepts by modifying old ones, and rediscovered the natural numbers and the primes. Eight years
later [Lenat and Brown](https://doi.org/10.1016/0004-3702(84)90016-X) [23](#ref-23) gave much of the credit to the
representation. A concept in AM was a LISP function of a few lines, and mutating such tiny programs
tended to give meaningful related concepts, whereas mutating a two page program "is doomed to almost
always giving garbage". Opulse makes the same bet on purpose, with a small grammar in which every
accepted draft terminates. It also records the definitions behind each task, so a rule a learner
proposes can be tested against the rule that produced the data.

**Learning rules from queries.** [Gold](https://doi.org/10.1016/S0019-9958(67)91165-5) [24](#ref-24) showed that
from positive examples alone, even the regular languages cannot be identified in the limit.
[Angluin's L\*](https://doi.org/10.1016/0890-5401(87)90052-6) [25](#ref-25) changed the protocol: a learner that
asks membership queries and receives counterexamples to its conjectures learns the minimal
automaton of a regular language in time polynomial in its number of states and the length of the
longest counterexample. The Opulse interpreter answers value queries exactly, and where z3 supports
the operators, the equivalence checker returns counterexamples within the configured value range.
Active and passive rule learning can therefore be compared on generated functions, without
importing the guarantees of L\*.

**Diagnostic tasks.** [bAbI](https://arxiv.org/abs/1502.05698) [26](#ref-26) grouped small question answering tasks
by the reasoning each was meant to require, such as chaining facts or deduction. Within three years
[recurrent relational networks](https://arxiv.org/abs/1711.08028) [27](#ref-27) were reported to solve all twenty
consistently, and from then on the set could not separate that model from stronger ones. Opulse
tasks record their properties, so results can be grouped by the difficulty being tested. A new seed
gives new definitions, and `opulse bench leakage` flags test operators whose definitions, up to
renaming, or whose values on a fixed sample also occur in a training library. All libraries share
one grammar, though, and a model can learn the grammar; generalisation to new definitions still has
to be measured.

**Self improvement.** Schmidhuber's [Gödel machine](https://arxiv.org/abs/cs/0309048) [28](#ref-28) rewrites its own
code once it has proved that the rewrite is useful. Opulse proves something much narrower: that a
candidate operator is well formed and its values are computed correctly. A model that proposes
operators can use the interpreter as its referee, but whether an operator helps has to be measured.

Three older ideas connect to the experiments: two run through those above, and the third suggests
one more. Anderson's knowledge compilation is the question
behind derivation granularity. Doyle's [truth maintenance system](https://doi.org/10.1016/0004-3702(79)90008-0) [29](#ref-29)
recorded a justification for each belief so that revising one could update the rest, which is the
question behind edit propagation. And in [Elman's](https://doi.org/10.1016/0010-0277(93)90058-4) [30](#ref-30)
experiments, a recurrent network learned a complex grammar only when training began with simple
sentences or with limited memory; with prerequisites on record, ordering by layer can be tested at
equal budgets.

## Limits

Opulse recomputes every value and step it writes with its reference interpreter, and its tests
compare that interpreter with compiled code and solvers across 298 configurations. That establishes
agreement with a specification, as far as tests can. Whether the specification resembles anything
a model meets outside the laboratory is a separate question.

The world is small on purpose. Values are integers or NaN, most operators take one or two arguments,
recursion follows a few templates and unfolds a handful of times, and the text is formal notation.
A model that learns to apply Opulse definitions has learned to apply definitions in this notation;
how much carries over is what the external tasks measure.

Some checks are sampled. The variety check and the behavioural part of the leakage check evaluate
operators on a fixed sample of inputs, so a clean leakage report lowers the chance that two
operators compute the same function without proving that they differ everywhere. The opening
operator shows how much a domain can hide: `◆₂` looks like a four step recursion, and with its first
argument at 31 it returns the same value for nineteen consecutive inputs.

Options set bounds or targets, not guarantees. `--max-layer 3` allows layer 3 without guaranteeing it, and a requested
share of recursive definitions is a target the generator can miss. Each task records what it
actually contains, so analyses should group items by measured properties such as actual dependency
depth, actual unfolding count and reference derivation length.

## Open questions

Three questions seem to me the most worth answering first.

Does practice make a model stop reading? If a model has applied a rule a thousand times and a prompt
then changes the rule, does it follow the prompt or its habit, and can training on contrast pairs
keep it reading?

Does indirect exposure count? A low level concept can also be used inside its dependents. If a
model practises a rule mostly through its dependents, how does that compare with direct practice?

Which atoms make a world whose lessons transfer? The integer atoms here were chosen for convenience.
Some other choice may yield regularities that hold on rules written in prose or code; another may
yield a world that only teaches itself. Comparing starting atom sets under the shared protocol, on
the same frozen external tasks, would tell them apart. Finding out is part of building the
laboratory.

## References

1. <span id="ref-1"></span> Nikhil Kandpal, Haikang Deng, Adam Roberts, et al. “Large Language Models Struggle to Learn Long-Tail Knowledge.” *arXiv preprint arXiv:2211.08411*, 2022. [Source](https://arxiv.org/abs/2211.08411).

2. <span id="ref-2"></span> Chujie Zheng, Zhenru Zhang, Beichen Zhang, et al. “ProcessBench: Identifying Process Errors in Mathematical Reasoning.” *arXiv preprint arXiv:2412.06559*, 2024. [Source](https://arxiv.org/abs/2412.06559).

3. <span id="ref-3"></span> Hugh Zhang, Jeff Da, Dean Lee, et al. “A Careful Examination of Large Language Model Performance on Grade School Arithmetic.” *arXiv preprint arXiv:2405.00332*, 2024. [Source](https://arxiv.org/abs/2405.00332).

4. <span id="ref-4"></span> Karl Cobbe, Vineet Kosaraju, Mohammad Bavarian, et al. “Training Verifiers to Solve Math Word Problems.” *arXiv preprint arXiv:2110.14168*, 2021. [Source](https://arxiv.org/abs/2110.14168).

5. <span id="ref-5"></span> Zeyuan Allen-Zhu. “ICML 2024 Tutorial: Physics of Language Models.” *ICML 2024 tutorial project page*, 2024. [Source](https://physics.allen-zhu.com/).

6. <span id="ref-6"></span> Tian Ye, Zicheng Xu, Yuanzhi Li, et al. “Physics of Language Models: Part 2.1, Grade-School Math and the Hidden Reasoning Process.” *arXiv preprint arXiv:2407.20311*, 2024. [Source](https://arxiv.org/abs/2407.20311).

7. <span id="ref-7"></span> Zeyuan Allen-Zhu and Yuanzhi Li. “Physics of Language Models: Part 3.1, Knowledge Storage and Extraction.” *arXiv preprint arXiv:2309.14316*, 2023. [Source](https://arxiv.org/abs/2309.14316).

8. <span id="ref-8"></span> Tian Ye, Zicheng Xu, Yuanzhi Li, et al. “Physics of Language Models: Part 2.2, How to Learn From Mistakes on Grade-School Math Problems.” *arXiv preprint arXiv:2408.16293*, 2024. [Source](https://arxiv.org/abs/2408.16293).

9. <span id="ref-9"></span> Alethea Power, Yuri Burda, Harri Edwards, et al. “Grokking: Generalization Beyond Overfitting on Small Algorithmic Datasets.” *arXiv preprint arXiv:2201.02177*, 2022. [Source](https://arxiv.org/abs/2201.02177).

10. <span id="ref-10"></span> Leonardo de Moura and Nikolaj Bjørner. “Z3: An Efficient SMT Solver.” *Tools and Algorithms for the Construction and Analysis of Systems*, 2008. [Source](https://www.microsoft.com/en-us/research/publication/z3-an-efficient-smt-solver/).

11. <span id="ref-11"></span> John R. Anderson. “Acquisition of Cognitive Skill.” *Psychological Review 89(4), pp. 369 to 406*, 1982. [Source](https://doi.org/10.1037/0033-295X.89.4.369).

12. <span id="ref-12"></span> Oded Ovadia, Menachem Brief, Moshik Mishaeli, et al. “Fine-Tuning or Retrieval? Comparing Knowledge Injection in LLMs.” *arXiv preprint arXiv:2312.05934*, 2023. [Source](https://arxiv.org/abs/2312.05934).

13. <span id="ref-13"></span> Zixuan Wang, Xingyu Dang, Jason D. Lee, et al. “The Power of Power Law: Asymmetry Enables Compositional Reasoning.” *arXiv preprint arXiv:2604.22951*, 2026. [Source](https://arxiv.org/abs/2604.22951).

14. <span id="ref-14"></span> Yuntian Deng, Yejin Choi, and Stuart Shieber. “From Explicit CoT to Implicit CoT: Learning to Internalize CoT Step by Step.” *arXiv preprint arXiv:2405.14838*, 2024. [Source](https://arxiv.org/abs/2405.14838).

15. <span id="ref-15"></span> Alec Radford, Jeffrey Wu, Rewon Child, et al. “Language Models are Unsupervised Multitask Learners.” *OpenAI*, 2019. [Source](https://github.com/openai/gpt-2).

16. <span id="ref-16"></span> Roi Cohen, Eden Biran, Ori Yoran, et al. “Evaluating the Ripple Effects of Knowledge Editing in Language Models.” *arXiv preprint arXiv:2307.12976*, 2023. [Source](https://arxiv.org/abs/2307.12976).

17. <span id="ref-17"></span> John Hewitt and Percy Liang. “Designing and Interpreting Probes with Control Tasks.” *arXiv preprint arXiv:1909.03368*, 2019. [Source](https://arxiv.org/abs/1909.03368).

18. <span id="ref-18"></span> Aleksandar Makelov, Georg Lange, and Neel Nanda. “Is This the Subspace You Are Looking for? An Interpretability Illusion for Subspace Activation Patching.” *arXiv preprint arXiv:2311.17030*, 2023. [Source](https://arxiv.org/abs/2311.17030).

19. <span id="ref-19"></span> David Lindner, János Kramár, Sebastian Farquhar, et al. “Tracr: Compiled Transformers as a Laboratory for Interpretability.” *arXiv preprint arXiv:2301.05062*, 2023. [Source](https://arxiv.org/abs/2301.05062).

20. <span id="ref-20"></span> Walter Dean and Alberto Naibo. “Recursive Functions.” *The Stanford Encyclopedia of Philosophy, Summer 2025 edition*, 2025. [Source](https://plato.stanford.edu/archives/sum2025/entries/recursive-functions/).

21. <span id="ref-21"></span> John McCarthy. “A Basis for a Mathematical Theory of Computation.” *Computer Programming and Formal Systems*, 1963. [Source](https://courses.grainger.illinois.edu/cs421/sp2011/project/mccarthy-basis.pdf).

22. <span id="ref-22"></span> Douglas B. Lenat. “AM: An Artificial Intelligence Approach to Discovery in Mathematics as Heuristic Search.” *Stanford Artificial Intelligence Laboratory Memo AIM-286*, 1976. [Source](https://en.wikisource.org/wiki/An_Artificial_Intelligence_Approach_to_Discovery_in_Mathematics_as_Heuristic_Search).

23. <span id="ref-23"></span> Douglas B. Lenat and John Seely Brown. “Why AM and Eurisko Appear to Work.” *Artificial Intelligence 23(3), pp. 269 to 294*, 1984. [Source](https://doi.org/10.1016/0004-3702(84)90016-X).

24. <span id="ref-24"></span> E. Mark Gold. “Language Identification in the Limit.” *Information and Control 10(5), pp. 447 to 474*, 1967. [Source](https://doi.org/10.1016/S0019-9958(67)91165-5).

25. <span id="ref-25"></span> Dana Angluin. “Learning Regular Sets from Queries and Counterexamples.” *Information and Computation 75(2), pp. 87 to 106*, 1987. [Source](https://doi.org/10.1016/0890-5401(87)90052-6).

26. <span id="ref-26"></span> Jason Weston, Antoine Bordes, Sumit Chopra, et al. “Towards AI-Complete Question Answering: A Set of Prerequisite Toy Tasks.” *arXiv preprint arXiv:1502.05698*, 2015. [Source](https://arxiv.org/abs/1502.05698).

27. <span id="ref-27"></span> Rasmus Berg Palm, Ulrich Paquet, and Ole Winther. “Recurrent Relational Networks.” *arXiv preprint arXiv:1711.08028*, 2017. [Source](https://arxiv.org/abs/1711.08028).

28. <span id="ref-28"></span> Juergen Schmidhuber. “Goedel Machines: Self-Referential Universal Problem Solvers Making Provably Optimal Self-Improvements.” *arXiv preprint arXiv:cs/0309048*, 2003. [Source](https://arxiv.org/abs/cs/0309048).

29. <span id="ref-29"></span> Jon Doyle. “A Truth Maintenance System.” *Artificial Intelligence 12(3), pp. 231 to 272*, 1979. [Source](https://doi.org/10.1016/0004-3702(79)90008-0).

30. <span id="ref-30"></span> Jeffrey L. Elman. “Learning and Development in Neural Networks: The Importance of Starting Small.” *Cognition 48(1), pp. 71 to 99*, 1993. [Source](https://doi.org/10.1016/0010-0277(93)90058-4).

## Acknowledgements

<!-- acknowledgements list -->

## Citation {#citation}

Please cite this post as:

Ma Kaijing. "A Laboratory for Data Laws." Blog post, 2026. https://mkj69.github.io/opulse/blog/

```bibtex
@misc{ma2026laboratory,
  author       = {Ma, Kaijing},
  title        = {A Laboratory for Data Laws},
  year         = {2026},
  howpublished = {\url{https://mkj69.github.io/opulse/blog/}},
  note         = {Blog post}
}
```
