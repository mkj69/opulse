#!/usr/bin/env bash
# Publish the English site built from mkdocs.yml.
set -euo pipefail
cd "$(dirname "$0")/.."
author_name=$(git config user.name || true)
author_email=$(git config user.email || true)
if [ -z "$author_name" ] || [ -z "$author_email" ]; then
  echo 'Configure git user.name and user.email before deploying.' >&2
  exit 2
fi

remote="${1:-$(git remote get-url origin 2>/dev/null || true)}"
if [ -z "$remote" ]; then
  echo 'Pass the GitHub repository URL, or configure an origin remote.' >&2
  exit 2
fi
./tools/build_site.sh
if [ -e site/zh ]; then
  echo 'The public build contains a Chinese site; refusing to publish it.' >&2
  exit 1
fi

publish_dir="$(mktemp -d)"
trap 'rm -rf "$publish_dir"' EXIT
git -C "$publish_dir" init -q
git -C "$publish_dir" remote add origin "$remote"
if git -C "$publish_dir" ls-remote --exit-code origin refs/heads/gh-pages >/dev/null; then
  git -C "$publish_dir" fetch -q origin gh-pages
  git -C "$publish_dir" checkout -q -b gh-pages FETCH_HEAD
  git -C "$publish_dir" rm -qr --ignore-unmatch .
else
  git -C "$publish_dir" checkout -q --orphan gh-pages
fi
cp -a site/. "$publish_dir/"
touch "$publish_dir/.nojekyll"
git -C "$publish_dir" add -A
if git -C "$publish_dir" diff --cached --quiet; then
  echo 'Site output is unchanged.'
  exit 0
fi
git -C "$publish_dir" -c user.name="$author_name" -c user.email="$author_email" \
  commit -qm 'Publish Opulse documentation'
git -C "$publish_dir" push origin gh-pages
