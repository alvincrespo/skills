#!/usr/bin/env bash
# Tests scripts/link-skills.sh against a throwaway HOME, so the real
# ~/.claude/skills and ~/.agents/skills are never touched.
#
#   scripts/test-link-skills.sh
#
# Exits 0 if every check passes, 1 otherwise.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LINK="$REPO_ROOT/scripts/link-skills.sh"
fail=0

# check <description> <command...>: runs the command, reports ✓ or ✗.
check() {
  local description="$1"
  shift
  if "$@"; then echo "✓ $description"; else echo "✗ $description"; fail=1; fi
}

# links_to <link> <expected target>
# shellcheck disable=SC2329  # called indirectly, through check "$@"
links_to() {
  [ -L "$1" ] && [ "$(readlink "$1")" = "$2" ]
}

# run_link: runs link-skills.sh, capturing its output and exit status.
run_link() {
  set +e
  output="$("$LINK" 2>&1)"
  status=$?
  set -e
}

HOME="$(mktemp -d)"
export HOME
trap 'rm -rf "$HOME"' EXIT
skills="$HOME/.claude/skills"
real_dir="$skills/github-labels-setup"

# A real directory where github-labels-setup's link would go, standing in
# for a copy installed by hand.
mkdir -p "$real_dir"
echo "hand-installed copy" > "$real_dir/marker.txt"

run_link
check "first run exits 1" [ "$status" -eq 1 ]
check "prints the skip line" grep -q "^skip github-labels-setup: $real_dir exists and isn't a symlink" <<<"$output"
check "real directory is still a real directory" [ -d "$real_dir" ]
check "real directory is not a link" [ ! -L "$real_dir" ]
check "real directory holds only its original file" [ "$(ls -A "$real_dir")" = "marker.txt" ]
check "real directory's file is unchanged" grep -qx "hand-installed copy" "$real_dir/marker.txt"
check "no link nested inside it" [ ! -e "$real_dir/github-labels-setup" ]

for skill_md in "$REPO_ROOT"/*/SKILL.md; do
  name="$(basename "$(dirname "$skill_md")")"
  [ "$name" = "github-labels-setup" ] && continue
  for target in "$HOME/.claude/skills" "$HOME/.agents/skills"; do
    check "$name linked in ${target#"$HOME"/}" links_to "$target/$name" "$REPO_ROOT/$name"
  done
done
check "github-labels-setup still linked in .agents/skills" \
  links_to "$HOME/.agents/skills/github-labels-setup" "$REPO_ROOT/github-labels-setup"

# A stray file at a link's path is skipped too, never replaced (ln -sfn
# would delete it).
stray="$HOME/.agents/skills/project-epic-planner"
rm "$stray"
echo "stray file" > "$stray"
run_link
check "stray file: run exits 1" [ "$status" -eq 1 ]
check "stray file: skip line names it" grep -q "^skip project-epic-planner: $stray exists and isn't a symlink" <<<"$output"
check "stray file: left in place, unchanged" grep -qx "stray file" "$stray"
rm "$stray"

# With the directory moved aside, a second run links it and succeeds.
rm -rf "$real_dir"
run_link
check "second run exits 0" [ "$status" -eq 0 ]
check "github-labels-setup now linked" links_to "$real_dir" "$REPO_ROOT/github-labels-setup"

# Re-running over existing links is still safe.
run_link
check "third run (all links already present) exits 0" [ "$status" -eq 0 ]

exit "$fail"
