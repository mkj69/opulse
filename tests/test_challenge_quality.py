"""Global value and uniqueness contract for the published Challenge page."""

import json
from pathlib import Path

from tools.challenge_quality import validate_global


ROOT = Path(__file__).resolve().parents[1]


def test_all_53_puzzles_have_distinct_shapes_varied_answers_and_specific_reveal_notes():
    rows = []
    for name in ("challenges", "expert", "legend"):
        data = json.loads((ROOT / "docs/assets/data/challenge" / f"{name}.json").read_text(encoding="utf-8"))
        assert data["schema"] == "opulse.challenge/1"
        rows.extend(data["challenges"])
    validate_global(rows)
    advanced = [row for row in rows if row["level"] in ("expert", "master")]
    assert all(abs(row["variant"]["answer"] - row["answer"]) >= 3 for row in advanced)
    edits = {(row["set"]["name"], row["variant"]["rule_id"],
              tuple(sorted((row["answer"], row["variant"]["answer"])))) for row in advanced}
    assert len(edits) == len(advanced)
    small = [row for row in rows if row["level"] in ("easy", "medium", "hard")]
    assert sum(row["question"].lstrip().startswith(("-", "+", "#", "&")) for row in small) <= 3
    for level in ("easy", "medium", "hard"):
        assert sum(row["question"].lstrip().startswith(("-", "+", "#", "&"))
                   for row in small if row["level"] == level) <= 2
