#!/usr/bin/env bash
#
# Build the site locally and publish it to the gh-pages branch.
#
# github.mit.edu has Actions disabled, so there's nothing to build the site
# there. Pages is enabled, though, so it will happily serve a branch — this
# script fills that gap by building here and pushing the output up.
#
# Knobs (all env-overridable):
#   BASE_URL       URL the site will be served at
#   DEPLOY_REMOTE  remote to publish to (default: origin)
#   DEPLOY_BRANCH  branch to publish to (default: gh-pages)
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# github.mit.edu runs without subdomain isolation, so Pages serves from a path
# on the main host. The pages.github.mit.edu form resolves but has no valid
# cert, which silently breaks every asset link — don't switch back to it.
BASE_URL="${BASE_URL:-https://github.mit.edu/pages/MIT-Cycling/cycling.mit.edu/}"
DEPLOY_REMOTE="${DEPLOY_REMOTE:-origin}"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-gh-pages}"

# Resolved here because the staging repo below has no remotes of its own.
REMOTE_URL="$(git remote get-url "$DEPLOY_REMOTE")"

SRC_SHA="$(git rev-parse --short HEAD)"
# Scoped past the results file: fetch_results.py rewrites it on every run, so
# its churn is expected and says nothing about uncommitted source edits.
if ! git diff-index --quiet HEAD -- ':!data/race_results_live.json' 2>/dev/null; then
  SRC_SHA="${SRC_SHA}-dirty"
  echo "WARNING: working tree has uncommitted changes; deploying them anyway."
fi

echo "Fetching race results..."
if ! python3 scripts/fetch_results.py; then
  echo "WARNING: results fetch failed; building with whatever is in data/."
fi

# Build straight into the staging dir rather than public/: hugo doesn't clean
# its destination by default, so a fresh dir is what keeps deleted pages from
# lingering — and it keeps a .git out of public/.
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

echo "Building site (baseURL: $BASE_URL)..."
hugo --minify --baseURL "$BASE_URL" -d "$STAGE"

echo "Publishing to $DEPLOY_REMOTE/$DEPLOY_BRANCH..."
cd "$STAGE"
touch .nojekyll
git init -q -b "$DEPLOY_BRANCH"
git add -A
git commit -q -m "Deploy $SRC_SHA"
git push -q --force "$REMOTE_URL" "$DEPLOY_BRANCH"

echo "Done. $BASE_URL"
