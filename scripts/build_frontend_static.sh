#!/usr/bin/env bash
# Rebuilds the plugin's frontend static assets and stages the result.
#
# The InvenTree production Docker image has no Node/npm installed (only the
# `dev`/`builder` build stages do - see contrib/container/Dockerfile in the
# InvenTree repo), so relying on a build step at plugin-install time (e.g.
# `pip install -e .` triggered via plugins.txt) does not work. Instead, the
# built reichelt_auto_import/static/ output is committed to git directly, and
# this script (wired up as a pre-commit hook) keeps it in sync with the
# frontend source automatically.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${repo_root}/frontend"

npm install --no-audit --no-fund
npm run build

cd "${repo_root}"
git add reichelt_auto_import/static

if ! git diff --cached --quiet -- reichelt_auto_import/static; then
    echo "Rebuilt frontend static assets (reichelt_auto_import/static) - review and re-commit."
    exit 1
fi
