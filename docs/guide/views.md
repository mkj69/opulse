# Views of a definition

One parsed definition supplies six views. The symbolic, formula, code, and prose views state the
rule. Each of those views parses back to the same definition tree after numeral bases are
normalized. The examples view contains
values computed by the reference interpreter. The summary reports proved facts and labels
observations as observations.

Generate a small integer operator set and print the six views of one operator:

```bash
opulse operators --set integer --layers 2 1 --seed 4 --out integer_ops.jsonl
opulse describe --operators integer_ops.jsonl --view all --symbol '♧₁'
```

The snippets below come from another generated operator. Run `python tools/docs_views.py`
to regenerate them. Its symbol depends on the generation seed.

## Symbolic

--8<-- "docs/snippets/views_symbolic.md"

## Formula

--8<-- "docs/snippets/views_formula.md"

## Python code

--8<-- "docs/snippets/views_code.md"

The code view can be executed and compared with the reference interpreter at boundary values
and sampled inputs through `Views.check_code`.

## Controlled prose

English:

--8<-- "docs/snippets/views_prose_en.md"

Each case is tried in order. A seeded choice changes the wording while preserving the parsed
definition. For example, the same branch definition has these English realizations:

--8<-- "docs/snippets/views_branch_symbolic.md"

--8<-- "docs/snippets/views_paraphrases.md"

## Examples

--8<-- "docs/snippets/views_examples.md"

Each table entry comes from the reference interpreter. The generator searches for inputs that
reach each case and lists any case for which it found no input.

## Summary

--8<-- "docs/snippets/views_summary.md"

A closed form appears only when the candidate is proved equivalent. Algebraic properties are
shown with their proof status. An observed range is identified as observed.

## Parse back

`Views.round_trip` renders a definition view, parses it, and compares its normalized syntax tree
with the original. For code, it also runs the function against the reference interpreter.

--8<-- "docs/snippets/views_round_trip.md"

## Benchmark prompts

`opulse bench build --definition-format` accepts `symbolic`, `prose`, `code`, `latex`,
`examples`, and `mixed`. The default symbolic output retains the existing record format.
The prompt check parses prose, code, and formula blocks back into definitions before computing
the answer. An examples prompt is checked by recomputing every table entry.

This generated task shows a prose definition:

--8<-- "docs/snippets/views_prompt.md"

The generated task file passes `opulse bench check`:

--8<-- "docs/snippets/views_prompt_check.md"
