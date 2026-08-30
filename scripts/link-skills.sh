#!/usr/bin/env bash
# Symlinks every skill folder in this repo into the local Claude harness
# skill directories, so `git pull` here keeps installed skills current
# without a separate reinstall step.
#
# Discovers skill folders by presence of a SKILL.md, not a hardcoded list —
# this script needs no edits when a new skill folder is added. Safe to run
# with zero skill folders present (today's state): it just no-ops.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGETS=("$HOME/.claude/skills" "$HOME/.agents/skills")

found_any=0

for target in "${TARGETS[@]}"; do
  mkdir -p "$target"
done

for skill_md in "$REPO_ROOT"/*/SKILL.md; do
  [ -e "$skill_md" ] || continue
  found_any=1
  skill_dir="$(dirname "$skill_md")"
  skill_name="$(basename "$skill_dir")"
  for target in "${TARGETS[@]}"; do
    ln -sfn "$skill_dir" "$target/$skill_name"
    echo "linked $skill_name -> $target/$skill_name"
  done
done

if [ "$found_any" -eq 0 ]; then
  echo "No skill folders found yet (no top-level SKILL.md present) — nothing to link."
fi
