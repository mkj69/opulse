# Installation

Opulse needs Python 3.10 or newer.

```bash
git clone https://github.com/mkj69/opulse.git && cd opulse
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

This installs the `opulse` command and its dependencies, including `z3-solver`, a solver used for some checks. See the [glossary](../glossary.md) for related terms.

## Optional extras

| Extra | Command | Adds |
| --- | --- | --- |
| Cython runtime | `pip install -e ".[cython]"` | compiled operators for large datasets (`--cython-build-dir`) |
| Documentation | `pip install -e ".[docs]"` | build this site with `mkdocs serve` |
| Interpretability | `pip install -e ".[interp]"` | activation collection, probes, and patching |

## Check the installation

```bash
opulse --help
python -m pytest -q          # the test suite
python tools/sweep.py --quick
```
