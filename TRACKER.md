# TRACKER.md — how this project is tracked

Same pattern as `pr-agent`: `PROJECT_PLAN.md` is the narrative version,
`tracker/issues.py` is the version meant to actually run — 6 epics, 27
child issues, and one release-validation issue, structured for GitHub
Issues + Projects (v2) with real sub-issue and blocked-by relationships.

## Set it up (one time)

```bash
gh auth login
gh auth refresh -s project        # project scope isn't in gh's default scopes

python3 scripts/setup_repo.sh alvincrespo/skills
```

That single script call creates the repo, pushes this content, sets
topics, and bootstraps labels, milestone, project board, and all 34
issues — same as `pr-agent`'s `setup_repo.sh`, adapted for this repo.

## The epic → issue map

The table below is a summary. **For the actual content of every issue —
title, body, full acceptance criteria — see [`ISSUES.md`](./ISSUES.md).**
That's what `scripts/bootstrap_github_project.py` turns into 34 real
GitHub issues; review it there before running the script, not after.

| Epic | Issues | Blocked by |
|---|---|---|
| Skill — github-labels-setup | 4 | — |
| Skill — github-project-bootstrap | 5 | github-labels-setup |
| Skill — github-repo-init | 4 | — |
| Skill — project-epic-planner | 4 | — |
| Skills repo scaffolding & governance | 6 | — |
| Repo creation & validation | 4 | Skills repo scaffolding & governance |
| *(standalone)* Release validation | — | All six epics |

```
labels-setup ──> project-bootstrap ──────────────┐
repo-init ────────────────────────────────────────┤
epic-planner ──────────────────────────────────────┼──> Release validation
scaffolding ──> repo creation & validation ────────┘
```

Four of the six epics are parallel-safe with each other — labels-setup,
repo-init, epic-planner, and scaffolding can all be worked in any order or
simultaneously. `project-bootstrap` waits on `labels-setup` (it calls into
that skill's script). `repo creation & validation` waits on `scaffolding`
(there's nothing to push before README/CLAUDE.md/LICENSE exist).

## Keeping this in sync

If scope changes, edit `tracker/issues.py` first, then regenerate:

```bash
python scripts/render_issues_md.py > ISSUES.md
```

Same one-way relationship as `pr-agent`: `tracker/issues.py` is the source
of truth; `ISSUES.md`, `PROJECT_PLAN.md`, and this file should all agree
with it, not the other way around.
