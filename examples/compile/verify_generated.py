"""Compile every operator of a generated set and check each network against the interpreter.

    opulse operators --out ops.jsonl --layers 20 10 6 --seed 3
    python examples/compile/verify_generated.py ops.jsonl --n 8

Prints one line per operator (layers, blocks, non-zero weights, exact and OOV outputs on the
domain, wrong slots, wrong outputs) and a summary. Needs torch.
"""

from __future__ import annotations

import argparse
import itertools
import time
from collections import Counter

from opulse.compile import CompileError, Compiler, Vocab
from opulse.compile.network import build_network
from opulse.compile.verify import verify
from opulse.core import OperatorRegistry
from opulse.verify import Oracle


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("operators", help="operator JSONL file")
    parser.add_argument("--n", type=int, default=8, help="inputs range over 0..n-1")
    parser.add_argument("--lo", type=int, help="smallest slot value (default -2n)")
    parser.add_argument("--hi", type=int, help="largest slot value (default 2n-1)")
    parser.add_argument("--max-blocks", type=int, default=5000)
    args = parser.parse_args()
    registry = OperatorRegistry.from_jsonl(args.operators)
    oracle = Oracle(registry)
    vocab = Vocab(-2 * args.n if args.lo is None else args.lo, 2 * args.n - 1 if args.hi is None else args.hi)
    compiler = Compiler(oracle, vocab, max_blocks=args.max_blocks)
    totals = Counter()
    print("symbol kind layers blocks nonzero exact oov slot_wrong output_wrong seconds")
    for op in registry:
        if op.definition is None:
            continue
        start = time.time()
        try:
            network = build_network(compiler.compile(op))
        except CompileError as error:
            totals["not compiled"] += 1
            print(op.symbol, op.definition_type, "not compiled:", error)
            continue
        rows = list(itertools.product(range(args.n), repeat=op.n_ary))
        report = verify(network, oracle, rows, lambda row, op=op: oracle.evaluate(op, row).value)
        stats = network.stats()
        totals["operators"] += 1
        totals["ok"] += report.ok
        totals["exact on whole domain"] += report.exact
        totals["exact outputs"] += report.output_exact
        totals["oov outputs"] += report.output_oov
        totals["wrong outputs"] += report.output_wrong
        totals["wrong slots"] += report.slot_wrong
        totals["slot checks"] += report.slot_checks
        print(op.symbol, op.definition_type, stats["layers"], stats["blocks"], stats["nonzero_params"],
              report.output_exact, report.output_oov, report.slot_wrong, report.output_wrong,
              f"{time.time() - start:.1f}")
    print(dict(totals))
    return 0 if totals["wrong outputs"] == 0 and totals["wrong slots"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
