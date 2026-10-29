---
hide:
  - navigation
---

# Visual tour

Each widget shows a different way to use generated rules. An [atom](../glossary.md) is an operation computed directly; an [operator](../glossary.md) is a named operation built from atoms or other operators. The examples use fixed seeds and sets of about 10, 100, 1,000, and 10,000 operators. Shapes such as ◆₁ are names, not clues to a rule ([notation](notation.md)).

## Grow an operator set {#growing-an-operator-set}

See how operators build on earlier ones across [layers](../glossary.md). Choose a scale, then select an operator to see its definition and the rules it needs.

<div id="tour-growth-kinds" data-kinds-legend></div>

--8<-- "docs/snippets/vis_growth.html"

One measured run with reduced acceptance checks grew 100,000 operators in about 8.1 hours ([Performance](../about/benchmarks.md)).

## Unfold to atoms at any granularity { #unfold-to-atoms }

<span id="unfold-at-any-granularity"></span>

An [unfolding](../glossary.md) replaces a defined call with the branch selected by its inputs. An atom computes its result directly. [Granularity](../glossary.md) sets how much work each step shows: with all operators known, a computation may take one step; fully unfolded, it may take tens of thousands. Choose a layer boundary or mark known operators in the searchable groups, then compare the step count for the same answer. The Steps view shows 50 steps per page and lets you jump to any step; the Tree view loads branches when opened.

--8<-- "docs/snippets/granularity_scales.html"

## Test a model in context

The same question gets a different answer when one supplied definition changes. Choose a pair and step through both answers to see where they diverge.

--8<-- "docs/snippets/vis_contrast.html"

## Grade every step

Two solutions reach the same answer, but one contains a wrong rewrite. Switch between them and find the first line the checker rejects.

--8<-- "docs/snippets/vis_steps_scales.html"

## Solve for the unknown

The [interpreter](../glossary.md) checks every candidate input in the stated range. Choose a scale and step through the checks to see why the answer is unique there.

--8<-- "docs/snippets/vis_solve.html"

## Guess the rule

Several rules fit the first examples. Reveal more examples, rule out candidates, and test the remaining rule on new inputs.

--8<-- "docs/snippets/vis_induce.html"

## Prove or refute an equivalence

Each pair may agree everywhere or have a counterexample. Step through the pairs and inspect whether [z3](../glossary.md) proved a claim or the interpreter checked the stated range.

--8<-- "docs/snippets/vis_equivalence.html"

## Edit one operator

A change to one definition can affect operators that call it, including indirect callers. Choose an example and follow the changed values through the dependency graph.

--8<-- "docs/snippets/vis_ripple.html"

## Choose how often operators appear

The bars count operator uses in sampled expressions. Switch between uniform and Zipf sampling, then play the samples to compare their frequencies.

--8<-- "docs/snippets/vis_frequency.html"
