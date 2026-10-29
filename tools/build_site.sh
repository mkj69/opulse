#!/usr/bin/env bash
# Build the English public site and fail on broken documentation links.
set -euo pipefail
cd "$(dirname "$0")/.."
OPULSE_PYTHON="${OPULSE_PYTHON:-python}"
# Refresh the Python files the playground page runs in the browser (a no-op when they match src/).
PYTHONPATH="$PWD/src" "$OPULSE_PYTHON" tools/build_playground.py
PYTHONPATH="$PWD/src" "$OPULSE_PYTHON" -m mkdocs build --strict --clean -f mkdocs.yml
touch site/.nojekyll
echo "built English site/"
