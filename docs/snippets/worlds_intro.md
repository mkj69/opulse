One tree can join strings and drop a character, or join lists and drop an element. A reference interpreter computes each result and checks each step.

**Same tree, different material.**
Train on source world trees, then test those trees in a target world after practising its atoms. Compare with training on unrelated trees and with target world training alone at equal token budgets.

*Worlds:* strings and lists; clock and permutations; grids and melodies.

*Open question:* Yuan et al. found that RL on composed string transformations improved Countdown accuracy once the model knew its atomic skills ([2509.25123](https://arxiv.org/abs/2509.25123)). The tasks differ in both tree and material, so the source of transfer remains unclear.

**Which material best prepares for pretraining.**
Warm up identical models on the same trees in two or three worlds, with a shallow tree control in each. Compare how many training tokens each needs to reach a fixed loss on held out text and code.

*Worlds:* two or three of strings, permutations and relations.

*Open question:* Yamaguchi et al. found that synthetic training saved at least 21B pretraining tokens at 3B parameters; gains followed long range retrieval, with no consistent evidence for the proposed grammatical prior ([2609.39827](https://arxiv.org/abs/2609.39827)). Which property caused the gain remains open.

**Variety at a fixed budget.**
Spend the same token budget on one world or several, then test on held out trees and a new world. Compare with one world containing as many distinct trees and one world shown in several notations.

*Worlds:* all of them.

*Open question:* In Guru, RL in one domain helped domains common in pretraining, while Logic, Simulation and Tabular needed their own training data ([2506.14965](https://arxiv.org/abs/2506.14965)). Its domains also differ in rules, verifiers and format.

**State tracking on rules never seen.**
Build card tasks from swaps, rotations, composition and inversion, varying sequence length and whether each operator appeared in training. Compare equal token budgets with and without checked intermediate card orders.

*Worlds:* permutations.

*Open question:* Assuming TC⁰ ≠ NC¹, Merrill et al. prove limits on arbitrary length permutation composition for the transformer and state space model classes they analyse; Mamba style models also struggle in their experiments ([2404.08819](https://arxiv.org/abs/2404.08819)).

**Edits that ripple.**
Change one relation table entry and compare query answers before and after. Separate errors on the edited entry from errors on paths that use it and matched paths that do not.

*Worlds:* relations.

*Open question:* On RippleEdits, tested editing methods failed to update related facts consistently, and a simple in context editing baseline scored best ([2307.12976](https://arxiv.org/abs/2307.12976)).

**A step checker for a new material.**
Train a process verifier on interpreter checked steps, then compare its judgements with the interpreter in a held out world. Test both fixed solutions and solutions sampled during RL to measure false approvals.

*Worlds:* all of them, one held out at a time.

*Open question:* ProcessBench used expert labels for the first wrong step in 3,400 math solutions; its tested process reward models did not generalise beyond GSM8K and MATH to harder problems ([2412.06559](https://arxiv.org/abs/2412.06559)).

These are proposed experiments, not training results; pictures help readers while models receive text. Pairing trees across worlds uses skeleton export (`opulse skeleton`) and records how closely the atoms correspond.
