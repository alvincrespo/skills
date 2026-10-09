#!/usr/bin/env bash
# Symlinks every skill folder in this repo into the local Claude harness
# skill directories, so `git pull` here keeps installed skills current
# without a separate reinstall step.
#
# Discovers skill folders by presence of a SKILL.md, not a hardcoded list —
# this script needs no edits when a new skill folder is added. Safe to run
# with zero skill folders present: it just no-ops.
#
# Existing symlinks are replaced, so re-running is safe. Anything else
# already at a link's path (a real directory, such as a copy installed by
# hand) is skipped and reported, and the script exits 1: `ln -sfn` would
# otherwise put the link *inside* that directory rather than replacing it,
# and the old copy would keep loading. Nothing is ever deleted.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGETS=("$HOME/.claude/skills" "$HOME/.agents/skills")

found_any=0
skipped=0

for target in "${TARGETS[@]}"; do
  mkdir -p "$target"
done

for skill_md in "$REPO_ROOT"/*/SKILL.md; do
  [ -e "$skill_md" ] || continue
  found_any=1
  skill_dir="$(dirname "$skill_md")"
  skill_name="$(basename "$skill_dir")"
  for target in "${TARGETS[@]}"; do
    link="$target/$skill_name"
    if [ -e "$link" ] && [ ! -L "$link" ]; then
      echo "skip $skill_name: $link is a real directory, not a link. Move it aside and re-run." >&2
      skipped=1
      continue
    fi
    ln -sfn "$skill_dir" "$link"
    echo "linked $skill_name -> $link"
  done
done

if [ "$found_any" -eq 0 ]; then
  echo "No skill folders found yet (no top-level SKILL.md present) — nothing to link."
fi

exit "$skipped"
