"""MkDocs hooks: make the ``opulse`` Pygments lexer available to code blocks.

An installed Opulse registers the lexer through its ``pygments.lexers`` entry point.
The documentation is often built from a source checkout instead, so this hook puts
``src/`` on the path and registers the lexer before any page is rendered.
"""

from __future__ import annotations

import sys
import json
from pathlib import Path
from shutil import copyfile

SRC = Path(__file__).resolve().parents[1] / "src"
ROOT = SRC.parent


def on_config(config):
    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))
    from opulse.display.pygments_lexer import register

    register()
    return config


def on_post_build(config):
    """Localize the Chinese site and remove Chinese data from the public site."""
    if Path(config.docs_dir).resolve() == ROOT / "docs_zh":
        localized = ROOT / "docs_zh" / "snippets" / "localized_assets"
        site_assets = Path(config.site_dir) / "assets"
        for source in localized.rglob("*"):
            if source.is_file():
                copyfile(source, site_assets / source.relative_to(localized))
        return

    if (Path(config.config_file_path).resolve() != ROOT / "mkdocs.yml"
            or config.theme["language"] != "en"
            or config.get("extra", {}).get("translated_paths")):
        return

    def english_only(value):
        if isinstance(value, dict):
            return {key: english_only(item) for key, item in value.items()
                    if key != "zh" and not key.endswith("_zh")}
        if isinstance(value, list):
            return [english_only(item) for item in value]
        return value

    for path in (Path(config.site_dir) / "assets" / "data").rglob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        path.write_text(json.dumps(english_only(data), ensure_ascii=False,
                                   separators=(",", ":")) + "\n", encoding="utf-8")
