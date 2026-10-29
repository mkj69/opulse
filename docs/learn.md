---
hide:
  - navigation
  - toc
---

# Learn: from atoms to definitions

Start with numbers, then use the same idea with words, lists and grids. Each example is already evaluated; edit the expression (or, from lesson 2 onward, the rules) and press **Run** to try your own.

<div class="ol-page" data-opulse-learn markdown="1">

<section class="ol-card" id="atoms" markdown="1">
## 1. Atoms: the operations you choose

Atoms are starting operations. Here are the integer world's atoms; you can [add your own in the Playground](guide/playground.md#atoms).

<div class="ol-atoms">
<div class="ol-atom"><code>a + b</code><strong>Add</strong><span>Add two integers.</span></div>
<div class="ol-atom"><code>a - b</code><strong>Subtract</strong><span>Subtract b from a.</span></div>
<div class="ol-atom"><code>a * b</code><strong>Multiply</strong><span>Multiply two integers.</span></div>
</div>

<h3 class="ol-more-atoms">More atoms</h3>
<div class="ol-atoms">
<div class="ol-atom"><code>a / b</code><strong>Divide</strong><span>Round toward zero; zero divisor gives NaN.</span></div>
<div class="ol-atom"><code>a % b</code><strong>Remainder</strong><span>Remainder after division; zero divisor gives NaN.</span></div>
<div class="ol-atom"><code>- a</code><strong>Negate</strong><span>Change the sign.</span></div>
<div class="ol-atom"><code>a @</code><strong>Reverse</strong><span>Reverse decimal digits; keep the sign.</span></div>
<div class="ol-atom"><code># a</code><strong>Triangle</strong><span>Sum 1 through a; negate for negative a.</span></div>
<div class="ol-atom"><code>a $</code><strong>Bit count</strong><span>Count 1 bits in the absolute value.</span></div>
<div class="ol-atom"><code>&amp; a</code><strong>Digit sum</strong><span>Sum decimal digits; keep the sign.</span></div>
<div class="ol-atom"><code>a ⁺</code><strong>Successor</strong><span>Add one.</span></div>
<div class="ol-atom"><code>a ⁻</code><strong>Predecessor</strong><span>Subtract one.</span></div>
<div class="ol-atom"><code>a «</code><strong>Double</strong><span>Multiply by two.</span></div>
<div class="ol-atom"><code>a »</code><strong>Half</strong><span>Halve, rounding toward zero.</span></div>
<div class="ol-atom"><code>a °</code><strong>Parity</strong><span>0 if even, 1 if odd.</span></div>
<div class="ol-atom"><code>defined a</code><strong>Defined?</strong><span>1 for an integer, 0 for NaN.</span></div>
</div>

No rule is needed yet: atoms are evaluated directly. In `(3 + 4) * 2`, first add, then multiply; the trace shows two **compute** steps. Next, we give this calculation a name.

<div data-learn-example="atoms"></div>

**Try it:** What is `4 * 3`? <a href="../challenge/?mode=compute">Try more →</a>
</section>

<section class="ol-card" id="substitution" markdown="1">
## 2. Substitute the inputs

`a ◆ b = { (a + b) * 2 }` names the calculation from lesson 1: ◆ takes two inputs, adds them, then doubles the sum. In `3 ◆ 4`, one **unfold** step replaces both `a` and `b` with `3` and `4`; then two **compute** steps evaluate `+` and `*`.

<div data-learn-example="substitution"></div>

**Try it:** Predict `5 ◆ 1` before opening the answer. <a href="../challenge/?mode=compute">Try more →</a>
</section>

<section class="ol-card" id="layers" markdown="1">
## 3. One operator can call another

`a ♣ b = { (a ◆ b) - a }` uses ◆ from the previous card. First unfold ♣, then unfold ◆; the highlighted part shows what changes at each step.

<div data-learn-example="layers"></div>

**Try it:** What is `5 ♣ 2`? <a href="../challenge/?mode=compute">Try more →</a>
</section>

<section class="ol-card" id="branch" markdown="1">
## 4. Choose a branch

`a ▲ b = { a - b, if a >= b; b - a, else }` gives the distance between two numbers. `>=` means greater than or equal to; the first branch handles equality too. Here `3 ▲ 3` uses that branch and gives zero.

<div data-learn-example="branch_equal"></div>

**Try it:** At `a = b = 4`, which branch runs, and what is the answer? <a href="../challenge/?mode=wrongstep">Try more →</a>
</section>

<section class="ol-card" id="recursion" markdown="1">
## 5. Repeat, with a stopping point

`a ★ b = { 0, if b <= 0; (a ★ (b - 1)) + a, else }` adds `a` once for each count in `b`. `<=` means less than or equal to: when `b` reaches zero, the rule returns `0` instead of calling itself again. The example `2 ★ 3` adds two three times; the exercise tries `3 ★ 4`. An arithmetic result beyond the configured value bound gives `NaN`, meaning no valid number.

<div data-learn-example="recursion"></div>

**Try it:** Predict `3 ★ 4` by adding three four times. <a href="../challenge/?mode=compute">Try more →</a>
</section>

<section class="ol-card" id="read" markdown="1">
## 6. Read the shape of a rule

`a ◆ b` is binary: it has two inputs. `◇ a` is unary prefix (symbol before input), `a ♠` is unary postfix (symbol after input), and `⊙(a, b, c)` is the call form for three inputs. The three examples below show these shapes in order. In a branched rule like lesson 4's, a semicolon separates branches; Opulse tries them in order and uses `else` if earlier conditions fail.

<div data-learn-example="prefix"></div>
<div data-learn-example="postfix"></div>
<div data-learn-example="call"></div>

**Try it:** What is `⊙(3, 5, 4)`? <a href="../challenge/?mode=describe">Try more →</a>
</section>

<section class="ol-card" id="worlds" markdown="1">
## 7. Same structure, new material

The string and list rules both join two inputs, then drop the first item. `⊕` joins strings and `⇥` drops the first character; `⊞` joins lists and `⌄` drops the first element. The first two examples use binary `a ◆ b`. The grid example uses a different, unary `a ◆` rule: `↻` rotates clockwise by 90°, so applying it twice turns a grid halfway around.

<div data-learn-example="strings"></div>
<div data-learn-example="lists"></div>
<div data-learn-example="grid"></div>

**Try it:** After seeing `"sun" ◆ "day"`, predict `[1, 2] ◆ [3, 4]`. <a href="../challenge/?mode=translate">Try more →</a> · [Explore Worlds →](worlds/index.md)
</section>

<section class="ol-card" id="next" markdown="1">
## 8. Where to go next

The [Challenge](challenge.md) has six angles: compute a result, invert an input, decide a claim, describe a rule, induce a pattern, and create a solution. The rule below, `a ◈ b = { a, if a >= b; b, else }`, chooses the larger input; try editing it to choose the smaller one. Use the [Playground](guide/playground.md) to write a whole world of your own.

<div data-learn-example="next"></div>

**Try it:** Predict `7 ◈ 4`. <a href="../challenge/?mode=target">Try more →</a>
</section>

</div>
