---
hide:
  - navigation
  - toc
---

# Playground

Choose a World and edit its [atoms](../glossary.md), the operations computed directly. Write a rule and evaluate an expression to see its value and checked steps. [Pyodide](https://pyodide.org) runs the Python package in your browser.

<div id="opulse_playground" class="opg" markdown="0">
<noscript><p>The playground needs JavaScript.</p></noscript>
</div>

## Choose a world

The **World** selector chooses the starting atoms and settings. Changing worlds resets edits to both. Selecting a named world also loads an example definition. Worlds from the [Worlds page](../worlds/index.md) use the same value displays here.

For example, the Bits world uses `a ◇ b = { a ⊻ b }` and `5 ◇ 3`. The value is `6`, because `⊻` computes bitwise XOR. Relations reads its supplied relation table; Clock starts in modular mode with a 12-hour dial.

## Hide the definition

Beside **Example**, choose **Hide the definition**. Select a rule from the current world, the example set, or an Induce challenge. **Random** picks an available rule. The table shows input and output examples. Enter an input and select **Ask the oracle** to see its output. Rules the hidden operator calls appear under **Known rules**.

Write a complete definition in **Your guessed rule** and select **Check**. The browser interpreter compares both rules on every integer input in the range shown above the table. Clock uses 0 through 11. Other numeric worlds and example sets use −3 through 3. Induce challenges use their own stated ranges. For other input types, Check uses the displayed finite input sets drawn from the world's examples. A differing result includes the first counterexample. **Reveal** shows the hidden definition.

## Atoms

The **Atoms** tab lists every atom of the world with its symbol, arity, types and rule. Each row has a switch and a message line.

- **Switch an atom off.** Expressions and grown operators no longer use it. For example, with `*` off, `2 * 3` is an error and Grow writes no multiplication.
- **Give an atom a new symbol.** Type into the symbol field. The expression grammar, palette and steps use the new symbol at once. The row reports invalid symbols, including spaces, digits (`1`, `³` and `₂`), brackets, grammar characters and keywords such as `if`. It also reports a symbol used by another atom in the same role or one that makes adjacent symbols ambiguous. Negation keeps `-` because negative numbers use it.
- **Edit the rule.** The rule is the sentence that prompts and the step view show for the atom. Editing it changes no value.
- **Reset** returns a row to its default symbol and rule.

**Add a custom atom** turns one Python function into an atom. Enter its name, symbol, arity, position (for one input), types and rule. Types are written as inputs and result, for example `str, int -> str`; an empty field means integers. A result of `None` gives NaN. The atom is checked before it joins the table, and an error stays in the form.

For example, name `cube`, symbol `⊛`, arity `1`, position **After argument**, rule `a ⊛ is a cubed.` and this function:

```python
def cube(a):
    return a ** 3
```

The expression `3 ⊛` then evaluates to `27`.

## Settings

The **Settings** tab shows the settings that matter in the playground. The grey text under each field is its key in a config file.

| Field | Config key | Effect |
| --- | --- | --- |
| Mode | `semantics.mode` | `exact`: a result beyond the bound is NaN. `legacy`: results wrap around the bound. `modular`: results use the world's modulus. |
| Value bound | `semantics.bound` | Largest absolute value an atom may return; empty means no bound. |
| Longest string, longest list | `semantics.max_string_length`, `semantics.max_list_length` | Shown for the Strings and Lists worlds. |
| Recursive operators | `recursion.enabled` | Off: Grow writes only simple and branch operators. |
| Template | `recursion.style` | `bounded_mod`, `direct`, `peano`, `bits` or `primitive`. |
| Recursion bound | `recursion.direct_bound` | Unfoldings allowed in direct, peano and primitive recursion. |
| Smallest and largest modulus | `recursion.modulus_min`, `recursion.modulus_max` | The modulus range of `bounded_mod` recursion. |
| Naming, shape sets, extra shapes, index characters | `operators.naming`, `operators.shape_sets`, `operators.shape_chars`, `operators.index_chars` | How grown operators are named, for example `◇₃`. |

Mode, value bound and length limits affect evaluation. Recursion and naming settings affect Grow. For example, with the bound `100`, `60 + 50` gives NaN.

## Grow operators

The **Grow** tab grows an operator set from the atoms that are on, with the same generation pipeline as `opulse operators`. Enter the operators per layer, for example `6 6`, and a seed, then select **Grow operators**. The definitions replace the editor content, and the expression calls the highest operator. With the same atoms, settings and seed, Grow writes the same set again.

The browser does not run [z3](../glossary.md), a constraint solver. Grow skips two generation checks: dead branches and degenerate subexpressions. A grown set can therefore hold a branch that no input reaches. **Load an example set** puts in the editor a set that the CLI generated with these checks.

## Copy as config

**Copy as config** shows three parts and copies them:

- `world.yaml`, the config file with every setting above. It also sets `operators.reject_dead_branches` and `operators.reject_degenerate` to `false`, to match the browser.
- `world_atoms.py`, a plugin module that registers the world, the custom atoms, the new symbols and the edited rules. Run as a script, it writes the starting operator set.
- The commands:

```bash
python world_atoms.py initial.jsonl
opulse --plugin world_atoms.py operators --config world.yaml --initial initial.jsonl \
    --layers 6 6 --proportions 0.4 0.4 0.2 --seed 1 --out operators.jsonl
```

With the same layers and seed, the CLI writes the definitions that Grow wrote. Set the two solver switches to `true` to run the full checks; the set then differs.

## Write definitions

Write one definition per line. A definition may continue until its braces close. For example, `a ⊕ b = { (a * a) + (b * b) }` returns the sum of two squares.

The left side applies one new symbol to `a` and `b`. A binary symbol appears between its arguments. A unary symbol may appear before or after its argument. Branches are separated by semicolons and tried in order. A branch can use `if` with comparisons and Boolean operators; the final branch can use `else`. An operator may call itself, while a cycle between different operators is rejected. A line beginning with `//` is a comment.

Binary operators group to the left. For example, `1 + 2 * 3` means `(1 + 2) * 3`. Parentheses specify a different grouping. The [semantics page](../reference/semantics.md) gives the full grammar.

## Read the result

**Value** is computed from the definition text. **Base ops** counts atom applications and **calls** counts all operator applications. **Steps** show each reduction. **Unfold** replaces a defined operator with the selected branch body. **Compute** applies an atom. **Undefined** yields NaN. The page checks the last complete reduction against the interpreter value.

The branch detail shows conditions in evaluation order. The dependency graph shows which definitions call other operators. Selecting a defined operator in the graph selects its definition in the editor.

For example, `a ◇ = { a / 2, if a % 2 == 0; (3 * a) + 1, else }` chooses its first branch for an even input. The step detail states which condition was true.

## Keyboard and sharing

Press <kbd>Ctrl</kbd> and <kbd>Enter</kbd> to evaluate immediately. Use arrow keys in the step list, or `j` and `k` when no text field has focus, to move through steps. In the tab row, the arrow keys move between Atoms, Settings and Grow.

**Copy link** saves the definitions, the expression, the world, the atom table changes, the custom atoms, the settings and the Grow fields in the page address. **Hide panel** gives the editor more room.
