# Project Plan: alvincrespo/skills

**A small, growing collection of Claude Skills for real engineering
workflows, starting with a pipeline for turning a project idea into a
fully-tracked, live GitHub Project board.**

This document is the narrative version of the plan, in the same format as
`pr-agent/PROJECT_PLAN.md`. The full reasoning behind every decision here —
why four skills instead of one, why labels are configurable, why
`mattpocock/skills`'s structure was right-sized down rather than copied
wholesale — lives in `SKILLS_PLAN.md` from the conversation that produced
this repo. For the actual, self-contained tickets, see
[`ISSUES.md`](./ISSUES.md), generated from
[`tracker/issues.py`](./tracker/issues.py).

---

## 1. Objective

Ship four Claude Skills, packaged as an installable Claude Code plugin:

1. `project-epic-planner` — turns a rough project description into a
   structured, reviewable epic/story breakdown with a dependency graph
2. `github-repo-init` — creates a new GitHub repo with deliberate settings
   and baseline scaffolding
3. `github-labels-setup` — creates or updates a configurable label
   taxonomy on a repo, standalone and reusable
4. `github-project-bootstrap` — creates the milestone, linked Project v2
   board, and every issue (with sub-issue and dependency links) from a
   structured plan

Chained together: describe a project → review the generated plan → trigger
repo-init and bootstrap → a real, fully-tracked GitHub Project exists.

## 2. Definition of done

- [ ] All four skills exist with complete `SKILL.md` files
- [ ] `claude plugin validate . --strict` passes against
      `.claude-plugin/plugin.json` and `marketplace.json`
- [ ] The full chain (repo-init → plan → review → labels + bootstrap) has
      been run end-to-end against a real, disposable repo — not just each
      skill tested in isolation
- [ ] Each skill also packaged as a standalone `.skill` file, for anyone
      who wants one skill rather than the whole plugin
- [ ] `github-repo-init` and `github-project-bootstrap` are
      user-invoked-only (`disable-model-invocation: true`); Claude never
      fires either from inferred context alone

## 3. Scope

**In scope (v1):**
- Exactly these four skills, no more
- GitHub only, via `gh` CLI (matches everything already proven in
  `pr-agent`'s bootstrap tooling)
- A flat repo layout — no bucket folders, no router skill, no public docs
  site (see §7 for why each is deferred, not rejected)

**Explicitly out of scope (v1):**
- Any skill unrelated to this specific plan → repo → issues pipeline
- Non-GitHub issue trackers (Linear, Jira, local files)
- A general-purpose "skills marketplace" experience beyond what
  `.claude-plugin/marketplace.json` gives for free

## 4. The four skills, in one line each

| Skill | Does | Invocation |
|---|---|---|
| `project-epic-planner` | Plan the epics/stories | Model-invoked |
| `github-repo-init` | Create the repo | **User-invoked only** |
| `github-labels-setup` | Set up labels | Model-invoked |
| `github-project-bootstrap` | Milestone + board + issues | **User-invoked only** |

Full reasoning for the split and the invocation-control choices:
`docs/adr/0001-four-skills-not-one.md` and
`docs/adr/0002-invocation-control-on-github-actions.md`.

## 5. What has to change from the pr-agent scripts

The underlying `gh` mechanics are already proven — four real bugs, all
found and fixed against a live API while bootstrapping `pr-agent` itself.
What's left is generalization, not new logic:

1. **Data format**: `bootstrap_github_project.py`'s
   `from tracker.issues import ...` becomes a `--data <path.json>`
   argument. A JSON Schema formalizes the contract between
   `project-epic-planner`'s output and this skill's input.
2. **Label extraction**: the nine hardcoded label tuples move into
   `github-labels-setup`'s own script, reading a configurable JSON list
   instead. `github-project-bootstrap` calls into it rather than
   duplicating the logic.
3. **Repo-init generalization**: `setup_repo.sh`'s `pr-agent`-specific
   description and topics become parameters; its chained call to the
   bootstrap script is removed now that these are separately-triggered
   skills.

## 6. Repo layout (v1)

```
alvincrespo/skills/
├── README.md
├── CLAUDE.md
├── LICENSE
├── .claude-plugin/
│   ├── plugin.json
│   └── marketplace.json
├── scripts/
│   └── link-skills.sh
├── docs/
│   └── adr/
│       ├── 0001-four-skills-not-one.md
│       └── 0002-invocation-control-on-github-actions.md
├── project-epic-planner/
│   ├── SKILL.md
│   └── references/
│       ├── ticket-quality-rules.md
│       └── project-template.md
├── github-labels-setup/
│   ├── SKILL.md
│   ├── labels/default.json
│   └── scripts/ensure_labels.py
├── github-repo-init/
│   ├── SKILL.md
│   └── scripts/setup_repo.sh
└── github-project-bootstrap/
    ├── SKILL.md
    ├── references/epic-schema.md
    └── scripts/bootstrap_github_project.py
```

## 7. Deliberately deferred (not rejected)

Each of these is a real part of `mattpocock/skills`'s actual structure —
fetched and read directly, not guessed at — deferred here because a
4-skill repo doesn't have the problem each one solves yet:

- **Bucket folders** (`engineering/`, `misc/`, etc.) — introduce once a
  genuinely different domain of skill shows up, not preemptively
- **Promoted/non-promoted distinction** — meaningless with no backlog of
  drafts to hide
- **A router skill** (his `ask-matt`) — worth it once picking the right
  skill among many gets genuinely ambiguous; not at four
- **A public docs site** — specific to an existing personal blog/brand
- **`package.json`-synced plugin versioning** — these skills are
  Python-scripted; `plugin.json`'s own `version` field is the sole source
  of truth, no second file to keep in sync

## 8. Rough sequencing

1. `github-labels-setup` (smallest, and a dependency of bootstrap)
2. `github-project-bootstrap` (proven logic, mechanical JSON conversion)
3. `github-repo-init` (mechanical parameterization)
4. `project-epic-planner` (the subjective one — expect more iteration)
5. Repo scaffolding (README, CLAUDE.md, LICENSE, ADRs, link-skills.sh)
6. Create and push the repo
7. Plugin manifests + `claude plugin validate . --strict`
8. Full chain test on a throwaway repo
9. Package and share

## 9. Risks

| Risk | Mitigation |
|---|---|
| Plugin manifest schema assumed rather than verified | Explicit AC on the manifest-creation ticket: confirm against current Claude Code docs first — this repo already paid for guessing wrong four times on `gh` CLI behavior |
| `project-epic-planner` reproduces the *first-draft* ticket quality this whole project started at, not the corrected quality it ended at | The five standing rules are written into a required reference doc, not left implicit; tested against an unrelated project before trusting it |
| Invocation-control flags forgotten on a future fifth skill | Stated as a standing CLAUDE.md rule, not a one-time decision — applies to anything added later with real side effects |
