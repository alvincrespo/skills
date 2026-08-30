# Regression test: `pr-agent`'s tracker converted to the JSON schema (read-only)

**Date:** 2026-08-30
**Issue:** [#11 — "Regression-test: convert pr-agent's tracker data to JSON"](https://github.com/alvincrespo/skills/issues/11)

## Scope of this check

Issue #11's acceptance criteria call for two things: converting
`alvincrespo/pr-agent`'s `tracker/issues.py` into the new
`github-project-bootstrap` JSON schema, and then running the converted
`bootstrap_github_project.py --data <path.json>` against a **disposable
test repo** to confirm it produces the same 51 issues, dependency graph,
and blocked-by links as the original run.

This document does the first half plus a read-only, programmatic
structural-parity check as the closest safe substitute for the second
half. It does **not** run `bootstrap_github_project.py` against any repo,
disposable or otherwise, and it does not create a disposable test repo.

That's an intentional, precedent-following choice, not an oversight. There
is standing user feedback (recorded in this user's cross-session Claude
memory as "Manual live gh writes") that when a task calls for a
*mutating* `gh` CLI call against a repo other than the one currently being
worked in, the repo owner wants to run that command themselves, by hand —
not have Claude execute it. That was confirmed twice already on the exact
sibling case: issue #5 in the `github-labels-setup` epic asked for a live
run against `alvincrespo/pr-agent`, and the merged PR #38
(`github-labels-setup/docs/regression-test-pr-agent.md`) deliberately did
**not** perform that run — it substituted a read-only comparison and left
the mutating command for the owner to run by hand. This document is that
same substitution, one level up in blast radius: instead of one
`gh label create --force` call per label, the live run this issue asks
for would mean `gh repo create`, `gh issue create` (51 times), `gh project
create`, and `gh issue edit --add-blocked-by` calls — a strictly larger
set of irreversible mutations against a repo outside `alvincrespo/skills`.
Even against a repo created specifically to be disposable, creating that
repo in the first place is itself a mutating `gh repo create` call this
constraint covers, so it is left to the owner too.

The only `gh` call made against `alvincrespo/pr-agent` for this check was
the read-only fetch of `tracker/issues.py`'s content. No `gh repo create`,
`gh issue create`, `gh project create`, `gh label create`, `gh api
--method POST`, or any other write call was made against
`alvincrespo/pr-agent` or against any other repo.

## Source: `alvincrespo/pr-agent`'s `tracker/issues.py`

Fetched read-only via:

```bash
gh api repos/alvincrespo/pr-agent/contents/tracker/issues.py --jq .content | base64 -d > /tmp/pr-agent-issues.py
```

The file is a plain Python module (no imports beyond the standard
library, no side effects on import) defining three top-level names:

- `MILESTONE` — a dict with `title` and `description`.
- `EPICS` — a list of 8 epic dicts, each with `title`, `labels`,
  `depends_on` (a list of earlier epic titles), `body`, and `issues` (a
  list of child-issue dicts, each with `title`, `labels`, `body`).
- `RELEASE_VALIDATION_ISSUE` — a single dict with `title`, `labels`,
  `body`, tied to the milestone rather than any one epic.

The 8 epics, in file order, with their `depends_on` graph and child-issue
counts:

| Epic | # child issues | `depends_on` |
|---|---|---|
| Epic: Repository & Environment Setup | 5 | (none) |
| Epic: Core Agent Loop | 5 | Epic: Repository & Environment Setup |
| Epic: Agent Tools | 10 | Epic: Repository & Environment Setup |
| Epic: Configuration & Safety Guardrails | 6 | Epic: Core Agent Loop, Epic: Agent Tools |
| Epic: Testing & Validation | 5 | Epic: Configuration & Safety Guardrails |
| Epic: Observability & Logging | 4 | Epic: Core Agent Loop |
| Epic: CLI & Orchestration UX | 4 | Epic: Core Agent Loop |
| Epic: Documentation | 3 | Epic: Repository & Environment Setup |

`5 + 5 + 10 + 6 + 5 + 4 + 4 + 3 = 42` child issues. Each of the 8 epics
also becomes its own GitHub issue, and `RELEASE_VALIDATION_ISSUE` is one
more standalone issue tied to the milestone. `8 epics + 42 child issues +
1 release-validation issue = 51` — matching this issue's acceptance
criterion of 51 total issues.

## Conversion: `EPICS` / `MILESTONE` / `RELEASE_VALIDATION_ISSUE` → JSON

The conversion is a direct structural transcription — the Python dicts
already use the same field names the target schema expects
(`title` / `labels` / `depends_on` / `body` / `issues` on each epic;
`title` / `labels` / `body` on each child issue and on
`RELEASE_VALIDATION_ISSUE`; `title` / `description` on `MILESTONE`), so no
renaming or reshaping of individual fields was needed — only wrapping the
three top-level Python names into the single JSON object the schema
specifies:

```json
{
  "milestone": {"title": "...", "description": "..."},
  "epics": [
    {
      "title": "Epic: ...", "labels": [...], "depends_on": ["Epic: ..."], "body": "...",
      "issues": [{"title": "...", "labels": [...], "body": "..."}]
    }
  ],
  "release_validation_issue": {"title": "...", "labels": [...], "body": "..."}
}
```

The conversion was done by a small one-off script
(`importlib`-loading the fetched `pr-agent-issues.py` module directly,
rather than hand-copying/retyping any text) that built this JSON structure
field-for-field from `MILESTONE`, `EPICS`, and `RELEASE_VALIDATION_ISSUE`,
and wrote it to `github-project-bootstrap/docs/pr-agent-tracker.json`.
Loading the original module directly (instead of re-typing its content)
removes transcription error as a source of mismatch by construction — the
only place a mismatch could still enter is the conversion script's own
field-mapping logic, which the comparison below checks independently.

## Structural comparison and evidence

The same one-off script re-loaded the written JSON file with `json.load`
and diffed it against the in-memory `MILESTONE` / `EPICS` /
`RELEASE_VALIDATION_ISSUE` Python objects, field by field: milestone title
and description; epic count, order, and titles; per-epic labels, body,
and `depends_on` graph (including that every `depends_on` entry names an
earlier-defined epic title, per the schema's own stated constraint); per-
epic issue count; and, per issue, title, labels, and body. Actual output:

```
Wrote /Users/alvincrespo/workspace/skills/github-project-bootstrap/docs/pr-agent-tracker.json

=== Structural comparison ===
Epic count:                 orig=8  json=8
Epic titles/order match:    True
Total child-issue count:    orig=42  json=42
Grand total (epics + child issues + release-validation issue):
                             orig=51  json=51

Per-epic breakdown (title | #issues | depends_on):
  - Epic: Repository & Environment Setup | 5 issues | depends_on=[]
  - Epic: Core Agent Loop | 5 issues | depends_on=['Epic: Repository & Environment Setup']
  - Epic: Agent Tools | 10 issues | depends_on=['Epic: Repository & Environment Setup']
  - Epic: Configuration & Safety Guardrails | 6 issues | depends_on=['Epic: Core Agent Loop', 'Epic: Agent Tools']
  - Epic: Testing & Validation | 5 issues | depends_on=['Epic: Configuration & Safety Guardrails']
  - Epic: Observability & Logging | 4 issues | depends_on=['Epic: Core Agent Loop']
  - Epic: CLI & Orchestration UX | 4 issues | depends_on=['Epic: Core Agent Loop']
  - Epic: Documentation | 3 issues | depends_on=['Epic: Repository & Environment Setup']

=== RESULT: PASS — zero mismatches across all compared fields ===
```

Zero mismatches were found across: milestone title/description; epic
count (8 = 8), order, and titles; every epic's labels, body, and
`depends_on` list (including referential integrity — every `depends_on`
entry names an epic defined earlier in the list, matching the schema's
"earlier-defined epic titles only" rule); every epic's child-issue count
(42 total, matching per-epic in the table above); every child issue's
title, labels, and body; and the release-validation issue's title,
labels, and body. The grand total — 8 epics + 42 child issues + 1
release-validation issue — is 51 on both sides, matching the acceptance
criterion.

The converted JSON file (`github-project-bootstrap/docs/pr-agent-tracker.json`)
is valid JSON (`python3 -m json.tool` parses it without error) and its
top-level shape matches the target schema: `milestone` (keys `title`,
`description`), `epics` (a list of 8, each with keys `title`, `labels`,
`depends_on`, `body`, `issues`), and `release_validation_issue` (keys
`title`, `labels`, `body`).

## Conclusion

- The converted `github-project-bootstrap/docs/pr-agent-tracker.json` is a
  **faithful, structurally-verified reproduction** of
  `alvincrespo/pr-agent`'s `tracker/issues.py`: same 8 epics in the same
  order with the same titles, the same 42 child issues distributed across
  them identically, the same `depends_on` dependency graph, and the same
  labels/bodies throughout. Total issue count is 51, matching this
  issue's acceptance criterion.
- This is a **structural-parity prediction**, not a live-run confirmation.
  It proves the JSON *data* matches the Python *data* it was converted
  from. It does **not** exercise `bootstrap_github_project.py` itself —
  it says nothing about whether the script's `gh issue create --parent`,
  `gh issue edit --add-blocked-by`, or GitHub Project v2 board-creation
  calls behave correctly, handle GitHub API errors, rate limits, or
  partial-failure/resume correctly, or actually produce 51 real GitHub
  issues with the right sub-issue and blocked-by links when pointed at a
  real repo.
- The one caveat worth naming explicitly: this comparison verifies the
  JSON *data* is faithful to the Python *data*. It cannot verify that the
  original Python data itself was ever exercised end-to-end against
  `alvincrespo/pr-agent` in exactly this shape (e.g., whether the real
  board currently reflects all 51 issues) — that would require reading
  the live board, which this document does not do, staying strictly
  read-only and in scope for issue #11.
- Issue #11's second acceptance-criteria bullet — "Run the converted
  script against a disposable test repo... and confirm it produces the
  same 51 issues, the same dependency graph, and the same blocked-by
  links" — is **not** being marked done by this document. That mutating
  run (including creating the disposable repo itself) was intentionally
  left for the repo owner to run by hand, per the standing feedback cited
  above.

## Manual command left for the repo owner

`scripts/bootstrap_github_project.py` (issues #8/#9) is not yet on `main`
as of this PR. Once it lands, create a fresh **disposable** repo by hand
first — not `alvincrespo/pr-agent` itself, to avoid duplicate-run
interference with the already-populated real board — and then run:

```bash
python scripts/bootstrap_github_project.py --repo <owner>/<disposable-repo-name> --data github-project-bootstrap/docs/pr-agent-tracker.json
```

Given the structural-parity evidence above, the expected outcome is 51
issues created (8 epics + 42 child issues + 1 release-validation issue),
with sub-issue links matching each epic's `issues` list and
`--add-blocked-by` links matching the `depends_on` graph in the table
above. Running this command against a real disposable repo — and
confirming that expected outcome actually holds — is what would satisfy
issue #11's second acceptance-criteria bullet. This PR only gets you the
converted data plus the structural-parity prediction; it does not itself
satisfy that bullet, mirroring the relationship PR #38 had to issue #5.
