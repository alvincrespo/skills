#!/usr/bin/env bash
# Creates a new GitHub repository from the current directory's
# contents, pushes it, and sets its topics. Ends there — run the
# github-labels-setup skill next to set up the repo's label taxonomy.
#
# Run with the project to publish as the current working directory — not
# from an empty directory, and not from wherever this script lives. Invoke
# the script by its own path:
#
#   /path/to/github-repo-init/scripts/setup_repo.sh <owner>/repo-name \
#       [--description "..."] [--topics "a,b,c"]
#
# If the project already has a .git directory it's used as-is, but it must
# have at least one commit and no `origin` remote — both are checked before
# anything is created on GitHub. Uncommitted changes are not pushed.
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
# Requires: gh CLI, authenticated (gh auth login), git.

set -euo pipefail

usage() {
  echo "Usage: $0 <owner>/repo-name [--description \"...\"] [--topics \"a,b,c\"]"
}

die() {
  echo "Error: $*" >&2
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
      exit 0
      ;;
    -*)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
    *)
      if [ -n "$REPO" ]; then
        echo "Unexpected argument: $1" >&2
        usage >&2
        exit 1
      fi
      REPO="$1"
      shift
      ;;
  esac
done

[ -n "$REPO" ] || { usage >&2; exit 1; }

# Split --topics on commas, trimming whitespace and dropping empty entries,
# so a bad list fails here rather than after the repo already exists.
IFS=',' read -ra TOPIC_LIST <<< "${TOPICS}"
TOPIC_ARGS=()
for topic in "${TOPIC_LIST[@]}"; do
  topic="${topic#"${topic%%[![:space:]]*}"}"
  topic="${topic%"${topic##*[![:space:]]}"}"
  if [ -n "${topic}" ]; then
    TOPIC_ARGS+=(--add-topic "${topic}")
  fi
done
[ "${#TOPIC_ARGS[@]}" -gt 0 ] || die "--topics contained no non-empty topics"

# Preflight: `gh repo create --source=. --remote=origin --push` creates the
# GitHub repo before it touches local git, so a local problem found only at
# that point leaves an empty repo behind on GitHub. Check first.
echo "==> Checking local git state"
if [ -e .git ]; then
  echo "    .git already exists — using it as-is, not re-initializing."
  git rev-parse --verify -q HEAD >/dev/null \
    || die "this repository has no commits yet; commit something before publishing"
  if git remote get-url origin >/dev/null 2>&1; then
    die "an 'origin' remote already exists ($(git remote get-url origin)); remove or rename it first"
  fi
  if [ -n "$(git status --porcelain)" ]; then
    echo "    Warning: uncommitted changes present — they will NOT be pushed."
  fi
else
  git init
  git add -A
  git commit -m "Initial commit"
fi

echo "==> Creating ${REPO} on GitHub and pushing this content"
gh repo create "${REPO}" \
  --public \
  --description "${DESCRIPTION}" \
  --source=. \
  --remote=origin \
  --push

echo "==> Setting repository topics"
gh repo edit "${REPO}" "${TOPIC_ARGS[@]}"

echo ""
echo "==> Repo ready."
echo "    Repo:    https://github.com/${REPO}"
echo ""
echo "Next: run the github-labels-setup skill to set up this repo's label"
echo "taxonomy."
echo ""
echo "Still manual, on purpose:"
echo "  - Branch protection on main (no CI check to require yet)"
echo "  - A pre-push secret scan of the initial commit (gitleaks or trufflehog)"
echo "    before you trust this content is safe on a public remote"
