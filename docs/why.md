# Why Opulse

Opulse combines chosen basic operations into new rules. You can vary how those rules appear in tasks and compare the recorded task properties. The reference program checks answers against the written definitions. See the [glossary](glossary.md) for terms used on this page.

## Execution or reasoning?

The [six angles](guide/benchmark.md#six-angles) distinguish what a model does with a rule. Compute follows shown rules to a result, and Invert works back from a result to an input. Decide proves or refutes a claim, while Describe moves between formal rules and plain language. Induce recovers a rule from examples or carries its structure to new material, and Create builds a new definition or expression that meets a goal.

## Three things Opulse gives you

### Generate distinct rules at larger scales {#new-concepts-at-scale}

Learning a rule supplied in context is difficult. [CL-bench](https://arxiv.org/abs/2602.03587) has 500 expert written contexts with knowledge absent from earlier training. Ten frontier models solve 17.2% of its tasks on average, and the best solves 23.7%. [ReSyn](https://arxiv.org/abs/2602.20117) generates environments that check their own answers and lifts a 7B model by 27% (relative) on BBEH.

`opulse operators` composes chosen atoms into definitions by substitution, conditional choice, and bounded recursion. A seed selects an operator set. A run with reduced acceptance checks grew 100,000 operators in about 8.1 hours ([Performance](about/benchmarks.md)). `opulse bench leakage` compares operator definitions up to renaming and values on sampled inputs across sets. With `--context full`, each `opulse bench build` task states the definitions it needs.

Evidence: seeds 1 and 2 give 40 operators each with no definition in common, even after renaming ([check](#new-concepts)).

### Every factor a separate option {#one-factor-at-a-time}

Properties of synthetic data can change what a model learns. [ScaleLogic](https://arxiv.org/abs/2605.06638) reports up to 10.66 points of downstream transfer from more expressive logic. [2609.39827](https://arxiv.org/abs/2609.39827) reports that synthetic training on synthetic tasks before pretraining saves at least 21B tokens at 3B parameters. [Logic Before Language](https://arxiv.org/abs/2608.03930) reports 36B tokens saved by training on formal derivations before pretraining. Its authors describe earlier synthetic tasks built on narrow primitives such as Dyck languages. Skills with power law frequencies compose more readily than uniformly frequent skills in [Wang et al.](https://arxiv.org/abs/2604.22951).

Opulse makes primitives, depth, frequency, and notation separate settings. Choose [atoms](guide/atoms.md), set definition counts with `opulse bench build --min-definitions` and `--max-definitions`, limit concept layers with `--max-layer`, and set expression depth with `--max-depth`. `recursion.*` configures recursion, and `--max-abs-value` limits magnitude. `--operator-frequency uniform` or `zipf:ALPHA` sets operator usage in `opulse expressions` and `opulse bench build`. `--naming` and the numeral base change how a rule is written. Task records expose the resulting `axes`.

Evidence: with English names, 50 tasks keep all 50 answers and 13 of 14 recorded features; with `zipf:1.5`, the usage Gini of 2,000 expressions rises from 0.112 to 0.658 while the minimum, median, 90th percentile and maximum of their size and depth stay the same ([check](#one-option)).

### Every step checkable {#every-step-checked}

A score on familiar problems can come from memory. On [GSM1k](https://arxiv.org/abs/2405.00332), a fresh copy of GSM8K, tested models lose up to 8% accuracy. Finding an incorrect line in a solution often takes expert labels. [ProcessBench](https://arxiv.org/abs/2412.06559) contains 3,400 solutions labeled that way.

`opulse bench build --format steps` writes tasks that call for one rewrite per line. The interpreter checks each line and identifies the first wrong step. `opulse bench score` reports both answer accuracy and step validity.

Evidence: a derivation with one wrong value inside `0 * (…)` reaches the right answer, and the grader rejects it at line 5 ([check](#wrong-step)).

## Try it in one minute {#try-it}

Run these checks in order from the repository root after `pip install -e .`. Later checks use the first operator file. Work files go to `outputs/ev/`. The outputs below are real and produced by `python tools/docs_evidence.py`; log lines on stderr are omitted. Displayed definitions use shape and subscript labels such as ◆₁, while files in `outputs/ev/` retain their original symbols.

### Two seeds give different concepts {#new-concepts}

**Claim.** Different seeds can grow distinct operator sets from the same atoms.

**Check.** Grow 40 operators per seed in two layers of 20. Compare definition text, definitions after renaming (`structural`), and values on 16 fixed inputs per argument (`behavioural`). `--check-variety` rejects nearly constant operators.

--8<-- "docs/snippets/evidence/seeds.md"

**Reading.** Seeds 1 and 2 each give 40 accepted definitions. They share no definition text or structure after renaming. No operator in seed 2 matches one in seed 1 on the sampled inputs. The sample cannot establish that every pair differs on every input.

### Change one option and inspect the records {#one-option}

**Claim.** Naming and operator frequency are separate settings whose effects can be checked in records.

**Check A: naming.** Build 50 tasks twice with the same seed. Change only `--naming english`, then compare answers and all 14 fields of `axes`.

--8<-- "docs/snippets/evidence/naming.md"

**Reading.** All 50 answers agree. Thirteen of the 14 `axes` fields agree in all 50 pairs, including definitions needed and base operations executed. Only `naming` differs.

**Check B: frequency.** Draw 2,000 expressions with uniform operator frequency and 2,000 with `--operator-frequency zipf:1.5`. `opulse audit-data` reports usage Gini, where 0 means equal usage and values near 1 mean concentrated usage.

--8<-- "docs/snippets/evidence/frequency.md"

**Reading.** Usage Gini rises from 0.112 to 0.658. Applications, depth, highest layer, and operation count retain the same minimum, median, 90th percentile, and maximum. See [Configuration](reference/configuration.md) for the other settings.

### A wrong step is caught at its line {#wrong-step}

**Claim.** A derivation can reach the correct answer through a wrong step, and the grader identifies that line.

**Check.** Build one task with `--format steps`. `tools/docs_evidence.py derive` changes the result of `(-56) @` on line 5 from `-65` to `-64`. Later lines keep the reference values. Multiplication by 0 preserves the final answer. `opulse bench score` grades the response, and `tools/docs_evidence.py grade` prints the step message.

--8<-- "docs/snippets/evidence/steps.md"

**Reading.** The final answer has `accuracy 1.0`. The step grader counts 3 valid lines and identifies line 5 as the first error, with the changed value before and after. See [Benchmarking models](guide/benchmark.md#grading-the-reasoning-not-only-the-answer) for the grading rules.

## Why data is hard to study {#difficulties}

* In natural corpora, concept frequency, expression depth, notation, and topic often change together. Opulse sets these through separate options and records task `axes` for inspection.
* Labels for intermediate steps are missing from most data and cost expert time to add ([above](#every-step-checked)). Opulse writes derivations and checks each rewrite with the interpreter.
* A familiar problem can be answered from memory ([above](#every-step-checked)). A new seed gives new definitions, and with `--context full` each task states the ones it needs.
* A failure on a realistic context can have several causes at once ([above](#new-concepts-at-scale)). Opulse records definitions needed, expression depth, recursion and other `axes` for each task, so failures can be grouped by one property.
* Prior exposure to a definition cannot be known for every model. `opulse bench leakage` reports overlaps within the operator sets supplied for a study.

## Where the answers come from

The reference interpreter applies definitions according to the written [semantics](reference/semantics.md). Compiled code, solver results, and solution steps are checked against it. Before `opulse bench build` writes a compute or contrast task with full context, it parses the definitions back from the prompt and rederives the answer; hole tasks are solved and checked by the solver. [Correctness](about/correctness.md#robustness-across-notations-and-settings) describes checks that pass in 298 configurations covering notation, alphabet, numeric mode, recursion template, partial definitions, and numeral bases.

## Boundaries {#current-scope}

By default operators take one or two arguments. The setting `operators.arity_weights` also grows operators with three or more arguments, written in call form such as `⊕(a, b, c)`. Definitions use nesting, ordered branches, and bounded recursion, with a few fixed recursion shapes. No operator takes another operator as an argument. Bounded recursion makes every evaluation finite, and the generated shapes stay within primitive recursion. Some operations return NaN for undefined inputs, such as division by zero. Values are integers in the numeric presets; the typed presets add booleans, strings and lists of integers ([Typed values](guide/types.md)).

Checks establish agreement with the written semantics. They cannot establish that those semantics are the ones a researcher wants. Leakage checks use sampled inputs and do not prove that two operators differ everywhere. Different seeds can give different concepts; run `opulse bench leakage` for each train and test split and report results over several operator sets.

Continue with the [experiment ideas](experiments.md) or the [quickstart](getting-started/quickstart.md).


The [lineage](lineage.md) traces the earlier work these ideas come from.
