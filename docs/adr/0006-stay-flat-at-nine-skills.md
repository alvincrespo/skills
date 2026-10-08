# ADR 0006: Stay flat at nine skills

## Status
Accepted

## Context
Every skill is a top-level folder. `PROJECT_PLAN.md` §7 deferred "bucket
folders (`engineering/`, `misc/`, etc.)" until "a genuinely different
domain of skill shows up", and `.claude/CLAUDE.md` repeated that as the
trigger to revisit.

That trigger has now fired three times:
- `axc-og-cards` generates Open Graph images (ADR 0003).
- The four `axc-cut-release*` skills, being imported for the "Release
  skills shipped" milestone, are release tooling.
- #66 plans `axc-dependabot-sweep`, for dependency maintenance.

That's nine skills once the release skills land, and ten after #66, across
four domains: the GitHub project pipeline, images, releases and
dependencies.

## Decision
Stay flat. Every skill remains a top-level folder, and none move.

## Reasoning
The layout is cheap to keep and expensive to change. Moving to buckets
would break every path that assumes skills sit one level down. As of
this ADR, that's:

| Where | What assumes one level |
|---|---|
| `.claude-plugin/plugin.json` | Each `skills` entry is `./<skill>` |
| `scripts/link-skills.sh` | Discovers skills with `"$REPO_ROOT"/*/SKILL.md`, and names each link after the folder |
| `scripts/package-standalone-skills.sh` | Packages `"$REPO_ROOT/$skill"` |
| `github-project-bootstrap/scripts/bootstrap_github_project.py` | Finds `github-labels-setup` at `Path(__file__).parent.parent.parent / "github-labels-setup"` |
| `project-epic-planner/scripts/render_plan.py` | `SKILLS_ROOT = Path(__file__).parent.parent.parent`, then finds `github-project-bootstrap` and `github-labels-setup` under it |
| `project-epic-planner/scripts/test_render_plan.py` | Finds `github-project-bootstrap/docs/pr-agent-tracker.json` the same way |
| `project-epic-planner/SKILL.md` and `references/*.md` | Relative links to `../github-project-bootstrap/…` and `../../github-project-bootstrap/…` |
| `.claude/release.json` and `.github/workflows/release.yml` | List each Python test file by `<skill>/scripts/…` path, and run `npm … --prefix axc-og-cards` |
| `scripts/e2e/axc-og-cards/` | `run.mjs` uses `path.join(REPO_ROOT, "axc-og-cards")`; `cases.mjs` imports `../../../axc-og-cards/scripts/lib/plan.mjs` |
| `axc-cut-release*` (planned in #94) | The sub-skills call the router's script as `${CLAUDE_SKILL_DIR}/../axc-cut-release/scripts/release_tool.py` |

Install paths depend on it too. The plugin, `npx skills add` and
`scripts/link-skills.sh` all install skills side by side under a single
directory. That's what makes the `../<sibling>` lookups above work once
installed, so the skills would keep a flat install layout even if the
repo used buckets. The repo layout would then differ from the install
layout, and every sibling lookup would need a different path in the repo
than when installed.

Buckets also don't fix a real problem yet:
- At nine or ten skills, the README's Skills list can be read top to
  bottom.
- Names already group the skills. The `github-*` skills are the pipeline,
  and the `axc-` prefix marks personal-workflow skills (`axc-og-cards`,
  `axc-cut-release*`, and `axc-dependabot-sweep` to come).

## Consequences
- New skills keep going in as top-level folders, and `scripts/link-skills.sh`
  keeps finding them with no edits.
- Revisit this decision when either happens:
  1. The plugin lists **more than 15 skills** (count the `skills` array in
     `.claude-plugin/plugin.json`).
  2. Two skills in different domains need the same folder name.
- A move to buckets would mean updating every row of the table above, so
  check it against the repo again first (`git grep -n
  'parent.parent.parent\|\.\./[a-z-]*/\|REPO_ROOT' -- '*.py' '*.sh' '*.mjs' '*.md'`
  is a starting point).
- `.claude/CLAUDE.md` points to this ADR instead of carrying its own
  revisit rule.
