# Interpretability with exact values

`opulse interp` uses full context compute tasks and a locally cached Hugging Face causal model. Install its dependencies with `pip install "opulse[interp]"`. If you installed from a clone, use `pip install -e ".[interp]"`. Importing `opulse` does not load those packages.

## Collect residual states

```bash
# requires: opulse[interp]
opulse operators --out ops.jsonl --layers 2 1
opulse bench build --operators ops.jsonl --out tasks.jsonl --count 3 --max-answer-share 1
opulse interp collect --model Qwen/Qwen2.5-0.5B --tasks tasks.jsonl --operators ops.jsonl --layers 0,4,8 --device cpu --out interp_states
```

This command saves one residual vector per selected layer at the last token overlapping each subexpression and at the last prompt token. `interp_states/activations.npz` contains an array with shape `(observations, layers, hidden_size)`. `interp_states/metadata.jsonl` records token and character spans, exact values, operator symbols, expression depth, operator layer, and reduction steps inside defined operators. Token spans include all tokens that overlap a subexpression.

## Fit probes

```bash
# requires: opulse[interp]
opulse interp probe --activations interp_states --bins=-10,0,10 --out probe.json
```

This command fits a linear ridge classifier over four value bins and a linear ridge regressor. It holds out complete operators for testing and reports bin accuracy and mean absolute error for each layer and expression depth. Undefined values are excluded from fitting and scoring. The bin boundaries in this example are negative ten, zero, and ten.

```bash
# requires: opulse[interp]
opulse interp probe --activations interp_states --site reduction_step --bins=-10,0,10 --out reduction_probe.json
```

This command probes values produced inside unfolded definitions at the token position of the source operator call. The depth for these rows includes the reducer unfolding depth.

## Patch one argument

```bash
# requires: opulse[interp]
opulse interp patch --model Qwen/Qwen2.5-0.5B --tasks tasks.jsonl --operators ops.jsonl --layers 0,4,8 --device cpu --out interp_patches
```

This command changes one numeric argument in each usable task and computes the new intermediate value and final answer from the prompt definitions. It copies the counterfactual residual state at the changed subexpression into the clean run. It adds an `Answer:` cue after the prompt and records the log likelihood margin between the complete counterfactual answer and the original answer before and after each patch. A patch counts as moving to the predicted answer when its margin becomes positive and increases. `interp_patches/patches.jsonl` contains each comparison and `interp_patches/summary.json` groups the fraction by layer and token position.

The Python functions `align_task`, `collect`, `probe`, `counterfactual`, and `patch` are in `opulse.integrations.nnsight`. `align_task` accepts a task record, an operator registry, settings, and a fast tokenizer. Its output includes one record for each node in the source expression.
