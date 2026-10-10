---
name: axc-cut-release-preflight
description: Run safety checks before tagging a release, driven by the repo's `.claude/release.json`. Validates that the repo, the version source file(s), and the release workflow are in a state where pushing a `vX.Y.Z` tag will publish successfully — then runs the configured lint/build/test/integrity commands. Read-only — never modifies files or git state. Use when the user says "/axc-cut-release-preflight", or invoked by `axc-cut-release-tag` before a tag push.
---

# Release Preflight

Run before tagging a release. Catches the issues that actually break releases — version source
desync, stale `main`, retag collisions, mismatched repo metadata, a release workflow missing a
required permission or step, a failing build.

## Adapter config (`.claude/release.json`)

Read `.claude/release.json` first (Read tool). If missing, auto-detect (`package.json` → npm,
`go.mod` → go) and offer to write one — see `axc-cut-release` for defaults. Fields used here: `repo`,
`mainBranch`, `version.files[]` (`path` + `match`), `checks.{lint,build,test,integrity}`,
`release.{workflow,workflowChecks[]}`. `{V}` / `version` = the version without the `v` prefix.

## Argument

Optional version arg (e.g. `0.2.1`). If omitted, take it from `release_tool.py current` (the version
in `version.files[0]`) and confirm with the user that's the release they're planning.

## The helper script

Checks 1 (tag), 2 (version files) and 3 (workflow) below call `release_tool.py`, which lives in the
router skill next to this one. All the subcommands used here are read-only:

```bash
python3 "${CLAUDE_SKILL_DIR}/../axc-cut-release/scripts/release_tool.py" <subcommand> [args]
```

Run it from the repo being released. Exit `0` = pass, `1` = a check failed, `2` = bad input or config
(message on stderr). Report exit `2` as a hard block with the message, not as a crash.

## Checks (run all, report each, don't stop on failure)

Group results into four sections. For each check, print a single line `✓` or `✗` plus a one-line
explanation. End with an overall verdict.

### 1. Git state

- **Working tree clean** — `git status --porcelain` returns empty.
- **On `mainBranch`** — `git rev-parse --abbrev-ref HEAD` == `mainBranch`.
- **Up to date with origin** — `git fetch origin <mainBranch>` then compare `git rev-parse <mainBranch>`
  to `git rev-parse origin/<mainBranch>`.
- **Tag for this version does not exist** — `release_tool.py tag-status <V>` prints `absent`, `local`,
  `remote` or `both` (tag name from `release.tagFormat`). Anything but `absent` is a hard block, and
  the report should cite the tag and where it exists — retagging is a separate destructive op the user
  must explicitly authorize.

### 2. Version source

- **Every `version.files[]` equals the version, and they agree with each other** —
  `release_tool.py check-versions <V>` prints `✓ <path> = <found>` or `✗ <path> = <found> (expected V)`
  per file, plus a `files disagree` line if they differ from one another. Exit `1` is a hard block: the
  bump didn't land, the wrong version was passed, or the files are desynced (the build/test will fail in
  CI). Use its lines as this section's ✓/✗ entries.
- **`repo` matches the GitHub remote** — read `git config --get remote.origin.url` (normalize
  SSH↔HTTPS) and compare to `repo`. Mismatch is a warning (fork/rename).

### 3. Release workflow (`release.workflow`)

`release_tool.py workflow-checks` verifies **each** string in `release.workflowChecks[]` against the
`release.workflow` file — the per-tech assertions the repo declared (OIDC/provenance for npm,
`contents: write` + `action-gh-release` for GitHub Releases, etc.) — and prints one
`✓ <string>` or `✗ <string> (not found in <path>)` per entry; use those as this section's lines. Exit `1`
(any ✗) or `2` (workflow file missing) is a hard block; say which string is missing and what the
workflow should contain so the user can act without re-investigating.

### 4. Local build

Only run if checks 1–3 had no hard failures (no point testing a broken state). Run each configured
command; skip (don't fail) any that's empty/absent:

- **`checks.lint`** clean — treat a missing optional tool (e.g. `golangci-lint` not installed) as 🟡,
  not ❌.
- **`checks.build`** clean.
- **`checks.test`** — all tests pass (this is what catches a `version.files[]` desync).
- **`checks.integrity`** — e.g. `npm pack --dry-run` (tarball has the right version/files) or
  `go mod verify` (and `go mod tidy` produces no diff).

## Verdict

End with one of:

- ✅ **Ready to release.** — all checks passed. Suggest the next commands:
  ```
  git tag <tagFormat>
  git push origin <tagFormat>
  ```
- 🟡 **Mostly ready, but…** — non-blocking issues (missing optional tool, repo-metadata mismatch).
  Show what's odd and let the user decide.
- ❌ **Blocked.** — one or more hard failures. List them and don't suggest tagging.

## What this skill does NOT do

- **Does not modify anything.** Read-only by design — no git operations beyond `fetch`, no edits, no
  commits, no tag creation, no pushes. The user runs `git tag` / `git push` after the green light.
- **Does not check the remote registry/releases.** Verifying the publisher config or existing releases
  would need API calls; assume that one-time setup is in place.
- **Does not auto-fix problems.** If a check fails, explain what's wrong and the fix — but don't apply
  it. The user opens a PR with the fix.

## Implementation hints

- Run independent checks in parallel where possible (multiple Bash calls in one message).
- For SSH↔HTTPS normalization: strip `git@github.com:` prefix and `.git` suffix, prepend
  `https://github.com/`, then compare to `repo`.
