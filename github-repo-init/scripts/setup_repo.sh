#!/usr/bin/env bash
# Creates the alvincrespo/skills GitHub repository from this directory's
# contents, then bootstraps labels, milestone, project board, and all 34
# epic/story issues.
#
# Run from inside this project directory (the one containing this
# github-repo-init/scripts/ folder, tracker/, docs/, README.md, etc.) —
# not from an empty directory.
#
#   ./github-repo-init/scripts/setup_repo.sh <owner>/repo-name \
#       [--description "..."] [--topics "a,b,c"]
#
#   --description <text>   Repo description passed to `gh repo create`.
#                           Default: "A small, growing collection of
#                           Claude Skills for real engineering workflows."
#   --topics <a,b,c>        Comma-separated topics passed to
#                           `gh repo edit --add-topic`.
#                           Default: claude-skills,claude-code,
#                           ai-agent-tooling,github-automation
#
# Omitting either flag falls back to its documented default above rather
# than erroring.
#
# Requires: gh CLI, authenticated (gh auth login), git, python3.

set -euo pipefail

usage() {
  echo "Usage: $0 <owner>/repo-name [--description \"...\"] [--topics \"a,b,c\"]" >&2
  exit 1
}

DESCRIPTION="A small, growing collection of Claude Skills for real engineering workflows."
TOPICS="claude-skills,claude-code,ai-agent-tooling,github-automation"
REPO=""

while [ $# -gt 0 ]; do
  case "$1" in
    --description)
      DESCRIPTION="${2:?--description requires a value}"
      shift 2
      ;;
    --topics)
      TOPICS="${2:?--topics requires a value}"
      shift 2
      ;;
    -h|--help)
      usage
      ;;
    -*)
      echo "Unknown option: $1" >&2
      usage
      ;;
    *)
      if [ -n "$REPO" ]; then
        echo "Unexpected argument: $1" >&2
        usage
      fi
      REPO="$1"
      shift
      ;;
  esac
done

[ -n "$REPO" ] || usage

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
IFS=',' read -ra TOPIC_LIST <<< "${TOPICS}"
TOPIC_ARGS=()
for topic in "${TOPIC_LIST[@]}"; do
  TOPIC_ARGS+=(--add-topic "${topic}")
done
gh repo edit "${REPO}" "${TOPIC_ARGS[@]}"

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
