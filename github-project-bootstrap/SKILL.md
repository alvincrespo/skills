---
name: github-project-bootstrap
description: Bootstrap a GitHub milestone, a linked Project (v2) board, and every epic/story issue (with sub-issue and blocked-by relationships) on a repo from a structured JSON plan.
disable-model-invocation: true
---

# GitHub Project Bootstrap

Turn a structured JSON plan into a live milestone, a linked Project (v2)
board, and the full set of epic and story issues on a real GitHub repo —
including sub-issue (`--parent`) and blocked-by relationships.

**This skill is user-invoked only.** Its frontmatter sets
`disable-model-invocation: true`, so Claude never fires it from
conversational context, no matter how strongly a request seems to imply
it — a human has to explicitly ask for a project to be bootstrapped, every
time. This skill creates real, only partly reversible GitHub artifacts (a
milestone, a project board, dozens of issues), which is exactly the case
`docs/adr/0002-invocation-control-on-github-actions.md` carves out for
explicit-only invocation.

## Invocation

```bash
python scripts/bootstrap_github_project.py \
  --repo <owner>/<repo> \
  --data <path/to/plan.json> \
  [--project-title <title>] \
  [--labels-file <path/to/labels.json>]
```

- `--repo` (required): the target repo as `owner/name`.
- `--data` (required): path to a JSON file describing the milestone, epics,
  and release-validation issue to create. See "Plan file shape" below.
- `--project-title` (optional): title for the Project (v2) board. Defaults
  to the repo's own name if omitted.
- `--labels-file` (optional): path to a labels JSON file, in the same
  `{name, color, description}` array shape `github-labels-setup` uses.
  Defaults to `github-labels-setup/labels/default.json` if omitted.

## What it does

1. Creates (or updates) the label taxonomy on the target repo by shelling
   out to `github-labels-setup/scripts/ensure_labels.py` — this skill does
   not duplicate label-creation logic itself. See
   `github-labels-setup/SKILL.md` and
   `docs/adr/0001-four-skills-not-one.md` for why that's a call into the
   sibling skill's script rather than its own implementation.
2. Creates the milestone named in the plan file, or reuses it if a
   milestone with that title already exists on the repo.
3. Creates (or reuses) a GitHub Project (v2) named `--project-title` (or
   the repo name, by default), and links it to the target repo so it shows
   up under the repo's own Projects tab — Projects (v2) are account-level,
   not repo-level, so creating one doesn't automatically associate it with
   any particular repo.
4. For each epic in the plan, in file order: creates the epic as an issue
   labeled `epic`, links it as blocked-by whatever its dependencies name,
   then creates each of its child issues linked to it via GitHub's
   sub-issue relationship (`gh issue create --parent`).
5. Creates the standalone release-validation issue named in the plan,
   linked as blocked-by every epic.
6. Adds every issue it creates to the Project board.

## Plan file shape

`--data` points at a JSON file with top-level keys `milestone`, `epics`,
and `release_validation_issue` — the schema is documented in
[`references/epic-schema.md`](references/epic-schema.md). Read that file
rather than relying on a description here; this doc intentionally doesn't
restate the schema so there's exactly one place it can drift from the
script's actual expectations.

## Idempotency

Safe to re-run against the same repo and plan file:

- Labels go through `ensure_labels.py`'s `--force` behavior, so re-applying
  the same taxonomy updates existing labels in place instead of erroring.
- The milestone and the Project board are looked up by title/name before
  creating, so a second run reuses them rather than duplicating.
- Issues are looked up by exact title before creating, so a second run
  mostly no-ops instead of creating duplicates.

That said, treat it as a one-time bootstrap, not a sync tool to run on
every edit to the plan file. If the plan changes after the first run, edit
or close the affected issues by hand rather than relying on a re-run to
reconcile scope changes.

## Scope

This skill only bootstraps GitHub artifacts (labels, milestone, project
board, issues) from an already-written plan file. It doesn't write the
plan itself — that's `project-epic-planner` — and it doesn't create the
repo it runs against — that's `github-repo-init`. See
`docs/adr/0001-four-skills-not-one.md` for why those stay separate skills
rather than folding into this one.
