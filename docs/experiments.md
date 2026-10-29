# Experiment ideas

A data law describes how a property of training data affects what a model learns. Opulse records task properties so you can vary one generation setting and measure what changed. The designs below include data generation commands. This page reports no training results. See the [glossary](glossary.md) for terms used here.

- **Evaluate an existing model, with no training.** Supply definitions in prompts, then run and score the tasks with the [benchmark tools](guide/benchmark.md).
- **Train a model.** Use generated expressions or benchmark tasks as training data, then evaluate with the same [benchmark tools](guide/benchmark.md).

The task types follow [six angles](guide/benchmark.md#six-angles): **Compute** follows rules to results (`compute`, `contrast`); **Invert** recovers inputs (`hole`); **Decide** proves or refutes claims (`equivalence`, `law`, `edit`); **Describe** moves between rules and plain language (`opulse.language`); **Induce** infers rules or transfers structures (`induce`, skeletons); and **Create** builds definitions or expressions for a goal (`simplify`, `faster`, `invent`, `refactor`).

The map groups every idea by how it would use a model. Each card states a question, a design and a decision its result could inform. Some cards also show sample data.

<p class="op-hint op-xmap-hint">Click an idea to jump to it</p>

<nav class="op-xmap" aria-label="Overview of experiment ideas">
<div class="op-xmap-group op-xmap-evaluate"><a class="op-xmap-title" href="#evaluate">Evaluate existing models</a><div class="op-xmap-tiles"><a class="op-xmap-tile" href="#failure-predictor">Which tasks predict failure</a><a class="op-xmap-tile" href="#induce">Predict outputs or state the rule</a><a class="op-xmap-tile" href="#distractors">Distractors and retrieval</a><a class="op-xmap-tile" href="#probes-and-patches">Probes and patches</a><a class="op-xmap-tile" href="#edit-propagation">Edit propagation</a></div></div>
<div class="op-xmap-group op-xmap-train"><a class="op-xmap-title" href="#train">Train new models</a><div class="op-xmap-tiles"><a class="op-xmap-tile" href="#transfer">Transfer outside Opulse</a><a class="op-xmap-tile" href="#weights-or-context">Weights or context</a><a class="op-xmap-tile" href="#process-reward">Process or outcome reward</a><a class="op-xmap-tile" href="#derivation-tokens">Derivation length</a><a class="op-xmap-tile" href="#long-tail">Long tail of concepts</a><a class="op-xmap-tile" href="#breadth-or-depth">Breadth or depth</a><a class="op-xmap-tile" href="#prerequisite-order">Prerequisite order</a><a class="op-xmap-tile" href="#spacing">Spacing</a><a class="op-xmap-tile" href="#contrast-reward">Contrast pair reward</a><a class="op-xmap-tile" href="#auto-curriculum">Automatic curriculum</a></div></div>
<div class="op-xmap-group op-xmap-observe"><a class="op-xmap-title" href="#observing">Observe inside models</a><div class="op-xmap-tiles"><a class="op-xmap-tile" href="#applied-rules-per-parameter">Rules per parameter</a><a class="op-xmap-tile" href="#read-only-rules">Rules only read</a><a class="op-xmap-tile" href="#manipulate-rules">Manipulating rules</a><a class="op-xmap-tile" href="#precompute">Precomputing values</a><a class="op-xmap-tile" href="#depth-vs-layers">Depth and layers</a><a class="op-xmap-tile" href="#corrected-mistakes">Corrected mistakes</a><a class="op-xmap-tile" href="#delayed-generalization">Delayed generalization</a><a class="op-xmap-tile" href="#discover">Better definitions</a></div></div>
<div class="op-xmap-group op-xmap-worlds"><a class="op-xmap-title" href="#across-worlds">Across worlds</a><div class="op-xmap-tiles"><a class="op-xmap-tile" href="#same-tree-other-world">Same tree, other world</a><a class="op-xmap-tile" href="#warm-up-material">Best warm up material</a><a class="op-xmap-tile" href="#world-variety">One world or several</a><a class="op-xmap-tile" href="#step-checker-new-world">Step checker in a new world</a></div></div>
<div class="op-xmap-group op-xmap-weights"><a class="op-xmap-title" href="#inside-weights">Inside the weights</a><div class="op-xmap-tiles"><a class="op-xmap-tile" href="#write-concept">Write a concept in</a><a class="op-xmap-tile" href="#compiled-solution">Can training find a compiled solution</a></div></div>
</nav>

## Data laws you can measure {#data-laws}

Each row is a candidate regularity that one of the designs below would measure.

<div class="op-laws-grid" role="list">
<div class="op-law-row" role="listitem"><div class="op-law-cell"><b>Knob</b>Examples, rule size, world and answer type</div><div class="op-law-cell"><b>Measure</b>Query accuracy and equivalent rule rate</div><div class="op-law-cell"><b>Would inform</b>Choose prediction or explicit rule induction (<a href="#induce">induction</a>)</div></div>
<div class="op-law-row" role="listitem"><div class="op-law-cell"><b>Knob</b>Operator kinds, recursion, task family</div><div class="op-law-cell"><b>Measure</b>Change on outside rule tasks</div><div class="op-law-cell"><b>Would inform</b>Set synthetic rule data budget (<a href="#transfer">transfer</a>)</div></div>
<div class="op-law-row" role="listitem"><div class="op-law-cell"><b>Knob</b>Rule exposure and query count</div><div class="op-law-cell"><b>Measure</b>Accuracy and compute per answer</div><div class="op-law-cell"><b>Would inform</b>Choose training or retrieval (<a href="#weights-or-context">weights or context</a>)</div></div>
<div class="op-law-row" role="listitem"><div class="op-law-cell"><b>Knob</b>Reward mode and trace use</div><div class="op-law-cell"><b>Measure</b>Free format accuracy per compute</div><div class="op-law-cell"><b>Would inform</b>Choose step verifier investment (<a href="#process-reward">process reward</a>)</div></div>
<div class="op-law-row" role="listitem"><div class="op-law-cell"><b>Knob</b>Derivation detail and depth</div><div class="op-law-cell"><b>Measure</b>New composition accuracy per token</div><div class="op-law-cell"><b>Would inform</b>Choose trace length by item (<a href="#derivation-tokens">derivation tokens</a>)</div></div>
<div class="op-law-row" role="listitem"><div class="op-law-cell"><b>Knob</b>Frequency weights and floor</div><div class="op-law-cell"><b>Measure</b>Accuracy by exposure decile</div><div class="op-law-cell"><b>Would inform</b>Set rare concept exposure (<a href="#long-tail">long tail</a>)</div></div>
<div class="op-law-row" role="listitem"><div class="op-law-cell"><b>Knob</b>Concept count and examples</div><div class="op-law-cell"><b>Measure</b>Accuracy at fixed tokens</div><div class="op-law-cell"><b>Would inform</b>Split budget across concepts (<a href="#breadth-or-depth">breadth or depth</a>)</div></div>
<div class="op-law-row" role="listitem"><div class="op-law-cell"><b>Knob</b>Edit position and method</div><div class="op-law-cell"><b>Measure</b>New and old answers by distance</div><div class="op-law-cell"><b>Would inform</b>Update dependent rules (<a href="#edit-propagation">edit propagation</a>)</div></div>
<div class="op-law-row" role="listitem"><div class="op-law-cell"><b>Knob</b>Record order and spacing</div><div class="op-law-cell"><b>Measure</b>Retention and forgetting curves</div><div class="op-law-cell"><b>Would inform</b>Set order and replay interval (<a href="#prerequisite-order">prerequisite order</a>, <a href="#spacing">spacing</a>)</div></div>
<div class="op-law-row" role="listitem"><div class="op-law-cell"><b>Knob</b>Probe layer and task depth</div><div class="op-law-cell"><b>Measure</b>Probe accuracy and patch shift</div><div class="op-law-cell"><b>Would inform</b>Choose supervision targets (<a href="#probes-and-patches">probes and patches</a>)</div></div>
<div class="op-law-row" role="listitem"><div class="op-law-cell"><b>Knob</b>Definitions, depth, rewrite count</div><div class="op-law-cell"><b>Measure</b>Accuracy in matched cells</div><div class="op-law-cell"><b>Would inform</b>Set deep composition share (<a href="#failure-predictor">failure predictor</a>)</div></div>
<div class="op-law-row" role="listitem"><div class="op-law-cell"><b>Knob</b>Library size and junk share</div><div class="op-law-cell"><b>Measure</b>Rules applied on new inputs</div><div class="op-law-cell"><b>Would inform</b>Set concepts per model size (<a href="#applied-rules-per-parameter">applied rules per parameter</a>)</div></div>
<div class="op-law-row" role="listitem"><div class="op-law-cell"><b>Knob</b>Model layers and task depth</div><div class="op-law-cell"><b>Measure</b>No trace accuracy by depth</div><div class="op-law-cell"><b>Would inform</b>Choose traces or model depth (<a href="#depth-vs-layers">depth vs layers</a>)</div></div>
<div class="op-law-row" role="listitem"><div class="op-law-cell"><b>Knob</b>Sampler and target success band</div><div class="op-law-cell"><b>Measure</b>Samples to reach each difficulty cell</div><div class="op-law-cell"><b>Would inform</b>Pace RL difficulty (<a href="#auto-curriculum">automatic curriculum</a>)</div></div>
<div class="op-law-row" role="listitem"><div class="op-law-cell"><b>Knob</b>Source world trees, target data amount</div><div class="op-law-cell"><b>Measure</b>Target world accuracy at each target data amount</div><div class="op-law-cell"><b>Would inform</b>Supplement scarce target data (<a href="#same-tree-other-world">same tree, other world</a>)</div></div>
<div class="op-law-row" role="listitem"><div class="op-law-cell"><b>Knob</b>Warm up world and tree depth</div><div class="op-law-cell"><b>Measure</b>Total tokens to a fixed held out loss, including warm up</div><div class="op-law-cell"><b>Would inform</b>Choose a warm up corpus (<a href="#warm-up-material">warm up material</a>)</div></div>
<div class="op-law-row" role="listitem"><div class="op-law-cell"><b>Knob</b>Worlds sharing one budget</div><div class="op-law-cell"><b>Measure</b>Held out tree and unseen world accuracy</div><div class="op-law-cell"><b>Would inform</b>Fund a new generator or more samples (<a href="#world-variety">one world or several</a>)</div></div>
<div class="op-law-row" role="listitem"><div class="op-law-cell"><b>Knob</b>Held out world and RL step</div><div class="op-law-cell"><b>Measure</b>False approvals against the exact checker</div><div class="op-law-cell"><b>Would inform</b>Choose learned or exact step checks (<a href="#step-checker-new-world">step checker</a>)</div></div>
<div class="op-law-row" role="listitem"><div class="op-law-cell"><b>Knob</b>Model depth and training steps</div><div class="op-law-cell"><b>Measure</b>Slot probe accuracy and patch shift by layer</div><div class="op-law-cell"><b>Would inform</b>Use compiled networks as references (<a href="#compiled-solution">compiled solution</a>)</div></div>
</div>

<p class="op-hint">Click to show the controls</p>

??? note "Controls for every training experiment"

    1. Use at least three operator seeds per condition. Report results for each operator set and pooled results.
    2. Use fresh operator sets for claims about new concepts. Check them with `opulse bench leakage --train-operators A --test-operators B`. Its fixed input sample reduces overlap risk but cannot prove that two operators differ everywhere. Report shared atoms.
    3. Audit exposure in three counts: direct calls, appearances in supplied definitions, and applications in reference derivations. The `defined_operators` field records operators written in an expression, while prerequisites can also be practiced inside dependent definitions and derivations.
    4. When traces differ in length, compare both equal training tokens and equal problems.
    5. Freeze the problem set where arms differ only in presentation or exposure. Separate `expressions` or `bench build` runs sample different expressions, so save one expression set and render each arm from it with an external script. Where arms change the generator or the task family, match and report measured task properties.
    6. Report measured dependency depth, branch count, unfolding count, reference rewrite count, prompt tokens and answer magnitude with cell counts. Settings such as `--max-layer`, `--max-depth`, `expressions.max_depth` and `operators.max_if_branches` are caps.
    7. Fix `--naming symbols` unless notation is under study. For naming studies, hold the numeral base fixed and use aliases with matched token counts, since names change familiarity and token count together; study the numeral base separately.

    Training advice applies to real training only if the [transfer experiment](#transfer) shows that the relevant gain transfers outside Opulse.

## Evaluate existing models {#evaluate}

### Which property of a composed problem predicts failure? {#failure-predictor}

**Question.** For a model reading definitions in context, does accuracy track the number of definitions, the longest dependency chain, or the total rewrite count?

**What it would tell you.** If chain length predicts failure at fixed work, a team training models can add deeper compositions. If definition count predicts failure, it can train rule selection. If rewrite count explains the difference, it can target computation length with traces or inference tokens. Empty matched cells would limit any causal claim.

<div class="op-xp">
<script type="application/json" class="op-xp-spec">
{"vary": {"knob": "One property varied, others matched", "values": ["definition count", "chain length", "rewrite count"], "shape": "chips"}, "fixed": ["same operator set", "other two measured properties matched", "same prompt style"], "measure": ["answer accuracy", "first wrong rewrite"]}
</script>
<script type="application/json" class="op-xp-peek">
--8<-- "docs/snippets/peeks/failure-predictor.json"
</script>
</div>

<p class="op-hint">Click to show the setup and commands</p>

??? note "Setup, commands and measures"

    **Setup.** Generate `opulse bench build --family compute --context full` tasks across several `--min-definitions`, `--max-definitions`, `--max-layer` and `--max-depth` settings on three libraries. Select matched cells in advance so one measured property varies while the others overlap. Use a `--format steps` subset to locate the first wrong rewrite.

    **Measure.** Report accuracy and cell counts for each matched cell, accuracy when each needed component is asked alone, residual differences between cells, and first error position.

    **Why Opulse.** Natural multi step questions change topic familiarity and retrieval difficulty along with length. Opulse records definitions and exact rewrite counts for each task.

    **Data generation check.** Five task sets from one operator library require exactly 1, 2 or 4 definitions; add distractors to one 4 definition set and omit definitions from another. The saved records show actual `definitions_needed` and `distractors` values. `opulse bench run` can query a model and `opulse bench score` can group its replies by these axes.

    --8<-- "docs/snippets/evidence/context.md"

    **Sources.** Dziri et al. 2023, [*Faith and Fate: Limits of Transformers on Compositionality*](https://arxiv.org/abs/2305.18654), arXiv:2305.18654. Press et al. 2022, [*Measuring and Narrowing the Compositionality Gap in Language Models*](https://arxiv.org/abs/2210.03350), arXiv:2210.03350. Zhou et al. 2025, [*GSM-Infinite: How Do Your LLMs Behave over Infinitely Increasing Context Length and Reasoning Complexity?*](https://arxiv.org/abs/2502.05252), arXiv:2502.05252.

### Does stating the rule beat predicting outputs? {#induce}

**Question.** Given input and output examples of a hidden operator, can a model predict new outputs or state an equivalent rule more reliably as the example count, rule size and world change?

**Regularity.** Measure query output accuracy and the rate of equivalent definitions against the number of shown examples and the recorded `axes.body_size`, separately in each world. `--max-size` is a cap, and `--examples` is a target minimum when more examples are needed to distinguish candidate rules.

**What it would tell you.** If equivalent definitions hold up where individual predictions fail, use explicit rules for repeated queries. If predictions hold up but definitions fail, use direct answers and treat a written rule as a separate capability.

<div class="op-xp">
<script type="application/json" class="op-xp-spec">
{"vary": {"knob": "Examples, rule size and world", "values": ["3 examples", "6 examples", "smaller rules", "larger rules", "integer", "grid"], "shape": "chips"}, "fixed": ["same hidden operator and queries within each answer pair", "same input range", "matched prompt budget"], "measure": ["query output accuracy", "equivalent definition rate"], "lanes": [{"name": "predict", "steps": ["read examples", "write query outputs"]}, {"name": "define", "steps": ["read same examples", "write an equivalent rule"]}]}
</script>
</div>

<p class="op-hint">Click to show the setup and commands</p>

??? note "Setup, commands and measures"

    **Setup.** Build `induce` tasks in each world, then make paired `--answer predict` and `--answer define` requests from the same saved task records. Keep the examples, hidden operator, query inputs, input range and rulebook fixed within each pair. Use separate builds only to draw candidate tasks for different example and size settings; match the recorded body size, arity, number of known definitions and prompt tokens before comparing settings. Use at least three operator seeds per condition.

    ```bash
    opulse operators --out integer_ops.jsonl --layers 10 6 3 --seed 4
    opulse bench build --family induce --operators integer_ops.jsonl --out integer_induce.jsonl \
      --count 20 --seed 4 --examples 6 --examples-max 10 --queries 3 --answer both --max-size 6
    opulse bench check --tasks integer_induce.jsonl --operators integer_ops.jsonl
    python -c 'from opulse.worlds.showcase import world_spec; world_spec("grid").build()[1].to_jsonl("grid_ops.jsonl")'
    printf '{"preset": "grid"}\n' > grid_config.json
    opulse bench build --family induce --operators grid_ops.jsonl --config grid_config.json \
      --out grid_induce.jsonl --count 20 --seed 4 --examples 6 --examples-max 10 \
      --queries 3 --answer both --max-size 6
    opulse bench check --tasks grid_induce.jsonl --operators grid_ops.jsonl --config grid_config.json
    ```

    Repeat the builds with `--examples 3` and `--max-size 4`, then retain matched cells by the saved example count and `axes.body_size`. The paired answer prompts and the rulebook switch below require an external prompt builder; separate `bench build` runs do not guarantee the same tasks. Score predictions by exact query outputs. Score definitions by parsing, agreement with the examples and equivalence to the hidden rule. Equivalence can be proved or checked on the task's stated input range.

    **Rulebook switch.** Keep the same examples, hidden function and queries under two rulebooks with different available atoms or known definitions. Verify that both rulebooks can express the hidden function, then compare prediction and definition scores. This control measures whether the model uses the supplied rule language rather than only the example table.

    **Grid comparison.** In the grid world, retain tasks with one grid input and a grid output. Present their examples and held out query in an ARC style grid format, and compare output grid accuracy with equivalent rule rate on the same items. Collect more tasks if this filter leaves too few. These generated tasks use Opulse's fixed grid atoms and are not a score on the original ARC corpus.

    **Open question.** In [*RobustFill*](https://arxiv.org/abs/1703.07469), Devlin et al. found that program synthesis outperformed a comparable direct induction model on their string transformation task, while the comparison depended on the metric. Does the relative success of rule writing and direct prediction vary across Opulse worlds, especially grid tasks? Chollet's ARC supplies the few example grid task setting for that comparison.

    **Sources.** Devlin et al. 2017, [*RobustFill: Neural Program Learning under Noisy I/O*](https://arxiv.org/abs/1703.07469), arXiv:1703.07469. Chollet 2019, [*On the Measure of Intelligence*](https://arxiv.org/abs/1911.01547), arXiv:1911.01547.

### How do rule closure and retrieval interact with distractors? {#distractors}

**Question.** Does accuracy fall with distractor count, distractor similarity, or missing prerequisites? How does a retriever compare with the exact dependency closure?

**What it would tell you.** If count drives failure, a team training models can shorten supplied contexts. If missing prerequisites drive failure, it can expand retrieved definitions to their closure. If similar competing rules drive failure, it can train rule selection and evaluate retrieval at matched context lengths.

<div class="op-xp">
<script type="application/json" class="op-xp-spec">
{"vary": {"knob": "Supplied definitions", "values": ["0 distractor definitions", "8 distractor definitions", "32 distractor definitions", "128 distractor definitions"], "shape": "bars"}, "fixed": ["same query", "same needed rules", "same library"], "measure": ["answer accuracy", "closure recall"], "lanes": [{"name": "oracle", "steps": ["exact closure", "answer"]}, {"name": "retriever", "steps": ["retrieve top k", "answer"]}]}
</script>
<script type="application/json" class="op-xp-peek">
--8<-- "docs/snippets/peeks/distractors.json"
</script>
</div>
<p class="op-hint">Click to show the setup and commands</p>

??? note "Setup, commands and measures"

    **Setup.** Use `opulse bench build --family compute --context full` for the exact closure. Request `--distractors N` for N equal to 0, 8, 32 and 128, with a length matched control, and group tasks by the recorded `axes.distractors`, since whole dependency closures are drawn. Select same kind or behaviorally similar distractors in an external script and audit its selections; `opulse bench check` verifies answers against prompts, not distractor choice. Use `opulse bench build --family handbook` for a configurable set of relevant and distractor definitions. Compare a real retriever over the full library at several top k values with oracle closure.

    **Measure.** Report accuracy by count, similarity, position and prompt tokens; retriever closure recall; irrelevant definition use in step responses; and latency.

    **Why Opulse.** The needed closure is exact, so retrieval misses and irrelevant definitions can be counted separately.

    **Sources.** Shi et al. 2023, [*Large Language Models Can Be Easily Distracted by Irrelevant Context*](https://arxiv.org/abs/2302.00093), arXiv:2302.00093. Liu et al. 2023, [*Lost in the Middle: How Language Models Use Long Contexts*](https://arxiv.org/abs/2307.03172), arXiv:2307.03172.

### Can probes and patches predict use of intermediate values? {#probes-and-patches}

**Question.** The interpreter knows each intermediate value. Do probe scores recover those values from an open weight model, and do they predict the effect of a patch on its answer?

**What it would tell you.** If probe scores predict patch effects on fresh operators, a team training models can use them to choose intermediate values for supervision. If values decode well but patches have little effect, it can choose targets by measured training gains instead.

<div class="op-xp">
<script type="application/json" class="op-xp-spec">
{"vary": {"knob": "Activation site", "values": ["early layer", "middle layer", "late layer"], "shape": "chips"}, "fixed": ["same model", "held out operators", "same input pair"], "measure": ["probe accuracy", "patch margin shift"], "lanes": [{"name": "probe", "steps": ["collect model activations", "train probe on reference values"]}, {"name": "patch", "steps": ["swap activation", "measure shift"]}]}
</script>
<script type="application/json" class="op-xp-peek">
--8<-- "docs/snippets/peeks/probes-and-patches.json"
</script>
</div>
<p class="op-hint">Click to show the setup and commands</p>

??? note "Setup, commands and measures"

    **Setup.** Build tasks with `opulse bench build --family compute --context full --naming symbols --min-definitions 2 --max-definitions 4 --max-depth 2`. Collect aligned activations with `opulse interp collect --model M --tasks T --operators O --layers 0,4,8 --out A`; fit held out operator probes with `opulse interp probe --activations A --site subexpression --out P1` and `opulse interp probe --activations A --site reduction_step --out P2`; then run `opulse interp patch` on pairs that change one numeric argument. Compare shuffled labels, input token and position baselines, and patches at unrelated spans. Reduction steps share their source subexpression position.

    **Measure.** Report probe accuracy by layer on held out operators, the fraction of patches that make the counterfactual answer's likelihood margin positive, and agreement across depth and operator kind.

    **Why Opulse.** Opulse supplies exact reference values for subexpressions and exact counterfactual answers.

    **Sources.** Hewitt and Liang 2019, [*Designing and Interpreting Probes with Control Tasks*](https://arxiv.org/abs/1909.03368), arXiv:1909.03368. Zhang and Nanda 2023, [*Towards Best Practices of Activation Patching in Language Models: Metrics and Methods*](https://arxiv.org/abs/2309.16042), arXiv:2309.16042. Makelov et al. 2023, [*Is This the Subspace You Are Looking for? An Interpretability Illusion for Subspace Activation Patching*](https://arxiv.org/abs/2311.17030), arXiv:2311.17030. Mueller et al. 2025, [*MIB: A Mechanistic Interpretability Benchmark*](https://arxiv.org/abs/2504.13151), arXiv:2504.13151.

### Does an edited rule reach the operators built on it? {#edit-propagation}

**Question.** When a low layer definition changes, do dependent operators update at each distance? Evaluate edits supplied in context first, then train an edit into weights and test again.

**What it would tell you.** If context edits propagate and weight edits do not, a team training models can keep changeable rules in context. If neither propagates beyond one step, it can pair updates with examples of dependent operators.

<div class="op-xp">
<script type="application/json" class="op-xp-spec">
{"vary": {"knob": "Dependency distance", "values": ["0 hops (edited rule)", "1 hop", "2 hops", "3 hops"], "shape": "stack"}, "fixed": ["same input", "same rule edit", "unaffected control"], "measure": ["new answer rate", "old answer rate"], "lanes": [{"name": "context edit", "steps": ["show new rule", "test dependents"]}, {"name": "weight edit", "steps": ["train new rule", "test dependents"]}]}
</script>
<script type="application/json" class="op-xp-peek">
--8<-- "docs/snippets/peeks/edit-propagation.json"
</script>
</div>
<p class="op-hint">Click to show the setup and commands</p>

??? note "Setup, commands and measures"

    **Setup.** Build `opulse bench build --family edit` tasks that replace one nonrecursive prerequisite and retain cases where the answer changes. Run `python examples/edit_propagation.py ops.jsonl --out edits.jsonl` to list dependent operators and their values before and after on the fixed input sample. Fine tune a second arm on the edit and test it without a change section. A definition edit patch study also needs an external paired prompt builder because `opulse interp patch` changes a numeric argument.

    **Measure.** Report accuracy and old answer rate by dependency distance, conditional on answering the edited operator correctly, plus accuracy on unaffected expressions.

    **Why Opulse.** The dependency graph and every answer before and after an edit are exact. A dependent value need not change on every input.

    **Data generation check.** Contrast pairs swap one shown definition while keeping the expression and symbols fixed. The edit propagation script lists each dependent operator, its dependency distance, and values before and after on the sample.

    --8<-- "docs/snippets/evidence/edits.md"

    **Sources.** Cohen et al. 2023, [*Evaluating the Ripple Effects of Knowledge Editing in Language Models*](https://arxiv.org/abs/2307.12976), arXiv:2307.12976. Hase et al. 2023, [*Does Localization Inform Editing? Surprising Differences in Causality-Based Localization vs. Knowledge Editing in Language Models*](https://arxiv.org/abs/2301.04213), arXiv:2301.04213.

## Train new models {#train}

### Does training on Opulse transfer to rule following outside Opulse? {#transfer}

**Question.** After training on Opulse data, does a model improve at learning and applying rules stated in prose, code or real task contexts? Which structural factor carries any gain?

**What it would tell you.** If a factor improves a predeclared outside evaluation set, a team training models can assign synthetic data budget to that factor. If no factor transfers, the other training cards guide Opulse data generation only. That test would show whether the advice holds for the outside tasks and models it covers.

<div class="op-xp">
<script type="application/json" class="op-xp-spec">
{"vary": {"knob": "Training factor", "values": ["simple rules", "branches", "recursion", "task family"], "shape": "chips"}, "fixed": ["same base model", "same token budget", "outside tests frozen", "matched compute"], "measure": ["outside task change", "fresh rule accuracy"], "lanes": [{"name": "RL arm", "steps": ["vary one factor", "train"]}, {"name": "supervised arm", "steps": ["vary one factor", "train"]}, {"name": "test", "steps": ["outside tasks", "fresh rules"]}]}
</script>
<script type="application/json" class="op-xp-peek">
--8<-- "docs/snippets/peeks/transfer.json"
</script>
</div>

<p class="op-hint">Click to show the setup and commands</p>

??? note "Setup, commands and measures"

    **Setup.** Train RL and supervised arms from one base model. Fix outside sets, token and compute budgets, and a minimum meaningful gain in advance. Use context learning tasks such as CL-bench, verifiable math or code tasks, and new rule systems written in prose. Vary operator kinds with `opulse operators --proportions SIMPLE BRANCH RECURSIVE`, recursion style with config `recursion.style`, and task families with `opulse bench build --family compute`, `hole` and `contrast`. Use `--no-simple`, `--no-branches`, `--no-recursion` and `--max-substitution-depth` to isolate composition types. Match measured task properties and tokens. Include token matched real task training and no extra training as baselines. Vary prose rule semantics, wording and atoms separately.

    **Measure.** Report change from the base model on each outside set against the declared threshold, change on a fresh Opulse library, and losses on other base model tasks.

    **Why Opulse.** Each arm requests one structural change while atoms and reference semantics stay fixed; the accepted definition kinds and measured task properties are recorded, so arms can be matched.

    **Data generation check.** Two corpora of 2,000 expressions request different operator kind mixes while sharing atoms, layer sizes and seed. Inspect accepted definition kinds: the plain definition request in the recipe still accepted one recursive definition.

    --8<-- "docs/snippets/evidence/factors.md"

    **Sources.** Wang et al. 2026, [*How Deep Can LLMs Learn to Reason? Expressiveness Is Key*](https://arxiv.org/abs/2605.06638), arXiv:2605.06638. He et al. 2026, [*ReSyn: Autonomously Scaling Synthetic Environments for Reasoning Models*](https://arxiv.org/abs/2602.20117), arXiv:2602.20117. Dou et al. 2026, [*CL-bench: A Benchmark for Context Learning*](https://arxiv.org/abs/2602.03587), arXiv:2602.03587. Kabra et al. 2026, [*Learning from Synthetic Data Improves Multi-hop Reasoning*](https://arxiv.org/abs/2603.02091), arXiv:2603.02091.

### When should a rule be trained into weights instead of supplied in context? {#weights-or-context}

**Question.** For a rule queried many times, how do accuracy and total cost compare between training it into weights and supplying its definition at each query? Does a trained rule yield to a changed definition?

**What it would tell you.** If trained rules meet the accuracy requirement and follow a changed definition, a team training models can train rules above the measured query count and retrieve the rest. If practice makes the old answer persist after a swap, it can keep changing rules in retrieval and train override episodes.

<div class="op-xp">
<script type="application/json" class="op-xp-spec">
{"vary": {"knob": "Rule exposure", "values": ["none", "low", "medium", "high"], "shape": "chips"}, "fixed": ["same operator", "same query pool", "same model size"], "measure": ["accuracy", "compute per answer", "old answer rate"], "lanes": [{"name": "in weights", "steps": ["train rule", "query bare"]}, {"name": "in context", "steps": ["read rule", "query"]}, {"name": "swapped rule", "steps": ["read edit", "query"]}]}
</script>
<script type="application/json" class="op-xp-peek">
--8<-- "docs/snippets/peeks/weights-or-context.json"
</script>
</div>

<p class="op-hint">Click to show the setup and commands</p>

??? note "Setup, commands and measures"

    **Setup.** Generate one library with `opulse operators --layers 40 30 20 10 --seed S --out ops.jsonl`. Freeze an expression pool from `opulse expressions --operators ops.jsonl --out pool.jsonl --count N --cot none`; use an external sampler for several exposure levels. Train one policy on operator use and another on reading definitions. Render paired tests from saved expressions with definitions present, absent and replaced by unrelated definitions of similar length. Build `opulse bench build --family contrast` pairs and keep, with an external script, the pairs whose swapped definition belongs to a practiced operator.

    **Measure.** Report accuracy by policy and exposure level, pairs with both answers correct, old answer rate after swaps, and total training plus prompt and inference compute across stated future query counts.

    **Why Opulse.** The sampler sets prior exposure, and both original and changed answers are exact.

    **Sources.** Ovadia et al. 2023, [*Fine-Tuning or Retrieval? Comparing Knowledge Injection in LLMs*](https://arxiv.org/abs/2312.05934), arXiv:2312.05934. Kim et al. 2025, [*How Training Data Shapes the Use of Parametric and In-Context Knowledge in Language Models*](https://arxiv.org/abs/2510.02370), arXiv:2510.02370. Singh et al. 2025, [*Strategy Coopetition Explains the Emergence and Transience of In-Context Learning*](https://arxiv.org/abs/2503.05631), arXiv:2503.05631.

### Process reward, outcome reward, or supervised traces? {#process-reward}

**Question.** Does RL with exact step reward teach more than RL with outcome reward? Does either beat supervised reference traces at equal compute?

**What it would tell you.** If step or progress reward improves free format accuracy, a team training models can invest in step verifiers. If only written step validity improves, it can use outcome reward for capability and step checks for auditing. If supervised traces match RL, it can spend compute on more checked traces.

<div class="op-xp">
<script type="application/json" class="op-xp-spec">
{"vary": {"knob": "Training signal", "values": ["outcome", "steps", "progress", "supervised traces"], "shape": "chips"}, "fixed": ["same checkpoint", "same task pool", "matched compute"], "measure": ["free format accuracy", "valid derivations"], "lanes": [{"name": "outcome RL", "steps": ["sample answer", "score answer"]}, {"name": "step RL", "steps": ["sample trace", "check steps"]}, {"name": "progress RL", "steps": ["sample trace", "score verified prefix"]}, {"name": "supervised", "steps": ["reference trace", "train"]}]}
</script>
<script type="application/json" class="op-xp-peek">
--8<-- "docs/snippets/peeks/process-reward.json"
</script>
</div>

<p class="op-hint">Click to show the setup and commands</p>

??? note "Setup, commands and measures"

    **Setup.** Start all arms from one checkpoint. Build `opulse bench build --family compute --format steps --context full --min-definitions 2 --max-definitions 5`, then `opulse bench export --tasks T --operators ops.jsonl --out R`. Compare `examples/rl/grpo_opulse.py --reward outcome`, `--reward steps` and `--reward progress` with supervised training on reference traces rendered from the same frozen tasks. Count rollouts, verifier calls, forward and backward passes, and tokens. Test a fresh library in step and free formats. The progress mode averages the outcome reward with the verified prefix length divided by the reference derivation length.

    **Measure.** Report free format accuracy, complete valid derivations, first error position, tokens per correct answer, and empty, repeated or jumped steps.

    **Why Opulse.** The checker finds the first invalid rewrite in each attempted derivation.

    **Data generation check.** The recipe exports 200 step format tasks as RL records. `opulse.bench.reward.compute_score` reads each record's ground truth and uses its operator file to grade response steps.

    --8<-- "docs/snippets/evidence/faithful.md"

    **Sources.** Lightman et al. 2023, [*Let's Verify Step by Step*](https://arxiv.org/abs/2305.20050), arXiv:2305.20050. Setlur et al. 2024, [*Rewarding Progress: Scaling Automated Process Verifiers for LLM Reasoning*](https://arxiv.org/abs/2410.08146), arXiv:2410.08146. Zheng et al. 2024, [*ProcessBench: Identifying Process Errors in Mathematical Reasoning*](https://arxiv.org/abs/2412.06559), arXiv:2412.06559. Chu et al. 2025, [*SFT Memorizes, RL Generalizes: A Comparative Study of Foundation Model Post-training*](https://arxiv.org/abs/2501.17161), arXiv:2501.17161.

### How many derivation tokens should a training example carry? {#derivation-tokens}

**Question.** Are full derivations worth their token cost? Should detailed traces go only to selected examples?

**What it would tell you.** If coarse traces retain the gain of full ones, a team training models can spend saved tokens on more problems and concepts. If full traces help only deep items, it can reserve detailed solutions for long reference derivations. If targeted detail wins, it can use exact item properties to select examples.

<div class="op-xp">
<script type="application/json" class="op-xp-spec">
{"vary": {"knob": "Trace detail", "values": ["answer only", "coarse", "truncated", "full", "targeted"], "shape": "chips"}, "fixed": ["same expressions", "equal token budget", "same final test"], "measure": ["new composition accuracy", "gain per token"], "sketch": {"x": "trace tokens", "y": "new composition accuracy", "shapes": [{"name": "early plateau", "points": [[0, 0.08], [0.22, 0.66], [0.5, 0.72], [1, 0.74]], "decision": "use coarse traces"}, {"name": "late gain", "points": [[0, 0.06], [0.25, 0.2], [0.55, 0.52], [1, 0.87]], "decision": "reserve full traces"}]}}
</script>
<script type="application/json" class="op-xp-peek">
--8<-- "docs/snippets/peeks/derivation-tokens.json"
</script>
</div>

<p class="op-hint">Click to show the setup and commands</p>

??? note "Setup, commands and measures"

    **Setup.** Save one expression set and render answer only records with `--cot none`, coarse traces with `--cot en --cot-known-layers L`, truncated traces with `--cot en --cot-depth K`, and full traces with `--cot en`. An external renderer keeps the sampled expressions fixed. Select rare operators, deep dependencies and recursion for a targeted full trace arm. Add extra answer only problems and nonsolution padding controls. Compare equal tokens and equal problems, then continue all arms on the same natural text. `--cot-known-layers` also changes which lower layers are shown as computed. Export a training corpus and tokenizer records from the saved data.

    **Measure.** Report correct answers on new inputs and compositions per training token, accuracy by reference rewrite count and beyond trained depth, and loss during shared natural text continuation.

    **Why Opulse.** Opulse shortens derivations at selected layers while each remaining step stays checked.

    **Data generation check.** Two corpora use the same 500 expressions with `--cot en`; one unfolds all operators and the other treats layer 0 as known with `--cot-known-layers 1`. Records include operators used, dependencies and intermediate `steps` values.

    --8<-- "docs/snippets/evidence/invent.md"

    **Sources.** Deng, Choi and Shieber 2024, [*From Explicit CoT to Implicit CoT: Learning to Internalize CoT Step by Step*](https://arxiv.org/abs/2405.14838), arXiv:2405.14838. Chen et al. 2024, [*Do NOT Think That Much for 2+3=? On the Overthinking of o1-Like LLMs*](https://arxiv.org/abs/2412.21187), arXiv:2412.21187. Cheng, Aletras and Valentino 2026, [*Logic Before Language: Pre-pretraining on Formal Derivations Fosters Skill Acquisition and Compressibility*](https://arxiv.org/abs/2608.03930), arXiv:2608.03930.

### Does a long tail of concept frequencies help or starve rare concepts? {#long-tail}

**Question.** Does a power law frequency mix help compositions in a graph of defined concepts with branches and recursion? What happens to the rarest concepts?

**What it would tell you.** If skew helps rare compositions, a team training models can keep a frequent core around the tail. If rare accuracy falls, it can set an exposure floor from the measured practice curve.

<div class="op-xp">
<script type="application/json" class="op-xp-spec">
{"vary": {"knob": "Frequency mix", "values": ["uniform", "mild Zipf", "steep Zipf", "Zipf plus floor"], "shape": "chips"}, "fixed": ["same rule library", "same token budget", "rotated rank assignment"], "measure": ["accuracy by exposure", "worst decile accuracy"], "sketch": {"x": "operator exposure", "y": "accuracy", "shapes": [{"name": "rare concepts hold", "points": [[0, 0.38], [0.3, 0.62], [1, 0.86]], "decision": "keep frequent core"}, {"name": "rare concepts fall", "points": [[0, 0.06], [0.3, 0.38], [1, 0.86]], "decision": "set exposure floor"}]}}
</script>
<script type="application/json" class="op-xp-peek">
--8<-- "docs/snippets/peeks/long-tail.json"
</script>
</div>

<p class="op-hint">Click to show the setup and commands</p>

??? note "Setup, commands and measures"

    **Setup.** Generate and freeze one balanced expression pool. An external sampler draws uniform sets, Zipf sets at two or three exponents, and Zipf sets with a minimum exposure floor. Randomize frequency ranks within matched layer, kind and dependency count, then rotate ranks across replications. For a quick separate run, use `opulse expressions --operators ops.jsonl --out zipf.jsonl --count N --operator-frequency zipf:ALPHA --frequency-seed R` and the same command with `uniform`; these calls sample different pools. Test seen operators in new combinations with `--context none` and a fresh library with `--context full`.

    **Measure.** Report accuracy against direct calls, definition appearances and derivation applications; worst exposure decile; and tokens to fixed accuracy.

    **Why Opulse.** Frequency can be assigned at random to concepts with fixed definitions, rather than varying with topic or explanation quality.

    **Sources.** Wang, Dang, Lee and Lyu 2026, [*The Power of Power Law: Asymmetry Enables Compositional Reasoning*](https://arxiv.org/abs/2604.22951), arXiv:2604.22951. Kandpal et al. 2022, [*Large Language Models Struggle to Learn Long-Tail Knowledge*](https://arxiv.org/abs/2211.08411), arXiv:2211.08411. Zucchet et al. 2025, [*How do language models learn facts? Dynamics, curricula and hallucinations*](https://arxiv.org/abs/2503.21676), arXiv:2503.21676.

### At a fixed budget, more concepts or more examples per concept? {#breadth-or-depth}

**Question.** Once a concept has been seen, is the next token better spent on another use of it or a new concept?

**What it would tell you.** If the accuracy frontier favors breadth at a tested budget, a team training models can increase distinct concepts. If it favors practice, it can allocate more examples per concept. The measured frontier would give a rule for the tested model sizes and budgets.

<div class="op-xp">
<script type="application/json" class="op-xp-spec">
{"vary": {"knob": "Concept allocation", "values": ["few, many uses", "balanced", "many, few uses"], "shape": "chips"}, "fixed": ["same token budget", "same generator", "same model size"], "measure": ["held out accuracy", "new combination accuracy"], "sketch": {"x": "distinct concepts", "y": "accuracy", "shapes": [{"name": "breadth helps", "points": [[0, 0.25], [0.5, 0.64], [1, 0.9]], "decision": "add concepts"}, {"name": "practice helps", "points": [[0, 0.82], [0.5, 0.63], [1, 0.3]], "decision": "add examples"}]}}
</script>
<script type="application/json" class="op-xp-peek">
--8<-- "docs/snippets/peeks/breadth-or-depth.json"
</script>
</div>

<p class="op-hint">Click to show the setup and commands</p>

??? note "Setup, commands and measures"

    **Setup.** Build one library with `opulse operators --layers 128 128 128 --seed S --out ops.jsonl`. An external sampler draws dependency closed subsets of several sizes, crosses subset size with examples per operator at equal tokens, and logs direct and indirect exposure. Test seen operators on held out inputs and new compositions with `--context none`. Repeat at two model sizes.

    **Measure.** Report accuracy by distinct concept count, examples per concept and measured dependency depth at each budget and model size.

    **Why Opulse.** The generator can make fresh problems for one concept and fresh concepts under the same generation rules.

    **Sources.** Muennighoff et al. 2023, [*Scaling Data-Constrained Language Models*](https://arxiv.org/abs/2305.16264), arXiv:2305.16264. Allen-Zhu and Li 2024, [*Physics of Language Models: Part 3.3, Knowledge Capacity Scaling Laws*](https://arxiv.org/abs/2404.05405), arXiv:2404.05405.

### Does prerequisite order matter when the records are identical? {#prerequisite-order}

**Question.** With one fixed multiset of records and one update schedule, does record order change what is learned?

**What it would tell you.** If prerequisite order improves final accuracy, a team training models can order records by dependency layer. If it only improves early checkpoints, it can use staging when those checkpoints matter. If neither changes, it can spend effort on coverage.

<div class="op-xp">
<script type="application/json" class="op-xp-spec">
{"vary": {"knob": "Record order", "values": ["layer order", "flat shuffle", "reverse order"], "shape": "chips"}, "fixed": ["same records", "same update schedule", "same final phase"], "measure": ["checkpoint accuracy", "lower layer retention"], "lanes": [{"name": "layer order", "steps": ["base rules", "dependent rules"]}, {"name": "shuffle", "steps": ["mixed records", "same test"]}, {"name": "reverse", "steps": ["dependent rules", "base rules"]}]}
</script>
<script type="application/json" class="op-xp-peek">
--8<-- "docs/snippets/peeks/prerequisite-order.json"
</script>
</div>

<p class="op-hint">Click to show the setup and commands</p>

??? note "Setup, commands and measures"

    **Setup.** Create one library with `opulse operators --layers 40 30 20 10 --out ops.jsonl` and one saved `opulse expressions --operators ops.jsonl --out pool.jsonl --count N` pool. Label each record by its highest used layer from 0 to 3. An external scheduler presents identical records in layer order, flat shuffle and reverse order. Evaluate at equal checkpoints and after a shared final phase. Report an RL variant using `opulse bench build --max-layer L` pools separately because reward frequency changes with order.

    **Measure.** Report tokens to fixed accuracy by layer, top layer accuracy, lower layer retention, and accuracy before and after the common phase.

    **Why Opulse.** The graph identifies prerequisites while the record multiset stays fixed.

    **Sources.** Chen et al. 2023, [*Skill-it! A Data-Driven Skills Framework for Understanding and Training Language Models*](https://arxiv.org/abs/2307.14430), arXiv:2307.14430. Huang et al. 2024, [*Laying the Foundation First? Investigating the Generalization from Atomic Skills to Complex Reasoning Tasks*](https://arxiv.org/abs/2403.09479), arXiv:2403.09479. Wang, Nichani, Bietti et al. 2025, [*Learning Compositional Functions with Transformers from Easy-to-Hard Data*](https://arxiv.org/abs/2505.23683), arXiv:2505.23683.

### Does spacing the same repetitions change retention? {#spacing}

**Question.** With the same records, exposure counts and last exposure step, does spacing earlier uses change retention and later composition?

**What it would tell you.** If spaced exposure helps, a team training models can spread concept families across a run and replay them. If massed exposure helps, it can teach each concept in one block. Either curve can inform replay intervals within the tested training regime.

<div class="op-xp">
<script type="application/json" class="op-xp-spec">
{"vary": {"knob": "Practice spacing", "values": ["massed", "even intervals", "growing intervals"], "shape": "chips"}, "fixed": ["same records", "same exposure count", "same last exposure"], "measure": ["retained accuracy", "forgetting curve"], "lanes": [{"name": "train", "steps": ["schedule repeats", "last exposure"]}, {"name": "test", "steps": ["new inputs", "later dependents"]}]}
</script>
<script type="application/json" class="op-xp-peek">
--8<-- "docs/snippets/peeks/spacing.json"
</script>
</div>

<p class="op-hint">Click to show the setup and commands</p>

??? note "Setup, commands and measures"

    **Setup.** Save one `opulse expressions --cot none` pool. An external scheduler places earlier concept exposures in massed blocks, even intervals or growing intervals while fixing each concept's count and last exposure step. Test after equal updates and again after a block on unrelated operators, using new inputs for the concepts and their dependents.

    **Measure.** Report accuracy at both test points and forgetting curves by exposure count and time since last exposure.

    **Why Opulse.** The scheduler sets record order, and the audit counts direct calls, definition appearances and derivation applications for each concept.

    **Sources.** Pavlik and Anderson 2005, [*Practice and Forgetting Effects on Vocabulary Memory: An Activation-Based Model of the Spacing Effect*](https://doi.org/10.1207/s15516709cog0000_14), Cognitive Science, doi:10.1207/s15516709cog0000_14. Luo et al. 2023, [*An Empirical Study of Catastrophic Forgetting in Large Language Models During Continual Fine-tuning*](https://arxiv.org/abs/2308.08747), arXiv:2308.08747. O'Neill et al. 2026, [*Can a Language Model Learn Facts Continually in Its Weights?*](https://arxiv.org/abs/2607.11020), arXiv:2607.11020.

### Does outcome RL on contrast pairs make a model respond to the supplied definition? {#contrast-reward}

**Question.** When a rule changes under the same expression and symbols, does pair training improve sensitivity to the supplied definition?

**What it would tell you.** If pair reward raises paired accuracy at equal compute, a team training models can add counterfactual pairs where rules change. If it adds nothing, it can use the budget for ordinary tasks.

<div class="op-xp">
<script type="application/json" class="op-xp-spec">
{"vary": {"knob": "Reward unit", "values": ["single answer reward", "pair reward"], "shape": "chips"}, "fixed": ["same contrast pairs", "same compute", "same starting model"], "measure": ["paired accuracy", "other answer rate"], "lanes": [{"name": "single", "steps": ["answer A", "answer B"]}, {"name": "pair", "steps": ["both answers", "one reward"]}]}
</script>
<script type="application/json" class="op-xp-peek">
--8<-- "docs/snippets/peeks/contrast-reward.json"
</script>
</div>

<p class="op-hint">Click to show the setup and commands</p>

??? note "Setup, commands and measures"

    **Setup.** Build `opulse bench build --family contrast` pairs and train two RL arms on the same pairs. One rewards each answer alone. An external trainer wrapper rewards a pair only when both answers are correct. Report positive reward rollout rate because pair reward is sparser. Test fresh pairs alone and in both orders, plus controls with definitions removed, irrelevant edits and unseen swap kinds.

    **Measure.** Report both answers correct per pair, rate of giving the other member's answer, and ordinary compute accuracy.

    **Why Opulse.** A contrast pair keeps the expression and symbols fixed and computes both answers exactly.

    **Sources.** Wu et al. 2023, [*Reasoning or Reciting? Exploring the Capabilities and Limitations of Language Models Through Counterfactual Tasks*](https://arxiv.org/abs/2307.02477), arXiv:2307.02477. Chen et al. 2025, [*Reasoning Models Don't Always Say What They Think*](https://arxiv.org/abs/2505.05410), arXiv:2505.05410.

### Does practice at a moderate success rate help? {#auto-curriculum}

**Question.** A sampler groups tasks into cells by structure: definitions needed, operator layer, expression depth, branches and recursion. It favors cells whose recent success rate is in a target band and opens harder neighbors after mastery. Does this reach the hard cells with fewer samples than uniform sampling or a fixed easy to hard order?

**What it would tell you.** If the adaptive sampler reaches the hardest cells sooner at equal compute, a team running RL could let measured success choose the next difficulty. If a fixed order does as well, the simpler schedule would be enough for these axes.

<div class="op-xp">
<script type="application/json" class="op-xp-spec">
{"vary": {"knob": "Task sampler", "values": ["uniform", "fixed easy to hard", "adaptive, band 0.4 to 0.7"], "shape": "chips"}, "fixed": ["same task pool", "same RL budget", "same grader", "separate held out tasks"], "measure": ["samples to reach each cell", "held out accuracy by cell"], "lanes": [{"name": "adaptive", "steps": ["grade answer", "update cell rate", "move one axis"]}]}
</script>
<script type="application/json" class="op-xp-peek">
--8<-- "docs/snippets/peeks/auto-curriculum.json"
</script>
</div>

<p class="op-hint">Click to show the setup and commands</p>

??? note "Setup, commands and measures"

    **Setup.** Build a task pool with `opulse bench build` across several `--min-definitions`, `--max-definitions`, `--max-layer` and `--max-depth` settings. Reserve separate tasks in each cell for measuring progress, since repeated pool samples could make a cell appear mastered. `CurriculumSampler.from_tasks(tasks, seed=7)` groups the training records into cells; `sample` picks the next task and `observe` records each graded outcome. Its `target_band`, `window` and `min_observations` arguments set the band and the memory. `opulse env curriculum --simulate --low 0.4 --high 0.7 --window 20` runs a seeded synthetic learner, which checks the sampler and says nothing about a model. The [Automatic curriculum](guide/environments.md#automatic-curriculum) section describes the sampler.

    **Measure.** Samples and compute until each cell first reaches the band, final accuracy by cell, and accuracy on cells no arm sampled.

    **Why Opulse.** Every task records its structural axes, so a cell and its neighbors along one axis are defined exactly.

## Observing models with controlled synthetic data {#observing}

Studies such as Physics of Language Models, TinyStories, and grokking train models on generated data and measure what they learn. Some also inspect internal states. The designs below apply this method to generated rules: an experiment can set operator frequency, composition depth, branching, recursion, and whether definitions appear in the prompt. Its interpreter computes subexpression values and checks rewrite steps. This makes it possible to test rule use on new inputs and compare internal measurements with exact intermediate values. An interpretability integration aligns subexpressions with token spans for probes and activation patches.

| Work | What is generated, and the knob | What it reported |
| --- | --- | --- |
| Allen-Zhu and Li, [*Physics of Language Models: Part 1, Learning Hierarchical Language Structures*](https://arxiv.org/abs/2305.13673), [arXiv:2305.13673](https://arxiv.org/abs/2305.13673) (TMLR 2025) | Strings from synthetic context free grammars; grammar difficulty, position encoding, and noise. | Tested GPT models learned the grammars; probes recovered parse structure; attention resembled dynamic programming. |
| Ye, Xu, Li and Allen-Zhu, [*Physics of Language Models: Part 2.1, Grade-School Math and the Hidden Reasoning Process*](https://arxiv.org/abs/2407.20311), [arXiv:2407.20311](https://arxiv.org/abs/2407.20311) (ICLR 2025) | iGSM problems from random dependency graphs with arithmetic mod 23; operation count, parameter count, and model depth. | Probes found necessary parameters before the answer was generated; depth mattered for reasoning length. |
| Ye, Xu, Li and Allen-Zhu, [*Physics of Language Models: Part 2.2, How to Learn From Mistakes on Grade-School Math Problems*](https://arxiv.org/abs/2408.16293), [arXiv:2408.16293](https://arxiv.org/abs/2408.16293) (ICLR 2025) | iGSM solutions retract an invalid next parameter with `[BACK]`; retry rate and training stage vary. | Retry data in pretraining raised accuracy at equal tokens; LoRA fine tuning did not reproduce the gain. |
| Allen-Zhu and Li, [*Physics of Language Models: Part 3.1, Knowledge Storage and Extraction*](https://arxiv.org/abs/2309.14316), [arXiv:2309.14316](https://arxiv.org/abs/2309.14316) (ICML 2024) | Biographies of 100,000 invented people; wording diversity and training schedule. | Facts memorized from one rigid wording were hard to extract by question; diverse wording helped. |
| Allen-Zhu and Li, [*Physics of Language Models: Part 3.2, Knowledge Manipulation*](https://arxiv.org/abs/2309.14402), [arXiv:2309.14402](https://arxiv.org/abs/2309.14402) (ICLR 2025) | Biographies with classification, comparison, and reverse lookup questions. | Retrieval could succeed while manipulation without a written intermediate and reverse lookup failed. |
| Allen-Zhu and Li, [*Physics of Language Models: Part 3.3, Knowledge Capacity Scaling Laws*](https://arxiv.org/abs/2404.05405), [arXiv:2404.05405](https://arxiv.org/abs/2404.05405) (ICLR 2025) | Random attribute tuples; people count, model size, exposures, and junk share. | About 2 bits of recoverable knowledge per parameter at 1000 exposures, less at 100; junk reduced it. |
| Allen-Zhu, [*Physics of Language Models: Part 4.1, Architecture Design and the Magic of Canon Layers*](https://arxiv.org/abs/2512.17351), [arXiv:2512.17351](https://arxiv.org/abs/2512.17351) (NeurIPS 2025) | Five synthetic tasks for reasoning depth, breadth, capacity, manipulation, and structure. | Canon layers increased tested reasoning depth and breadth in its comparisons. |
| Eldan and Li, [*TinyStories: How Small Can Language Models Be and Still Speak Coherent English?*](https://arxiv.org/abs/2305.07759), [arXiv:2305.07759](https://arxiv.org/abs/2305.07759) | Stories using a young child's vocabulary; story features. | Models with a few million parameters produced coherent stories on the restricted corpus. |
| Power et al., [*Grokking: Generalization Beyond Overfitting on Small Algorithmic Datasets*](https://arxiv.org/abs/2201.02177), [arXiv:2201.02177](https://arxiv.org/abs/2201.02177); Nanda et al., [*Progress measures for grokking via mechanistic interpretability*](https://arxiv.org/abs/2301.05217), [arXiv:2301.05217](https://arxiv.org/abs/2301.05217); Varma et al., [*Explaining grokking through circuit efficiency*](https://arxiv.org/abs/2309.02390), [arXiv:2309.02390](https://arxiv.org/abs/2309.02390) | Binary operation tables such as addition mod 113; training fraction and weight decay. | Test accuracy rose after training accuracy saturated; a Fourier circuit formed before that rise. |
| Liu, Ash, Goel et al., [*Transformers Learn Shortcuts to Automata*](https://arxiv.org/abs/2210.10749), [arXiv:2210.10749](https://arxiv.org/abs/2210.10749) (ICLR 2023) | State sequences from 19 automata; model depth from 1 to 16 layers. | Shallow shortcuts often failed under length or distribution shift. |
| Weiss, Goldberg and Yahav, [*Thinking Like Transformers*](https://arxiv.org/abs/2106.06981), [arXiv:2106.06981](https://arxiv.org/abs/2106.06981) | RASP programs for transformer computations. | Programs bounded the layers and heads needed for several tasks. |
| Lindner et al., [*Tracr: Compiled Transformers as a Laboratory for Interpretability*](https://arxiv.org/abs/2301.05062), [arXiv:2301.05062](https://arxiv.org/abs/2301.05062); Shaw et al., [*ALTA: Compiler-Based Analysis of Transformers*](https://arxiv.org/abs/2410.18077), [arXiv:2410.18077](https://arxiv.org/abs/2410.18077) | Programs compiled into transformer weights. | Known circuits permit interpretability tests; Tracr notes limits in realism. |
| Gupta et al., [*InterpBench: Semi-Synthetic Transformers for Evaluating Mechanistic Interpretability Techniques*](https://arxiv.org/abs/2407.14494), [arXiv:2407.14494](https://arxiv.org/abs/2407.14494) | Models trained to implement specified circuits. | Its strict training method kept intended circuits causally responsible more faithfully. |
| Zhou et al., [*What Algorithms can Transformers Learn? A Study in Length Generalization*](https://arxiv.org/abs/2310.16028), [arXiv:2310.16028](https://arxiv.org/abs/2310.16028) (ICLR 2024) | Counting, sorting, addition, and parity; training length. | Tasks with short RASP-L programs generalized to longer lengths more often. |

Follow ups using controlled generated data include:

* Zucchet et al. 2025, [*How do language models learn facts? Dynamics, curricula and hallucinations* (arXiv:2503.21676)](https://arxiv.org/abs/2503.21676): a plateau preceded recall; skewed distributions shortened it.
* Gu, Lyu, Li and Zhang 2025, [*Data Mixing Can Induce Phase Transitions in Knowledge Acquisition* (arXiv:2505.18091)](https://arxiv.org/abs/2505.18091): recall jumped across model size or mixing thresholds.
* Behnia, Deora and Thrampoulidis 2025, [*Facts in Stats: Impacts of Pretraining Diversity on Language Model Generalization* (arXiv:2510.16096)](https://arxiv.org/abs/2510.16096): context diversity delayed fact learning and sometimes enabled recall in new contexts.
* Kim et al. 2025, [*How Training Data Shapes the Use of Parametric and In-Context Knowledge in Language Models* (arXiv:2510.02370)](https://arxiv.org/abs/2510.02370); Ye, Feldman and Talwar 2026, [*Cram Less to Fit More: Training Data Pruning Improves Memorization of Facts* (arXiv:2604.08519)](https://arxiv.org/abs/2604.08519); O'Neill et al. 2026, [*Can a Language Model Learn Facts Continually in Its Weights?* (arXiv:2607.11020)](https://arxiv.org/abs/2607.11020).
* Balesni, Korbak and Evans, [*Lessons from Studying Two-Hop Latent Reasoning* (arXiv:2411.16353)](https://arxiv.org/abs/2411.16353), first posted as *The Two-Hop Curse*; Hu et al. 2025, [*Between Circuits and Chomsky: Pre-pretraining on Formal Languages Imparts Linguistic Biases* (arXiv:2502.19249)](https://arxiv.org/abs/2502.19249).
* Yao et al. 2025, [*Language models can learn implicit multi-hop reasoning, but only if they have lots of training data* (arXiv:2505.17923)](https://arxiv.org/abs/2505.17923): data needs grew exponentially with hop count in its tests, and depth needs grew with hops.
* Ye et al. 2025, [*How does Transformer Learn Implicit Reasoning?* (arXiv:2505.23653)](https://arxiv.org/abs/2505.23653); Wang et al., [*Finding the Minimal Parameter Budget for Implicit Reasoning: A Data Complexity Driven Scaling Law for Language Models* (arXiv:2504.03635)](https://arxiv.org/abs/2504.03635) (ICML 2026); Kohli et al. 2026, [*Loop, Think, & Generalize: Implicit Reasoning in Recurrent-Depth Transformers* (arXiv:2604.07822)](https://arxiv.org/abs/2604.07822); Huang et al. 2026, [*Transformers Provably Learn to Internalize Chain-of-Thought* (arXiv:2605.28600)](https://arxiv.org/abs/2605.28600).
* Wu, Kapur, Sahai and Russell 2025, [*Synthetic Error Injection Fails to Elicit Self-Correction In Language Models* (arXiv:2512.02389)](https://arxiv.org/abs/2512.02389); Wang, Alazali and Zhong 2026, [*How Does Unfaithful Reasoning Emerge from Autoregressive Training? A Study of Synthetic Experiments* (arXiv:2602.01017)](https://arxiv.org/abs/2602.01017); Puduppully et al. 2026, [*Correct Answers, Invalid Traces: What Verifiable Grade-School Math Reveals About Chain-of-Thought Traces* (arXiv:2609.38107)](https://arxiv.org/abs/2609.38107): many correct iGSM answers carried invalid traces.
* Chanin and Garriga-Alonso 2026, [*SynthSAEBench: Evaluating Sparse Autoencoders on Scalable Realistic Synthetic Data* (arXiv:2602.14687)](https://arxiv.org/abs/2602.14687); Korznikov et al. 2026, [*Sanity Checks for Sparse Autoencoders: Do SAEs Beat Random Baselines?* (arXiv:2602.14111)](https://arxiv.org/abs/2602.14111); Mueller et al. 2025, [*MIB: A Mechanistic Interpretability Benchmark* (arXiv:2504.13151)](https://arxiv.org/abs/2504.13151); Singh et al. 2025, [*Strategy Coopetition Explains the Emergence and Transience of In-Context Learning* (arXiv:2503.05631)](https://arxiv.org/abs/2503.05631).

**What Opulse adds to this method**

* **Applying stored rules.** Generated operators can be tested on inputs absent from training, separating definition recall from use.
* **Controlling the graph and its operations.** The experiment sets operator frequency, definition layer, branching, and recursion while recording composition depth per item.
* **Exact intermediate targets.** The interpreter values each subexpression and checks each rewrite. Token alignment links those values to probes and predicted patch effects.
* **Training a mechanism for a fixed computation.** Opulse fixes the computation and supplies its reference values while the model's mechanism is learned from examples.

Opulse's formal expressions do not test natural prose. Applied rule capacity overlaps the frequency and exposure cards on this page; the depth study overlaps the trace and interpretability cards. These designs add training from scratch across model sizes and measurements at saved checkpoints.

The eight designs below assume small GPT style models trained from scratch. Use several seeds per size and save checkpoints. Fix one operator library per comparison and audit training exposure before evaluation. Save checkpoints in Hugging Face format for `opulse interp` measurements. Checkpoint probes use shuffled label and untrained model controls. An external serializer builds training documents from Opulse records; evaluation inputs are split before sampling.

### How many rules can a model apply per parameter? {#applied-rules-per-parameter}

<span class="op-tag">In the style of Physics of LMs</span>

**Question.** How many generated operators can a model apply to new inputs without a definition in its prompt, at a given parameter count?

**What it would tell you.** If applied rules per parameter falls as library size or junk share grows, a team training models can test a smaller concept set or filter low value examples before adding more concepts.

<div class="op-xp">
<script type="application/json" class="op-xp-spec">
{"vary": {"knob": "Rule load", "values": ["small library", "medium library", "large library", "with junk"], "shape": "chips"}, "fixed": ["same rule generator", "same test inputs", "matched exposure"], "measure": ["new input accuracy", "rules per parameter"], "lanes": [{"name": "train", "steps": ["definitions and applications", "control exposures"]}, {"name": "test", "steps": ["no definition in prompt", "count rules on new inputs"]}]}
</script>
<script type="application/json" class="op-xp-peek">
--8<-- "docs/snippets/peeks/applied-rules-per-parameter.json"
</script>
</div>

<p class="op-hint">Click to show the setup and commands</p>

??? note "Setup, commands and measures"

    **Setup.** Train at four or more model sizes and several library seeds. Generate libraries such as `opulse operators --layers 40 30 20 10 --seed S --out ops.jsonl`, with layer counts that vary across conditions. Serialize definitions and `opulse expressions --cot none` applications at 100 and 1000 exposures per operator. Split each operator's inputs before sampling. Run junk comparisons at equal total tokens and at equal useful exposures; in the junk arms, seven eighths of tokens come from additional operators outside the evaluated set, each seen only a few times. Audit definition, surface, and transitive exposure separately. Test without definitions, then test new compositions. Probe rule identity and component values at checkpoints.

    **Measure.** Correct applications on held out inputs per parameter, by definition size, kind, layer, exposure, and junk arm. This is a rule count; a bits per parameter estimate would require a rule family with known entropy.

    **Why Opulse.** Library size, exposure, and test inputs can be set separately. The interpreter grades rule application on inputs absent from training.

    **Sources.** [Allen-Zhu and Li, arXiv:2404.05405](https://arxiv.org/abs/2404.05405); [Wang et al., arXiv:2504.03635](https://arxiv.org/abs/2504.03635); [Ye, Feldman and Talwar, arXiv:2604.08519](https://arxiv.org/abs/2604.08519).

### Can a model use a rule it has only read? {#read-only-rules}

<span class="op-tag">In the style of Physics of LMs</span>

**Question.** If an operator appears in training only as definition text, can a model apply it later without the definition in its prompt?

**What it would tell you.** If read only definitions work only with varied renderings, a team training models can vary how each concept is stated. If applications are necessary, the team can include worked uses of each concept.

<div class="op-xp">
<script type="application/json" class="op-xp-spec">
{"vary": {"knob": "Rule presentation", "values": ["one wording", "varied wording", "worked uses"], "shape": "chips"}, "fixed": ["same B rules", "same token budget", "same test inputs"], "measure": ["definition recall", "new input accuracy"], "lanes": [{"name": "read only", "steps": ["show B rules", "test B uses"]}, {"name": "applications", "steps": ["show B uses", "test B uses"]}]}
</script>
<script type="application/json" class="op-xp-peek">
--8<-- "docs/snippets/peeks/read-only-rules.json"
</script>
</div>

<p class="op-hint">Click to show the setup and commands</p>

??? note "Setup, commands and measures"

    **Setup.** Divide the library into A and B by dependency closure so no A operator calls B. A appears as definitions and applications. B appears only as definitions. Audit all B appearances. An external serializer varies names and ordering in B training documents; `opulse bench build --naming symbols` and `--shuffle` change benchmark prompts only. Compare one versus several B renderings and mixed versus definitions first schedules. Test B on held out inputs with `opulse bench build --context none`, then with `--context full`. Probe B definition content and application values at checkpoints.

    **Measure.** B definition recall, B application accuracy with and without context, and the recall to application gap by rendering and schedule.

    **Why Opulse.** Each B definition's presentation and exposure can be audited, and the interpreter checks new applications.

    **Sources.** [Allen-Zhu and Li, arXiv:2309.14316](https://arxiv.org/abs/2309.14316); [Behnia, Deora and Thrampoulidis, arXiv:2510.16096](https://arxiv.org/abs/2510.16096); [O'Neill et al., arXiv:2607.11020](https://arxiv.org/abs/2607.11020).

### Can a model manipulate a rule it can apply? {#manipulate-rules}

<span class="op-tag">In the style of Physics of LMs</span>

**Question.** Once a model applies an operator correctly, can it classify, compare, and invert results of that operator?

**What it would tell you.** If derived questions fail without a written intermediate, a team training models can add intermediate steps or train those question types directly. If inverse lookup fails, the team can add inverse uses.

<div class="op-xp">
<script type="application/json" class="op-xp-spec">
{"vary": {"knob": "Question type", "values": ["forward", "classify", "compare", "inverse"], "shape": "chips"}, "fixed": ["same stored rules", "same input range", "unique inverse"], "measure": ["answer accuracy", "intermediate probe"], "lanes": [{"name": "direct", "steps": ["ask question", "answer"]}, {"name": "written", "steps": ["write value", "answer"]}]}
</script>
<script type="application/json" class="op-xp-peek">
--8<-- "docs/snippets/peeks/manipulate-rules.json"
</script>
</div>
<p class="op-hint">Click to show the setup and commands</p>

??? note "Setup, commands and measures"

    **Setup.** Train on forward applications from a library whose operators have distinct functions on the test domain. Ask for a forward value, a property such as parity or sign, a comparison of two values, and a unique inverse in a stated range. Build inverse tasks with `opulse bench build --family hole`, parse each expression to locate `x`, and keep tasks where it is a direct argument of one operator. Ask each question with and without a written intermediate. Probe the intermediate at the answer position.

    **Measure.** Accuracy by question type and intermediate condition; probe accuracy for the intermediate value.

    **Why Opulse.** The same stored rules supply all question types. The hole solver checks uniqueness in the stated range.

    **Sources.** [Allen-Zhu and Li, *Physics of Language Models: Part 3.2, Knowledge Manipulation*, arXiv:2309.14402](https://arxiv.org/abs/2309.14402); [Berglund et al., *The Reversal Curse: LLMs trained on "A is B" fail to learn "B is A"*, arXiv:2309.12288](https://arxiv.org/abs/2309.12288).

### Does a model precompute values before a question? {#precompute}

<span class="op-tag">In the style of Physics of LMs</span>

**Question.** When several named subexpressions precede a question, which values can be detected before the model knows which one it must answer?

**What it would tell you.** If values appear before the question only after question first training, a team training models can test whether the order of questions and source material changes later answer accuracy.

<div class="op-xp">
<script type="application/json" class="op-xp-spec">
{"vary": {"knob": "Prompt order", "values": ["bindings first", "question first", "mixed order"], "shape": "chips"}, "fixed": ["same bindings", "same asked name", "same model size"], "measure": ["value probe", "answer accuracy"], "lanes": [{"name": "bindings first", "steps": ["give bindings", "probe values", "ask question"]}, {"name": "question first", "steps": ["ask question", "give bindings", "probe values"]}]}
</script>
<script type="application/json" class="op-xp-peek">
--8<-- "docs/snippets/peeks/precompute.json"
</script>
</div>
<p class="op-hint">Click to show the setup and commands</p>

??? note "Setup, commands and measures"

    **Setup.** An external prompt builder lists bindings such as `a = 3 ◆₁ 5`, `b = a ●₂ 2`, and `c = 4 ◆₁ 1`, then randomly asks about one name after an identical prefix. Compare with a question first training arm. Use interpreter values and dependencies as labels. Extend token alignment to binding positions before using `opulse interp collect` and `opulse interp probe`; the compute task alignment does not cover this binding format.

    **Measure.** Before the question, probe every binding's value and dependency against input only controls. After the question, probe needed values. Extend patch targeting to binding spans and compare changes with interpreter predicted answers.

    **Why Opulse.** The interpreter provides exact values and a dependency graph for needed and unneeded bindings.

    **Sources.** [Ye, Xu, Li and Allen-Zhu, arXiv:2407.20311](https://arxiv.org/abs/2407.20311); [Pal et al., *Future Lens: Anticipating Subsequent Tokens from a Single Hidden State*, arXiv:2311.04897](https://arxiv.org/abs/2311.04897); [Yang et al., *Internal Chain-of-Thought: Empirical Evidence for Layer-wise Subtask Scheduling in LLMs*, arXiv:2505.14530](https://arxiv.org/abs/2505.14530).

### How does composition depth relate to model depth? {#depth-vs-layers}

<span class="op-tag">In the style of Physics of LMs</span>

**Question.** How much measured composition depth can a model compute without a written trace as its layer count changes?

**What it would tell you.** If accuracy falls beyond a measured depth, a team training models can test written traces or more inference tokens there. If deeper models extend that range at equal parameters, the team can compare the added compute cost with the gain.

<div class="op-xp">
<script type="application/json" class="op-xp-spec">
{"vary": {"knob": "Model layers", "values": ["4 layers", "8 layers", "16 layers", "32 layers"], "shape": "stack"}, "fixed": ["matched parameters", "matched rewrite count", "same test pool"], "measure": ["accuracy by depth", "first decodable layer"], "lanes": [{"name": "train", "steps": ["fixed library", "save checkpoints"]}, {"name": "test", "steps": ["deeper problems", "no trace"]}]}
</script>
<script type="application/json" class="op-xp-peek">
--8<-- "docs/snippets/peeks/depth-vs-layers.json"
</script>
</div>
<p class="op-hint">Click to show the setup and commands</p>

??? note "Setup, commands and measures"

    **Setup.** Train models with 4, 8, 16, and 32 layers at matched parameter counts. Record training and inference FLOPs. Match rewrite count and answer range as far as generation permits while varying measured dependency depth from 1 to D. Test at D+1 and D+2, then test whether a trace restores accuracy. For recursion, set `recursion.style: direct` and a `recursion.direct_bound` covering train and test inputs; train through U unfoldings and test U+1 and U+2. Probe the first model layer that carries each subexpression value.

    **Measure.** Answer accuracy without a trace by composition depth and model layers; first decodable layer by subexpression depth; accuracy on longer unfoldings. A layer to computation step correlation alone would not prove a fixed number of layers per step.

    **Why Opulse.** Each item has measured composition depth, recursion count, and exact intermediate values.

    **Sources.** [Liu, Ash, Goel et al., arXiv:2210.10749](https://arxiv.org/abs/2210.10749); [Allen-Zhu, arXiv:2512.17351](https://arxiv.org/abs/2512.17351); [Yao et al., arXiv:2505.17923](https://arxiv.org/abs/2505.17923); [Kohli et al., arXiv:2604.07822](https://arxiv.org/abs/2604.07822).

### Do corrected mistakes in derivations help? {#corrected-mistakes}

<span class="op-tag">In the style of Physics of LMs</span>

**Question.** Which verified error and correction examples, if any, change later rule use?

**What it would tell you.** If corrections help at equal tokens, a team training models can add the successful error type and stage to a concept corpus. If only the model's own errors help, the team can generate corrections from its checkpoints.

<div class="op-xp">
<script type="application/json" class="op-xp-spec">
{"vary": {"knob": "Correction examples", "values": ["none", "invalid rewrite", "unready step", "false retraction"], "shape": "chips"}, "fixed": ["same token budget", "same rule library", "same clean traces"], "measure": ["fresh rule accuracy", "retraction quality"], "lanes": [{"name": "clean", "steps": ["valid trace", "continue"]}, {"name": "corrected", "steps": ["inject error", "retract", "continue"]}]}
</script>
<script type="application/json" class="op-xp-peek">
--8<-- "docs/snippets/peeks/corrected-mistakes.json"
</script>
</div>
<p class="op-hint">Click to show the setup and commands</p>

??? note "Setup, commands and measures"

    **Setup.** Start with `opulse expressions --cot en` traces. Compare an unready next subexpression, an invalid rewrite, and a retraction marker without a real error. Follow each injected error with a marker and the correct continuation. Compare simple mutations with the model's own errors. Use retry rates 0, 0.05, 0.2, and 0.5 at equal tokens in pretraining, LoRA fine tuning, and full fine tuning, each against clean traces. An external parser splits responses at retractions and passes each segment to the step checker, which otherwise stops at the first invalid rewrite. Probe whether an attempted step is represented as unready.

    **Measure.** Final accuracy on a fresh library, retraction rate, and shares of retractions after invalid and valid lines.

    **Why Opulse.** The step checker identifies the first invalid rewrite, so an injected error and its correction can be graded.

    **Sources.** [Ye, Xu, Li and Allen-Zhu, arXiv:2408.16293](https://arxiv.org/abs/2408.16293); [Wu, Kapur, Sahai and Russell, arXiv:2512.02389](https://arxiv.org/abs/2512.02389); [Puduppully et al., arXiv:2609.38107](https://arxiv.org/abs/2609.38107).

### Does delayed generalization occur for composed operators? {#delayed-generalization}

<span class="op-tag">In the style of Physics of LMs</span>

**Question.** After fitting training pairs, can a model later apply a composed operator to held out inputs without a trace?

**What it would tell you.** If held out accuracy rises only after a period of training beyond training accuracy saturation, a team training models can test whether longer practice on a fixed concept set is worth its compute cost. If component representations change first, the team can test those representations as early indicators.

<div class="op-xp">
<script type="application/json" class="op-xp-spec">
{"vary": {"knob": "Training coverage", "values": ["25% pairs", "50% pairs", "75% pairs"], "shape": "bars"}, "fixed": ["same finite grid", "same rule library", "saved checkpoints"], "measure": ["held out accuracy", "steps from training fit to held out target"]}
</script>
<script type="application/json" class="op-xp-peek">
--8<-- "docs/snippets/peeks/delayed-generalization.json"
</script>
</div>
<p class="op-hint">Click to show the setup and commands</p>

??? note "Setup, commands and measures"

    **Setup.** Train on answer only data well past training accuracy saturation. Use a fixed library with a finite input grid, such as 0 through 30. Check for operator collisions on the grid. Split exact input pairs before sampling: use 25, 50, or 75 percent of each composed operator's pairs for training. Audit indirect exposure of held out pairs and vary weight decay. Track new compositions and held out pairs across checkpoints with memorization and algorithmic baselines. Probe component values; a component selecting extension is needed for targeted `opulse interp patch` tests.

    **Measure.** Training steps between saturation and held out success by training fraction and composition depth; the first checkpoint with decodable component values; patch effects where a component selecting patch exists. Decodability alone would not establish that a concept became one internal step; that claim would require predicted patch effects.

    **Why Opulse.** Exact pair splits and depth labels make delayed rule application measurable. Interpreter values provide probe and patch targets.

    **Sources.** [Power et al., arXiv:2201.02177](https://arxiv.org/abs/2201.02177); [Nanda et al., arXiv:2301.05217](https://arxiv.org/abs/2301.05217); [Wang et al., *Grokked Transformers are Implicit Reasoners: A Mechanistic Journey to the Edge of Generalization*, arXiv:2405.15071](https://arxiv.org/abs/2405.15071); [Huang et al., arXiv:2605.28600](https://arxiv.org/abs/2605.28600).

### Can a model discover better definitions? {#discover}

**Question.** Given operator definitions, can a model write an equivalent definition with fewer base evaluations, or refactor several definitions into a shorter reusable library?

**What it would tell you.** If models find valid definitions that score above the stored reference, a team training models can test these tasks as reinforcement learning environments for invention with exact checks. If gains transfer to unseen operator sets, the team can test whether learned search procedures generalize.

<div class="op-xp">
<script type="application/json" class="op-xp-spec">
{"vary": {"knob": "Definition search", "values": ["original", "faster rule", "shared helper", "refactored set"], "shape": "chips"}, "fixed": ["same input list", "same equivalence check", "same cost metric"], "measure": ["valid candidates", "evaluation savings"], "lanes": [{"name": "faster", "steps": ["propose rule", "check equivalence", "count calls"]}, {"name": "refactor", "steps": ["propose library", "check functions", "count calls"]}]}
</script>
</div>
<p class="op-hint">Click to show the setup and commands</p>

??? note "Setup, commands and measures"

    **Setup.** Build tasks with `opulse bench build --operators ops.jsonl --out faster.jsonl --family faster --count 100`, and the same command with `--family refactor`. A faster task gives one definition and asks for an equivalent one that evaluates fewer base operations on a stated input list. A refactor task gives several definitions and asks for a library, fresh helpers allowed, that computes the same functions with fewer applications in total. Run a model with `opulse bench run` and grade with `opulse bench score`. For an iterative search, `opulse discover --operators ops.jsonl --problems problems.txt --record discovery.jsonl --model MODEL --metric usefulness` asks a model for proposals round after round, admits only proposals that strictly improve the metric, and records each decision; `--replay` rechecks a saved record.

    **Measure.** A candidate counts as equivalent over the configured domain only when the solver proves it; otherwise report its agreement and cost on the stated finite range. Report valid candidates, the score relative to the reference definition, the share of candidates that beat the reference, and the strength of the equivalence check behind each.

    **Why Opulse.** Interpreter counts compare evaluation cost exactly. A solver proof, where the fragment allows one, or a complete check on a stated finite range separates a real improvement from a shorter text that computes a different function on that range.

    **Sources.** [Benchmarking models](guide/benchmark.md). [Discovering better definitions](guide/discovery.md).

## Across worlds {#across-worlds}

A world uses strings, lists, bits or integers to realize the same composition grammar. A definition's tree can stay fixed while its atoms and value types change, so these cards ask what composition learned in one world carries to another. The [Worlds page](worlds/index.md#what-the-worlds-are-for) gives the full design. Each comparison would name its correspondence grade: G1 confirms matching signatures only; G2 also requires the listed equations; G3 requires a bijection that commutes with every paired atom on the declared finite domains. Surface forms need separate comparison.

### Does a composition tree learned in one world help in another? {#same-tree-other-world}

**Question.** If a model practises composition trees in one world, does it need fewer examples to compose the same trees in a second world whose atoms it already knows?

**What it would tell you.** If training data built from the same trees in a source world reduces the target examples needed, a team could supplement scarce target data with cheaper source data. G3 establishes correspondence on the declared finite domains; compare tokenization and prompt form separately. G1 makes no claim about behavioral similarity.

<div class="op-xp">
<script type="application/json" class="op-xp-spec">
{"vary": {"knob": "Source tree exposure", "values": ["same trees, source world", "unrelated trees, source world", "no source trees"], "shape": "chips"}, "fixed": ["identical target atom practice", "identical target fine tuning", "same total token budget", "same skeleton split", "grade recorded"], "measure": ["target world accuracy", "target examples to fixed accuracy", "first wrong step"], "arrow": {"from": "strings trees", "to": "lists trees", "label": "same skeleton"}}
</script>
<script type="application/json" class="op-xp-peek">
--8<-- "docs/snippets/peeks/same-tree-other-world.json"
</script>
</div>

<p class="op-hint">Click to show the setup and commands</p>

??? note "Setup, commands and measures"

    **Setup.** Extract skeletons with `opulse skeleton extract --operators source.jsonl --out skeletons.json`, then fill them in two worlds with `opulse skeleton match --skeletons skeletons.json --world NAME=ATOMS_JSONL --world NAME2=ATOMS2_JSONL --out-dir matched`. Use `--type-maps` when the worlds use different value types. `--grade-domains` and `--equations` test G2 and G3; `--nan-tolerance` and `--length-tolerance` match undefined rates and unfolded lengths. Split matched tasks with `opulse bench split --tasks matched_tasks.jsonl --out-dir split --by skeleton` and check overlap with `opulse bench leakage --train-tasks split/train.jsonl --test-tasks split/test.jsonl`. Give every arm identical target atom practice and target fine tuning at each target data amount; vary source tree exposure while matching total tokens. Use unrelated training records to fill the budget in the arm without source trees.

    **Measure.** Target accuracy minus the unrelated trees arm, by grade, with intervals over skeletons and seeds; target examples needed to reach a fixed accuracy.

    **Why Opulse.** One skeleton is filled in two worlds with a recorded grade and matched probes, so the tree is held fixed while the material changes.

### Which material best teaches composition before pretraining? {#warm-up-material}

**Question.** With matched trees and warm up tokens, which world reduces the total tokens needed to reach a fixed held out loss? Does any saving depend on tree depth or material?

**What it would tell you.** If one material saves more tokens at matched depth, a team could generate its warm up data in that material. If only the deep tree arms save tokens, depth would matter more than material. Either answer would cover only the worlds and the pretraining mix tested.

<div class="op-xp">
<script type="application/json" class="op-xp-spec">
{"vary": {"knob": "Warm up world and depth", "values": ["strings deep", "strings shallow", "lists deep", "lists shallow", "no warm up"], "shape": "chips"}, "fixed": ["matched skeletons within depth", "same warm up tokens", "same total token ceiling", "same pretraining stream"], "measure": ["total tokens to a fixed held out loss, including warm up", "held out text and code loss"], "lanes": [{"name": "each arm", "steps": ["warm up", "pretrain on text and code", "evaluate"]}]}
</script>
</div>

<p class="op-hint">Click to show the setup and commands</p>

??? note "Setup, commands and measures"

    **Setup.** Fill matched deep and shallow skeleton sets in each world with `opulse skeleton match`, then write a warm up corpus for each world and depth with `opulse corpus --operators strings=strings.jsonl --out warmup_strings`. Match the resulting token counts, rather than only `--documents`; a shallow arm in each world uses `--max-layer 0`. Warm up tokens count within the fixed total budget. Run the same pretraining stream after each warm up, and repeat across at least two serializations.

    **Measure.** Total tokens to reach a fixed loss on held out text and code, including warm up tokens.

    **Why Opulse.** The same trees exist in several materials, so material and depth can be varied separately.

### At a fixed budget, one world or several? {#world-variety}

**Question.** Does spreading one token budget over several worlds beat spending it on one world at matched tree variety?

**What it would tell you.** If the mixture beats single world arms at matched tree variety and target atom practice, another world could be worth generating. A separate low and high tree variety comparison would test how much the skeleton distribution matters.

<div class="op-xp">
<script type="application/json" class="op-xp-spec">
{"vary": {"knob": "Worlds sharing the budget", "values": ["1 world", "2 worlds", "4 worlds"], "shape": "bars"}, "fixed": ["same total tokens", "matched skeleton distribution for world count comparison", "same test world", "matched test world atom practice"], "measure": ["held out tree accuracy", "unseen composition accuracy"], "lanes": [{"name": "tree variety control", "steps": ["one world", "low versus high skeleton variety"]}, {"name": "notation control", "steps": ["one world", "new notations"]}]}
</script>
<script type="application/json" class="op-xp-peek">
--8<-- "docs/snippets/peeks/world-variety.json"
</script>
</div>

<p class="op-hint">Click to show the setup and commands</p>

??? note "Setup, commands and measures"

    **Setup.** Build a mixed task stream with `opulse bench build --world strings=strings.jsonl --world lists=lists.jsonl --world-mix strings:0.5,lists:0.5 --out mixed_tasks.jsonl`, and a mixed corpus with `opulse corpus --operators strings=strings.jsonl --operators lists=lists.jsonl --world-mix strings:0.5,lists:0.5 --out mixed_corpus`. A `--world-settings` file holds `skeleton_weights` per world; match that distribution for the world count comparison, then compare low and high skeleton variety within one world. Hold one world out of composition training for testing, but give every arm identical practice on its atoms so an accuracy change can be linked to composition.

    **Measure.** Accuracy on held out trees and on new compositions in the test world for each arm and both controls.

    **Why Opulse.** Each task records its world and skeleton, so the number of worlds can change while the trees stay fixed.

### Does a learned step checker hold up in a new material? {#step-checker-new-world}

**Question.** Train a process verifier on steps checked by the exact step checker in some worlds. Would it agree with the exact step checker in a held out world, on fixed solutions and solutions sampled during RL?

**What it would tell you.** If false approvals grow during RL in the held out world, a team could keep exact step checks in each tested world. High agreement would support testing the process verifier in further domains.

<div class="op-xp">
<script type="application/json" class="op-xp-spec">
{"vary": {"knob": "Held out world", "values": ["integer", "bits", "strings", "lists"], "shape": "chips"}, "fixed": ["same step format", "same process verifier", "exact label on each scored step"], "measure": ["agreement with exact step checker", "false approvals during RL"], "lanes": [{"name": "train", "steps": ["steps from other worlds", "fit process verifier"]}, {"name": "test", "steps": ["held out world", "compare with exact step checker"]}]}
</script>
<script type="application/json" class="op-xp-peek">
--8<-- "docs/snippets/peeks/step-checker-new-world.json"
</script>
</div>

<p class="op-hint">Click to show the setup and commands</p>

??? note "Setup, commands and measures"

    **Setup.** Build step tasks with `opulse bench build --format steps` in each world, using `opulse operators --preset` for the atoms. Score responses with `opulse bench score --operators`, which grades each step line and reports the first wrong one. Train the verifier on labels from all worlds but one, then run RL against it in the held out world while the exact checker scores the same samples.

    **Measure.** Agreement with the checker on fixed solutions, false approvals and false rejections during RL, and the gap between learned and exact reward over training.

    **Why Opulse.** Each scored step has an exact label, so judgments in the held out world can be checked.

## Inside the weights {#inside-weights}

Opulse can compile an operator into a network whose weights compute its definition exactly on a finite range, with a named slot for every input, intermediate value and output. These two designs use such networks to ask what a trained model does with the same computation. Neither has been run. The [Stitching page](stitching/index.md#two-follow-up-experiments) explains how operators become weights and lists both designs; the [handwired language model guide](guide/handwired.md) gives the commands.

### Can a new concept be written into a pretrained LLM with its weights frozen? {#write-concept}

**Question.** A compiled network computes ◆₁ exactly. The token reader gets its operand from token IDs; the probe reader fits an adapter to the residual stream. A write adapter adds the result at the final prompt token without updating the pretrained model's weights. Would the model answer `◆₁ 5 =` and `Compute ( ◆₁ 5 ) + 1 =`?

**What it would tell you.** If both forms improve on held out prompts relative to no injection while shuffled slot controls fail, the inserted signal may affect both answers; a separate control would still need to isolate composition. If only direct answer accuracy improves, the value may not be used in the longer calculation. If the read value and compiled result are correct but the answer is wrong, inspect the write adapter and later layers.

<div class="op-xp">
<script type="application/json" class="op-xp-spec">
{"vary": {"knob": "Adapter setting", "values": ["token reader", "probe reader", "unembedding writer", "linear writer"], "shape": "chips"}, "fixed": ["frozen model weights", "same compiled ◆₁", "same prompts"], "measure": ["direct answer accuracy", "accuracy inside longer expressions", "reader accuracy"], "lanes": [{"name": "inject", "steps": ["read operand", "compiled ◆₁", "write to residual"]}, {"name": "control", "steps": ["shuffled slots", "same prompts"]}]}
</script>
<script type="application/json" class="op-xp-peek">
--8<-- "docs/snippets/peeks/write-concept.json"
</script>
</div>

<p class="op-hint">Click to show the setup and commands</p>

??? note "Setup, commands and measures"

    **Setup.** `python examples/handwired/inject.py` compiles `a ◆₁ = { (a % 3) + 1 }` and injects it at the final prompt token. Its token reader uses token IDs; its probe reader fits an adapter on residual states. The unembedding and linear writers select the write path; the linear writer fits an adapter. Set the read layer, write layer and injection strength, then select a locally cached model. <!-- needs: compile, handwired --> Compare each setting with the same prompts without injection, with shuffled slot mappings, and on prompts the adapters were not fitted on. Add a control that distinguishes use in composition from an effect on the final answer.

    **Measure.** Answer accuracy and answer log probability on direct prompts and on longer expressions, reader accuracy, and the compiled value, recorded separately so reading, computing and writing errors can be told apart.

    **Why Opulse.** The compiled network and the interpreter give the exact answer for every prompt, so a wrong answer can be traced to one stage.

### Does gradient descent find the compiled solution? {#compiled-solution}

**Question.** Train a small transformer from scratch on ◆₁ prompts. First check whether it reproduces the compiled network's table; if so, compare intermediate values, their order and the effect of activation patches.

**What it would tell you.** Agreement among probes, layer alignment and patches, with slot specific interventions and controls for alternative computations, would support shared, causally relevant intermediate information. It would not establish that training found the compiled mechanism. If answers are right but these values have no detected causal effect, another computation remains possible; probes could also miss present values.

<div class="op-xp">
<script type="application/json" class="op-xp-spec">
{"vary": {"knob": "Training run", "values": ["seed", "model depth", "training steps"], "shape": "chips"}, "fixed": ["same operator", "same row split", "same character vocabulary"], "measure": ["slot probe accuracy by layer", "patch margin shift", "CKA with compiled layers"], "arrow": {"from": "compiled network", "to": "trained network", "label": "compare slot by slot"}}
</script>
<script type="application/json" class="op-xp-peek">
--8<-- "docs/snippets/peeks/compiled-solution.json"
</script>
</div>

<p class="op-hint">Click to show the setup and commands</p>

??? note "Setup, commands and measures"

    **Setup.** `python examples/handwired/train_small.py` would train a GPT2 style model on CPU. Its settings cover model layers, hidden width, attention heads, training steps and seed. A definitions file and symbol list could train several operators together. `python examples/handwired/report.py` would write the probe, alignment, CKA and patching report. <!-- needs: compile, handwired --> A study would need several seeds, enough steps to fit the table, controls for answer frequency and prompt form, and interventions that target one slot while testing alternative computations.

    **Measure.** Held out answer accuracy, probe accuracy for each compiled slot at each layer, the layer that best decodes each slot next to the compiled layer that writes it, and patch margin shifts toward the interpreter's counterfactual answer.

    **Why Opulse.** Reference answers and compiled slot values would allow a trained model to be compared with a known solution slot by slot. The data peek below shows the operand split and interpreter answers, not slot labels or a trained network.

## Propose an experiment {#propose}

Propose your own experiment idea at [GitHub Discussions](https://github.com/mkj69/opulse/discussions) or as an [issue](https://github.com/mkj69/opulse/issues). You can also say which experiment on this page you would like to see run.

If you run one of these designs, please share the setup and what you found, including a result with no gain; it tells others as much as a positive one. [Join us](contribute.md) lists the ways to take part and how each contribution is credited.
