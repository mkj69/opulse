"""``opulse`` command line.

Commands
    atoms         export a built-in starting operator set
    operators     grow an operator set layer by layer (resumable)
    expressions   sample and evaluate expressions over an operator set
    corpus        write a sharded pretraining corpus and probe data
    verify        check operators/expressions against the reference semantics
    audit         compare legacy stored compute functions with their definitions
    audit-data    summarize datasets and check quality gates
    complexity    fit measured base-operation costs
    analyze       SMT-LIB export, dead branches and algebraic properties of operators
    interest      interestingness scores and behavioural duplicates of operators
    holes         fill-in-the-blank problems with checked solution sets
    equivalences  equivalent operators and expression pairs with checked labels
    bench         model-facing benchmark: build tasks, run a model, score
    discover      propose definitions and keep measured improvements; replay records
    integrations  task files for lm-evaluation-harness and Inspect
    describe      add bilingual operator descriptions
    env           multi-turn environments: play an episode, replay and score transcripts
    export        Hugging Face datasets, pretraining corpora and tokenizer files
    interp        model internals on Opulse expressions (nnsight)
    trace         derivation of one expression at a chosen granularity
    explain       formula, behaviour table and dependencies of one operator
    skeleton      extract typed structures and instantiate them in atom worlds
    viz           build a portable report for operators and expressions
    wizard        create a settings file with an optional preview
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from opulse.cli import (
    analyze,
    atoms,
    audit,
    audit_data,
    bench,
    complexity,
    corpus,
    describe,
    discover,
    env,
    equivalences,
    export,
    expressions,
    holes,
    integrations,
    interest,
    interp,
    operators,
    skeleton,
    trace,
    verify,
    viz,
    wizard,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="opulse", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--plugin", action="append", default=[], metavar="MODULE",
                        help="import a module (dotted name or .py file) that registers atoms; repeatable. "
                             "OPULSE_PLUGINS (comma-separated) is read as well")
    commands = parser.add_subparsers(dest="command", required=True)
    for module in (atoms, operators, expressions, corpus, verify, audit, audit_data, complexity, analyze, interest, holes,
                   equivalences, bench, export, integrations, describe, env, trace, viz, wizard, interp, discover,
                   skeleton):
        module.register(commands)
    # Plugins must be loaded before parsing: they can add atoms that commands refer to.
    plugins = [p for p in os.environ.get("OPULSE_PLUGINS", "").split(",") if p.strip()]
    raw = list(sys.argv[1:] if argv is None else argv)
    for i, token in enumerate(raw):
        if token == "--plugin" and i + 1 < len(raw):
            plugins.append(raw[i + 1])
        elif token.startswith("--plugin="):
            plugins.append(token.split("=", 1)[1])
    if plugins:
        from opulse.core.primitives import load_plugins

        load_plugins(plugins)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return args.run(args) or 0


if __name__ == "__main__":
    sys.exit(main())
