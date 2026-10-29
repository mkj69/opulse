"""``opulse audit-data``: report dataset contents and check release gates."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from opulse.analysis.audit import audit_data


def _share(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or not 0 <= number <= 1:
        raise argparse.ArgumentTypeError("share must be between 0 and 1")
    return number


def register(commands) -> None:
    cmd = commands.add_parser("audit-data", help="summarize expression or benchmark JSONL and check quality gates")
    cmd.add_argument("files", nargs="+", type=Path, help="expression or benchmark JSONL files")
    cmd.add_argument("--out", type=Path, required=True, help="write the JSON report here")
    cmd.add_argument("--operators", type=Path, help="operator JSONL for usage coverage")
    cmd.add_argument("--max-duplicate-share", type=_share, default=0.01)
    cmd.add_argument("--max-most-common-answer-share", type=_share, default=0.2)
    cmd.add_argument("--max-cross-file-overlap", type=_share, default=0.0)
    cmd.add_argument("--no-require-uniform-provenance", action="store_false",
                     dest="require_uniform_provenance", help="allow mixed operator sets or configs")
    cmd.set_defaults(run=run)


def run(args) -> int:
    from opulse.canary import marked

    report = audit_data(args.files, args.operators, max_duplicate_share=args.max_duplicate_share,
                        max_common_answer_share=args.max_most_common_answer_share,
                        max_cross_file_overlap=args.max_cross_file_overlap,
                        require_uniform_provenance=args.require_uniform_provenance)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(marked(report), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Audited {report['counts']['total']} records in {len(args.files)} file(s).")
    answers = report["answers"]
    print(f"Undefined: {answers['undefined_count']} ({answers['undefined_share']:.1%}); "
          f"distinct defined answers: {answers['distinct']}; most common: {answers['most_common_share']:.1%}.")
    for name, axis in report["axes"].items():
        print(f"{name}: n={axis['count']}, min={axis['min']}, median={axis['median']}, "
              f"p90={axis['p90']}, max={axis['max']}.")
    for item in report["files"]:
        duplicates = item["duplicates"]
        print(f"{item['path']}: {item['count']} {item['kind']} records; "
              f"duplicate trees {duplicates['trees']['count']}, prompts {duplicates['prompts']['count']}.")
    if report["operator_coverage"]:
        coverage = report["operator_coverage"]
        print(f"Defined operators used: {coverage['used_count']}/{coverage['defined_total']}; "
              f"usage Gini: {coverage['gini']:.3f}.")
        for layer, counts in coverage["by_layer"].items():
            print(f"  layer {layer}: {counts['used']}/{counts['defined']} used")
    print(f"Cross-file overlap: {report['overlap']['max_share']:.1%}; "
          f"uniform provenance: {report['provenance']['uniform']}.")
    print("Quality gates: " + ("PASS" if report["gates"]["passed"] else
                               "FAIL (" + ", ".join(report["gates"]["failures"]) + ")"))
    print(f"Report: {args.out}")
    return 0 if report["gates"]["passed"] else 1
