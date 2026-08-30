---
name: github-labels-setup
description: Create or update a GitHub repo's label taxonomy (name, color, description) from a configurable JSON file, applying each label idempotently so the same command is safe to re-run against a repo that already has some or all of the labels. Use when the user says "set up labels", "standardize labels across repos", "as part of setting up issue tracking", or otherwise asks to create, sync, or apply a label taxonomy on a GitHub repo.
---

# GitHub Labels Setup

Create or update a repo's label taxonomy from a JSON config, one label at a
time, via `gh label create --force`. Standalone and reusable — "set up my
standard labels on this repo" is a complete request on its own, with no
milestone, project board, or issue creation involved (see
`docs/adr/0001-four-skills-not-one.md`).

## Invocation

```bash
python scripts/ensure_labels.py --repo <owner>/<repo> --labels-file <path-to-labels.json>
```

`scripts/ensure_labels.py` reads the labels file and, for each entry, runs:

```bash
gh label create <name> --repo <owner>/<repo> --color <color> --description <description> --force
```

`--force` makes this idempotent: a label that already exists with that name
gets its color and description updated in place instead of erroring, so the
exact same command can be re-run any time the taxonomy changes without
producing duplicates or drift.

## Labels config JSON shape

`--labels-file` points at a JSON file containing an array of objects, each
with exactly three string fields:

```json
[
  {
    "name": "priority:P0",
    "color": "B60205",
    "description": "Drop everything"
  }
]
```

- `name` — the label's exact name as it will appear on the repo.
- `color` — a hex color **without** a leading `#` (e.g. `B60205`, not
  `#B60205` — `gh label create --color` rejects the leading `#`).
- `description` — the label's description text.

No other fields are read. Every entry needs all three; a config file
missing `name`, `color`, or `description` on any entry is invalid input.

## Default taxonomy as a starting point

`labels/default.json` ships a nine-label taxonomy already proven in
production use: `epic`, `task`, `safety-critical`, `priority:P0`,
`priority:P1`, `priority:P2`, `size:S`, `size:M`, `size:L`.

Treat it as a copyable starting point, not a fixed or required list. Point
`--labels-file` at `labels/default.json` directly to reproduce that
taxonomy on a new repo, or copy the file and edit the array — add, remove,
rename, or recolor any entry — to match a repo's own conventions before
running the script. Nothing about `ensure_labels.py` depends on these nine
specific names; any correctly-shaped JSON array of `{name, color,
description}` objects works.

## Scope

This skill only applies a label taxonomy to a repo.
`github-project-bootstrap` calls into this skill's script as its own first
step rather than duplicating label-creation logic (see
`docs/adr/0001-four-skills-not-one.md`), but that's a detail of how that
other skill is built — this one's responsibility ends at the labels
existing on the target repo with the right name, color, and description.
