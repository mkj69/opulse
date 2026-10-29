# Example deduplication status

The published-JSON audit covers 262 puzzles. After a full ordered regeneration,
the site-wide audit reports **55 repeated-rule groups, 38 overused-template
groups, 8 overused rule families, and 2 degenerate featured rules**. Number-card,
question/answer, tier-question, atom-variety, and missing-atom violations are
zero. **The strict gate is not green.**

The audit counts operators written in Expert/Master/Legend questions and edited
rules, not their other closure helpers. World *challenge* rules are compared
with every other featured rule site-wide, not with their showcase helpers.
Other puzzles count displayed featured definitions, including candidate rules
in the tour and edited rules. Constants-blind nontrivial templates are limited
to three puzzles across at least two angles. Trivial one-atom applications are
exempt from the template limit, but not exact-rule uniqueness.

## Replaced puzzles

The following replacements predate the current audit change; no puzzles have
been replaced in the current step. In the descriptions, `$` means
popcount, `#` triangular number, and `&` digit sum in the integer world.

| Puzzle | Before | After | Reason |
| --- | --- | --- | --- |
| successor-c6 | Three successor steps | A four-to-eleven branch returning two | Teaches a boundary instead of repeating the first challenge's composition. |
| integer-c6 | Popcount of first input times digit sum of second | Digit sum of six times the input's popcount | Shows the order of two ordinary operations, not the first challenge's rule. |
| bits-c6 | OR of two input popcounts | OR of one with the input's popcount | Keeps a small, distinctive bit-count example, not the fourth challenge's rule. |
| strings-c6 | Lowercase of two strings joined | Lowercase of one string reversed | Makes both the case change and the order change visible. |
| lists-c6 | First item after concatenation | Drop the head, then append `[1, 2]` | Exercises an empty remainder and an ordered suffix without duplicating c2. |
| rel-c6 | Neighbour, then colleague | Follow the full relation chain and test for Luz | Moves from a copied lookup to a checked Boolean inference. |
| induce-02 | `a - 2*b` | `popcount(a) - b` | Changes the characteristic atom and avoids a reused weighted difference. |
| induce-04 | `max(a,b)` | `a + popcount(b)` | Replaces an overused maximum with a distinguishable bit-count pattern. |
| induce-07 | Helper `a + 2*b` | Helper `a + triangular(b)` | Gives the two-rule inference its own structured helper. |
| ripple-02 | Helper `a - b` | Helper `popcount(a) + popcount(b)` | Makes the changed dependency observable without another subtraction alias. |
| ripple-03 | Helper `a*b` | Helper `popcount(a)*popcount(b)` | Distinguishes the layered effect from bare multiplication. |
| ripple-04 | Helper `a+b` | Helper `popcount(a)+b` | Makes the parity-dependent propagation use a real atom. |
| ripple-06 | Helper `a+2*b` | Helper `popcount(a)+2*b` | Avoids another weighted-sum helper. |
| ripple-08 | Helper `a-1` | Helper `triangular(a)+1` | Separates the unaffected branch from another decrement rule. |
| ripple-11 | Helper `a-b` | Helper `(a%3)-b` | Gives the changed branch a distinct remainder-based dependency. |
| shorten-09 | Duplicated weighted sum | Separate digit sums of a tens digit and a units digit | Demonstrates how joining digits avoids repeated atom calls. |
| shorten-10 | Expanded sum squared | Expanded difference squared | Uses a distinct textbook factoring identity. |
| target-01 | Double first input, then add second | Product plus signed difference | Replaces a reused weighted sum with an order-sensitive product. |
| target-02 | Product plus first input | Product minus first popcount | Gives the card operator a different atom and input role. |
| target-03 | Absolute difference | Double the distance only when left is smaller | Keeps a clear, asymmetric boundary. |
| target-04 | Sum of two squares | Triangular first input plus second | Uses a small, transparent integer atom. |
| target-05 | Sum capped at ten | Subtract ten only after crossing ten | Makes a wraparound rather than another capped sum. |
| target-06 | Squared difference | Multiply for even sum, add for odd sum | Teaches one parity-controlled choice. |
| target-07 | Twice the signed gap | Difference of squares | Uses a recognisable identity and order-dependent sign. |
| target-08 | Difference of squares | Last digit of product | The solution visibly crosses a tens boundary. |
| wrongstep-03 | Double the helper's value | Add the triangular first input | Preserves the wrong-branch lesson without copying a doubling rule. |
| wrongstep-04 | Product plus two | Product plus first popcount | Keeps the mistaken multiplication step, but changes the featured rule. |
| wrongstep-12 | Gap plus twice first input | Gap plus successor of first input | Keeps the swapped-argument slip with a different calculation. |

The generator filters and manual review reject multiplication by one or zero,
addition/subtraction of zero, division by one, double negation, subtracting an
input from itself, unused parameters, and direct aliases. Regeneration also
checks its own mode-specific witness, range, answer, and proof requirements.
During manual selection, a string candidate that only measured concatenated
length was set aside as less representative; a permutation candidate failed the
required output type/identifiability; integer candidates with showcase-sized
inputs were rejected as oversized; and candidate relation, pitch, action, and
grid examples failed undefined-input, state-validity, or visible-transformation
checks. These are rejections, not published puzzles. The tour's three exported
rows record zero additional example-resampling rejections.

## Remaining work

The compute ladder still reuses primitive-alias definitions and several
constants-blind templates. Other collisions remain in Ripple, Wrongstep,
Hole, the tour candidates, the Expert/Legend main operators, and some world
challenges. Two featured rules fail the quality filter: Legend-03 contains
`a - a` and clock-c2 subtracts a negative expression from itself. Most
generators do **not** yet consult the shared registry; only Target does.
`tools/regenerate_examples.py` completes its deterministic generator order,
but the final strict audit fails until generators are redesigned and puzzle
explanations reverified.
