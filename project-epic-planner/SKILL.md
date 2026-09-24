---
name: project-epic-planner
description: Turn a rough project idea into a structured, reviewable plan of epics and stories with a real dependency graph, saved as a JSON file github-project-bootstrap can consume plus a rendered markdown doc for human review. Use when the user wants to plan or scope a project — "help me plan this", "what would the roadmap look like", "break this down into tickets", "how should I split this work up", "turn this idea into issues", "write the epics and stories for this" — even if they never say "epic" or "story". Produces a document only; nothing is created on GitHub.
---

# Project Epic Planner

Turn a project description into an epic/story breakdown that's ready to
review: every ticket self-contained, every leaf story testable, every
dependency real. The output is a plan file, not GitHub issues — turning an
approved plan into issues is `github-project-bootstrap`'s job, and only
when a human explicitly asks for it.

This skill is model-invoked on purpose (no `disable-model-invocation`):
planning is reversible. It writes a document someone reads and edits;
nothing acts on it automatically. See
`docs/adr/0002-invocation-control-on-github-actions.md`.

## Required reading

Before generating **any** ticket, read
[`references/ticket-quality-rules.md`](references/ticket-quality-rules.md)
in full. Its five rules aren't style preferences — each is a mistake that
was made and corrected on a real project, and a plan that breaks one isn't
ready for review.

## Workflow

### 1. Pin down the project template

Get the project into the shape defined in
[`references/project-template.md`](references/project-template.md):
`project_name`, `one_line_description`, `objective`, `in_scope`,
`out_of_scope`, optional `known_pieces`, `repo.visibility`,
`repo.license`, and `target_milestone_name`.

If the user gave a filled-in template, use it. Otherwise draft one from
what they've said, show it, and get it confirmed before planning — ask
about anything you'd otherwise be guessing, especially scope boundaries.
Apply the template's validation rules; send back a failing template with
the specific problem rather than filling the gap yourself.

### 2. Draft the plan

Following the ticket-quality rules:

- **Epics** from the `objective` and `in_scope` items — every in-scope
  item covered by at least one epic, nothing from `out_of_scope` planned.
  Build on `known_pieces` rather than re-planning them.
- **Stories** under each epic, one per independently testable unit of
  work, each with a body carrying exact commands, schemas, paths, and a
  `### Acceptance criteria` checklist that includes a specific test.
- **Dependencies** on each epic (`depends_on`) only where it's genuinely
  blocked, with the "because" written into the epic's body — and a note
  on notable parallel-safe pairs.
- **One release-validation issue**: the end-to-end check against a real
  run that proves the milestone's objective is met, with the target given
  as a runtime parameter.
- **Milestone**: `title` is the template's `target_milestone_name`;
  `description` states the definition of done, derived from `objective`.

### 3. Write the plan JSON

Save it as `<project_name>-plan.json` in the current directory unless the
user names another path. The shape is exactly `github-project-bootstrap`'s
`--data` format — read
[`epic-schema.md`](../github-project-bootstrap/references/epic-schema.md)
for it rather than working from memory. The constraints that most often
bite:

- Epics are ordered so every `depends_on` entry names an epic **earlier**
  in the array.
- Every title — epic, story, and release validation — is unique across the
  whole plan. Bootstrap matches existing issues by exact title.
- `release_validation_issue` always has a `labels` key (`[]` is fine).
- Labels come only from the taxonomy that will be applied to the repo —
  by default `github-labels-setup/labels/default.json` (`safety-critical`,
  `priority:P0`–`P2`, `size:S`/`M`/`L`). Bootstrap adds `epic` and `task`
  itself; don't repeat them.

### 4. Validate and render

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/render_plan.py \
  --data <project_name>-plan.json \
  --out <project_name>-plan.md \
  [--labels-file <path/to/labels.json>]
```

The script validates the JSON with `github-project-bootstrap`'s own loader
(shape and `depends_on` ordering), then checks for duplicate titles and
unknown labels. Pass `--labels-file` when the repo will use a taxonomy
other than the default. On any failure it exits 1 and writes nothing — fix
the JSON and re-run. On success it writes the markdown: a dependency-graph
table, then every epic and story in full.

### 5. Self-review, then hand over for review

Run the checklist at the end of `ticket-quality-rules.md` against the
rendered plan and fix what fails before showing it. Then point the user at
the markdown file, summarize the epics and the dependency graph in a few
lines, and flag any judgment calls you made.

Iterate on feedback by editing the **JSON** and re-rendering — never edit
the markdown directly. The JSON is the source of truth; the markdown only
exists so it can be reviewed.

### 6. Stop

The skill ends at an approved plan. Tell the user the next steps, but
don't run them: `github-repo-init` (if the repo doesn't exist yet),
then `github-project-bootstrap` with `--data <project_name>-plan.json`.
Both are user-invoked only and create real GitHub artifacts; the user
triggers them explicitly when they're ready.

## Output

| File | What it is |
|---|---|
| `<project_name>-plan.json` | The plan in `github-project-bootstrap`'s `--data` format. Source of truth. |
| `<project_name>-plan.md` | Generated by `render_plan.py` from the JSON, for human review. Never hand-edited. |

## Scope

This skill only produces a plan. It doesn't create a repo
(`github-repo-init`), labels (`github-labels-setup`), or any milestone,
board, or issue (`github-project-bootstrap`). See
`docs/adr/0001-four-skills-not-one.md` for why planning stays separate from
the skills that act on GitHub.
