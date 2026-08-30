#!/usr/bin/env bash
# Creates the alvincrespo/skills GitHub repository from this directory's
# contents, then bootstraps labels, milestone, project board, and all 34
# epic/story issues.
#
# Run from inside this project directory (the one containing this
# scripts/ folder, tracker/, docs/, README.md, etc.) — not from an
# empty directory.
#
#   ./scripts/setup_repo.sh <owner>/skills
#
# Requires: gh CLI, authenticated (gh auth login), git, python3.

set -euo pipefail

REPO="${1:?Usage: ./scripts/setup_repo.sh <owner>/repo-name}"
DESCRIPTION="A small, growing collection of Claude Skills for real engineering workflows."

echo "==> Checking for uncommitted local git history"
if [ -d .git ]; then
  echo "    .git already exists — using it as-is, not re-initializing."
else
  git init
  git add -A
  git commit -m "Initial commit: skills repo scaffolding + tracker"
fi

echo "==> Creating ${REPO} on GitHub and pushing this content"
gh repo create "${REPO}" \
  --public \
  --description "${DESCRIPTION}" \
  --source=. \
  --remote=origin \
  --push

echo "==> Setting repository topics"
gh repo edit "${REPO}" \
  --add-topic claude-skills \
  --add-topic claude-code \
  --add-topic ai-agent-tooling \
  --add-topic github-automation

echo "==> Requesting the 'project' OAuth scope (needed to create/populate a Project v2 board)"
gh auth refresh -s project

echo "==> Bootstrapping labels, milestone, project board, and all epics/issues"
python3 scripts/bootstrap_github_project.py --repo "${REPO}"

echo ""
echo "==> Done."
echo "    Repo:    https://github.com/${REPO}"
echo ""
echo "Still manual, on purpose:"
echo "  - Branch protection on main (no CI check to require yet)"
echo "  - A pre-push secret scan of the initial commit (gitleaks or trufflehog)"
echo "    before you trust this content is safe on a public remote"
echo "  - .claude-plugin/plugin.json and marketplace.json — deliberately NOT"
echo "    created by this script. See the 'Create plugin manifests and"
echo "    validate' issue: the schema needs confirming against current"
echo "    Claude Code docs, not assumed from memory."
