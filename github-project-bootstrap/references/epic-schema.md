# Epics/stories JSON schema

This is the portable data format that replaces the current
`tracker/issues.py` Python module -- same fields (`MILESTONE`, `EPICS`,
`RELEASE_VALIDATION_ISSUE`), expressed as JSON instead of hardcoded Python
so `scripts/bootstrap_github_project.py` can eventually read it via a
`--data <path.json>` argument instead of importing a specific module. (That
conversion is a separate story in this epic -- this document only defines
the shape, it doesn't change the script.)

A machine-checkable version of everything below lives alongside this file
at [`epic-schema.schema.json`](./epic-schema.schema.json), a JSON Schema
(2020-12 draft) a data file can be validated against directly.

## Top-level shape

```json
{
  "milestone": {"title": "...", "description": "..."},
  "epics": [
    {
      "title": "Epic: ...",
      "labels": [...],
      "depends_on": ["Epic: ..."],
      "body": "...",
      "issues": [{"title": "...", "labels": [...], "body": "..."}]
    }
  ],
  "release_validation_issue": {"title": "...", "labels": [...], "body": "..."}
}
```

Three top-level keys, all required: `milestone`, `epics`, and
`release_validation_issue`.

## Field reference

### `milestone` (object, required)

The single GitHub milestone every created issue is filed under.

| Field | Type | Required | Notes |
|---|---|---|---|
| `milestone.title` | string | yes | Exact milestone title. `ensure_milestone()` looks up an existing milestone by this exact title and reuses it; otherwise creates one. Also passed as `--milestone <title>` on every `gh issue create` call -- `gh` wants the milestone's *title* here, not its numeric ID. |
| `milestone.description` | string | yes | Milestone description body, used only when creating a new milestone. |

### `epics` (array of objects, required)

Ordered list of epics. **Order matters** -- see
[The ordering constraint](#the-ordering-constraint-depends_on-must-only-point-backward)
below. Each entry:

| Field | Type | Required | Notes |
|---|---|---|---|
| `epics[].title` | string | yes | Exact epic issue title, e.g. `"Epic: Skill — github-project-bootstrap"`. Every `EPICS` entry in `tracker/issues.py` today follows an `"Epic: ..."` naming convention, but nothing in the script or this schema enforces that prefix -- it's convention, not a constraint. What *is* load-bearing: this exact string is what other epics' `depends_on` entries reference, so it must match verbatim wherever it's cited. |
| `epics[].labels` | array of strings | no (default `[]`) | Additional labels layered on top of the literal `epic` label the bootstrap script always adds (`["epic"] + epic.get("labels", [])` in `scripts/bootstrap_github_project.py`). Today's data uses this for `priority:*` and `size:*` labels. |
| `epics[].depends_on` | array of strings | no (default `[]`) | Titles of other epics this epic is blocked by. Each entry becomes a `gh issue edit --add-blocked-by` link once every named epic's issue number is known. See the ordering constraint below -- this is the field it applies to. |
| `epics[].body` | string | yes | Issue body markdown for the epic. |
| `epics[].issues` | array of objects | yes (may be empty) | This epic's child story issues, created as GitHub sub-issues of it (`gh issue create --parent <epic-number>`). The key itself is required even if an epic currently has no children. |

Each entry in `epics[].issues`:

| Field | Type | Required | Notes |
|---|---|---|---|
| `epics[].issues[].title` | string | yes | Exact child issue title. |
| `epics[].issues[].labels` | array of strings | no (default `[]`) | Additional labels layered on top of the literal `task` label the bootstrap script always adds (`["task"] + child.get("labels", [])`). |
| `epics[].issues[].body` | string | yes | Issue body markdown for the child issue. |

### `release_validation_issue` (object, required)

The single standalone issue created after all epics, linked as blocked-by
every epic issue. Same three fields as a child issue -- it has no
`depends_on` or `issues` of its own:

| Field | Type | Required | Notes |
|---|---|---|---|
| `release_validation_issue.title` | string | yes | Exact issue title. |
| `release_validation_issue.labels` | array of strings | no (default `[]`) | See the note below -- this field is optional in this schema even though today's script reads it slightly differently than the two `labels` fields above. |
| `release_validation_issue.body` | string | yes | Issue body markdown. |

**Note on `labels` optionality:** `epics[].labels` and
`epics[].issues[].labels` are read in `scripts/bootstrap_github_project.py`
via `epic.get("labels", [])` / `child.get("labels", [])` -- already
optional today, defaulting to no extra labels. `RELEASE_VALIDATION_ISSUE`'s
`labels`, by contrast, is read via direct dict access
(`RELEASE_VALIDATION_ISSUE["labels"]`, no `.get()`), so a real KeyError
would occur today if it were omitted. This schema treats `labels` as
optional at all three levels for consistency, since nothing about the
*shape* of `release_validation_issue` requires it to behave differently
from a child issue. The story that converts the bootstrap script to read
this JSON format (a later story in this epic) should decide whether to
preserve today's strict direct-access behavior for
`release_validation_issue` specifically, or normalize it to default-to-`[]`
like the other two -- either way, this schema doesn't forbid omitting it.

## The ordering constraint: `depends_on` must only point backward

`epics[].depends_on` entries may only name the `title` of an epic that
appears **earlier** in the `epics` array -- never that epic's own title,
and never a later epic's.

This isn't an arbitrary restriction; it's the constraint that makes the
bootstrap script's single-pass, no-topological-sort creation order safe.
`tracker/issues.py`'s own module docstring states the rule this schema is
preserving:

> `depends_on` encodes a REAL dependency graph — `EPICS` is ordered so
> nothing depends on a later epic, which is what makes the bootstrap
> script's single-pass creation order safe.

And `scripts/bootstrap_github_project.py`'s epic loop relies on exactly
that ordering. It walks `for epic in EPICS:` once, in array order, building
up `epic_number_by_title` as it goes:

```python
for epic in EPICS:
    ...
    epic_number = create_issue(...)
    epic_number_by_title[epic["title"]] = epic_number
    ...
    # Epic-to-epic dependencies. EPICS is ordered so every name in
    # "depends_on" refers to an epic already created above — if that
    # ever stops being true, the KeyError below is the signal to fix
    # the ordering in tracker/issues.py rather than the script.
    depends_on = epic.get("depends_on", [])
    if depends_on:
        blocker_numbers = [str(epic_number_by_title[title]) for title in depends_on]
        link_blocked_by(owner, repo, epic_number, blocker_numbers)
```

`epic_number_by_title[title]` only has entries for epics the loop has
*already* processed. If a `depends_on` entry names the current epic itself,
or an epic later in the array, that lookup raises a `KeyError` -- and by
that point the script has already created a partial, half-linked set of
real issues in a live GitHub repo, with no automatic rollback. Requiring
the data file itself to be pre-sorted so every `depends_on` reference
points backward is what lets the script avoid a topological sort entirely:
one forward pass is provably enough, because the data is guaranteed
acyclic and already in a valid creation order before the script ever runs.
A JSON (or hand-written) data file that violates this ordering would
reproduce that exact mid-run failure the moment it's fed to the bootstrap
script.

## What JSON Schema can validate here vs. what it can't

[`epic-schema.schema.json`](./epic-schema.schema.json) validates
**shape**: that `milestone`, `epics`, and `release_validation_issue` are
present and correctly typed; that every required field exists; that
`depends_on` and `labels` are arrays of strings when present.

It **cannot** validate the ordering constraint above. JSON Schema has no
keyword for "this array element's string value must equal the value of
some `title` field on an earlier element of a different array" -- that's a
cross-reference between two different parts of the document, keyed by
value and by array position, which is outside what any JSON Schema draft
(2020-12 included) can express. A document can pass
`epic-schema.schema.json` validation in full and still have an epic whose
`depends_on` names itself or a later epic.

That check has to be written as real code in whatever loads the data file
-- walking `epics` in order, maintaining the set of titles seen so far, and
rejecting any `depends_on` entry not already in that set. This document
only specifies the rule that check needs to enforce; implementing it is a
separate, later story in this epic (the one that converts
`scripts/bootstrap_github_project.py` to read `--data <path.json>`), not
part of this one.
