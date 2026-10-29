"""Regenerate every world showcase under docs/assets/data/worlds.

    python tools/docs_worlds.py                 # every world
    python tools/docs_worlds.py grid pitch      # some worlds; index.json still lists all
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from opulse.worlds.showcase import WORLD_IDS, export_world
from opulse.worlds.showcase_tasks import export_tasks

ORDER = ("successor", "integer", "clock", "bits", "strings", "lists", "logic", "perm", "rel", "grid",
         "pitch", "action")


def main(selected: list[str]) -> None:
    directory = Path(__file__).resolve().parents[1] / "docs/assets/data/worlds"
    directory.mkdir(parents=True, exist_ok=True)
    if selected and selected[0] == "--tasks":
        for world in selected[1:] or ORDER:
            start = time.time()
            export_tasks(world, directory)
            print(world, "tasks", f"{time.time() - start:.0f}s", flush=True)
        return
    for world in selected or ORDER:
        start = time.time()
        if world in WORLD_IDS:
            data = export_world(world, directory)[0]
        else:
            from opulse.worlds.action import export_world_showcase

            data = export_world_showcase(world, directory / f"{world}.json")
        export_tasks(world, directory)
        print(world, f"{time.time() - start:.0f}s", "grown", len(data["operators"]),
              "curated", len(data["curated"]), "rejected", data["curation_rejected"], flush=True)
    index = []
    for world in ORDER:
        data = json.loads((directory / f"{world}.json").read_text(encoding="utf-8"))
        summary, summary_zh = SUMMARIES[world]
        index.append({"world": world, "title": data["title"], "title_zh": data.get("title_zh", data["title"]),
                      "dimension": data["dimension"], "summary": summary, "summary_zh": summary_zh})
    (directory / "index.json").write_text(json.dumps(index, ensure_ascii=False))
    if __package__:
        from .world_curation_report import main as write_curation_report
    else:
        from world_curation_report import main as write_curation_report

    write_curation_report()


SUMMARIES = {
    "successor": ("counting up from zero", "从零往上数"),
    "integer": ("integer arithmetic", "整数运算"),
    "clock": ("arithmetic on a 12 hour dial", "12 格表盘上的运算"),
    "bits": ("bit patterns and shifts", "二进制位和移位"),
    "strings": ("characters and words", "字符和单词"),
    "lists": ("lists of integers", "整数列表"),
    "logic": ("true and false", "真与假"),
    "perm": ("shuffling five cards", "洗五张卡片"),
    "rel": ("a table of people", "一张人物关系表"),
    "grid": ("coloured grids up to 10×10", "最大 10×10 的彩色网格"),
    "pitch": ("notes and melodies", "音符和旋律"),
    "action": ("a robot on a block map", "积木地图上的机器人"),
}


if __name__ == "__main__":
    main(sys.argv[1:])
