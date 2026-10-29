"""Write an auditable summary of the published world selections."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs/assets/data/worlds"
REPORT = ROOT / "docs/worlds/curation-report.md"
ORDER = ("successor", "integer", "clock", "bits", "strings", "lists", "logic",
         "perm", "rel", "grid", "pitch", "action")


def main() -> None:
    lines = ["# World curation report", "",
             "Counts use the default seed of each world. Rejection rules run in exporter order, so each rejected operator has one primary reason. Other eligible operators were left out to keep the list short.", "",
             "Rejected rules: **undefined** has no defined example; **constant** or **near constant** has one output on all or at least 85% of probes; **unused argument** has no observed input effect; **atom equivalent**, **duplicate**, and **shape duplicate** repeat an atom, a shown value table, or a numeric pattern shifted by a constant; **cancelled constant** and **alias** contain an inert arithmetic or direct wrapper; **bad helper** depends on one of those rules; **long sentence** exceeds 22 words; **opaque sentence** hides its operation behind a summary or too many helpers, or uses a contrived self shift, remainder, or large repeat seed. Action additionally uses **no effect** for state transitions that never change the state.", ""]
    lines.extend(["Core worlds use `opulse.generation.interest` scores for every grown operator. Action skills use a sampled state-change score because the core fingerprinter has no state probe type.", ""])
    for world in ORDER:
        data = json.loads((DATA / f"{world}.json").read_text(encoding="utf-8"))
        rows = {row["name"]: row for row in data["operators"]}
        lines.extend([f"## {data['title']}", "",
                      f"Grown: **{len(rows)}**. Curated: **{len(data['curated'])}**. "
                      f"Eligible but not selected: **{data['curation_not_selected']}**.", "",
                      "| Rejection rule | Count |", "| --- | ---: |"])
        for reason, count in data["curation_rejected"].items():
            lines.append(f"| {reason.replace('_', ' ')} | {count} |")
        lines.extend(["", "Top eight:", ""])
        for name in data["curated"][:8]:
            lines.append(f"- **{name}** — {rows[name]['plain']}")
        lines.append("")
    REPORT.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
