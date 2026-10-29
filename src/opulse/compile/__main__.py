"""``python -m opulse.compile [--n 16] [--json out.json]``: run the stitching experiment."""

from __future__ import annotations

import argparse
import json

from opulse.canary import marked
from opulse.compile.demo import format_results, run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m opulse.compile", description=__doc__)
    parser.add_argument("--n", type=int, default=16, help="inputs range over 0..n-1 (default 16)")
    parser.add_argument("--json", help="also write the full results to this file")
    parser.add_argument("--trained", action="store_true",
                        help="also train MLP stand-ins for two operators and stitch them (part c)")
    args = parser.parse_args(argv)
    results = run(args.n)
    print(format_results(results))
    if args.trained:
        from opulse.compile.demo import format_trained, run_trained

        results["trained"] = run_trained(args.n)
        print()
        print(format_trained(results["trained"]))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(marked(results), handle, ensure_ascii=False, indent=2)
    ok = all(row["verify"]["ok"] for row in results["operators"].values()) and all(
        entry[label]["verify"]["ok"] and entry["whole_equals_stitched"]
        for entry in results["stitching"].values() for label in ("whole", "stitched", "stitched_compact"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
