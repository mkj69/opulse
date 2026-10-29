# Contributing to Opulse

This file has the technical steps. The reasons to take part, and
the kinds of help that are most useful, are on the [Join us](https://mkj69.github.io/opulse/contribute/)
page.

Small contributions are welcome: a fixed typo, a clearer sentence or a failing command reported
with its seed all count.

## Where to ask

* Questions, experiment ideas and results: [GitHub Discussions](https://github.com/mkj69/opulse/discussions).
* Bugs, wrong answers, wrong derivation steps and documentation errors:
  [GitHub Issues](https://github.com/mkj69/opulse/issues).

If you are unsure where something belongs, open a discussion. Every message is read.

## Development setup

Opulse needs Python 3.10 or newer.

```bash
git clone https://github.com/mkj69/opulse.git && cd opulse
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"            # opulse, z3-solver, sympy, numpy, pyyaml, pytest, hypothesis, ruff
pip install -e ".[docs]"           # only if you work on the documentation site
```

## Tests

```bash
python -m pytest -q                # the full test suite
python tools/sweep.py --quick      # the pipeline under 11 settings, about 16 s
python tools/sweep.py              # all 298 configurations, before a change to generation or semantics
```

A pull request should keep both green. A change to the semantics, the interpreter, generation,
the step checker or the solvers should come with a test that fails without it.

## Code style

Opulse uses [ruff](https://docs.astral.sh/ruff/) for linting. Run it on the files you change:

```bash
ruff check path/to/changed_file.py
```

Some older files still have findings; please do not mix unrelated lint fixes into a functional
change. Keep functions small, name things after what they compute, and write docstrings for
public functions.

## Adding atoms or a world

An atom is a Python function with a symbol, a shape and one sentence that states its rule. A
world is a set of atoms you choose, plus the configuration that grows operators from them.

* [Atoms: choose your own](https://mkj69.github.io/opulse/guide/atoms/) shows how to register
  atoms with `register_primitive`, write a starting set and load it with `--plugin`.
* [Worlds](https://mkj69.github.io/opulse/worlds/) shows the worlds that exist and what each one
  contains.

A new world can come in as a plugin module, or as a starting set in `data/` with a config in
`configs/`. Please include a short page that states each atom's rule, a test that grows a few
operators from it and checks their derivations, and a z3 encoding for each atom if you want the
solver based analyses to cover it.

## Documentation

The site lives in `docs/` and is built with MkDocs Material. Build it before you open a pull
request; `--strict` turns warnings, including broken links between pages, into errors:

```bash
./tools/build_site.sh
```

The public site is English only. `./tools/build_site_local.sh` builds the English and Chinese
sites with language switchers for local use. The Chinese site is never published.

Style rules for every page:

* No dashes of any kind in prose: no em dash, en dash or hyphen joining words. Rewrite the
  sentence instead. Code, commands and flags are exempt.
* State facts with evidence: a number, a command, a link to a check. Leave out hype, filler and
  words that only sound impressive.
* No progress or roadmap wording. Describe what the code does now. The experiment ideas say
  plainly that none has been run yet; keep it that way until a result exists.

## Commits and pull requests

1. Fork the repository and create a branch from `main`.
2. Keep each commit to one change. Write the subject as `area: what changed`, for example
   `bench: score the first wrong rewrite` or `docs: clarify recursion bounds`.
3. Run the tests, the quick sweep, ruff on your files, and the docs builds if you touched docs.
4. Open a pull request that says what changed, why, and how you checked it. Link the issue or
   discussion it comes from.

Review happens in the pull request. A request for changes is part of the work, not a judgement
of you.

## Licences

By contributing, you agree that your code is released under the Apache License 2.0, and that
your documentation and data are released under the Creative Commons Attribution 4.0 International
licence (CC BY 4.0), the same terms as the rest of the project.

## Contributors

See the [GitHub contributors page](https://github.com/mkj69/opulse/graphs/contributors) for contributors; people whose ideas lead to experiments are credited by name in those experiments.

## Code of conduct

Everyone who takes part follows the [code of conduct](CODE_OF_CONDUCT.md).
