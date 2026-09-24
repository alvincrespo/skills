#!/usr/bin/env bash
# Packages the skills that work on their own as standalone .skill files,
# using skill-creator's package_skill.py. Output goes to dist/ (gitignored).
#
# Only skills that are fully self-contained AND safe to model-invoke are
# packaged. Everything else ships only via the plugin, where all four
# skills are installed side by side:
#   - project-epic-planner reuses github-project-bootstrap's plan loader
#     and github-labels-setup's default labels (ADR 0001: no duplication).
#   - github-project-bootstrap shells out to github-labels-setup's script.
#   - github-repo-init and github-project-bootstrap set
#     disable-model-invocation (ADR 0002), which package_skill.py's
#     validator rejects, and which a .skill install wouldn't enforce anyway.
# Add a skill to STANDALONE only if none of that applies to it.
#
# Usage:
#   scripts/package-standalone-skills.sh
#
# Finds package_skill.py in the official skill-creator plugin install; set
# SKILL_CREATOR_DIR to the skill-creator skill folder (the one containing
# scripts/package_skill.py) to use a different copy.

set -euo pipefail

STANDALONE=(github-labels-setup)

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST="$REPO_ROOT/dist"
SKILL_CREATOR_DIR="${SKILL_CREATOR_DIR:-$HOME/.claude/plugins/marketplaces/claude-plugins-official/plugins/skill-creator/skills/skill-creator}"

if [ ! -f "$SKILL_CREATOR_DIR/scripts/package_skill.py" ]; then
  echo "Error: package_skill.py not found under $SKILL_CREATOR_DIR/scripts/" >&2
  echo "Install the skill-creator plugin, or set SKILL_CREATOR_DIR." >&2
  exit 1
fi

mkdir -p "$DIST"
for skill in "${STANDALONE[@]}"; do
  # package_skill.py imports `scripts.quick_validate`, so it must run as a
  # module from the skill-creator folder.
  (cd "$SKILL_CREATOR_DIR" && python3 -m scripts.package_skill "$REPO_ROOT/$skill" "$DIST")
done
