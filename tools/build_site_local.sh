#!/usr/bin/env bash
# Build both local language sites with their switchers.
set -euo pipefail
cd "$(dirname "$0")/.."
OPULSE_PYTHON="${OPULSE_PYTHON:-python}"
PYTHONPATH="$PWD/src" "$OPULSE_PYTHON" tools/build_playground.py
PYTHONPATH="$PWD/src" "$OPULSE_PYTHON" -m mkdocs build --strict -f mkdocs.local.yml
PYTHONPATH="$PWD/src" "$OPULSE_PYTHON" -m mkdocs build --strict -f mkdocs.zh.yml
echo "built local site/ and site/zh/"
