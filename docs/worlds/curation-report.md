# World curation report

Counts use the default seed of each world. Rejection rules run in exporter order, so each rejected operator has one primary reason. Other eligible operators were left out to keep the list short.

Rejected rules: **undefined** has no defined example; **constant** or **near constant** has one output on all or at least 85% of probes; **unused argument** has no observed input effect; **atom equivalent**, **duplicate**, and **shape duplicate** repeat an atom, a shown value table, or a numeric pattern shifted by a constant; **cancelled constant** and **alias** contain an inert arithmetic or direct wrapper; **bad helper** depends on one of those rules; **long sentence** exceeds 22 words; **opaque sentence** hides its operation behind a summary or too many helpers, or uses a contrived self shift, remainder, or large repeat seed. Action additionally uses **no effect** for state transitions that never change the state.

Core worlds use `opulse.generation.interest` scores for every grown operator. Action skills use a sampled state-change score because the core fingerprinter has no state probe type.

## Successor

Grown: **100**. Curated: **24**. Eligible but not selected: **8**.

| Rejection rule | Count |
| --- | ---: |
| undefined | 0 |
| constant | 0 |
| near constant | 1 |
| unused argument | 7 |
| atom equivalent | 1 |
| duplicate | 0 |
| shape duplicate | 10 |
| cancelled constant | 0 |
| alias | 0 |
| bad helper | 0 |
| long sentence | 25 |
| opaque sentence | 24 |

Top eight:

- **◆₆** — Subtract one from a twice, stopping at zero.
- **★₅** — Add one to a, then add one to it.
- **♣₈** — Apply ◆₆ to a, then subtract one from it, stopping at zero.
- **♣₁₇** — Apply ◆₆ to a, then apply ◆₆ to the result.
- **★₇** — Subtract one from a, stopping at zero, then apply ★₅ to the result.
- **♦₃₁** — Apply ☆₂₁ to a and (a ♣₁₀).
- **♤₃₃** — Apply △₂₃ to a and a, then apply ☆₂₆ to the result.
- **♢₄₀** — Apply ♣₈ to a, then apply ♦₃₉ to the result and a.

## Integers

Grown: **100**. Curated: **24**. Eligible but not selected: **13**.

| Rejection rule | Count |
| --- | ---: |
| undefined | 0 |
| constant | 0 |
| near constant | 3 |
| unused argument | 9 |
| atom equivalent | 0 |
| duplicate | 0 |
| shape duplicate | 0 |
| cancelled constant | 0 |
| alias | 0 |
| bad helper | 6 |
| long sentence | 24 |
| opaque sentence | 21 |

Top eight:

- **♦₆** — Reverse the digits of a, then multiply it by b.
- **▼₇** — Negate a, then multiply the result by itself.
- **■₄** — Sum the digits of b, then multiply it by the number of one bits in a.
- **♠₃₈** — Multiply b by a, then apply ♦₉ to the result.
- **▽₁₄** — Apply ■₄ to a and 6, then sum its digits.
- **○₃₆** — Apply ▼₇ to a, then multiply it by ●₁₁ a.
- **●₁₆** — Negate a, then apply ■₄ to the result and (□₁₀ a).
- **□₁₀** — Count the one bits of a, then apply ■₄ to the result and (the digit sum of a).

## Clock

Grown: **100**. Curated: **24**. Eligible but not selected: **3**.

| Rejection rule | Count |
| --- | ---: |
| undefined | 0 |
| constant | 0 |
| near constant | 1 |
| unused argument | 11 |
| atom equivalent | 1 |
| duplicate | 0 |
| shape duplicate | 0 |
| cancelled constant | 3 |
| alias | 0 |
| bad helper | 14 |
| long sentence | 25 |
| opaque sentence | 18 |

Top eight:

- **▽₅** — Negate a, then add the result to itself.
- **☆₄** — Count the one bits of a, then add a to it.
- **△₁** — Subtract the signed triangle number of a from b.
- **●₉** — Subtract 3 from a.
- **□₁₄** — Negate a, then subtract the number of one bits in a from it.
- **●₆** — Take the signed triangle number of b, then divide it by -a, rounding toward zero.
- **♢₁₈** — Apply □₁₁ to a and a, then negate it.
- **♣₁₃** — Apply ☆₄ to b, then apply △₁ to the result and (a ☆₄).

## Bits

Grown: **100**. Curated: **24**. Eligible but not selected: **9**.

| Rejection rule | Count |
| --- | ---: |
| undefined | 0 |
| constant | 2 |
| near constant | 5 |
| unused argument | 4 |
| atom equivalent | 0 |
| duplicate | 0 |
| shape duplicate | 0 |
| cancelled constant | 0 |
| alias | 0 |
| bad helper | 8 |
| long sentence | 30 |
| opaque sentence | 18 |

Top eight:

- **♦₅** — Count the one bits of b, then OR it with the number of one bits in a bit by bit.
- **▲₈** — Count the one bits of a, then shift it left by a ●₇ bits.
- **♤₁** — XOR b with a bit by bit, then apply ▲₈ to the result.
- **◇₁₂** — Apply ▼₉ to a, then OR it with a bit by bit.
- **★₁₅** — Apply ★₁₄ to a, then OR it with the number of one bits in a bit by bit.
- **△₁₁** — Apply ●₇ to b, then shift it left by a ●₇ bits.
- **★₁₄** — Apply ♤₁ to a and (a ▼₉).
- **□₁₀** — Apply ♦₅ to a and (a ●₇).

## Strings

Grown: **100**. Curated: **24**. Eligible but not selected: **51**.

| Rejection rule | Count |
| --- | ---: |
| undefined | 0 |
| constant | 1 |
| near constant | 3 |
| unused argument | 1 |
| atom equivalent | 3 |
| duplicate | 0 |
| shape duplicate | 3 |
| cancelled constant | 0 |
| alias | 0 |
| bad helper | 2 |
| long sentence | 12 |
| opaque sentence | 0 |

Top eight:

- **♣₁** — Append b to a, then turn it into lowercase.
- **▲₆** — Append a in uppercase to "a".
- **♦₈** — Reverse a, then turn it into lowercase.
- **■₄** — Apply ♣₁ to a and b, then turn it into uppercase.
- **△₅** — Apply ♣₁ to a and b, then count its characters.
- **△₁₈** — Subtract a △₅ b from 4.
- **◇₁₇** — Apply ♣₁ to "ab" and (a in uppercase).
- **♥₇** — Apply ▲₆ to a, then turn it into lowercase.

## Lists

Grown: **98**. Curated: **24**. Eligible but not selected: **44**.

| Rejection rule | Count |
| --- | ---: |
| undefined | 0 |
| constant | 0 |
| near constant | 0 |
| unused argument | 2 |
| atom equivalent | 2 |
| duplicate | 2 |
| shape duplicate | 2 |
| cancelled constant | 0 |
| alias | 0 |
| bad helper | 2 |
| long sentence | 19 |
| opaque sentence | 1 |

Top eight:

- **★₅** — Drop the first element of a, then append [1, 2] to it.
- **♥₇** — Append b to a, then take element 2 from it, counting from zero.
- **□₁₀** — Append b to a, then take its first element.
- **○₁** — Append b to a, then apply ▼₁₂ to the result.
- **♠₉** — Apply ★₅ to a, then append [1] to it.
- **☆₄** — Subtract a ▼₁₂ from 1.
- **▼₁₂** — Add up the elements of a, then negate it.
- **♢₁₇** — Take the remainder when dividing 3 by the sum of the elements of a.

## Logic

Grown: **96**. Curated: **24**. Eligible but not selected: **6**.

| Rejection rule | Count |
| --- | ---: |
| undefined | 0 |
| constant | 0 |
| near constant | 2 |
| unused argument | 8 |
| atom equivalent | 23 |
| duplicate | 23 |
| shape duplicate | 0 |
| cancelled constant | 0 |
| alias | 0 |
| bad helper | 0 |
| long sentence | 10 |
| opaque sentence | 0 |

Top eight:

- **△₁** — Negate a, then apply ▽₉ to the result and a.
- **▽₉** — Apply ▽₇ to a and b, then negate it.
- **△₁₁** — Apply △₁₀ to a and b, then negate it.
- **▽₇** — OR a with a ◆₆ b.
- **▲₁₂** — Apply ▽₉ to b and (a ⇔ b).
- **♠₂₂** — If a is true, XOR a with a ⋀ b; otherwise AND a with b.
- **♡₄₉** — Apply ★₄₇ to a and b, then AND it with a.
- **▽₅₅** — Apply ★₄₇ to a and b, then apply ♤₄₂ to the result.

## Permutation cards

Grown: **100**. Curated: **24**. Eligible but not selected: **32**.

| Rejection rule | Count |
| --- | ---: |
| undefined | 0 |
| constant | 0 |
| near constant | 2 |
| unused argument | 1 |
| atom equivalent | 1 |
| duplicate | 2 |
| shape duplicate | 2 |
| cancelled constant | 0 |
| alias | 0 |
| bad helper | 0 |
| long sentence | 36 |
| opaque sentence | 0 |

Top eight:

- **♤₁** — Rotate a one place right, then reverse its order.
- **▼₄** — Rotate a one place right, then swap the cards at positions 0 and 4 in the result.
- **♧₈** — Rotate a one place right, then find where card 1 goes under it.
- **●₉** — Invert a, then find where card 0 goes under it.
- **♠₁₈** — Follow [4, 1, 2, 0, 3] with a ♤₁.
- **★₅** — Swap cards in [2, 3, 4, 0, 1] using a ♧₈ as a position code.
- **♡₃₈** — Apply ●₂₅ to a, then rotate it one place left.
- **◇₁₀** — Find where card a ●₉ goes under [3, 2, 4, 0, 1].

## Relations

Grown: **100**. Curated: **24**. Eligible but not selected: **49**.

| Rejection rule | Count |
| --- | ---: |
| undefined | 0 |
| constant | 0 |
| near constant | 9 |
| unused argument | 0 |
| atom equivalent | 1 |
| duplicate | 0 |
| shape duplicate | 0 |
| cancelled constant | 0 |
| alias | 0 |
| bad helper | 0 |
| long sentence | 17 |
| opaque sentence | 0 |

Top eight:

- **●₁** — Look up the neighbour of a, then look up that person's colleague.
- **♠₅** — Look up the colleague of a, then look up that person's parent.
- **♣₇** — Look up the parent of a, then look up that person's neighbour.
- **★₄** — Apply ●₁ to a, then look up that person's neighbour.
- **♦₆** — Look up the parent of a, then apply ★₄ to the result.
- **♠₁₁** — Apply ♦₈ to a, then look up that person's colleague.
- **♠₁₀** — Test whether "Luz" equals a ♦₈.
- **♧₁₇** — Apply ▽₁₄ to a, then look up that person's neighbour.

## Grids

Grown: **100**. Curated: **24**. Eligible but not selected: **14**.

| Rejection rule | Count |
| --- | ---: |
| undefined | 8 |
| constant | 0 |
| near constant | 18 |
| unused argument | 0 |
| atom equivalent | 3 |
| duplicate | 5 |
| shape duplicate | 0 |
| cancelled constant | 2 |
| alias | 0 |
| bad helper | 5 |
| long sentence | 21 |
| opaque sentence | 0 |

Top eight:

- **●₁₀** — Rotate a 90 degrees clockwise, then wrap it right by 3 columns.
- **●₈** — Wrap a right by b columns, then recolour the colour 0 cells in the result to colour 2.
- **♢₇** — Crop a to the smallest rectangle that holds all its nonzero cells, then flip it upside down.
- **★₄** — Apply ♢₇ to a, then shift it right by 1 column, filling with 0.
- **●₉** — Apply ●₈ to a and b, then apply ♢₇ to the result.
- **▽₁₁** — Shift a down by b rows, filling with 0, then shift it right by 4 columns, filling with 0.
- **◇₁₂** — Use the number of colour b cells in a as a two digit code to recolour the 2×3 grid 303/010.
- **♣₃₄** — Apply ●₈ to a and b, then apply ★₄ to the result.

## Pitch

Grown: **98**. Curated: **24**. Eligible but not selected: **40**.

| Rejection rule | Count |
| --- | ---: |
| undefined | 0 |
| constant | 0 |
| near constant | 2 |
| unused argument | 0 |
| atom equivalent | 1 |
| duplicate | 1 |
| shape duplicate | 0 |
| cancelled constant | 0 |
| alias | 0 |
| bad helper | 0 |
| long sentence | 30 |
| opaque sentence | 0 |

Top eight:

- **▲₁** — Append b to a, then reverse its notes.
- **♢₅** — Transpose a by b semitones, then measure the semitones from it to C5.
- **♦₁₀** — Build a major triad on a, then reverse its notes.
- **■₆** — Build a minor triad on a, then mirror it around C5.
- **♧₈** — Take the remainder when dividing 4 by the semitones from a to b.
- **♧₁₂** — Append a ▲₁ b to [D4:1 F4:2].
- **◆₄** — Apply ▲₁ to a and b, then append [D4:1 F4:2] to it.
- **♧₁₁** — Test whether [D4:1 F4:2] equals a mirrored around b.

## Action

Grown: **100**. Curated: **24**. Eligible but not selected: **43**.

| Rejection rule | Count |
| --- | ---: |
| undefined | 0 |
| constant | 0 |
| near constant | 0 |
| no effect | 2 |
| unused argument | 0 |
| atom equivalent | 0 |
| duplicate | 30 |
| cancelled constant | 0 |
| long sentence | 1 |
| opaque sentence | 0 |
| alias | 0 |

Top eight:

- **★₁** — Turn right, then move forward.
- **□₂** — If open water is ahead, turn left; otherwise move forward.
- **♧₁₅** — Pick up what is ahead until the cell ahead has no blocks, at most 2 times.
- **▲₁₆** — Move forward, then move forward.
- **▽₂₅** — Turn left, then move forward.
- **♤₇** — Move forward, then place the held object ahead.
- **♧₁₃** — Turn right, then place the held object ahead.
- **♦₁₉** — Pick up what is ahead, then move forward.
