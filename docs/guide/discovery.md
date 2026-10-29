# Discovering better definitions

Opulse measures four properties of definitions. A candidate that replaces an operator is checked for equal behavior before its measured improvement can be accepted. A solver proof is reported as `proved`. When a proof is unavailable, a complete finite input check is labelled `checked on range [lo, hi]`.

**Size** counts operator applications in every branch body and condition. This is the count used by `simplify`.

**Cost** sums base operation evaluations reported by the reference interpreter on a recorded list of inputs. Repeated inputs are counted repeatedly.

**Usefulness** counts syntax tree nodes in a problem family after the deterministic `invent` rewrite. At each node the rewriter chooses the matching definition with the largest positive saving.

**Library size** sums the sizes of all definitions in the proposed operator set.

The input list is part of every cost task or discovery record. Cost describes that list, so another input distribution can give a different ordering.

## Benchmark families

`simplify` asks for an equal definition within an operation budget. Its report includes a score above 1, `beats_reference: true`, and a positive margin when a valid answer uses fewer operations than the stored reference.

`invent` asks for definitions that shorten several expressions. Its score is the saving divided by the hidden definition's saving. The report includes `beats_reference` and the extra number of saved nodes. It also reports equivalence to hidden definitions separately, since a useful new definition need not be the hidden one.

`faster` asks for an equal definition that uses fewer base operation evaluations on the task's input list. The grader checks equality and obtains cost from the interpreter counter. For example, removing `+ 0` from a body reduces its measured cost by one for each input.

`refactor` asks for replacements for every original operator in a small set. A submission may introduce helper operators. The grader checks each original symbol against its replacement and counts the original symbols and every proposed helper; fixed prerequisite definitions are context. For example, two copies of a body with three applications can share one helper body and use one helper call in each original definition.

Build any of these families with `opulse bench build` and select the family name. `opulse bench check` derives its reference from the prompt, `opulse bench score` grades responses, and `opulse bench export` writes the same grading data for reinforcement learning.

## Discovery loop

`opulse discover` reads an operator file and one problem expression per line. It accepts either a JSONL script of proposals or an OpenAI compatible chat endpoint. The endpoint uses `OPENAI_API_KEY` when that environment variable is set. The `usefulness`, `size`, `cost`, and `library_size` metrics choose which strict improvement is accepted. The `size` and `cost` metrics need a target operator. Cost also needs a JSON input list. Accepted definitions join the library shown in later rounds. Run `opulse discover` with `help` to see the file and endpoint options.

This output came from a two round scripted CLI run on the shipped integer atoms. The problems were `5 + 1` and `7 + 1`. The first proposal was `a ☆ = { a + 1 }`; the second was `a ★ = { a + 1 }`. The second proposal saved no further nodes.

```json
{
  "rounds": 2,
  "accepted": 1,
  "metric": "usefulness",
  "initial_value": 6,
  "final_value": 4,
  "library": [
    "a ☆ = { a + 1 }"
  ],
  "record": "/tmp/w37_cli_record_6.jsonl"
}
```

Replay of that record returned the same summary. Use the replay option of `opulse discover` with the record and original operator file to verify each accepted proposal again.

Each JSONL record starts with the number of rounds, initial definitions, problems, chosen metric, input list, checked range, base atom fingerprint, semantics, notation, and a hash. Each later line records a round, proposer name, proposed definition, optional replacement target, metric before and after, acceptance, equivalence verdict and strength, the numbers of problems that became shorter, and hashes linking it to the preceding line. Replay checks the hashes, compares the initial definitions and base atoms with the supplied operator file, recomputes each row, and raises an error if a recorded decision or measurement differs.

Recursive equality often cannot be proved by the solver. In that case a finite range check supports only the stated range. The metric does not measure whether a definition is easier for a human to understand.
