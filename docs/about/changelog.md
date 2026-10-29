# Changelog

## Unreleased

* `opulse bench`: tasks that give a model exactly the definitions it needs (`build`), a resumable
  client for OpenAI-compatible servers (`run`), exact grading with a breakdown by difficulty axis
  (`score`), RL records and a verl reward function (`export`, `opulse.bench.reward`), and a check
  that a test operator set shares no concept with a training set (`leakage`).
* Controlled ablations: definitions removed, operators renamed to pseudo-words or English words,
  distractor definitions, shuffled order; sets built with the same seed are paired problem by problem.
* Step-format tasks: every rewrite a model writes is checked for local value preservation, and
  single rewrites are told apart from jumps.
* Answer balance (no answer above 5% of a set, or above one task in sets under 20 tasks) and closure-size limits when sampling problems.
* `opulse corpus`: sharded plain text pretraining corpora (definitions, values, derivations,
  descriptions) with a document mix, definitions included or left out, operator frequency, splits
  by operator set or by operator with no held out operator in another split, exact deduplication,
  a manifest with counts, token estimates and provenance, and probe records with the span and value
  of every derivation step.
* `opulse expressions --workers N`: generation in seeded blocks with worker processes; the output
  does not depend on N. Step by step records skip undefined expressions and traces over the step
  limit before building them.

## 0.2.0

* Written semantics with integers plus NaN, truncating division, a value bound and two numeric modes
  (`exact`, `legacy`).
* Reference interpreter; generated Python and Cython code checked against it; `opulse verify`.
* Hand-written parser: configurable notation, uniquely decodable operator symbols, unary chains,
  numeral base markers, Greek-letter operators.
* z3 encoding of every operator, including bounded recursion; dead and always-undefined branches
  rejected during generation.
* Algebraic properties, equivalence of operators and expressions, SymPy proposals checked by z3.
* SMT-LIB export (`z3` field) checked by an independent evaluator.
* Fill-in-the-blank problems with complete and unique solution sets and reverse derivations.
* English and Chinese operator descriptions and step-by-step solutions.
* Atomic starting set (successor, predecessor, bits) and the `peano` recursion template.
* Cost fitting, dependency graph, HTML report, configuration wizard.
* Parameter sweep over 298 configurations.
