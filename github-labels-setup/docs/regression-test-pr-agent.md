# Regression test: `ensure_labels.py` against `alvincrespo/pr-agent` (read-only)

**Date:** 2026-08-30
**Issue:** [#5 — "Regression-test against alvincrespo/pr-agent's real labels"](https://github.com/alvincrespo/skills/issues/5)

## Scope of this check

Issue #5's acceptance criteria call for actually running `ensure_labels.py`
with `--force` against the real `alvincrespo/pr-agent` repo. The repo owner
was asked whether to execute that mutating run as part of this automated
pass and **explicitly declined** — they want to run it themselves, by hand,
later.

So this document does **not** claim the live-run AC bullet is satisfied.
Instead it does the closest safe substitute: a **read-only comparison**
between `alvincrespo/pr-agent`'s current real labels and the nine entries
in `labels/default.json` (from the still-open `issue-4-default-labels-config`
branch), to predict whether a live `--force` run would be a true no-op.

The only `gh` call made against `alvincrespo/pr-agent` for this check was
the read-only `gh label list`. No `gh label create` / `gh label edit` / any
write call was made against that repo.

## Source: `labels/default.json` (from `origin/issue-4-default-labels-config`)

Read via `git show origin/issue-4-default-labels-config:github-labels-setup/labels/default.json`:

```json
[
  {"name": "epic", "color": "5319E7", "description": "A tracked body of work with child issues"},
  {"name": "task", "color": "0E8A16", "description": "A single actionable unit of work"},
  {"name": "safety-critical", "color": "B60205", "description": "Touches the merge/push/allowlist safety boundary"},
  {"name": "priority:P0", "color": "D93F0B", "description": "Blocks the v1 release milestone"},
  {"name": "priority:P1", "color": "FBCA04", "description": "Should land before v1, not release-blocking"},
  {"name": "priority:P2", "color": "C5DEF5", "description": "Nice to have / stretch"},
  {"name": "size:S", "color": "C2E0C6", "description": "About one session"},
  {"name": "size:M", "color": "FEF2C0", "description": "About two to three sessions"},
  {"name": "size:L", "color": "F9D0C4", "description": "Open-ended, may need its own breakdown"}
]
```

## Source: `scripts/ensure_labels.py` (from `origin/issue-3-ensure-labels-script`)

Read via `git show origin/issue-3-ensure-labels-script:github-labels-setup/scripts/ensure_labels.py`.
The exact per-label command it shells out to (the mechanism this regression
test is predicting the outcome of) is:

```bash
gh label create <name> --repo <owner>/<repo> --color <color> --description <description> --force
```

invoked from the CLI as:

```bash
python scripts/ensure_labels.py --repo <owner>/<repo> --labels-file labels/default.json
```

Per the script's own docstring, `--force` is what makes it idempotent:
"re-running against a repo that already has some or all of these labels
just updates color/description in place rather than failing on 'label
already exists'." The script has no dry-run mode — it always shells out to
`gh label create --force` for every entry in the labels file, once per run.

## Read-only fetch: `alvincrespo/pr-agent`'s current real labels

Command run (read-only, no mutation):

```bash
gh label list --repo alvincrespo/pr-agent --json name,color,description
```

Full output (19 labels total — 10 are GitHub's stock defaults on that repo,
9 are the custom taxonomy from `labels/default.json`):

```json
[
  {"color":"f143ab","description":"Barrier affecting people with disabilities","name":"accessibility"},
  {"color":"d73a4a","description":"Something isn't working","name":"bug"},
  {"color":"0075ca","description":"Improvements or additions to documentation","name":"documentation"},
  {"color":"cfd3d7","description":"This issue or pull request already exists","name":"duplicate"},
  {"color":"a2eeef","description":"New feature or request","name":"enhancement"},
  {"color":"7057ff","description":"Good for newcomers","name":"good first issue"},
  {"color":"008672","description":"Extra attention is needed","name":"help wanted"},
  {"color":"e4e669","description":"This doesn't seem right","name":"invalid"},
  {"color":"d876e3","description":"Further information is requested","name":"question"},
  {"color":"ffffff","description":"This will not be worked on","name":"wontfix"},
  {"color":"5319E7","description":"A tracked body of work with child issues","name":"epic"},
  {"color":"0E8A16","description":"A single actionable unit of work","name":"task"},
  {"color":"D93F0B","description":"Blocks the v1 release milestone","name":"priority:P0"},
  {"color":"FBCA04","description":"Should land before v1, not release-blocking","name":"priority:P1"},
  {"color":"C5DEF5","description":"Nice to have / stretch","name":"priority:P2"},
  {"color":"B60205","description":"Touches the merge/push/allowlist safety boundary","name":"safety-critical"},
  {"color":"F9D0C4","description":"Open-ended, may need its own breakdown","name":"size:L"},
  {"color":"FEF2C0","description":"About two to three sessions","name":"size:M"},
  {"color":"C2E0C6","description":"About one session","name":"size:S"}
]
```

## Field-by-field comparison (the 9 `labels/default.json` entries only)

| name | `default.json` color | `pr-agent` color | `default.json` description | `pr-agent` description | Match? |
|---|---|---|---|---|---|
| epic | `5319E7` | `5319E7` | A tracked body of work with child issues | A tracked body of work with child issues | Yes |
| task | `0E8A16` | `0E8A16` | A single actionable unit of work | A single actionable unit of work | Yes |
| safety-critical | `B60205` | `B60205` | Touches the merge/push/allowlist safety boundary | Touches the merge/push/allowlist safety boundary | Yes |
| priority:P0 | `D93F0B` | `D93F0B` | Blocks the v1 release milestone | Blocks the v1 release milestone | Yes |
| priority:P1 | `FBCA04` | `FBCA04` | Should land before v1, not release-blocking | Should land before v1, not release-blocking | Yes |
| priority:P2 | `C5DEF5` | `C5DEF5` | Nice to have / stretch | Nice to have / stretch | Yes |
| size:S | `C2E0C6` | `C2E0C6` | About one session | About one session | Yes |
| size:M | `FEF2C0` | `FEF2C0` | About two to three sessions | About two to three sessions | Yes |
| size:L | `F9D0C4` | `F9D0C4` | Open-ended, may need its own breakdown | Open-ended, may need its own breakdown | Yes |

All 9 of 9 labels already exist on `alvincrespo/pr-agent` with an exact
name, color, and description match against `labels/default.json`. No
missing labels, no color drift, no description drift, and no duplicate or
near-duplicate names (e.g. no `Epic` vs `epic` casing collision) were
observed among the 19 labels returned.

## Conclusion

This is **read-only evidence, not a live-run confirmation**. Based on it:

- Because `gh label create --force` on an existing label updates it in
  place rather than creating a duplicate, and because all 9 target labels
  already match `labels/default.json` on every compared field, a live
  `ensure_labels.py --force` run against `alvincrespo/pr-agent` is
  predicted to be a true no-op: it would re-assert the same 9
  name/color/description triples that are already present, create zero new
  labels, and change zero existing labels.
- This prediction is **not** a substitute for actually running the script.
  It does not (and cannot, read-only) verify things like `gh` auth/scope
  correctness for the write path, API error handling, or exact CLI
  behavior under `--force` beyond what the script's own docstring claims.
- The first acceptance-criteria bullet on issue #5 ("Run `ensure_labels.py`
  against the already-existing `alvincrespo/pr-agent` repo") is **not**
  being marked done by this document. That mutating run was intentionally
  skipped per the repo owner's explicit instruction.

## Manual command left for the repo owner

To actually complete the live-run acceptance criterion, run this by hand
once `scripts/ensure_labels.py` and `labels/default.json` have landed on
`main` (currently they exist only on the open `issue-3-ensure-labels-script`
and `issue-4-default-labels-config` branches/PRs respectively):

```bash
python github-labels-setup/scripts/ensure_labels.py --repo alvincrespo/pr-agent --labels-file github-labels-setup/labels/default.json
```

Given the comparison above, the expected output is that all 9 labels are
"ensured" with no visible change on the GitHub side — consistent with, but
not a substitute for, the read-only prediction in this document.
