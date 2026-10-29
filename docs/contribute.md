---
description: How to take part in Opulse, from sharing an experiment idea to building a new world.
hide:
  - navigation
---

# Join us

You can help test how models use rules supplied in a prompt, or whether skills learned with numbers transfer to text, logic, and sound. The [experiment ideas](experiments.md) report designs without training results. The [Worlds](worlds/index.md) show example starting operations; you can add rules from a field you know.

## Ways to take part

<div class="op-grid op-join" markdown>
<div class="op-card" markdown>
### :material-lightbulb-on-outline: Share an idea
Propose an experiment, or tell us which existing idea you most want to see run, and why; the
reason often helps more than the vote.

[Discussions](https://github.com/mkj69/opulse/discussions)
</div>
<div class="op-card" markdown>
### :material-flask-outline: Run an experiment
Pick a design from the [experiment ideas](experiments.md), run it, and post what you saw. Post a
result with no gain too, so the next person knows that path has been tried.

[Discussions](https://github.com/mkj69/opulse/discussions)
</div>
<div class="op-card" markdown>
### :material-earth: Build a world
Register atoms from chemistry, music theory, a game or your own work, then contribute them as a
starting set with a config, or as a plugin module.

[Atoms guide](guide/atoms.md)
</div>
<div class="op-card" markdown>
### :material-bug-outline: Report a problem
A crash, a wrong answer, or a derivation step the checker accepted and you think it should not
have. Paste the command and the seed if you have them.

[Issues](https://github.com/mkj69/opulse/issues)
</div>
<div class="op-card" markdown>
### :material-book-open-variant: Improve the docs
Fix a sentence that confused you, add the example you wished a page had, or offer a translation
into a language you read well.

[Issues](https://github.com/mkj69/opulse/issues)
</div>
<div class="op-card" markdown>
### :material-puzzle-outline: Add an integration
Connect Opulse to a trainer, an evaluation harness or an interpretability tool, so the data and
the step checker reach the tools people already use.

[Contributing guide](https://github.com/mkj69/opulse/blob/main/CONTRIBUTING.md)
</div>
<div class="op-card" markdown>
### :material-format-quote-close: Cite and tell others
If Opulse helps your work, cite it. If you know someone who studies these questions, send them
the link.

[Citation](#cite)
</div>
</div>

## How we work together

* Use [Discussions](https://github.com/mkj69/opulse/discussions) for ideas and questions. Use [Issues](https://github.com/mkj69/opulse/issues) for reproducible problems.
* The [GitHub contributors page](https://github.com/mkj69/opulse/graphs/contributors) lists code contributors. Include attribution when an experiment builds on someone else's idea.
* A typo fix, a failed command with reproduction steps, or a clearer example can improve the docs.
* If an experiment cannot answer its question, explain which comparison or measurement is missing.

The technical steps (setup, tests, code style, pull requests and licences) are in
[CONTRIBUTING.md](https://github.com/mkj69/opulse/blob/main/CONTRIBUTING.md). Everyone who takes
part follows the [code of conduct](https://github.com/mkj69/opulse/blob/main/CODE_OF_CONDUCT.md).

## Good first steps

1. Install Opulse and run the tests:

    ```bash
    git clone https://github.com/mkj69/opulse.git && cd opulse
    python -m venv .venv && source .venv/bin/activate
    pip install -e ".[dev]"
    python -m pytest -q
    python tools/sweep.py --quick   # the pipeline under 11 settings, about 16 s
    ```

2. Write a definition of your own in the [playground](guide/playground.md) and step through its
   evaluation. Nothing to install for this one.
3. Read the [experiment ideas](experiments.md) and pick the one you would most like to know the
   answer to. Then say so in [Discussions](https://github.com/mkj69/opulse/discussions).

## Cite {#cite}

To cite Opulse, use the citation file in the repository (CITATION.cff) or the entry at the end of the [blog post](blog/index.md#citation).

The code is released under Apache 2.0, and the documentation and data under CC BY 4.0.
