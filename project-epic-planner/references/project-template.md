# Project template: input schema

The structured description of a project that `project-epic-planner` turns
into an epic/story breakdown. A user fills this in (or Claude drafts it
from conversation and the user confirms it) **before** any ticket is
generated — every field here is something the plan needs to know and
shouldn't have to guess.

This is the *input* side of the skill. The *output* side — the epics and
stories JSON that `github-project-bootstrap` consumes — is defined in
[`github-project-bootstrap/references/epic-schema.md`](../../github-project-bootstrap/references/epic-schema.md).

## Shape

```yaml
project_name: string
one_line_description: string
objective: string
in_scope: [string]
out_of_scope: [string]
known_pieces: [string]   # optional
repo:
  visibility: public | private
  license: string
target_milestone_name: string
```

Every field is required except `known_pieces`.

## Field reference

| Field | Type | Required | What it's for |
|---|---|---|---|
| `project_name` | string | yes | The project's name, and the default repo name (the `repo-name` half of `<owner>/repo-name`) if the repo is created with `github-repo-init`. The owner is deliberately **not** part of the template — it's a runtime parameter supplied when a skill actually runs, never baked into the plan. |
| `one_line_description` | string | yes | One sentence. Becomes the repo description (`setup_repo.sh --description`) and the plan document's subtitle. |
| `objective` | string | yes | What "finished" looks like, in a paragraph. The planner derives the milestone description and the epics from this; if an epic can't be traced back to the objective, it doesn't belong in the plan. |
| `in_scope` | list of strings | yes, non-empty | The concrete deliverables. Every item should end up covered by at least one epic. |
| `out_of_scope` | list of strings | yes, may be empty | Things someone could reasonably assume are included but aren't. The planner must not generate tickets for any of these. An empty list is valid, but writing at least one entry usually surfaces an assumption worth stating. |
| `known_pieces` | list of strings | no | Components, scripts, or decisions that already exist or are already settled — prior code to port, a chosen library, an existing schema. Seeds the breakdown so the plan builds on what's there instead of re-planning it. Not a list of epics: the planner still decides how the work is split. |
| `repo.visibility` | `public` or `private` | yes | Intended visibility of the project's repo. |
| `repo.license` | string | yes | Intended license, as an SPDX identifier (`MIT`, `Apache-2.0`, …) or `none`. |
| `target_milestone_name` | string | yes | Becomes `milestone.title` in the output JSON — the single milestone every generated issue is filed under. |

### Caveat: `repo.*` is recorded, not yet applied

`github-repo-init`'s `setup_repo.sh` currently always creates the repo with
`--public` and doesn't set a license; it takes only `--description` and
`--topics`. Until it grows flags for these, `repo.visibility` and
`repo.license` are part of the plan for the human to act on (and for the
planner to reflect in tickets — e.g. a license-file story), not values any
script reads.

## Validation rules

- All fields except `known_pieces` are present.
- `project_name`, `one_line_description`, `objective`, and
  `target_milestone_name` are non-empty strings.
- `in_scope` has at least one entry; `out_of_scope` and `known_pieces` may
  be empty lists.
- `repo.visibility` is exactly `public` or `private`.
- No item appears in both `in_scope` and `out_of_scope`.

The planner checks these before generating anything. A template that fails
them is sent back to the user with the specific problem, not silently
filled in.

## Worked example: this repo

The template as it would have been filled in for `alvincrespo/skills`
itself — the project that produced this skill. Compare against
[`PROJECT_PLAN.md`](../../PROJECT_PLAN.md) and
[`tracker/issues.py`](../../tracker/issues.py) to see what a plan generated
from it should look like.

```yaml
project_name: skills
one_line_description: >-
  A small, growing collection of Claude Skills for real engineering
  workflows.
objective: >-
  Ship four Claude Skills, packaged as an installable Claude Code plugin,
  that chain together into a pipeline: describe a project, review a
  generated epic/story plan, then create the repo and bootstrap a live,
  fully tracked GitHub Project board from that plan. Done means all four
  skills have complete SKILL.md files, the plugin passes
  `claude plugin validate . --strict`, and the full chain has been run
  end to end against a real, disposable repo.
in_scope:
  - "project-epic-planner: turn a rough project description into a reviewable epic/story breakdown with a dependency graph"
  - "github-repo-init: create a GitHub repo with deliberate settings and baseline scaffolding"
  - "github-labels-setup: create or update a configurable label taxonomy on a repo, standalone and reusable"
  - "github-project-bootstrap: create the milestone, linked Project v2 board, and every issue with sub-issue and dependency links from a structured plan"
  - "Plugin packaging: .claude-plugin/plugin.json and marketplace.json, validated with --strict"
  - "A standalone .skill file for each skill"
  - "An end-to-end chain test against a throwaway repo"
out_of_scope:
  - "Any skill unrelated to the plan -> repo -> issues pipeline"
  - "Non-GitHub issue trackers (Linear, Jira, local files)"
  - "A marketplace experience beyond what marketplace.json provides"
  - "Bucket folders, a router skill, or a public docs site"
  - "package.json-synced versioning"
known_pieces:
  - "pr-agent's bootstrap_github_project.py and setup_repo.sh: the gh mechanics (milestone, Project v2, sub-issues, blocked-by links) are already proven against the live API; the work is generalizing them, not rewriting them"
  - "pr-agent's nine-label taxonomy (epic, task, safety-critical, priority:P0-P2, size:S-L)"
  - "tracker/issues.py as the plan format, to be replaced by a JSON file passed via --data"
  - "gh CLI as the only GitHub interface"
  - "github-repo-init and github-project-bootstrap must be user-invoked only (disable-model-invocation: true)"
repo:
  visibility: public
  license: MIT
target_milestone_name: "v1 — Four Skills Shipped & Shareable"
```
